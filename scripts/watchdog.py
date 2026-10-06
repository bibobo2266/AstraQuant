"""
AstraQuant 進度監看 — 只在真的有變動時才留言。

監看的是「事實」不是「自我回報」：branch head、PR head、issue 最新留言 ID。
CLAIMED 留言本身不算接工，所以另外檢查「宣告了分支但分支沒動」。

背景雜訊（夜盤排程、本腳本自己的 state commit）會被濾掉，
不然每半小時都會通知一次，通知就失去意義。
"""
import json
import os
import re
import base64
import datetime as dt
import urllib.request
import urllib.error

API = "https://api.github.com"
REPO = os.environ["GITHUB_REPOSITORY"]
TOK = os.environ["GH_TOKEN"]
ISSUE = os.environ.get("WATCH_ISSUE", "6")
STATE_PATH = "state/watchdog.json"
CLAIM_GRACE_MIN = 30                      # 留 CLAIMED 後多久沒 commit 就算未接工
IGNORE_MSG = ("watchdog:", "night session")   # main 上不算進度的自動 commit
TRACK_BRANCH = re.compile(r"^(sol|solb|main)")


def api(path, method="GET", data=None):
    req = urllib.request.Request(
        f"{API}/{path}", method=method,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Authorization": f"Bearer {TOK}",
                 "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r), r.status
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return json.loads(raw or b"{}"), e.code
        except Exception:
            return {"raw": raw.decode(errors="replace")}, e.code


def now():
    return dt.datetime.now(dt.timezone.utc)


def parse_ts(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=dt.timezone.utc)


def tpe(ts):
    return (ts + dt.timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")


# ---------------- 取現況 ----------------

def snapshot():
    out = {"branches": {}, "prs": {}, "last_comment": None}

    br, _ = api(f"repos/{REPO}/branches?per_page=100")
    for b in br if isinstance(br, list) else []:
        if TRACK_BRANCH.match(b["name"]):
            out["branches"][b["name"]] = b["commit"]["sha"]

    pr, _ = api(f"repos/{REPO}/pulls?state=open&per_page=50")
    for p in pr if isinstance(pr, list) else []:
        out["prs"][str(p["number"])] = {
            "sha": p["head"]["sha"], "draft": p["draft"], "title": p["title"]}

    cm = all_comments()
    if cm:
        out["last_comment"] = cm[-1]["id"]
    return out


def all_comments():
    """issue comments 端點不吃 sort/direction（實測回的是建立順序），
    所以直接翻頁取完，最後一則才是最新。"""
    out, page = [], 1
    while page <= 10:
        c, code = api(f"repos/{REPO}/issues/{ISSUE}/comments"
                      f"?per_page=100&page={page}")
        if code != 200 or not isinstance(c, list) or not c:
            break
        out += c
        if len(c) < 100:
            break
        page += 1
    return out


def commit_time(sha):
    c, code = api(f"repos/{REPO}/commits/{sha}")
    if code != 200:
        return None
    return parse_ts(c["commit"]["committer"]["date"].replace("+00:00", "Z"))


def real_main_commits(old_sha, new_sha):
    """main 上扣掉背景自動 commit 之後，還剩下的真正變動。"""
    if not old_sha or old_sha == new_sha:
        return []
    cp, code = api(f"repos/{REPO}/compare/{old_sha}...{new_sha}")
    if code != 200:
        return [f"（無法比對 {old_sha[:7]}..{new_sha[:7]}）"]
    keep = []
    for c in cp.get("commits", []):
        msg = c["commit"]["message"].splitlines()[0]
        if any(msg.lower().startswith(p) for p in IGNORE_MSG):
            continue
        keep.append(f"{c['sha'][:7]} {msg}")
    return keep


def stale_claims():
    """找出「留了 CLAIMED、但宣告的分支在寬限時間內沒有 commit」的情況。"""
    flags = []
    seen = set()
    for c in reversed(all_comments()[-20:]):
        body = c.get("body", "")
        if "status: CLAIMED" not in body:
            continue
        tid = re.search(r"task_id:\s*(\S+)", body)
        tid = tid.group(1) if tid else "UNKNOWN"
        if tid in seen:                       # 同一 task 只看最新那則
            continue
        seen.add(tid)
        age = (now() - parse_ts(c["created_at"])).total_seconds() / 60
        if age < CLAIM_GRACE_MIN:
            continue
        br = re.search(r"branch:\s*(\S+)", body)
        if not br:
            continue
        name = br.group(1)
        b, code = api(f"repos/{REPO}/branches/{name}")
        if code != 200:
            flags.append(f"{tid}：宣告分支 `{name}` 不存在"
                         f"（CLAIMED 已 {age:.0f} 分鐘）")
            continue
        t = commit_time(b["commit"]["sha"])
        if t and t < parse_ts(c["created_at"]):
            flags.append(f"{tid}：分支 `{name}` 自 CLAIMED 後無新 commit"
                         f"（已 {age:.0f} 分鐘，head {b['commit']['sha'][:7]}）")
    return flags


# ---------------- state ----------------

def read_state():
    d, code = api(f"repos/{REPO}/contents/{STATE_PATH}")
    if code != 200:
        return {}, None
    return json.loads(base64.b64decode(d["content"]).decode()), d["sha"]


def write_state(state, sha):
    body = {"message": "watchdog: state [skip ci]",
            "content": base64.b64encode(
                json.dumps(state, indent=1, ensure_ascii=False).encode()).decode()}
    if sha:
        body["sha"] = sha
    api(f"repos/{REPO}/contents/{STATE_PATH}", "PUT", body)


# ---------------- 主流程 ----------------

def main():
    old, sha = read_state()
    new = snapshot()
    lines = []

    main_new = new["branches"].get("main")
    hits = real_main_commits(old.get("branches", {}).get("main"), main_new)
    if hits:
        lines.append("**main 有新 commit**")
        lines += [f"- {h}" for h in hits]

    ob = old.get("branches", {})
    for name, s in sorted(new["branches"].items()):
        if name == "main":
            continue
        if name not in ob:
            lines.append(f"**新分支** `{name}` → {s[:7]}")
        elif ob[name] != s:
            lines.append(f"**分支更新** `{name}`：{ob[name][:7]} → {s[:7]}")
    for name in sorted(set(ob) - set(new["branches"])):
        if name != "main":
            lines.append(f"**分支消失** `{name}`")

    op = old.get("prs", {})
    for n, p in sorted(new["prs"].items(), key=lambda kv: int(kv[0])):
        if n not in op:
            lines.append(f"**新 PR** #{n}　{p['title']}　head {p['sha'][:7]}")
        elif op[n]["sha"] != p["sha"]:
            lines.append(f"**PR #{n} head 更新**："
                         f"{op[n]['sha'][:7]} → {p['sha'][:7]}")
        elif op[n].get("draft") and not p["draft"]:
            lines.append(f"**PR #{n} 由 Draft 轉為 Ready**")
    for n in sorted(set(op) - set(new["prs"]), key=int):
        lines.append(f"**PR #{n} 已關閉或合併**")

    if old.get("last_comment") and new["last_comment"] != old["last_comment"]:
        lines.append(f"**issue #{ISSUE} 有新留言**"
                     f"（最新 comment id {new['last_comment']}）")

    flags = stale_claims()
    prev_flags = old.get("flags", [])
    new_flags = [f for f in flags if f not in prev_flags]
    if new_flags:
        lines.append("**接工未確認**")
        lines += [f"- {f}" for f in new_flags]

    new["flags"] = flags
    new["checked_at"] = now().strftime("%Y-%m-%dT%H:%M:%SZ")

    if not lines:
        print("no change")
        if old:                      # 狀態沒變就不寫檔，少一次 commit
            return
        write_state(new, sha)
        return

    body = (f"actor: Watchdog\ntype: PROGRESS_DELTA\n"
            f"checked_at: {tpe(now())} +08:00\n\n"
            + "\n".join(lines)
            + "\n\n本留言由排程自動產生，只報事實變動，不代表驗收。")
    r, code = api(f"repos/{REPO}/issues/{ISSUE}/comments", "POST", {"body": body})
    print("comment", code, r.get("id"))
    write_state(new, sha)


if __name__ == "__main__":
    main()
