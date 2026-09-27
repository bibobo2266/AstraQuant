#!/usr/bin/env python3
from __future__ import annotations
import os,re
from pathlib import Path
import pandas as pd

SOURCE_ROOT=Path(os.environ.get("SOURCE_ROOT","source_runtime/minervini_picks/data")).resolve()
REPORT_PATH=Path(os.environ.get("REPORT_PATH","docs/ADJ_INVALID_CLASSIFICATION.md"))
KEYS=["date","stock_id"]; OHLC=["open","max","min","close"]

def yr(p):
    m=re.search(r"(20\d{2})",p.name)
    if not m: raise ValueError(p.name)
    return int(m.group(1))

def norm(df):
    df=df.copy(); df["stock_id"]=df["stock_id"].astype(str); df["date"]=pd.to_datetime(df["date"],errors="coerce")
    for c in OHLC: df[c]=pd.to_numeric(df[c],errors="coerce")
    return df

def classify(df):
    any_nonpos=(df[OHLC] <= 0).any(axis=1)
    close_nonpos=df["close"] <= 0
    geom=(df["max"]>=df[["open","close","min"]].max(axis=1)) & (df["min"]<=df[["open","close","max"]].min(axis=1))
    invalid=any_nonpos | ~geom
    return invalid,any_nonpos,close_nonpos,~geom

def main():
    aps=sorted((SOURCE_ROOT/"adj").glob("prices_adj_*.parquet"))
    tradp=SOURCE_ROOT/"reference"/"tradability.parquet"
    if not aps or not tradp.exists(): raise SystemExit("BLOCKED")
    t=pd.read_parquet(tradp,columns=["date","stock_id","valid_ohlc","buy_blocked","sell_blocked","observed_trade","reason"])
    t["stock_id"]=t["stock_id"].astype(str); t["date"]=pd.to_datetime(t["date"],errors="coerce")
    rows=[]
    for p in aps:
        y=yr(p); d=norm(pd.read_parquet(p,columns=KEYS+OHLC)); d=d[d.stock_id.str.fullmatch(r"[1-9]\d{3}",na=False)].copy()
        invalid,nonpos,close_nonpos,geom_bad=classify(d)
        d["invalid_adj"]=invalid; d["nonpos"]=nonpos; d["close_nonpos"]=close_nonpos; d["geom_bad"]=geom_bad
        m=d.merge(t[t.date.dt.year.eq(y)],on=KEYS,how="left",indicator=True,validate="one_to_one")
        bad=m[m.invalid_adj]
        rows.append({
            "year":y,"rows":len(m),"invalid_adj":len(bad),"nonpos":int(bad.nonpos.sum()),
            "close_nonpos":int(bad.close_nonpos.sum()),"geom_bad":int(bad.geom_bad.sum()),
            "trad_missing":int((bad["_merge"]!="both").sum()),
            "buy_blocked":int(bad["buy_blocked"].fillna(False).sum()),
            "sell_blocked":int(bad["sell_blocked"].fillna(False).sum()),
            "observed_trade_false":int((~bad["observed_trade"].fillna(False)).sum()),
            "trad_valid_true":int(bad["valid_ohlc"].fillna(False).sum()),
        })
    unresolved=sum(r["trad_valid_true"] for r in rows)
    status="PASS_CANONICAL_MASK_REQUIRED" if unresolved==0 else "NEEDS_REVIEW"
    lines=["# Adjusted Invalid OHLC Classification","",f"Status: **{status}**","",
           "Purpose: determine whether invalid adjusted OHLC rows are source defects or rows already excluded by execution/tradability semantics.","",
           "| Year | Numeric ADJ rows | Invalid ADJ | Any nonpositive | Close nonpositive | Geometry bad | Missing tradability | Buy blocked | Sell blocked | observed_trade=False | Tradability says valid |",
           "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        lines.append(f"| {r['year']} | {r['rows']:,} | {r['invalid_adj']:,} | {r['nonpos']:,} | {r['close_nonpos']:,} | {r['geom_bad']:,} | {r['trad_missing']:,} | {r['buy_blocked']:,} | {r['sell_blocked']:,} | {r['observed_trade_false']:,} | {r['trad_valid_true']:,} |")
    lines += ["","## Decision rule","",
              "- If invalid adjusted rows are never marked valid by tradability, do not reopen source remediation solely for these rows.",
              "- Canonical research construction must mask/exclude invalid or non-tradable stock-days before technical-feature computation.",
              "- Rows lacking tradability coverage remain excluded from execution and require explicit research-universe handling.",
              "","## Next small task","","Audit PIT/reference datasets for temporal keys and null/order constraints."]
    REPORT_PATH.parent.mkdir(parents=True,exist_ok=True); REPORT_PATH.write_text("\n".join(lines)+"\n",encoding="utf-8")
if __name__=="__main__": main()
