# 監控後台 / Monitor backend

Cloudflare Worker + Durable Object（SQLite）。推到 main 時由 `.github/workflows/deploy-office.yml` 自動部署。

| 路徑 Path | 用途 Purpose |
|---|---|
| `POST /ingest` | hooks 送事件進來，需要 `Authorization: Bearer <INGEST_TOKEN>` |
| `GET /` | 監控畫面；第一次用 `/?k=<VIEW_TOKEN>` 打開，之後記在 cookie |
| `GET /?demo=1` | 示範模式（登入後） |
| `GET /api/sessions`、`/api/events` | 畫面用的資料 |

兩個密碼用 Worker secret 設定：`INGEST_TOKEN`、`VIEW_TOKEN`。資料保留 14 天。
