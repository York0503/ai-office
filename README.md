# AI 辦公室

一間由 Claude agent 組成的軟體公司，加上一個看得到「誰派了誰、每個人在做什麼」的遊戲風監控畫面。設計成在 Claude App 的 **Code → 雲端對話**裡用，Mac 關機也能跑。

## 組織

老闆（主對話）→ 7 個部門主管 → 組長 → 員工，一共 45 個角色。

| 部門 | 主管 | 底下 |
|---|---|---|
| 老闆室 | 專案經理 | |
| 產品部 | 產品總監 | 需求分析師、使用者研究員、市場研究員 |
| 設計部 | 設計總監 | UX 設計師、UI 設計師 |
| 研發部 | 技術長 | 首席架構師、前端組（組長＋Web、行動 App）、後端組（組長＋API、資料庫、整合）、裝置整合組（組長＋IoT、機器人） |
| 數據與 AI 部 | AI 長 | AI 研究員、資料分析師、MLOps、機器學習組（組長＋資料、模型、評估）、LLM 應用組（組長＋提示詞、RAG、Agent） |
| 平台部 | 平台主管 | DevOps 工程師、資安工程師 |
| 品保部 | 品保經理 | 審查員、測試工程師、紅隊、查核員 |
| 內容部 | 內容總監 | 技術文件寫手、文案寫手、翻譯 |

- 老闆的工作規則在 `CLAUDE.md`。
- 每個角色的性格、職責、權限在 `.claude/agents/*.md`。主管只能派自己的部屬；負責檢查的角色只能看、不能改檔案。
- 最深是「老闆 → 技術長 → 組長 → 工程師」，剛好是 Claude Code 預設的三層上限。

## 檔案

```
CLAUDE.md                      老闆的工作規則
.claude/agents/                44 個部門主管、組長、員工
.claude/settings.json          hooks（每個動作都回報）＋ 打開思考摘要
.claude/hooks/office_hook.py   把事件送到監控後台；失敗會安靜跳過，不影響工作
.claude/office.json            監控後台網址（ingest_url）
office/                        監控後台（Cloudflare Worker）和畫面
.github/workflows/             推到 main 時自動部署監控後台
```

## 第一次設定

1. **Cloudflare**：註冊免費帳號，打開一次 Workers & Pages 設定好你的 `workers.dev` 子網域。記下 Account ID，再到 My Profile → API Tokens 用「Edit Cloudflare Workers」範本建立一組 API Token。
2. **兩組密碼**：自己產生兩串 30 字以上的隨機英數字，一組叫 INGEST_TOKEN（hooks 送事件用），一組叫 VIEW_TOKEN（看畫面用）。
3. **GitHub Secrets**：這個 repo → Settings → Secrets and variables → Actions，新增四個：
   `CLOUDFLARE_API_TOKEN`、`CLOUDFLARE_ACCOUNT_ID`、`OFFICE_INGEST_TOKEN`、`OFFICE_VIEW_TOKEN`。
4. **部署**：Actions → 部署監控後台 → Run workflow。跑完在紀錄裡找到網址，像 `https://ai-office.你的子網域.workers.dev`。
5. **填網址**：把 `.claude/office.json` 的 `ingest_url` 改成 `https://ai-office.你的子網域.workers.dev/ingest`，commit 到 main。
6. **雲端環境金鑰**：在 claude.ai/code 編輯你的雲端環境，在 Network secrets 新增一筆：主機填 `ai-office.你的子網域.workers.dev`，Header 名稱 `Authorization`、前綴 `Bearer`、值填 INGEST_TOKEN。金鑰會在請求離開雲端機器後才加上去，雲端對話本身看不到它。

## 每次使用

1. 手機打開 Claude App → Code → 開新的雲端對話，選這個 repo，交代事情。
2. 用瀏覽器打開 `https://ai-office.你的子網域.workers.dev/?k=你的VIEW_TOKEN`（第一次之後會記住，可以加到主畫面）。
3. 畫面有三頁：**辦公室**（照部門看誰在動）、**派工樹**（誰派了誰）、**紀錄**（每個動作，可搜尋）。點任何人可以看他接到的任務、動作、思考摘要和交回的成果。

## 要知道的事

- **用量**：部門越多、工作越大，叫動的人越多。雲端對話的用量算在你的 Claude 方案額度裡。老闆會先判斷大小，小事自己做。
- **思考**：官方的 hooks 不提供思考內容。這裡開了 `showThinkingSummaries`，並試著從對話紀錄檔讀出「思考摘要」送到畫面；紀錄檔格式不是公開規格，讀不到時畫面就不會有思考。原始完整思考任何方式都拿不到。
- **隱私**：畫面會存你的指令、檔名、指令輸出（每個欄位截到 1500 字以內），放在你自己的 Cloudflare 帳號，保留 14 天。看畫面要 VIEW_TOKEN。
- **其他 repo 也要用**：把 `CLAUDE.md` 和 `.claude/` 整個複製過去即可。
- **想調整角色**：直接改 `.claude/agents/` 裡的檔案，或在對話裡請 Claude 幫你改。

## 在自己電腦上測監控後台

```bash
cd office
npm install
printf 'INGEST_TOKEN=test\nVIEW_TOKEN=test\n' > .dev.vars
npx wrangler dev
# 先打開 http://127.0.0.1:8787/?k=test 登入，再打開 http://127.0.0.1:8787/?demo=1 可以看示範
```
