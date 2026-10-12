"""Metadata publication retains bytes and refuses mismatched accepted commits."""
import base64
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from run_s3_ab_saved import GitHubCheckpointPublisher,git_blob


def probe(raw,corrupt=None):
    pub=GitHubCheckpointPublisher.__new__(GitHubCheckpointPublisher)
    pub.known={};calls=[];blob_sha=git_blob(raw)
    def api(method,path,body=None):
        calls.append((method,path,body))
        if path.startswith('git/ref/'):return {'object':{'sha':'parent'}}
        if method=='GET' and path=='git/commits/parent':return {'tree':{'sha':'base'}}
        if method=='POST' and path=='git/blobs':
            assert body['encoding']=='base64' and base64.b64decode(body['content'])==raw
            return {'sha':'wrong' if corrupt=='created_sha' else blob_sha}
        if method=='GET' and path=='git/blobs/'+blob_sha:
            return {'encoding':'base64','content':base64.b64encode(b'changed' if corrupt=='blob_bytes' else raw).decode()}
        if method=='POST' and path=='git/trees':
            entry=body['tree'][0];assert entry['sha']==blob_sha and 'content' not in entry
            return {'sha':'new-tree','tree':[],'truncated':True}
        if method=='GET' and path=='git/trees/new-tree':return {'tree':[{'path':'B','type':'tree','sha':'Btree'}]}
        if method=='GET' and path=='git/trees/Btree':return {'tree':[{'path':'progress.json','type':'blob','sha':'wrong-tree-sha' if corrupt=='tree_sha' else blob_sha}]}
        if method=='POST' and path=='git/commits':return {'sha':'candidate'}
        if method=='PATCH':return {}
        raise AssertionError((method,path))
    pub.api=api
    pub.read_file=lambda commit,path: b'changed' if corrupt=='candidate_bytes' else raw
    return pub,calls


def test_exact_base64_metadata_and_bounded_tree_lookup_before_ref():
    raw='{"error":"配股\\n traceback"}\r\n'.encode()
    pub,calls=probe(raw)
    assert pub.publish_files({'B/progress.json':raw},'test')=='candidate'
    assert pub.known['B/progress.json']==git_blob(raw)
    assert sum(method=='PATCH' for method,_,_ in calls)==1
    assert not any('recursive=1' in path for _,path,_ in calls)


@pytest.mark.parametrize('corrupt',['created_sha','blob_bytes','candidate_bytes','tree_sha'])
def test_metadata_corruption_never_moves_branch(corrupt):
    pub,calls=probe(b'{"completed":634}\n',corrupt)
    with pytest.raises(ValueError,match='mismatch'):
        pub.publish_files({'B/progress.json':b'{"completed":634}\n'},'test')
    assert not any(method=='PATCH' for method,_,_ in calls)
    assert pub.known=={}


def test_tree_directory_cache_removes_per_file_duplicate_requests():
    pub=GitHubCheckpointPublisher.__new__(GitHubCheckpointPublisher);calls=[]
    def api(method,path,body=None):
        calls.append(path)
        if path=='git/trees/root':return {'tree':[{'path':'B','type':'tree','sha':'leaf'}]}
        assert path=='git/trees/leaf'
        return {'tree':[{'path':str(i)+'.part','type':'blob','sha':'sha'+str(i)} for i in range(100)]}
    pub.api=api;cache={}
    for i in range(100):assert pub._tree_path_sha('root','B/'+str(i)+'.part',cache)=='sha'+str(i)
    assert calls==['git/trees/root','git/trees/leaf']
    with pytest.raises(ValueError,match='path absent'):pub._tree_path_sha('root','B/missing.part',cache)


def test_rate_limit_reset_waits_in_bounded_chunks_and_retries_same_request(monkeypatch):
    import io,urllib.error
    import run_s3_ab_saved as module
    pub=GitHubCheckpointPublisher.__new__(GitHubCheckpointPublisher);pub.token='test';pub.rate_wait_seconds=0
    attempts=[];sleeps=[]
    class Response:
        headers={'x-ratelimit-remaining':'99','x-ratelimit-reset':'2000'}
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return b'{"ok":true}'
    def open_request(request,timeout):
        attempts.append(request.full_url)
        if len(attempts)==1:raise urllib.error.HTTPError(request.full_url,403,'limited',{'x-ratelimit-remaining':'0','x-ratelimit-reset':'1090'},io.BytesIO(b'{"message":"API rate limit exceeded"}'))
        return Response()
    monkeypatch.setattr(module.urllib.request,'urlopen',open_request)
    monkeypatch.setattr(module.time,'time',lambda:1000.)
    monkeypatch.setattr(module.time,'sleep',sleeps.append)
    monkeypatch.delenv('S3_JOB_EPOCH',raising=False)
    assert pub.api('GET','git/ref/heads/research/trading-plan-r1')=={'ok':True}
    assert attempts[0]==attempts[1] and len(attempts)==2
    assert sleeps==[60.,35.] and pub.rate_wait_seconds==95.
    assert pub.api_request_count==2


def test_rate_wait_requires_server_timing_and_honors_total_budget(monkeypatch):
    import run_s3_ab_saved as module
    pub=GitHubCheckpointPublisher.__new__(GitHubCheckpointPublisher);pub.rate_wait_seconds=3590.
    monkeypatch.delenv('S3_JOB_EPOCH',raising=False)
    monkeypatch.setattr(module.time,'sleep',lambda _:pytest.fail('must not sleep'))
    with pytest.raises(RuntimeError,match='usable reset'):
        pub._rate_wait(403,{},'rate limit exceeded')
    with pytest.raises(RuntimeError,match='bounded job'):
        pub._rate_wait(429,{'retry-after':'11'},'limited')
    assert pub._rate_wait(403,{},'forbidden') is False


def test_ref_race_rebuilds_against_new_parent_without_force():
    pub,calls=probe(b'{}\n');original=pub.api;attempts=[]
    def racing(method,path,body=None):
        if method=='PATCH':
            attempts.append(body)
            if len(attempts)==1:raise RuntimeError('reference changed')
        if method=='GET' and path.startswith('git/ref/') and attempts:return {'object':{'sha':'other-parent'}}
        if method=='GET' and path=='git/commits/other-parent':return {'tree':{'sha':'base'}}
        return original(method,path,body)
    pub.api=racing
    assert pub.publish_files({'B/progress.json':b'{}\n'},'test')=='candidate'
    assert len(attempts)==2 and all(x['force'] is False for x in attempts)
