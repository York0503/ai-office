#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 辦公室：把 Claude Code 的 hook 事件送到監控後台。

- 由 .claude/settings.json 以 async 方式呼叫，不會拖慢 Claude。
- 任何錯誤都安靜跳過（exit 0、不輸出任何東西），監控掛了也不影響工作。
- 後台網址：環境變數 OFFICE_INGEST_URL，或 .claude/office.json 的 ingest_url。
- 驗證：雲端版由「network secret」在請求離開 VM 後自動加上 Authorization；
  在自己電腦上跑時，可以用環境變數 OFFICE_INGEST_TOKEN。
"""
import fcntl
import glob
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

MAX_STR = 1500          # 單一字串欄位最多保留幾個字
MAX_EVENT_BYTES = 24000 # 單一事件 JSON 上限
SKIP_KEYS = {"transcript_path"}  # 本機路徑，對畫面沒用


def debug(msg):
    if os.environ.get("OFFICE_DEBUG"):
        try:
            with open("/tmp/ai-office-debug.log", "a", encoding="utf-8") as f:
                f.write(time.strftime("%H:%M:%S ") + msg + "\n")
        except Exception:
            pass


def load_cfg():
    proj = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    cfg = {}
    try:
        cfg = json.loads((pathlib.Path(proj) / ".claude" / "office.json").read_text(encoding="utf-8"))
    except Exception:
        pass
    url = (os.environ.get("OFFICE_INGEST_URL") or cfg.get("ingest_url") or "").strip()
    token = (os.environ.get("OFFICE_INGEST_TOKEN") or "").strip()
    return url, token, cfg


def trim(v, n=MAX_STR):
    if isinstance(v, str):
        return v if len(v) <= n else v[:n] + f"…（截斷，原本 {len(v)} 字）"
    if isinstance(v, list):
        out = [trim(x, n) for x in v[:40]]
        if len(v) > 40:
            out.append(f"…（還有 {len(v) - 40} 項）")
        return out
    if isinstance(v, dict):
        return {k: trim(x, n) for k, x in list(v.items())[:60]}
    return v


def build_event(inp):
    ev = {k: v for k, v in inp.items() if k not in SKIP_KEYS}
    ev["ts"] = int(time.time() * 1000)
    for n in (MAX_STR, 400, 120):
        out = trim(ev, n)
        if len(json.dumps(out, ensure_ascii=False).encode()) <= MAX_EVENT_BYTES:
            return out
    return {k: out.get(k) for k in ("session_id", "hook_event_name", "agent_id", "agent_type",
                                    "tool_name", "tool_use_id", "ts")}


# ---------- 思考摘要（實驗功能）----------
# 官方 hooks 不提供思考內容。開了 showThinkingSummaries 之後，摘要可能會寫進對話紀錄檔，
# 這裡試著把新出現的摘要讀出來一起送。紀錄檔格式不是公開規格，讀不到就算了。

def _agent_from_file(path):
    stem = pathlib.Path(path).stem
    return stem[6:] if stem.startswith("agent-") else stem


def collect_thinking(inp, cfg):
    if cfg.get("send_thinking") is False:
        return []
    tp = inp.get("transcript_path")
    sid = inp.get("session_id") or "unknown"
    if not tp:
        return []
    main = pathlib.Path(tp)
    files = {str(main): None}
    for pattern in (main.parent / main.stem / "subagents" / "*.jsonl",
                    main.parent / main.stem / "*.jsonl"):
        for f in glob.glob(str(pattern)):
            files.setdefault(f, _agent_from_file(f))
    atp = inp.get("agent_transcript_path")
    if atp:
        files.setdefault(atp, inp.get("agent_id") or _agent_from_file(atp))

    key = hashlib.sha1(sid.encode()).hexdigest()[:16]
    state_path = pathlib.Path(f"/tmp/ai-office-{key}.json")
    lock = open(f"/tmp/ai-office-{key}.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return []  # 別的 hook 正在讀，下一個事件再補
    out = []
    try:
        try:
            state = json.loads(state_path.read_text())
        except Exception:
            state = {}
        for path, file_agent in files.items():
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            off = state.get(path, 0)
            if size <= off:
                continue
            with open(path, "rb") as f:
                f.seek(off)
                chunk = f.read(min(size - off, 4_000_000))
            end = chunk.rfind(b"\n")
            if end < 0:
                continue
            state[path] = off + end + 1
            for line in chunk[:end].splitlines():
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                msg = obj.get("message")
                if obj.get("type") != "assistant" or not isinstance(msg, dict):
                    continue
                for block in msg.get("content") or []:
                    if isinstance(block, dict) and block.get("type") == "thinking":
                        text = (block.get("thinking") or "").strip()
                        if text:
                            out.append({
                                "hook_event_name": "Thinking",
                                "session_id": sid,
                                "agent_id": obj.get("agentId") or file_agent,
                                "text": trim(text, 4000),
                                "ts": int(time.time() * 1000),
                            })
        state_path.write_text(json.dumps(state))
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()
    return out[:30]


def post(url, token, payload):
    data = json.dumps(payload, ensure_ascii=False).encode()
    args = ["curl", "-sS", "-m", "8", "-o", "/dev/null", "-w", "%{http_code}",
            "-X", "POST", "-H", "Content-Type: application/json"]
    if token:
        args += ["-H", f"Authorization: Bearer {token}"]
    try:
        r = subprocess.run(args + ["--data-binary", "@-", url], input=data,
                           capture_output=True, timeout=10)
        debug(f"curl {r.stdout.decode(errors='ignore')} {r.stderr.decode(errors='ignore')[:200]}")
        return
    except FileNotFoundError:
        pass
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=8) as resp:
        debug(f"urllib {resp.status}")


def main():
    url, token, cfg = load_cfg()
    if not url:
        return
    raw = sys.stdin.read()
    inp = json.loads(raw) if raw.strip() else {}
    events = [build_event(inp)]
    try:
        events += collect_thinking(inp, cfg)
    except Exception as e:
        debug(f"thinking: {e!r}")
    post(url, token, {"events": events})


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # 監控壞掉也不能影響工作
        debug(f"error: {e!r}")
    sys.exit(0)
