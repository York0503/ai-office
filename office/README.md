# 監控後台 / Monitor backend

Cloudflare Worker + Durable Object（SQLite）。推到 main 時由 `.github/workflows/deploy-office.yml` 自動部署。

| 路徑 Path | 用途 Purpose |
|---|---|
| `POST /ingest` | hooks 送事件進來，需要 `Authorization: Bearer <INGEST_TOKEN>` |
| `GET /` | 監控畫面；第一次用 `/?k=<VIEW_TOKEN>` 打開，之後記在 cookie |
| `GET /?demo=1` | 示範模式（登入後） |
| `GET /api/sessions`、`/api/events` | 畫面用的資料 |

兩個密碼用 Worker secret 設定：`INGEST_TOKEN`、`VIEW_TOKEN`。資料保留 14 天。

部署後的網址格式：`https://ai-office.<你的子網域>.workers.dev`（第一次部署前要先在 Cloudflare 打開一次 Workers & Pages，才會建立 workers.dev 子網域）。
