#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把上游工具專案的工具檔案同步到這個（私人工作）專案。

  python3 scripts/sync_tool.py <上游資料夾> <這個專案資料夾>
- 只動工具檔案（上游 config/office.example.json 的 guard.tool_paths，扣掉 sync.skip）。
- 上游刪掉的員工設定、hooks、監控程式，這邊也會刪掉；其他資料夾不會刪任何東西。
"""
import json
import pathlib
import shutil
import sys

DELETE_DIRS = (".claude/agents/", ".claude/hooks/", "office/src/")


def load_paths(up):
    cfg = json.loads((up / "config" / "office.example.json").read_text(encoding="utf-8"))
    return cfg["guard"]["tool_paths"], cfg.get("sync", {}).get("skip", [])


def allowed(rel, patterns):
    import fnmatch
    for pat in patterns:
        if pat.endswith("/**"):
            if rel.startswith(pat[:-3] + "/"):
                return True
        elif fnmatch.fnmatchcase(rel, pat):
            return True
    return False


def files_under(root):
    out = set()
    for p in root.rglob("*"):
        if p.is_file() and ".git" not in p.relative_to(root).parts and "node_modules" not in p.parts:
            out.add(p.relative_to(root).as_posix())
    return out


def main(up, here):
    up, here = pathlib.Path(up).resolve(), pathlib.Path(here).resolve()
    patterns, skip = load_paths(up)
    want = {f for f in files_under(up) if allowed(f, patterns) and not allowed(f, skip)}
    copied = 0
    for rel in sorted(want):
        src, dst = up / rel, here / rel
        if dst.exists() and dst.read_bytes() == src.read_bytes():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
        print("更新", rel)
    removed = 0
    for rel in sorted(files_under(here)):
        if rel.startswith(DELETE_DIRS) and rel not in want and allowed(rel, patterns):
            (here / rel).unlink()
            removed += 1
            print("刪除", rel)
    print(f"同步完成：更新 {copied} 個、刪除 {removed} 個")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
