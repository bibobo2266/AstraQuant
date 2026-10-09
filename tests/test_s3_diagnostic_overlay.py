"""Approved fixed overlay: excluded is not unused; no formal unlock."""
import json
from pathlib import Path
import pandas as pd
import pytest
import astraquant.research.trading_plan_r1_s3 as s3

def test_approved_real_exclusion_list():
    root=Path('/workspace/scratch/4498b78b33c4')
    p=root/'AstraQuant-full/results/trading_plan_r1/accounting_export_37769333701/s3_wiring_v5/missing_limit_keys.csv'
    if not p.exists():pytest.skip('frozen missing-key evidence absent')
    stocks=sorted(pd.read_csv(p,dtype={'stock':str}).stock.unique())
    m=dict(purpose='s3_accounting_probe',diagnostic_overlay=dict(version='A_exclude_missing_limits_102',approval_issue_comment=6072210571,missing_keys_sha256=s3.DIAGNOSTIC_A_MISSING_SHA,missing_keys_path=str(p.relative_to(root)),excluded_stocks=stocks))
    assert len(s3._diagnostic_a_exclusions(m,root))==102
    assert not {'6286','5305'} & s3._diagnostic_a_exclusions(m,root)
    for key,value in [('excluded_stocks',stocks[:-1]),('approval_issue_comment',0),('version','B'),('missing_keys_sha256','0'*64)]:
        wrong=json.loads(json.dumps(m));wrong['diagnostic_overlay'][key]=value
        with pytest.raises(ValueError):s3._diagnostic_a_exclusions(wrong,root)
    wrong=json.loads(json.dumps(m));wrong['purpose']='s3_source'
    with pytest.raises(ValueError):s3._diagnostic_a_exclusions(wrong,root)

def test_existing_probe_has_no_overlay():
    assert not s3._diagnostic_a_exclusions({},Path('.'))


def test_reviewed_b_restoration_and_tamper_rejection():
    root=Path('/workspace/scratch/4498b78b33c4')
    p=root/'AstraQuant-full/results/trading_plan_r1/accounting_export_37769333701/s3_wiring_v5/missing_limit_keys.csv'
    supplement=root/'AstraQuant-full/results/trading_plan_r1/limit_supplement_2016_2018/price_limit_supplement_2016_2018.parquet'
    if not p.exists() or not supplement.exists():pytest.skip('reviewed real B evidence absent')
    all_stocks=set(pd.read_csv(p,dtype={'stock':str}).stock)
    m=dict(purpose='s3_accounting_probe',files=[dict(path=str(supplement.relative_to(root)),role='supplement_2016_2018',sha256=s3.DIAGNOSTIC_B_LIMIT_SHA)],diagnostic_overlay=dict(version='B_restore_verified_21_exclude_81',approval_issue_comment=6072210571,restoration_review_comment=6072459378,missing_keys_sha256=s3.DIAGNOSTIC_A_MISSING_SHA,missing_keys_path=str(p.relative_to(root)),restored_stocks=sorted(s3.DIAGNOSTIC_B_RESTORED),excluded_stocks=sorted(all_stocks-s3.DIAGNOSTIC_B_RESTORED)))
    assert len(s3._diagnostic_a_exclusions(m,root))==81
    restored=pd.read_parquet(supplement);missing=pd.read_csv(p,dtype={'stock':str})
    assert len(missing[missing.stock.isin(s3.DIAGNOSTIC_B_RESTORED)])==65
    actual=set(zip(restored.date.astype(str),restored.stock_id.astype(str)))
    assert all((row.date,row.stock) in actual for row in missing[missing.stock.isin(s3.DIAGNOSTIC_B_RESTORED)].itertuples())
    for key,value in [('restoration_review_comment',0),('restored_stocks',sorted(s3.DIAGNOSTIC_B_RESTORED)[:-1]),('excluded_stocks',sorted(all_stocks))]:
        wrong=json.loads(json.dumps(m));wrong['diagnostic_overlay'][key]=value
        with pytest.raises(ValueError):s3._diagnostic_a_exclusions(wrong,root)
    wrong=json.loads(json.dumps(m));wrong['files'][0]['sha256']='0'*64
    with pytest.raises(ValueError):s3._diagnostic_a_exclusions(wrong,root)
    wrong=json.loads(json.dumps(m));wrong['diagnostic_overlay']['version']='A_exclude_missing_limits_102'
    with pytest.raises(ValueError,match='cannot alter fixed A'):s3._diagnostic_a_exclusions(wrong,root)


def test_distinct_date_conversion_preserves_owner_values_and_index():
    from astraquant.research.trading_plan_r1 import _day
    values=pd.Series(pd.to_datetime(['2016-01-04','2016-01-04','2021-12-31']),index=[4,8,9])
    pd.testing.assert_series_equal(s3._day_labels(values),values.map(_day))


def test_shared_verified_buffers_do_not_bypass_mutation_guard(tmp_path):
    from test_trading_plan_r1_s3 import bundle,engine
    root,days=bundle(tmp_path);e=engine(root)
    other=s3.S3TradingPlanR1(inputs=e.inputs,run_id='sibling',entry_mode='next_open',exit_mode='sma20')
    other._bound_bars.loc[80,'close']=9999.
    for run in [e,other]:
        with pytest.raises(ValueError,match='changed verified S3'):run.prepare(days[80])
