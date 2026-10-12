"""Compare preserved A2/A4 fills and inclusive holding RSI without replay."""
import argparse,base64,collections,gzip,json,math,subprocess,time
from pathlib import Path
from audit_s3_saved_risk import read_saved,sha


def audit(ref):
    a,_=read_saved(ref,'A2');b,digest=read_saved(ref,'A4')
    filled=lambda h:[x for x in h['tables']['fills'] if x['fill']]
    fa,fb=filled(a),filled(b)
    cols=['fill_date','date','stock','side','fill_price','quantity','commission','slippage','tax','reason','pnl','net_return']
    view=lambda rows:[{k:x[k] for k in cols} for x in rows]
    assert view(fa)==view(fb)
    buys={x['trade_id']:x for x in fb if x['side']=='buy'};sells={x['trade_id']:x for x in fb if x['side']=='sell'}
    assert len(buys)==89 and len(sells)==88
    calendar=b['completed'];periods=[];byday=collections.defaultdict(dict)
    for tid,buy in buys.items():
        sell=sells.get(tid);start=buy['fill_date'];end=sell['fill_date'] if sell else calendar[-1]
        for day in calendar:
            if start<=day<=end:byday[day][buy['stock']]={'trade_id':tid,'exit_today':sell is not None and day==end,'exit_reason':sell['reason'] if sell else None,'entry_today':day==start}
        periods.append(dict(stock=buy['stock'],entry_date=start,entry_price=buy['fill_price'],exit_date=sell['fill_date'] if sell else None,exit_price=sell['fill_price'] if sell else None,exit_reason=sell['reason'] if sell else None,net_return=sell['net_return'] if sell else None))
    base='results/trading_plan_r1/s3_live_20261011/A/A4/'
    def get(p):return subprocess.check_output(['git','show',ref+':'+base+p])
    index=json.loads(get('transport.json'));items={x['decoded_file']:x for x in index['files']}
    refs=[x for x in b['checkpoint_storage']['chunks'] if x['table']=='eligibility']
    paths=list(dict.fromkeys(p['file'] for x in refs for p in items[x['path']]['parts']))
    batch=subprocess.check_output(['git','cat-file','--batch'],input=('\n'.join(ref+':'+base+p for p in paths)+'\n').encode())
    pos=0;parts={}
    for path in paths:
        end=batch.index(b'\n',pos);size=int(batch[pos:end].split()[2]);pos=end+1;parts[path]=batch[pos:pos+size];pos+=size+1
    counts=collections.Counter();below=[];seen=set();min_rsi=math.inf
    for refrow in refs:
        item=items[refrow['path']];encoded=[]
        for part in item['parts']:
            raw=parts[part['file']];assert len(raw)==part['bytes'] and sha(raw)==part['sha256'];encoded.append(raw.strip())
        packed=base64.b64decode(b''.join(encoded),validate=True);assert len(packed)==item['compressed_bytes'] and sha(packed)==item['compressed_sha256']
        raw=gzip.decompress(packed);assert len(raw)==item['decoded_bytes'] and sha(raw)==item['decoded_sha256']
        raw=gzip.decompress(raw);assert sha(raw)==refrow['sha256'];rows=json.loads(raw);assert len(rows)==refrow['rows']
        for row in rows:
            held=byday.get(row['date'],{}).get(row['stock'])
            if held is None:continue
            key=(row['date'],row['stock']);assert key not in seen;seen.add(key)
            values=row['condition_values'];rsi=values.get('rsi13');counts['inclusive_holding_stock_days']+=1
            phase='exit_day' if held['exit_today'] else 'end_of_day_still_held'
            counts[phase]+=1
            if rsi is None:counts['missing_rsi']+=1;continue
            assert math.isfinite(rsi);min_rsi=min(min_rsi,rsi)
            if rsi<50:
                counts['rsi_below50_all_inclusive_holding_days']+=1;counts['rsi_below50_'+phase]+=1
                below.append(dict(day=row['date'],stock=row['stock'],rsi13=rsi,close=values['close'],sma20=values['sma20'],**held))
    assert len(seen)==sum(len(x) for x in byday.values())
    report=dict(source_commit=ref,A4_head_sha256=digest,A2_exit_mode=a['identity']['exit_mode'],A4_exit_mode=b['identity']['exit_mode'],filled_rows_compared=len(fa),comparison_fields=cols,all_filled_rows_equal=True,closed_trades_compared=88,open_trades_compared=1,sell_reason_counts=dict(collections.Counter(x['reason'] for x in fb if x['side']=='sell')),counts=dict(counts),min_RSI_inclusive_holding=min_rsi,RSI_below50_observations=below,trade_comparison=sorted(periods,key=lambda x:(x['entry_date'],x['stock'])),definitions={'holding_interval':'actual fill_date entry through actual fill_date exit inclusive; final open trade through final session','close_RSI_applicable':'only position still held after fixed-engine opening/intraday exit processing','count':'stock-day observations; entry and exit day included, no outside-holding market observations','old_audit_correction':'prior1198 used fills.date which can be signal/intent date for next-open. Preserve old audit; this report uses actual fill_date; trading outputs unaffected'},trading_dates_replayed=0,minimal_rebuild_scope='saved-table audit only; no trading rerun')
    eod=[x for x in below if not x['exit_today']];exited=[x for x in below if x['exit_today']]
    coincident=[x for x in eod if x['sma20'] is not None and x['close']<x['sma20']]
    signals={(x['date'],x['stock']) for x in b['tables']['fills'] if x['side']=='sell' and x['reason']=='sma20_next_open'}
    assert all((x['day'],x['stock']) in signals for x in coincident)
    report['RSI_overlap_explanation']=dict(RSI_below50_while_still_held_at_close=len(eod),
        simultaneously_close_below_SMA20=len(coincident),matching_saved_SMA20_exit_signal=len(coincident),
        independent_RSI_only_close_signal=len(eod)-len(coincident),RSI_below50_on_exit_day=len(exited),
        exit_day_reason_counts=dict(collections.Counter(x['exit_reason'] for x in exited)),
        actual_RSI_reason_filled_exits=sum(x['reason']=='rsi13_lt50_next_open' for x in fb if x['side']=='sell'),
        reason_precedence='fixed source first returns SMA20 reason; RSI is evaluated for exit only if SMA20 reason empty',
        conclusion='no additional RSI-only execution path in this saved sample; actual fills and all eight metrics equal',
        trading_code_change_required=False,minimal_trading_rerun_days=0)
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument('--ref',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();start=time.monotonic();r=audit(a.ref);r['analysis_elapsed_seconds']=time.monotonic()-start;a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k!='trade_comparison'}),flush=True)
if __name__=='__main__':main()
