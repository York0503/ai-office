#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 辦公室：把 Claude Code 的 hook 事件送到監控後台。

- 以 async 方式執行，不會拖慢 Claude；任何錯誤都安靜跳過（exit 0、不輸出）。
- 送出前會遮罩看起來像金鑰、密碼、token 的字串；.env、金鑰檔這類檔案的內容完全不送。
- 沒設定監控網址（monitor.ingest_url / OFFICE_INGEST_URL）就什麼都不送。
"""
import fcntl
import glob
import hashlib
import json
import os
import pathlib
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import office_config as oc  # noqa: E402

MAX_STR = 1500
MAX_EVENT_BYTES = 24000
SKIP_KEYS = {"transcript_path"}
HIDDEN = "（敏感檔案，內容不送出）"


def debug(msg):
    if os.environ.get("OFFICE_DEBUG"):
        try:
            with open("/tmp/ai-office-debug.log", "a", encoding="utf-8") as f:
                f.write(time.strftime("%H:%M:%S ") + msg + "\n")
        except Exception:
            pass


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


def hide_sensitive_files(ev):
    """讀寫敏感檔案時，把檔案內容整個拿掉，只留檔名。"""
    ti = ev.get("tool_input")
    if not isinstance(ti, dict):
        return ev
    path = ti.get("file_path") or ti.get("notebook_path") or ti.get("path")
    if path and oc.is_sensitive_path(path):
        for k in ("content", "new_string", "old_string", "edits", "new_source"):
            if k in ti:
                ti[k] = HIDDEN
        if "tool_response" in ev:
            ev["tool_response"] = HIDDEN
        ev["sensitive_file"] = True
    return ev


def build_event(inp, secrets):
    ev = {k: v for k, v in inp.items() if k not in SKIP_KEYS}
    ev = hide_sensitive_files(ev)
    ev = oc.mask_obj(ev, secrets)
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


def collect_thinking(inp, secrets):
    """回傳 (思考事件, 診斷)。診斷是累計數字：找到幾個紀錄檔、幾段思考、幾段有內容。"""
    tp = inp.get("transcript_path")
    sid = inp.get("session_id") or "unknown"
    if not tp:
        return [], {"transcript_exists": False, "files_found": 0, "thinking_total": 0,
                    "thinking_nonempty": 0, "thinking_redacted": 0, "note": "hook 沒有收到 transcript_path"}
    main = pathlib.Path(tp)
    files = {str(main): None}
    for pattern in (main.parent / main.stem / "subagents" / "*.jsonl", main.parent / main.stem / "*.jsonl"):
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
        return [], None
    out = []
    try:
        try:
            state = json.loads(state_path.read_text())
        except Exception:
            state = {}
        diag = state.get("_diag") or {"thinking_total": 0, "thinking_nonempty": 0, "thinking_redacted": 0}
        diag["transcript_exists"] = main.exists()
        diag["files_found"] = sum(1 for f in files if os.path.exists(f))
        diag["transcript_dir"] = sorted(os.listdir(main.parent))[:15] if main.parent.exists() else []
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
            state[str(path)] = off + end + 1
            for line in chunk[:end].splitlines():
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                msg = obj.get("message")
                if obj.get("type") != "assistant" or not isinstance(msg, dict):
                    continue
                for block in msg.get("content") or []:
                    if isinstance(block, dict) and block.get("type") == "redacted_thinking":
                        diag["thinking_total"] += 1
                        diag["thinking_redacted"] += 1
                    if isinstance(block, dict) and block.get("type") == "thinking":
                        text = (block.get("thinking") or "").strip()
                        diag["thinking_total"] += 1
                        if text:
                            diag["thinking_nonempty"] += 1
                            out.append({
                                "hook_event_name": "Thinking",
                                "session_id": sid,
                                "agent_id": obj.get("agentId") or file_agent,
                                "text": trim(oc.mask_text(text, secrets), 4000),
                                "ts": int(time.time() * 1000),
                            })
        state["_diag"] = {k: diag[k] for k in ("thinking_total", "thinking_nonempty", "thinking_redacted")}
        state_path.write_text(json.dumps(state))
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()
    return out[:30], diag


def main():
    cfg = oc.load()
    if not (cfg.get("monitor", {}).get("ingest_url") or "").strip():
        return
    raw = sys.stdin.read()
    inp = json.loads(raw) if raw.strip() else {}
    secrets = oc.known_secret_values(cfg)
    events = [build_event(inp, secrets)]
    if cfg.get("monitor", {}).get("send_thinking", True):
        try:
            thoughts, diag = collect_thinking(inp, secrets)
            events += thoughts
            # 每次有人交回結果或整輪結束時，送一筆累計的診斷，方便查思考摘要為什麼沒出現
            if diag and inp.get("hook_event_name") in ("SubagentStop", "Stop", "SessionStart"):
                events.append(dict(diag, hook_event_name="Diag", session_id=inp.get("session_id"),
                                   remote=bool(os.environ.get("CLAUDE_CODE_REMOTE")),
                                   ts=int(time.time() * 1000)))
        except Exception as e:
            debug(f"thinking: {e!r}")
    oc.post_events(cfg, events, wait=True)
    debug(f"sent {len(events)} {inp.get('hook_event_name')}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        debug(f"error: {e!r}")
    sys.exit(0)
