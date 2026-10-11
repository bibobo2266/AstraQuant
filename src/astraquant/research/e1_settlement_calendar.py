"""Owner-approved terminal settlement dates; never extends the trading calendar."""
import hashlib
import json
from pathlib import Path

PROOF_SHA = '54a15d9fe4b6cfc9013e6ab2ec7718863a261cc48d27c619a4b46f71100b7186'
PROOF_DIR = Path(__file__).resolve().parents[3]/'results/trading_plan_r1/s3_live_20261011/e1_settlement_tail'


def verified_tail():
    raw=(PROOF_DIR/'calendar.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PROOF_SHA:
        raise ValueError('changed approved terminal settlement calendar')
    proof=json.loads(raw)
    for source in proof['sources']:
        data=(PROOF_DIR/source['file']).read_bytes()
        if len(data)!=source['bytes'] or hashlib.sha256(data).hexdigest()!=source['sha256']:
            raise ValueError('changed official settlement calendar evidence')
    twse=json.loads((PROOF_DIR/'twse_2022.json').read_bytes())
    tpex=(PROOF_DIR/'tpex_111.html').read_text()
    if (twse['date']!='20220101' or ['2022-01-03','國曆新年開始交易日','國曆新年開始交易。'] not in twse['data']
            or any(row[0]=='2022-01-04' for row in twse['data'])
            or '中華民國111年' not in tpex or '110年12月31日' not in tpex
            or '補假1日' not in tpex or '1月3日' not in tpex):
        raise ValueError('official terminal settlement schedule mismatch')
    return proof


def terminal_due(sessions, day, period):
    proof=verified_tail()
    if (period!=proof['period'] or sessions[-1]!=proof['calendar_end']
            or day not in proof['due_dates']):
        raise ValueError('terminal settlement supplement outside authorized E1 boundary')
    provenance={'schema':proof['schema'],'proof_sha256':PROOF_SHA,
                'tail_sessions':proof['tail_sessions'],'scope':proof['scope']}
    return proof['due_dates'][day],provenance
