# AI 辦公室 · AI Office

> **English summary** — A software company made of Claude Code subagents (a boss, a project manager, 7 department heads, 5 team leads and 31 staff, 45 roles in total, each with a role-fitting personality), plus a pixel-art live dashboard that shows who dispatched whom and every action they take. Built for Claude Code **cloud sessions** started from the Claude mobile app, with a Cloudflare Worker backend. A hook enforces the chain of command (heads can only dispatch their own people) and caps dispatches per round. Secrets never live in the repo (`config/office.json` is gitignored; cloud values go in your cloud environment's variables and network secrets), outgoing events are scrubbed for keys, and a guard hook plus a GitHub Action stop your work output from landing in this public repo — do real work in a private copy. Agent prompts are in Traditional Chinese; the dashboard and setup guide switch between Chinese and English. See [CHANGELOG.md](CHANGELOG.md) for what changed and why. MIT licensed.

一間由 Claude agent 組成的軟體公司，加上一個看得到「誰派了誰、每個人在做什麼」的遊戲風監控畫面。設計成在 Claude App 的 **Code → 雲端對話**裡用，電腦關機也能跑。監控畫面和設定說明都可以切換中文／English。

## 組織

老闆（主對話）→ 專案經理和 7 個部門主管 → 組長 → 員工，一共 45 個角色：老闆 1、專案經理 1、部門主管 7、組長 5、員工 31。

| 部門 | 主管 | 底下 |
|---|---|---|
| 老闆室 | 專案經理（直屬老闆） | |
| 產品部 | 產品總監 | 需求分析師、使用者研究員、市場研究員 |
| 設計部 | 設計總監 | UX 設計師、UI 設計師 |
| 研發部 | 技術長 | 首席架構師、前端組（前端組長＋Web 前端工程師、行動 App 工程師）、後端組（後端組長＋API 工程師、資料庫工程師、整合工程師）、裝置整合組（裝置組長＋IoT 工程師、機器人工程師） |
| 數據與 AI 部 | AI 長 | AI 研究員、資料分析師、MLOps 工程師、機器學習組（ML 組長＋資料工程師、模型工程師、模型評估工程師）、LLM 應用組（LLM 組長＋提示詞工程師、RAG 工程師、Agent 工程師） |
| 平台部 | 平台主管 | DevOps 工程師、資安工程師 |
| 品保部 | 品保經理 | 審查員、測試工程師、紅隊、查核員 |
| 內容部 | 內容總監 | 技術文件寫手、文案寫手、翻譯 |

- 老闆的工作規則在 `CLAUDE.md`；每個角色的性格、職責、權限在 `.claude/agents/*.md`。
- **階層由 hook 強制**：老闆只派專案經理和部門主管，主管和組長只能派自己的部屬，派錯人會被 `dispatch_guard.py` 擋下。
- **只能看、不能改檔案的 8 個角色**：需求分析師、使用者研究員、市場研究員、AI 研究員、資安工程師、審查員、紅隊、查核員。其他角色（包括測試工程師，他要寫測試檔）都可以改檔案。
- 最深是「老闆 → 技術長 → 組長 → 工程師」，也就是主對話底下三層，剛好是 Claude Code 預設的巢狀上限（可以用 `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` 調整）。

## 工具專案和工作專案分開

這個專案是**公開的工具**。真正交代工作請在**私人的工作專案**裡做，成果才不會被公開。

**如果你是這個專案的擁有者：**
1. 開一個空的**私人**專案（名稱不要叫 `ai-office`，例如 `ai-office-work`），加進 Claude GitHub App 的權限，再把這個專案的內容推過去；或者在這個專案的 Settings 勾選 **Template repository**，用 **Use this template** 建立私人專案。
2. 之後在 Claude App 開雲端對話時，選那個私人專案。
3. 工具有更新時，到私人專案的 **Actions → 同步工具更新 → Run workflow**，它會開一個 PR 讓你看過再合併。員工設定請在工具專案這邊改。

**如果你想自己用一套：** 先 fork 這個專案（或用 Use this template）建立你自己的公開工具專案，名稱用 `ai-office`；如果改了名稱，記得設定 `guard.tool_repo`。之後照上面的步驟建立你的私人工作專案，並把 `sync.upstream_repo` 改成你自己的工具專案。

## 檔案

```
CLAUDE.md                        老闆的工作規則
CHANGELOG.md                     修改紀錄：每次修了什麼、為什麼、怎麼確認
.claude/agents/                  專案經理、7 個部門主管、5 個組長、31 個員工
.claude/settings.json            hooks 設定 ＋ 打開思考摘要
.claude/hooks/office_hook.py     把事件送到監控後台（送出前遮罩金鑰，附思考摘要診斷）
.claude/hooks/dispatch_guard.py  派工守門：階層檢查＋每輪派工上限
.claude/hooks/guard_push.py      公開工具專案的守門員
.claude/hooks/session_setup.py   對話開始時接上 commit 前的金鑰檢查
.claude/hooks/office_config.py   共用：讀設定、遮罩、組織表、檔案範圍
config/office.example.json       設定範本（會上傳）
config/office.json               你的真實設定（不會上傳）
office/                          監控後台（Cloudflare Worker）和畫面
scripts/                         金鑰檢查、檔案範圍檢查、同步工具
.githooks/pre-commit             commit 前的金鑰檢查
.github/workflows/               部署、公開專案守門、同步工具
```

## 設定

所有私人和可調整的設定都在 `config/`，說明見 [config/README.md](config/README.md)。讀取順序是**環境變數 → `config/office.json` → `config/office.example.json`**。雲端對話看不到 `config/office.json`，所以雲端要用的值放在 claude.ai/code 的雲端環境設定裡。

### 第一次設定

1. **Cloudflare**：註冊免費帳號後，**先打開一次 Workers & Pages**。第一次打開會自動建立你的 `workers.dev` 子網域，沒有它部署會失敗。記下 Account ID。
2. **Cloudflare API Token**：建立 Account API token，權限只勾 **Developer Platform → Workers → Admin**。第一次部署要建立新的 Worker，需要 Admin；部署成功後可以改成 Editor。不要選「Full account and zone access」。
3. **兩組密碼**：產生兩串 30 字以上的隨機英數字（例如在電腦上執行 `openssl rand -hex 24`，或用手冊頁面上的按鈕）：INGEST_TOKEN（hooks 送事件用）和 VIEW_TOKEN（看畫面用）。
4. **GitHub Secrets**（工具專案）：Settings → Secrets and variables → Actions，新增 `CLOUDFLARE_API_TOKEN`、`CLOUDFLARE_ACCOUNT_ID`、`OFFICE_INGEST_TOKEN`、`OFFICE_VIEW_TOKEN`。
5. **部署**：Actions → 部署監控後台 → Run workflow。跑完打開這次的紀錄，在「部署到 Cloudflare Workers」那一步找到 `https://ai-office.你的子網域.workers.dev`。
6. **雲端環境**：在 claude.ai/code 開新對話的畫面，點訊息框下面的環境選單（☁）→ **New environment**，建一個專用的 `ai-office` 環境：
   - 環境變數：`OFFICE_INGEST_URL=https://ai-office.你的子網域.workers.dev/ingest`
   - 建好之後再打開它的設定，在 **Network secrets** 新增一筆：Allowed websites 填 `ai-office.你的子網域.workers.dev`，Header `Authorization`、前綴 `Bearer`、值是 INGEST_TOKEN
   - 想改派工上限：環境變數加 `OFFICE_MAX_DISPATCH=數字`（0 = 不限）
7. **工作專案**：照上一段建立私人專案。

### 每次使用

1. 手機打開 Claude App → Code → 開新的雲端對話：環境（☁）選 **ai-office**，Repo 選你的**私人工作專案**，交代事情。
2. 瀏覽器打開 `https://ai-office.你的子網域.workers.dev/?k=你的VIEW_TOKEN`（第一次之後會記住，可以加到主畫面）。右上角可以切換中文／English。
3. 畫面有三頁：**辦公室**（照部門看誰在動）、**派工樹**（誰派了誰）、**紀錄**（每個動作，可搜尋）。點任何人可以看他接到的任務、動作、思考摘要和交回的成果。

## 保護機制

| 保護 | 做什麼 |
|---|---|
| 設定不上傳 | `config/` 底下除了範本和說明，全部被 `.gitignore` 擋住；`.env`、金鑰檔也一樣 |
| commit 前掃金鑰 | `.githooks/pre-commit` 發現像金鑰的字串或敏感檔案就擋下。雲端對話會自動接上；自己電腦執行 `sh scripts/install-git-hooks.sh` |
| 送出前遮罩 | 監控事件裡看起來像金鑰、密碼、token 的字串換成 `***`；`.env`、金鑰檔的內容完全不送 |
| 階層守門 | 老闆只派專案經理和部門主管，主管和組長只能派自己的部屬，派錯就擋下 |
| 每輪派工上限 | 一輪派超過上限（預設 30 人次）就擋下，請老闆先整合或問你；你回覆後計數歸零，部屬交回結果不會歸零 |
| 守門 hook | 在公開工具專案裡，Claude 要推工具以外的檔案時直接擋下 |
| 守門 Action | 公開專案每次有人推上來，檢查檔案範圍和金鑰；有問題就失敗，GitHub 會照你的通知設定寄失敗通知 |

## 要知道的事

- **用量**：部門越多、工作越大，叫動的人越多。雲端對話的用量算在你的 Claude 方案額度裡。
- **思考**：官方 hooks 不提供思考內容。這裡開了 `showThinkingSummaries`，並試著從對話紀錄檔讀出「思考摘要」；紀錄檔格式不是公開規格。紀錄頁的「診斷」事件會顯示找到幾段思考、其中幾段有內容，讀不到時可以從這裡查原因。原始完整思考任何方式都拿不到。
- **觀看密碼**：帶 `?k=` 的網址會留在瀏覽器紀錄裡，不要分享。外洩時改 GitHub Secret `OFFICE_VIEW_TOKEN` 再重新部署一次就換掉了。
- **隱私**：監控資料存在你自己的 Cloudflare 帳號，每個欄位截到 1500 字以內，保留 14 天。
- **網頁上的惡意指令**：查資料的員工可能讀到藏了指令的網頁。負責研究和檢查的 8 個角色只能看、不能改；但工程師和組長也能上網，而且可以改檔案，所以要靠守門 hook 和品保把關，風險不是零。
- **守門的限制**：守門 hook 只攔得住 Claude；守門 Action 是事後提醒。真正的保證是：工作只在私人專案裡做。
- **免費額度**：監控畫面有動時每 1.5 秒更新、沒動時放慢到 6 秒、看不到時停止，避免用掉 Cloudflare 免費方案的請求數。

## 修改紀錄

所有修正都記在 [CHANGELOG.md](CHANGELOG.md)，每一筆寫清楚：**問題、怎麼發現、原因、修法、改了哪些檔案、怎麼確認修好**。之後如果又出錯，先從這裡找最近改過哪裡。改工具時請照同樣格式記一筆。

## 在自己電腦上測監控後台

```bash
cd office
npm install
printf 'INGEST_TOKEN=test\nVIEW_TOKEN=test\n' > .dev.vars
npx wrangler dev
# 先打開 http://127.0.0.1:8787/?k=test 登入，再打開 http://127.0.0.1:8787/?demo=1 看示範
```

## 授權

[MIT](LICENSE)
