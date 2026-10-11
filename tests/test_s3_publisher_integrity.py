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
        if method=='GET' and path=='git/trees/Btree':return {'tree':[{'path':'progress.json','type':'blob','sha':blob_sha}]}
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


@pytest.mark.parametrize('corrupt',['created_sha','blob_bytes','candidate_bytes'])
def test_metadata_corruption_never_moves_branch(corrupt):
    pub,calls=probe(b'{"completed":634}\n',corrupt)
    with pytest.raises(ValueError,match='mismatch'):
        pub.publish_files({'B/progress.json':b'{"completed":634}\n'},'test')
    assert not any(method=='PATCH' for method,_,_ in calls)
    assert pub.known=={}
