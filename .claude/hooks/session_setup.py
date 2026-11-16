#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""對話開始時，把 commit 前的金鑰檢查（.githooks/pre-commit）接上。安靜執行，失敗也不影響工作。"""
import os
import pathlib
import subprocess
import sys

root = pathlib.Path(os.environ.get("CLAUDE_PROJECT_DIR") or pathlib.Path(__file__).resolve().parents[2])
try:
    if (root / ".githooks" / "pre-commit").exists() and (root / ".git").exists():
        cur = subprocess.run(["git", "config", "--get", "core.hooksPath"], cwd=root,
                             capture_output=True, text=True).stdout.strip()
        if cur != ".githooks":
            subprocess.run(["git", "config", "core.hooksPath", ".githooks"], cwd=root,
                           capture_output=True, timeout=10)
except Exception:
    pass
sys.exit(0)
