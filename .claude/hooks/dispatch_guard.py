#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""派工守門：階層檢查＋每輪派工上限。

- 階層：主管和組長只能派自己的部屬；老闆只能派專案經理和部門主管（內建的 Explore 等外包不限）。
  依據 office/src/roster.json。關掉：guard.enforce_hierarchy = false。
  （subagent 設定檔裡的 Agent(類型) 寫法只對主對話有效，所以改由這個 hook 強制。）
- 上限：使用者每交代一次算新的一輪，計數歸零；部屬交回結果這類系統訊息不算新的一輪。
  每派一個人算一人次，超過 limits.max_dispatch_per_round（OFFICE_MAX_DISPATCH）就擋下；0 = 不限。
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


def deny(reason, cfg, inp, kind, extra=None):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}, ensure_ascii=False))
    ti = inp.get("tool_input") or {}
    ev = {"hook_event_name": "DispatchBlocked", "session_id": inp.get("session_id"),
          "agent_id": inp.get("agent_id"), "agent_type": inp.get("agent_type"),
          "tool_name": inp.get("tool_name"), "block_kind": kind, "reason": reason[:300],
          "tool_input": {"subagent_type": ti.get("subagent_type"), "description": ti.get("description")},
          "ts": int(time.time() * 1000)}
    ev.update(extra or {})
    oc.post_events(cfg, [ev], wait=False)


def hierarchy_problem(caller, target, roles, allowed):
    """回傳擋下的理由；沒問題回傳 None。"""
    if target not in roles:  # 內建或外部的 agent：只有老闆可以用
        if caller == "boss" or caller not in roles:
            return None
        return f"你是{roles[caller]['zh']}，只能派自己的部屬，不能派組織外的 agent（{target}）。"
    ok = allowed.get(caller, set())
    if target in ok:
        return None
    if caller == "boss":
        heads = "、".join(roles[s]["zh"] for s in sorted(ok))
        return f"老闆只直接派專案經理和部門主管（{heads}），{roles[target]['zh']}要交給他的主管去派。"
    if caller not in roles:
        return None
    if not ok:
        return f"{roles[caller]['zh']}沒有部屬，不能派工，請自己完成。"
    mine = "、".join(roles[s]["zh"] for s in sorted(ok))
    return f"你是{roles[caller]['zh']}，只能派自己的部屬：{mine}。{roles[target]['zh']}不歸你管。"


def main():
    raw = sys.stdin.read()
    inp = json.loads(raw) if raw.strip() else {}
    ev = inp.get("hook_event_name")
    sid = inp.get("session_id") or "unknown"
    cfg = oc.load()

    key = hashlib.sha1(sid.encode()).hexdigest()[:16]
    state_path = pathlib.Path(f"/tmp/ai-office-dispatch-{key}.json")
    with open(f"/tmp/ai-office-dispatch-{key}.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            state = json.loads(state_path.read_text())
        except Exception:
            state = {"count": 0}

        if ev == "UserPromptSubmit":
            if not inp.get("agent_id") and not oc.is_system_prompt(inp.get("prompt")):
                state_path.write_text(json.dumps({"count": 0, "since": int(time.time())}))
            return

        if ev != "PreToolUse" or inp.get("tool_name") not in ("Agent", "Task"):
            return
        target = (inp.get("tool_input") or {}).get("subagent_type") or "general-purpose"
        caller = inp.get("agent_type") if inp.get("agent_id") else "boss"

        if cfg.get("guard", {}).get("enforce_hierarchy", True):
            roles, allowed = oc.load_roster()
            problem = hierarchy_problem(caller or "unknown", target, roles, allowed) if roles else None
            if problem:
                deny(problem + "請改派正確的人，或把這件事交回給上一層。", cfg, inp, "hierarchy")
                return

        try:
            limit = int(cfg.get("limits", {}).get("max_dispatch_per_round") or 0)
        except (TypeError, ValueError):
            limit = 0
        if limit > 0 and state.get("count", 0) >= limit:
            deny(f"本輪已經派工 {state.get('count', 0)} 人次，達到上限 {limit}，這次派工被擋下。"
                 "請先整合手上已有的成果交回；如果真的需要更多人手，交回時說明原因，"
                 "由老闆用按鈕問使用者要不要繼續（使用者回覆後算新的一輪，計數會歸零）。"
                 "上限可以在 config/office.json 的 limits.max_dispatch_per_round 或環境變數 OFFICE_MAX_DISPATCH 調整。",
                 cfg, inp, "limit", {"limit": limit, "count": state.get("count", 0)})
            return
        state["count"] = state.get("count", 0) + 1
        state_path.write_text(json.dumps(state))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # 守門壞掉時不擋工作
    sys.exit(0)
