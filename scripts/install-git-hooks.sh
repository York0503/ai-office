#!/bin/sh
# 在自己的電腦上接上 commit 前的金鑰檢查（雲端對話會自動接上）
cd "$(git rev-parse --show-toplevel)" && git config core.hooksPath .githooks && echo "已啟用 commit 前的金鑰檢查"
