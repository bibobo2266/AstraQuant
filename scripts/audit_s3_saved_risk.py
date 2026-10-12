"""Read fixed saved S3 tables; no market retrieval or trading execution."""
import argparse,base64,gzip,hashlib,json,subprocess,time
from datetime import date
from pathlib import Path


def sha(b):return hashlib.sha256(b).hexdigest()
def read_saved(rev,cell):
    base='results/trading_plan_r1/s3_live_20261011/A/'+cell+'/'
    def get(path):return subprocess.check_output(['git','show',rev+':'+base+path])
    index=json.loads(get('transport.json'));items={x['decoded_file']:x for x in index['files']}
    def decode(item,parts=None):
        encoded=[]
        for part in item['parts']:
            b=get(part['file']) if parts is None else parts[part['file']]
            assert len(b)==part['bytes'] and sha(b)==part['sha256'];encoded.append(b.strip())
        b=base64.b64decode(b''.join(encoded),validate=True)
        assert len(b)==item['compressed_bytes'] and sha(b)==item['compressed_sha256']
        b=gzip.decompress(b);assert len(b)==item['decoded_bytes'] and sha(b)==item['decoded_sha256'];return b
    raw=decode(items['checkpoint.json']);h=json.loads(raw)
    from astraquant.research.trading_plan_r1_s3 import _digest
    assert h['state_digest']==_digest({k:v for k,v in h.items() if k!='state_digest'})
    refs=[x for x in h['checkpoint_storage']['chunks'] if x['table']=='equity']
    paths=list(dict.fromkeys(p['file'] for ref in refs for p in items[ref['path']]['parts']))
    batch=subprocess.check_output(['git','cat-file','--batch'],input=('\n'.join(rev+':'+base+p for p in paths)+'\n').encode())
    offset=0;parts={}
    for path in paths:
        end=batch.index(b'\n',offset);size=int(batch[offset:end].split()[2]);offset=end+1
        parts[path]=batch[offset:offset+size];offset+=size+1
    for ref in refs:
        b=gzip.decompress(decode(items[ref['path']],parts));assert sha(b)==ref['sha256']
        rows=json.loads(b);assert len(rows)==ref['rows'];h['tables']['equity'].extend(rows)
    assert [x['date'] for x in h['tables']['equity']]==h['completed']
    assert len(h['completed'])==1468 and not h['frozen']
    return h,sha(raw)


def risks(h):
    e=h['tables']['equity'];initial=h['initial_cash'];peak=initial;peak_index=-1;episodes=[];active=None;worst=None
    for i,row in enumerate(e):
        value=float(row['equity']);assert value>0
        if value>=peak:
            if active is not None:
                active.update(end=row['date'],recovered=True,trading_session_intervals=i-active['peak_index'],underwater_observations=i-active['peak_index']-1)
                episodes.append(active);active=None
            peak=value;peak_index=i
        else:
            if active is None:active=dict(peak_index=peak_index,start=e[peak_index]['date'] if peak_index>=0 else e[0]['date'],peak_equity=peak)
            depth=(peak-value)/peak
            if worst is None or depth>worst['fraction']:
                worst=dict(fraction=depth,peak_date=active['start'],trough_date=row['date'],peak_equity=peak,trough_equity=value)
    if active is not None:
        active.update(end=e[-1]['date'],recovered=False,trading_session_intervals=len(e)-1-active['peak_index'],underwater_observations=len(e)-1-active['peak_index']);episodes.append(active)
    longest=max(episodes,key=lambda x:(x['trading_session_intervals'],x['start'])) if episodes else None
    if longest:longest['calendar_days']=(date.fromisoformat(longest['end'])-date.fromisoformat(longest['start'])).days
    if worst:
        episode=next(x for x in episodes if x['start']==worst['peak_date'] and x['start']<=worst['trough_date']<=x['end'])
        worst['recovery_date']=episode['end'] if episode['recovered'] else None
    filled=[x for x in h['tables']['fills'] if x['fill']]
    closed=[x for x in filled if x['side']=='sell' and x['net_return'] is not None and not x['truncated']]
    assert len(closed)==88 and len({x['trade_id'] for x in closed})==88
    order={x['id']:i for i,x in enumerate(h['journal']) if x['kind']=='fill'}
    closed.sort(key=lambda x:(x['fill_date'],order.get(x['row_id'],0),x['row_id']))
    streak=[];max_streak=[]
    for row in closed:
        if row['net_return']<0:
            streak.append(row)
            if len(streak)>len(max_streak):max_streak=list(streak)
        else:streak=[]
    sensitivity={}
    for label,key in [('largest_net_profit_TWD','pnl'),('largest_net_return','net_return')]:
        winners=sorted([x for x in closed if x['net_return']>0],key=lambda x:(-x[key],x['fill_date'],x['row_id']))
        sensitivity[label]=[]
        for k in (1,3,5):
            removed=winners[:k];ids={x['row_id'] for x in removed};remaining=[x for x in closed if x['row_id'] not in ids]
            sensitivity[label].append(dict(remove_count=k,remaining_closed=len(remaining),expectancy=sum(x['net_return'] for x in remaining)/len(remaining),removed=[dict(stock=x['stock'],exit_date=x['fill_date'],net_profit_TWD=x['pnl'],net_return=x['net_return'],row_id=x['row_id']) for x in removed]))
    return dict(initial_equity=initial,final_equity=e[-1]['equity'],closed_count=88,open_count=len(h['positions']),baseline_expectancy=sum(x['net_return'] for x in closed)/len(closed),maximum_drawdown=worst,longest_drawdown=longest,maximum_consecutive_losses=dict(count=len(max_streak),start_exit_date=max_streak[0]['fill_date'] if max_streak else None,end_exit_date=max_streak[-1]['fill_date'] if max_streak else None,trade_ids=[x['trade_id'] for x in max_streak]),expectancy_after_removing_winners=sensitivity,definitions={'drawdown':'initial capital and saved end-of-session marked equity; no intraday claim','duration':'peak-to-recovery session intervals, or peak-to-last session if unrecovered; underwater observations also supplied','loss_streak':'closed filled sells by actual fill_date then canonical journal order; zero/positive return breaks streak','remove_winners':'primary rank net profit TWD pnl; secondary rank net_return; exclude saved closed rows, change denominator; no portfolio rerun','expectancy':'arithmetic mean of fixed ledger net_return after costs; open position excluded'})


def main():
    p=argparse.ArgumentParser();p.add_argument('--ref',default='133bce48713d2f3009f32557aec7a38d3387aa39');p.add_argument('--output',type=Path,required=True);a=p.parse_args();started=time.monotonic()
    h,digest=read_saved(a.ref,'A2');report=dict(cell='A2',source_commit=a.ref,checkpoint_sha256=digest,source_period=['2016-01-04','2021-12-31'],completed_sessions=1468,trading_dates_replayed=0,**risks(h));report['analysis_elapsed_seconds']=time.monotonic()-started
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
if __name__=='__main__':main()
