#!/usr/bin/env python3
"""把 minervini_picks 的 out/night_session.md 過濾成可公開的版本。

為什麼要過濾：AstraQuant 是 public repo。原檔裡的迴歸斜率 0.514、R² 0.559、
殘差標準差 0.373%、方向命中率分級、價差分級的 n 與平均報酬，都是 owner 自己
用私有資料驗出來的研究常數。這些常數不隨每日變動，寫在 Cowork 的 prompt 裡
即可，不需要每天從公開檔案讀。公開檔只放當日點位。

保留：資料日、收盤／漲跌／高低／成交量、價差點數、一口賺賠、警示旗標。
移除：所有歷史統計常數、開盤參考整段、盤中延續性註記。

輸入  source/out/night_session.md
輸出  out/night_session.md
"""

import datetime
import pathlib
import re
import sys
import zoneinfo

SRC = pathlib.Path("source/out/night_session.md")
DST = pathlib.Path("out/night_session.md")

# 這些一出現就代表進入研究常數區，之後的內容一律不要（旗標除外）。
STOP_MARKERS = ("**開盤參考**", "關於盤中延續性")
# 單行封鎖：價差分級的歷史統計。
DROP_PREFIXES = ("歷史上落在",)


def main() -> int:
    if not SRC.exists():
        print(f"找不到 {SRC}", file=sys.stderr)
        return 1

    text = SRC.read_text(encoding="utf-8")
    DST.parent.mkdir(parents=True, exist_ok=True)

    # 未取得：原封不動轉出，但不轉內部除錯步驟（那是給 owner 看的）。
    if "夜盤資料未取得" in text:
        head = [ln for ln in text.splitlines() if not ln.startswith("> 1.")
                and not ln.startswith("> 2.") and not ln.startswith("> 3.")
                and not ln.startswith("> 檢查順序")]
        DST.write_text("\n".join(head).rstrip() + "\n", encoding="utf-8")
        print("轉出：未取得")
        return 0

    # 來源檔可能是昨天成功、今天失敗留下的殘檔——它長得完全像今天的。
    # 上游有同樣的檢查，但公開檔是第二層，不能信任上游一定跑過。
    m = re.search(r"資料日 (\d{4}-\d{2}-\d{2})", text)
    today = datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Taipei")).date()
    if not m or datetime.date.fromisoformat(m.group(1)) != today:
        got = m.group(1) if m else "無法辨識"
        DST.write_text(
            "## 台指夜盤\n\n**夜盤資料未取得。**\n\n"
            f"原因：來源檔資料日為 {got}，不等於今天（{today}）。\n\n"
            "> 本節無資料時不提供任何點位或方向。\n", encoding="utf-8")
        print(f"轉出：未取得（來源檔 {got}，今天 {today}）")
        return 0

    out, stopped = [], False
    for line in text.splitlines():
        s = line.strip()
        if any(m in s for m in STOP_MARKERS):
            stopped = True
        if stopped:
            # 停止之後只補收警示旗標，其餘全丟。
            if s.startswith("> ⚠️"):
                out.append(line)
            continue
        if any(s.startswith(p) for p in DROP_PREFIXES):
            continue
        if s == "---":
            continue
        out.append(line)

    # 收斂連續空行
    cleaned, blank = [], False
    for line in out:
        if not line.strip():
            if blank:
                continue
            blank = True
        else:
            blank = False
        cleaned.append(line)

    body = "\n".join(cleaned).rstrip()
    if "夜盤 05:00 收盤" not in body:
        print("過濾後找不到收盤價，拒絕輸出殘缺檔", file=sys.stderr)
        return 1

    DST.write_text(body + "\n", encoding="utf-8")
    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
