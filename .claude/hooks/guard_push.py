#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公開工具專案的守門員。

在公開的工具專案（預設：專案名稱叫 ai-office）裡，Claude 要 git push 或開 PR 時，
檢查這次要推的檔案；只要有「工具以外的檔案」（工作成果），就擋下來。
工具檔案的範圍：config/office.example.json 的 guard.tool_paths。
專案名稱：guard.tool_repo（環境變數 OFFICE_TOOL_REPO），可以寫 "名稱" 或 "帳號/名稱"。
"""
import json
import os
import pathlib
import re
import subprocess
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import office_config as oc  # noqa: E402

PUSH_RX = re.compile(r"\bgit\b[^\n;&|]*\bpush\b|\bgh\s+pr\s+(?:create|merge)\b|\bgh\s+api\b[^\n]*\bcontents/")


def git(args, cwd):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or f"git {' '.join(args)} failed")
    return r.stdout.strip()


def files_to_push(cwd):
    for ref in ("origin/HEAD", "origin/main", "origin/master"):
        try:
            base = git(["merge-base", "HEAD", ref], cwd)
            out = git(["diff", "--name-only", f"{base}..HEAD"], cwd)
            return [x for x in out.splitlines() if x]
        except Exception:
            continue
    # 遠端還沒有任何分支：檢查所有沒推過的 commit
    out = git(["log", "--name-only", "--pretty=format:", "HEAD", "--not", "--remotes"], cwd)
    return sorted({x for x in out.splitlines() if x})


def deny(reason, cfg, inp):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}, ensure_ascii=False))
    oc.post_events(cfg, [{"hook_event_name": "PushBlocked", "session_id": inp.get("session_id"),
                          "agent_id": inp.get("agent_id"), "agent_type": inp.get("agent_type"),
                          "reason": reason[:400], "ts": int(time.time() * 1000)}], wait=False)


def main():
    raw = sys.stdin.read()
    inp = json.loads(raw) if raw.strip() else {}
    if inp.get("tool_name") != "Bash":
        return
    cmd = (inp.get("tool_input") or {}).get("command") or ""
    if not PUSH_RX.search(cmd):
        return
    cfg = oc.load()
    guard = cfg.get("guard", {})
    cwd = inp.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    try:
        slug = oc.repo_slug_from_url(git(["remote", "get-url", "origin"], cwd))
    except Exception:
        return  # 不是 git 專案或沒有 origin，不是我們要守的地方
    if not oc.is_tool_repo(slug, guard.get("tool_repo")):
        return
    try:
        files = files_to_push(cwd)
    except Exception as e:
        deny(f"這是公開的工具專案（{slug}），但無法確認這次要推哪些檔案（{e}），為了安全先擋下。"
             "請確認只有工具檔案後由使用者手動推送。", cfg, inp)
        return
    bad = [f for f in files if not oc.path_allowed(f, guard.get("tool_paths") or [])]
    sensitive = [f for f in files if oc.is_sensitive_path(f, allow_templates=True)]
    if bad or sensitive:
        both = list(dict.fromkeys(sensitive + bad))
        listed = "、".join(both[:10]) + ("…" if len(both) > 10 else "")
        deny(f"這是公開的工具專案（{slug}），這次要推的檔案裡有工具以外的東西或敏感檔案：{listed}。"
             "工作成果請放到私人的工作專案（用 Use this template 從工具專案產生的那個），不要推到這裡。"
             "如果你是在改工具本身，請把這些檔案移出這次的 commit。", cfg, inp)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
