# 設定 / Configuration

所有私人和可調整的設定都在這個資料夾。**只有 `office.example.json` 和這份說明會上傳**，其他檔案都被 `.gitignore` 擋住。

All private and adjustable settings live here. **Only `office.example.json` and this README are committed**; everything else in this folder is gitignored.

## 怎麼用 / How to use

```bash
cp config/office.example.json config/office.json   # 填你的真實設定 / fill in your real values
```

程式讀設定的順序：**環境變數 → `config/office.json` → `config/office.example.json`**。
雲端對話是從 GitHub 複製專案，看不到 `office.json`，所以雲端要用的值請放在 claude.ai/code 雲端環境的設定裡。

Lookup order: **environment variables → `config/office.json` → `config/office.example.json`**. Cloud sessions clone from GitHub and can't see `office.json`, so put cloud values in your cloud environment settings.

## 每個設定放哪裡 / Where each setting goes

| 設定 Setting | `office.json` | 雲端 Cloud | GitHub Secrets | 用途 Purpose |
|---|---|---|---|---|
| `monitor.ingest_url` | ✓ | 環境變數 `OFFICE_INGEST_URL` | | 監控後台網址（結尾 `/ingest`）/ monitor ingest URL |
| `monitor.ingest_token` | ✓ | Network secret（Authorization: Bearer …） | `OFFICE_INGEST_TOKEN` | hooks 送事件用的密碼 / token for sending events |
| `monitor.view_token` | ✓ | | `OFFICE_VIEW_TOKEN` | 看監控畫面的密碼 / password for the dashboard |
| `monitor.send_thinking` | ✓ | 環境變數 `OFFICE_SEND_THINKING` | | 要不要送思考摘要（實驗）/ send thinking summaries (experimental) |
| `cloudflare.account_id` | ✓ | | `CLOUDFLARE_ACCOUNT_ID` | 在自己電腦部署用 / for local deploys |
| `cloudflare.api_token` | ✓ | | `CLOUDFLARE_API_TOKEN` | 在自己電腦部署用 / for local deploys |
| `limits.max_dispatch_per_round` | ✓ | 環境變數 `OFFICE_MAX_DISPATCH` | | 每輪派工上限，0 = 不限 / per-round dispatch cap, 0 = none |
| `guard.tool_repo` | ✓ | 環境變數 `OFFICE_TOOL_REPO` | | 公開工具專案的名稱 / name of the public tool repo |
| `guard.tool_paths` | 範本 template | | | 公開專案允許的檔案 / files allowed in the public repo |
| `sync.upstream_repo` | 範本 template | Repository variable `OFFICE_UPSTREAM_REPO` | | 私人專案要從哪裡同步工具 / where the private repo syncs the tool from |
