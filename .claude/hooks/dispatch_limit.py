#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每輪派工上限。

- UserPromptSubmit：使用者每交代一次（新的一輪），計數歸零。
- PreToolUse（Agent）：每派一個人算一人次；超過上限就擋下，並告訴 Claude 先整合手上的成果或問使用者。
上限：limits.max_dispatch_per_round（環境變數 OFFICE_MAX_DISPATCH），0 代表不設上限。
"""
import fcntl
import hashlib
import json
import pathlib
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import office_config as oc  # noqa: E402


def main():
    raw = sys.stdin.read()
    inp = json.loads(raw) if raw.strip() else {}
    ev = inp.get("hook_event_name")
    sid = inp.get("session_id") or "unknown"
    cfg = oc.load()
    try:
        limit = int(cfg.get("limits", {}).get("max_dispatch_per_round") or 0)
    except (TypeError, ValueError):
        limit = 0

    key = hashlib.sha1(sid.encode()).hexdigest()[:16]
    state_path = pathlib.Path(f"/tmp/ai-office-dispatch-{key}.json")
    with open(f"/tmp/ai-office-dispatch-{key}.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            state = json.loads(state_path.read_text())
        except Exception:
            state = {"count": 0}

        if ev == "UserPromptSubmit":
            if not inp.get("agent_id"):
                state_path.write_text(json.dumps({"count": 0, "since": int(time.time())}))
            return

        if ev != "PreToolUse" or inp.get("tool_name") not in ("Agent", "Task") or limit <= 0:
            return

        if state.get("count", 0) >= limit:
            ti = inp.get("tool_input") or {}
            reason = (f"本輪已經派工 {state.get('count', 0)} 人次，達到上限 {limit}，這次派工被擋下。"
                      "請先整合手上已有的成果交回；如果真的需要更多人手，交回時說明原因，"
                      "由老闆用按鈕問使用者要不要繼續（使用者回覆後算新的一輪，計數會歸零）。"
                      "上限可以在 config/office.json 的 limits.max_dispatch_per_round 或環境變數 OFFICE_MAX_DISPATCH 調整。")
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                     "permissionDecision": "deny",
                                                     "permissionDecisionReason": reason}}, ensure_ascii=False))
            oc.post_events(cfg, [{"hook_event_name": "DispatchBlocked", "session_id": sid,
                                  "agent_id": inp.get("agent_id"), "agent_type": inp.get("agent_type"),
                                  "tool_name": inp.get("tool_name"),
                                  "tool_input": {"subagent_type": ti.get("subagent_type"),
                                                 "description": ti.get("description")},
                                  "limit": limit, "count": state.get("count", 0),
                                  "ts": int(time.time() * 1000)}], wait=False)
            return

        state["count"] = state.get("count", 0) + 1
        state_path.write_text(json.dumps(state))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # 計數壞掉時不擋工作
    sys.exit(0)
