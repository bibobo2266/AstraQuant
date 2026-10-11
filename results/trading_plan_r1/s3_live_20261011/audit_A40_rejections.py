"""Read-only audit of fixed checkpoint decisions against fixed S1/RAW."""
from pathlib import Path
import collections
import gzip
import hashlib
import json
import pandas as pd

root = Path('AstraQuant-checkout/results/trading_plan_r1/s3_live_20261011/A')
cell = root / 'A1'
cp = json.loads((cell / 'checkpoint.json').read_text())
# Take only the preserved restored generation, before the live worker advances.
frozen = Path('A40_audit_checkpoint.json')
if frozen.exists():
    cp = json.loads(frozen.read_text())
else:
    assert len(cp['completed']) == 40
    frozen.write_text(json.dumps(cp))
eligibility = []
for chunk in cp['checkpoint_storage']['chunks']:
    if chunk['table'] == 'eligibility':
        data = gzip.decompress((cell / chunk['path']).read_bytes())
        assert hashlib.sha256(data).hexdigest() == chunk['sha256']
        eligibility.extend(json.loads(data))
lookup = {(r['date'], r['stock']): r for r in eligibility}
assert len(lookup) == len(eligibility)
m = json.loads((root / 'manifest.json').read_text())
panel_path = Path(next(f['path'] for f in m['files'] if f['role'] == 'panel'))
panel = pd.read_parquet(panel_path, columns=['date', 'stock', 'eligibility', 'available_date', 'rs']).reset_index()
native_dtype = str(panel.eligibility.dtype)
native_types = dict(collections.Counter(type(x).__name__ for x in panel.eligibility))
assert set(native_types) <= {'bool', 'bool_', 'NoneType', 'float'}, native_types
panel['date_key'] = pd.to_datetime(panel.date).dt.strftime('%Y-%m-%d')
panel['stock_key'] = panel.stock.astype(str)
assert not panel.duplicated(['date_key', 'stock_key']).any()
p40 = panel[panel.date_key.isin(cp['completed'])]
pkeys = {(r.date_key, r.stock_key): r for r in p40.itertuples(index=False)}
raw = pd.read_parquet(Path(next(f['path'] for f in m['files'] if f['role'] == 'raw' and '2016' in f['path'])), columns=['date', 'stock_id', 'open', 'close'])
raw['date_key'] = pd.to_datetime(raw.date).dt.strftime('%Y-%m-%d')
raw['stock_key'] = raw.stock_id.astype(str)
r40 = raw[raw.date_key.isin(cp['completed'])]
rkeys = {(r.date_key, r.stock_key): r for r in r40.itertuples(index=False)}
assert len(rkeys) == len(r40)
date_flag_mismatches = []
for key, er in lookup.items():
    p = pkeys.get(key)
    expected = False if p is None or pd.isna(p.eligibility) else bool(p.eligibility)
    available = key[0] if p is None or pd.isna(p.available_date) else pd.Timestamp(p.available_date).strftime('%Y-%m-%d')
    if expected != er['condition_passes']['source_eligible'] or available != er['available_date'] or (available <= key[0]) != er['condition_passes']['available']:
        date_flag_mismatches.append(key)
rejected = [r for r in cp['tables']['decisions'] if r['reject_reason'] == 'not_eligible_or_not_available']
assert len(rejected) == 1942
rows = []
for decision in rejected:
    key = (decision['date'], decision['stock'])
    p = pkeys.get(key)
    er = lookup[key]
    rows.append(dict(date=key[0], stock=key[1], s1_key_exists=p is not None,
        s1_eligible=False if p is None or pd.isna(p.eligibility) else bool(p.eligibility),
        raw_key_exists=key in rkeys, available=er['condition_passes']['available'],
        source_eligible=er['condition_passes']['source_eligible'], valid=er['condition_passes']['valid'],
        data_status=er['data_status'], available_date=er['available_date']))
counts = dict(total=len(rows), s1_false_with_key=sum(r['s1_key_exists'] and not r['s1_eligible'] for r in rows),
    s1_key_missing=sum(not r['s1_key_exists'] for r in rows), raw_quote_missing=sum(not r['raw_key_exists'] for r in rows),
    available_after_signal_day=sum(not r['available'] for r in rows), invalid_bar=sum(not r['valid'] for r in rows),
    s1_true=sum(r['s1_eligible'] for r in rows), other_availability=sum(r['s1_eligible'] and r['raw_key_exists'] and r['available'] and r['valid'] for r in rows))
assert not date_flag_mismatches, date_flag_mismatches[:5]
def sample(key):
    er = lookup[key]
    p = pkeys.get(key)
    rawrow = rkeys.get(key)
    return dict(date=key[0], stock=key[1], panel_key_exists=p is not None,
        panel_eligibility=None if p is None else bool(p.eligibility),
        panel_available_date=None if p is None or pd.isna(p.available_date) else pd.Timestamp(p.available_date).strftime('%Y-%m-%d'),
        raw_key_exists=rawrow is not None, raw_close=None if rawrow is None else float(rawrow.close),
        ledger_condition_passes=er['condition_passes'], ledger_eligible=er['eligible'],
        trigger=er['condition_values']['trigger'], available_date=er['available_date'])
positive = next((k for k, r in lookup.items() if r['condition_passes']['source_eligible'] and r['condition_passes']['available'] and r['condition_passes']['valid']), None)
result = dict(pinned_checkpoint_commit='0397af3925429c37ae0ac5d90779c108176b2277', completed=40,
    checkpoint_sha256=hashlib.sha256((cell/'checkpoint.json').read_bytes()).hexdigest(),
    panel_sha256=hashlib.sha256(panel_path.read_bytes()).hexdigest(), panel_native_dtype=native_dtype,
    panel_native_value_types=native_types, panel_total_true=int(panel.eligibility.fillna(False).astype(bool).sum()),
    panel_A40_true=int(p40.eligibility.fillna(False).astype(bool).sum()), eligibility_rows_checked=len(eligibility),
    all_date_and_flag_join_mismatches=len(date_flag_mismatches), rejection_counts=counts,
    rejected_sample=sample((rows[0]['date'], rows[0]['stock'])),
    available_sample=sample(positive) if positive else sample(next(iter(lookup))),
    available_sample_has_true_s1=positive is not None,
    price_geometry_rejections=sum(r['reject_reason']=='invalid_geometry' for r in cp['tables']['decisions']),
    warning='If no S1 true rows exist in A40, the available sample proves quote/date availability only, not an eligible buy.',
    trades_replayed=False)
out = root.parent / 'A40_rejection_audit.json'
out.write_text(json.dumps(result, indent=2)+'\n')
pd.DataFrame(rows).to_csv(root.parent/'A40_rejection_classification.csv', index=False)
print(json.dumps(result, ensure_ascii=False), flush=True)
