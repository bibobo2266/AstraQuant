
const repo="bibobo2266/AstraQuant",branch="research/trading-plan-r1";
function unwrap(r){
 if(r.isError)throw Error(JSON.stringify(r.structuredContent||r.content));
 const s=r.structuredContent;
 if(s && s.encoding)return s;
 if(s && typeof s.content==="string")return JSON.parse(s.content);
 if(s)return s;
 throw Error("GitHub connector response absent");
}
let parent=null,served=0;
while(true){
 let poll=await tools.exec_command({cmd:"python - <<'PY'\nfrom pathlib import Path\nimport time\np=Path('/workspace/scratch/678885238d72/github_checkpoint_queue')\nfor i in range(10):\n pending=sorted(f for f in p.glob('*.request.json') if not f.with_name(f.name.replace('.request.json','.response.json')).exists())\n if pending:\n  f=pending[0];print(f.stem.replace('.request',''));q=__import__('json').loads(f.read_text())\n  if q['method']=='POST' and q['path']=='git/trees':\n   import hashlib\n   for e in q['body']['tree']:\n    b=e.pop('content').encode();e['content_bytes']=len(b);e['expected_blob']=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\\0'+b).hexdigest();e['uploaded']= (p/('blob-'+e['expected_blob']+'.saved')).exists()\n  print(__import__('json').dumps(q));break\n time.sleep(1)\nPY",max_output_tokens:250000,yield_time_ms:10000});
 if(poll.session_id)poll=await tools.write_stdin({session_id:poll.session_id,chars:"",yield_time_ms:1000,max_output_tokens:250000});
 if(poll.session_id)throw Error("queue poll did not finish");
 
 if(!poll.output.trim()){
 const check=await tools.exec_command({cmd:"python - <<'PY'\nimport json,fcntl\nfrom pathlib import Path\nroot=Path('/workspace/scratch/678885238d72/AstraQuant-checkout/results/trading_plan_r1/s3_live_20261011')\nlive=[]\nfor rnd in ['A','B']:\n f=(root/rnd/'execution.lock').open('a')\n try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)\n except BlockingIOError:live.append(rnd)\n f.close()\nprint(json.dumps({'live_rounds':live,'progress':{r:{'execution_id':d['execution_id'],'cells':{c:{k:v.get(k) for k in ['status','completed','current_date','external_checkpoint']} for c,v in d['cells'].items()}} for r in ['A','B'] for d in [json.loads((root/r/'progress.json').read_text())]}}))\nPY",max_output_tokens:10000});
 const observed=JSON.parse(check.output);
 store("latest_actual_progress",observed);
 if(!observed.live_rounds.length){
  notify({event:"worker_stopped",progress:observed.progress});
  await tools.mcp__codex_apps__github_add_comment_to_issue({repo_full_name:repo,pr_number:6,comment:"Sol-E｜連線服務實讀兩輪執行鎖均釋放，worker已退出；實際progress："+JSON.stringify(observed.progress)+"。若未達COMPLETE則保留保存日，不能當作全期完成；後續依具體log錯誤恢復。"});
  break;
 }
 continue;
 }
 const first=poll.output.indexOf("\n"),id=poll.output.slice(0,first).trim();
 const q=JSON.parse(poll.output.slice(first+1));
 let response;
 try{
 let r;
 if(q.method==="GET" && q.path.startsWith("contents/")){
 const [p,query]=q.path.slice(9).split("?ref=");
 const f=await tools.mcp__codex_apps__github_fetch_file({repository_full_name:repo,ref:query,path:decodeURIComponent(p)});
 if(f.isError)throw Error(JSON.stringify(f));
 const c=f.structuredContent.content;
 const chars="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";let b="";
 for(let i=0;i<c.length;i+=3){const a=c.charCodeAt(i),v=i+1<c.length?c.charCodeAt(i+1):0,w=i+2<c.length?c.charCodeAt(i+2):0;if(a>127||v>127||w>127)throw Error("transport content not ASCII");const n=(a<<16)|(v<<8)|w;b+=chars[(n>>18)&63]+chars[(n>>12)&63]+(i+1<c.length?chars[(n>>6)&63]:"=")+(i+2<c.length?chars[n&63]:"=");}
 r={structuredContent:{encoding:"base64",content:b}};
 }else if(q.method==="GET"){
  r=await tools.mcp__codex_apps__github_fetch({url:"https://api.github.com/repos/"+repo+"/"+q.path});
 }else if(q.method==="POST" && q.path==="git/trees"){
  
 const entries=[],cache=load("bridge_blob_cache")||{};
 for(let ix=0;ix<q.body.tree.length;ix++){
  const e=q.body.tree[ix];
  let blob=e.uploaded?e.expected_blob:cache[e.expected_blob];
  if(!blob){
   let content="";
   for(let offset=0;offset<e.content_bytes;offset+=16000){
    const part=await tools.exec_command({cmd:"python - <<'PY'\nimport json\nfrom pathlib import Path\nq=json.loads(Path('/workspace/scratch/678885238d72/github_checkpoint_queue/"+id+".request.json').read_text())\ns=q['body']['tree']["+ix+"]['content']\nprint(json.dumps(s["+offset+":"+Math.min(offset+16000,e.content_bytes)+"]))\nPY",max_output_tokens:20000});
    content+=JSON.parse(part.output);
   }
   const br=unwrap(await tools.mcp__codex_apps__github_create_blob({repository_full_name:repo,encoding:"utf-8",content}));
   if(br.sha!==e.expected_blob)throw Error("connector blob SHA mismatch "+e.path);
   blob=br.sha;cache[blob]=blob;store("bridge_blob_cache",cache);
 await tools.apply_patch("*** Begin Patch\n*** Add File: /workspace/scratch/678885238d72/github_checkpoint_queue/blob-"+blob+".saved\n+"+blob+"\n*** End Patch");
  }
  entries.push({path:e.path,mode:e.mode,type:e.type,sha:blob});
 }
 r=await tools.mcp__codex_apps__github_create_tree({repository_full_name:repo,base_tree_sha:q.body.base_tree,tree_elements:entries});
 }else if(q.method==="POST" && q.path==="git/commits"){
  r=await tools.mcp__codex_apps__github_create_commit({repository_full_name:repo,parent_sha:q.body.parents[0],tree_sha:q.body.tree,message:q.body.message});
 }else if(q.method==="PATCH" && q.path==="git/refs/heads/"+branch){
  r=await tools.mcp__codex_apps__github_update_ref({repository_full_name:repo,branch_name:branch,sha:q.body.sha,expected_sha:parent,force:false});
 }else if(q.method==="POST" && q.path==="issues/6/comments"){
  r=await tools.mcp__codex_apps__github_add_comment_to_issue({repo_full_name:repo,pr_number:6,comment:q.body.body});
 }else throw Error("Unsupported connector request "+q.method+" "+q.path);
 let result=unwrap(r);
 if(q.method==="GET"&&q.path==="git/ref/heads/"+branch)parent=result.object.sha;
 if(q.method==="POST"&&q.path==="git/trees"&&!result.tree)result.tree=[];
 response={result};
 served++;
 if(q.method==="PATCH")notify({event:"remote_commit_written",commit:q.body.sha,served});
 }catch(e){response={error:String(e)};notify({event:"connector_error",error:String(e)});}
 await tools.apply_patch("*** Begin Patch\n*** Add File: /workspace/scratch/678885238d72/github_checkpoint_queue/"+id+".response.json\n+"+JSON.stringify(response)+"\n*** End Patch");
}
