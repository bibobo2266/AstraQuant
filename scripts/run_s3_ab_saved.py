#!/usr/bin/env python3
"""Execute the authorized fixed A/B diagnostic with durable GitHub checkpoints.

Local checkpoints remain daily. Remote publication is first day, every 20
completed sessions, frozen state and final day; receipts name the saved day.
No workflow dispatch, source refresh or performance-gate changes.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

from source_accounting_smoke_replay import (
    package_checkpoint_transport, restore_s3_evidence_transport,
    run_s3_diagnostic_a,
)

REPO = 'bibobo2266/AstraQuant'
BRANCH = 'research/trading-plan-r1'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git_blob(data):
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


class GitHubCheckpointPublisher:
    def __init__(self, *, token_file, local_root, remote_root, interval=20):
        self.token = Path(token_file).read_text().strip()
        self.local_root = Path(local_root).resolve()
        self.remote_root = remote_root.strip('/')
        self.interval = interval
        self.state_path=self.local_root/'github_publisher_state.json'
        prior=json.loads(self.state_path.read_text()) if self.state_path.exists() else {}
        self.known = prior.get('known',{})
        self.receipts = prior.get('receipts',{})

    def api(self, method, path, body=None):
        url='https://api.github.com/repos/'+REPO+'/'+path
        headers={'Authorization':'Bearer '+self.token,
                 'Accept':'application/vnd.github+json','User-Agent':'AstraQuant-Sol-E'}
        data=None if body is None else json.dumps(body).encode()
        if data is not None: headers['Content-Type']='application/json'
        request=urllib.request.Request(url, data=data, headers=headers, method=method)
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=45) as result:
                    return json.load(result)
            except urllib.error.HTTPError as error:
                detail=error.read().decode(errors='replace')[:500]
                if error.code in {429,500,502,503,504} and attempt<2:
                    time.sleep(2*(attempt+1));continue
                raise RuntimeError(f'GitHub {method} {path}: HTTP {error.code}: {detail}') from None

    def read_file(self, commit, path):
        item=self.api('GET','contents/'+urllib.parse.quote(path, safe='/')+'?ref='+commit)
        if item.get('encoding')!='base64' or not item.get('content'):
            raise ValueError('GitHub text readback absent: '+path)
        return base64.b64decode(item['content'])

    def publish_files(self, files, message):
        # Inline text blobs and one tree/commit/ref update make the generation
        # visible atomically. No large ZIP; immutable parts are never resent.
        changed={p:b for p,b in files.items() if self.known.get(p)!=git_blob(b)}
        if not changed:
            raise ValueError('empty remote publication')
        for attempt in range(3):
            ref=self.api('GET','git/ref/heads/'+BRANCH)
            parent=ref['object']['sha']; commit=self.api('GET','git/commits/'+parent)
            entries=[dict(path=p,mode='100644',type='blob',content=b.decode('utf-8')) for p,b in changed.items()]
            tree=self.api('POST','git/trees',dict(base_tree=commit['tree']['sha'],tree=entries))
            returned={x['path']:x['sha'] for x in tree['tree'] if x['type']=='blob'}
            if not set(changed)<=set(returned):
                returned={x['path']:x['sha'] for x in self.api('GET','git/trees/'+tree['sha']+'?recursive=1')['tree'] if x['type']=='blob'}
            for p,b in changed.items():
                if returned.get(p)!=git_blob(b):raise ValueError('remote blob hash mismatch: '+p)
            new=self.api('POST','git/commits',dict(message=message,tree=tree['sha'],parents=[parent]))
            try:
                self.api('PATCH','git/refs/heads/'+BRANCH,dict(sha=new['sha'],force=False))
            except RuntimeError:
                if attempt<2 and self.api('GET','git/ref/heads/'+BRANCH)['object']['sha']!=parent:continue
                raise
            self.known.update({p:git_blob(b) for p,b in changed.items()})
            return new['sha']
        raise RuntimeError('remote branch changed repeatedly')

    def __call__(self, checkpoint):
        checkpoint=Path(checkpoint).resolve()
        checkpoint.relative_to(self.local_root)
        state=json.loads(checkpoint.read_text());cell=checkpoint.parent.name
        completed=state['completed'];count=len(completed)
        remaining=[d for d in state['sessions'] if d>=completed[0] and d not in completed]
        if (cell in self.receipts and count%self.interval and not state['frozen'] and remaining):
            return self.receipts[cell]
        package_checkpoint_transport(checkpoint.parent)
        manifest=(checkpoint.parent/'transport.json').read_bytes();inventory=json.loads(manifest)
        remote=self.remote_root+'/'+cell
        pieces={p['file']:p for item in inventory['files'] for p in item['parts']}
        files={remote+'/'+name:(checkpoint.parent/name).read_bytes() for name in pieces}
        files[remote+'/transport.json']=manifest
        for name,item in pieces.items():
            value=files[remote+'/'+name]
            if len(value)!=item['bytes'] or sha(value)!=item['sha256']:raise ValueError('local piece changed')
        # Preserve the declared run/manifest alongside each independently
        # restorable cell; secret material is never included.
        for name in ['manifest.json','receipt.json','progress.json']:
            path=checkpoint.parent.parent/name
            if path.exists():files[self.remote_root+'/'+name]=path.read_bytes()
        revision=self.publish_files(files, 'Save '+state['identity']['run_id']+' through '+completed[-1]+' [skip ci]')
        if self.read_file(revision,remote+'/transport.json')!=manifest:
            raise ValueError('remote transport readback mismatch')
        receipt=dict(commit=revision,repo=REPO,path=remote+'/transport.json',
                     transport_sha256=sha(manifest),checkpoint_sha256=sha(checkpoint.read_bytes()),
                     saved_completed_day=completed[-1],saved_completed_sessions=count,
                     local_completed_sessions=count,readback_verified=True,
                     remote_interval_sessions=self.interval,
                     publisher_sha256=sha(Path(__file__).read_bytes()))
        self.receipts[cell]=receipt
        from astraquant.research.trading_plan_r1_s3 import _atomic_write
        _atomic_write(self.state_path,json.dumps(dict(known=self.known,receipts=self.receipts)).encode())
        (checkpoint.parent/'external_checkpoint_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        print('REMOTE_CHECKPOINT '+json.dumps(receipt),flush=True)
        return receipt

    def download(self, receipt, destination):
        target=Path(destination);target.mkdir(parents=True,exist_ok=True)
        manifest=self.read_file(receipt['commit'],receipt['path'])
        if sha(manifest)!=receipt['transport_sha256']:raise ValueError('changed pinned remote manifest')
        (target/'transport.json').write_bytes(manifest)
        base=receipt['path'].rsplit('/',1)[0]
        for item in json.loads(manifest)['files']:
            for part in item['parts']:
                path=target/part['file'];path.resolve().relative_to(target.resolve())
                if path.exists() and sha(path.read_bytes())==part['sha256']:continue
                value=self.read_file(receipt['commit'],base+'/'+part['file'])
                if len(value)!=part['bytes'] or sha(value)!=part['sha256']:raise ValueError('changed remote part')
                path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(value)
        restore_s3_evidence_transport(target)
        if sha((target/'checkpoint.json').read_bytes())!=receipt['checkpoint_sha256']:
            raise ValueError('restored remote head mismatch')
        return target/'checkpoint.json'


def verify_next_day(publisher, output, workspace):
    from astraquant.research.trading_plan_r1_s3 import S3Inputs,S3BatchTradingPlanR1
    inputs=S3Inputs.open_accounting_probe(workspace,output/'manifest.json',output/'receipt.json')
    evidence=[]
    for cell, receipt in publisher.receipts.items():
        with tempfile.TemporaryDirectory(dir=output,prefix='remote-readback-') as directory:
            remote=publisher.download(receipt,directory)
            a=S3BatchTradingPlanR1.load_checkpoint(output/cell/'checkpoint.json',inputs=inputs)
            b=S3BatchTradingPlanR1.load_checkpoint(remote,inputs=inputs)
            day=a.remaining_sessions()[0]
            assert b.remaining_sessions()[0]==day
            for engine in [a,b]:
                engine.prepare(day);engine.reconcile_session(day,observed_at=day)
            a.save(Path(directory)/'local-next.json');b.save(Path(directory)/'remote-next.json')
            first=(Path(directory)/'local-next.json').read_bytes()
            assert first==(Path(directory)/'remote-next.json').read_bytes()
            evidence.append(dict(cell=cell,remote_checkpoint=receipt,next_day=day,
                                 next_day_state_sha256=sha(first),exact_state_equal=True))
            del a,b
    target=output/'remote_readback_next_day.json'
    target.write_text(json.dumps(evidence,indent=2)+'\n')
    revision=publisher.publish_files({publisher.remote_root+'/remote_readback_next_day.json':target.read_bytes()},
                                    'Verify pinned remote checkpoints and next-day accounting [skip ci]')
    return revision,evidence


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--workspace',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--remote-root',required=True)
    parser.add_argument('--token-file',required=True)
    parser.add_argument('--round',choices=['A','B'],required=True)
    parser.add_argument('--max-sessions',type=int)
    parser.add_argument('--verify-next-day',action='store_true')
    args=parser.parse_args();output=Path(args.output).resolve();output.mkdir(parents=True,exist_ok=True)
    import fcntl
    lock=(output/'execution.lock').open('w')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    lock.write(json.dumps(dict(pid=os.getpid(),started_at=time.time(),round=args.round)));lock.flush()
    publisher=GitHubCheckpointPublisher(token_file=args.token_file,local_root=output,remote_root=args.remote_root)
    try:
        result=run_s3_diagnostic_a(workspace=args.workspace,output_dir=output,round_name=args.round,
                                   max_sessions=args.max_sessions,checkpoint_publisher=publisher)
        failures={c:s for c,s in result['cells'].items() if s['status']=='ERROR'}
        if failures:raise RuntimeError(json.dumps(failures))
        if args.verify_next_day:
            revision,evidence=verify_next_day(publisher,output,Path(args.workspace))
            publisher.api('POST','issues/6/comments',dict(body='Sol-E｜'+args.round+' 實際遠端 checkpoint／下一日讀回驗證完成。執行 ID：'+result['execution_id']+'；保存根目錄：'+args.remote_root+'；讀回證據 commit：'+revision+'。四格皆逐片／壓縮／還原 SHA 通過，實際 engine 下一未完成日接續後完整 state bytes 相同。'+json.dumps(evidence,ensure_ascii=False)))
        publisher.api('POST','issues/6/comments',dict(body='Sol-E｜'+args.round+' 執行狀態：'+json.dumps(result,ensure_ascii=False)))
    except Exception as error:
        publisher.api('POST','issues/6/comments',dict(body='Sol-E｜'+args.round+' 具體失敗：'+type(error).__name__+': '+str(error)[:4000]+'；本機 PID '+str(os.getpid())+'；保存根目錄 '+args.remote_root+'。不宣稱恢復成功。'))
        raise


if __name__=='__main__':main()
