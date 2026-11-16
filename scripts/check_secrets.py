#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上傳前的金鑰檢查。

  python3 scripts/check_secrets.py --staged            # commit 前（.githooks/pre-commit 會自動跑）
  python3 scripts/check_secrets.py --files-from x.txt  # GitHub Action 用
  python3 scripts/check_secrets.py 檔案1 檔案2 ...
發現敏感檔案或像金鑰的字串就以 1 結束，並列出位置（不會印出金鑰本身）。
"""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / ".claude" / "hooks"))
import office_config as oc  # noqa: E402

MAX_BYTES = 1_000_000


def staged_files():
    out = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
                         cwd=ROOT, capture_output=True, text=True).stdout
    return [x for x in out.splitlines() if x]


def read(path, staged):
    if staged:
        r = subprocess.run(["git", "show", f":{path}"], cwd=ROOT, capture_output=True)
        return r.stdout if r.returncode == 0 else b""
    p = ROOT / path
    return p.read_bytes() if p.is_file() else b""


def main(argv):
    staged = "--staged" in argv
    if staged:
        files = staged_files()
    elif "--files-from" in argv:
        src = argv[argv.index("--files-from") + 1]
        files = [x.strip() for x in pathlib.Path(src).read_text(encoding="utf-8").splitlines() if x.strip()]
    else:
        files = [a for a in argv if not a.startswith("--")]

    problems = []
    for f in files:
        if oc.is_sensitive_path(f, allow_templates=True):
            problems.append(f"{f}：這是敏感檔案（例如 .env、金鑰檔、config/office.json），不能上傳")
            continue
        data = read(f, staged)
        if not data or len(data) > MAX_BYTES or b"\0" in data[:4096]:
            continue
        text = data.decode("utf-8", errors="ignore")
        for label, line in oc.find_secrets(text):
            problems.append(f"{f}:{line}：看起來像{label}")

    if problems:
        print("⛔ 上傳前檢查發現可能的金鑰或敏感檔案：")
        for p in problems[:50]:
            print("  - " + p)
        print("請把金鑰移到 config/office.json（不會上傳）或環境變數。如果確定是誤判，可以用 git commit --no-verify 跳過。")
        return 1
    print(f"✓ 金鑰檢查通過（{len(files)} 個檔案）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
