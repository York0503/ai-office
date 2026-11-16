#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公開工具專案的檔案範圍檢查（GitHub Action 用）。

  python3 scripts/check_public_paths.py changed.txt
列出不屬於工具範圍（config/office.example.json 的 guard.tool_paths）的檔案；有的話以 1 結束。
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / ".claude" / "hooks"))
import office_config as oc  # noqa: E402


def main(path):
    files = [x.strip() for x in pathlib.Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]
    patterns = oc.load().get("guard", {}).get("tool_paths") or []
    bad = [f for f in files if not oc.path_allowed(f, patterns)]
    if bad:
        print("⛔ 這是公開的工具專案，但這次推上來的檔案裡有工具以外的東西：")
        for f in bad[:50]:
            print("  - " + f)
        print("工作成果請放到私人的工作專案。如果這些真的是工具的一部分，請把路徑加進 config/office.example.json 的 guard.tool_paths。")
        return 1
    print(f"✓ 全部 {len(files)} 個檔案都在工具範圍內")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
