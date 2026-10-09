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
