# AI SEO Lab：六大優化領域的量化環境

這個 repo 是一個可以「實際玩」的模擬環境，用來回答兩個問題：

1. 那張「六大優化領域 × 來了幾次 × 來訪者種類 × 來最多的」統計圖，**資料到底從哪裡來、怎麼算出來的**？
2. 幫企業做 AI SEO 時，**要怎麼出具一份自己做得到、而且能量化成果的 demo**？

不需要安裝任何套件，只要 Python 3。

```bash
./run.sh                 # 產生「優化前」「優化後」兩份模擬 log → 分類 → 產出儀表板
open output/dashboard.html
```

## 整個環節一張圖

```
 企業網站                                 誰來了                          對應領域
 ──────────────────────────────────────────────────────────────────────────────────
 Googlebot / Bingbot ...   ──抓──▶  搜尋索引 ──▶ 一般搜尋結果           SEO
                                           └──▶ AI Overview / Copilot   AIO / AEO（同一批爬蟲）
 GPTBot / ClaudeBot / Meta-ExternalAgent ──▶ 模型訓練資料               LLMO
 OAI-SearchBot / Applebot / PerplexityBot ─▶ 生成式搜尋的即時索引       GEO
 ChatGPT-User / Perplexity-User ──────────▶ 使用者提問當下來抓頁面      AEO（即時答案抓取）
 HeadlessChrome / MCP 工具 / python ───────▶ AI Agent 代替人操作        AEO（AAIO）
 AhrefsBot / facebookexternalhit ─────────▶ 工具與連結預覽               AEO（工具・預覽）
 真人（Referer = google / chatgpt / maps）─▶ 真的有人點進來             自然流量（成果）
 Google Business Profile 後台 ────────────▶ 地圖曝光 / 路線 / 來電        MEO
```

所有「爬蟲」那幾列，**資料來源只有一個：網站伺服器的 access log**（或 Cloudflare 這類 CDN 的 log）。
每一行 log 都有 User-Agent，把 User-Agent 對到爬蟲名稱、再對到領域，就能算出圖上的數字。
「自然流量」用 Referer 分來源；「MEO」要從 Google Business Profile 拿，不在 log 裡。

## 這個 repo 裡有什麼

| 路徑 | 用途 |
|---|---|
| `lab/bots.json` | **核心對照表**：User-Agent 特徵 → 平台 → 領域。真實專案就是維護這張表 |
| `lab/generate_logs.py` | 產生模擬 nginx access log，含 `baseline`（優化前）與 `optimized`（優化後）兩個情境 |
| `lab/classify.py` | 讀 log → 分類 → `stats.json`。**真實環境可以直接餵 `/var/log/nginx/access.log`** |
| `lab/report.py` | `stats.json` → 一頁式儀表板，排版對照原圖，另加前後對照、AI 導流、熱門頁面、被擋爬蟲 |
| `lab/citation_check.py` | **AI 引用追蹤**：拿題庫問 Claude / Perplexity / OpenAI 或貼手動回答，算引用率與聲量 |
| `lab/queries/` | 關鍵字題庫，`宜蘭包棟.json` 是範例 |
| `run.sh` | 一鍵跑完整條流程 |
| `templates/` | 交付給客戶的範本：`robots.txt`、`llms.txt`、nginx log 格式、Schema 範例 |
| `docs/` | 解說文件（見下） |
| `output/` | 產出物；`.log` 不進版控，`.json` 與 `dashboard.html` 有附一份範例 |

## 文件

1. [`docs/01-六大領域與爬蟲對照.md`](docs/01-六大領域與爬蟲對照.md)：每個領域代表什麼、哪些爬蟲算進去、為什麼 SEO 與 AIO 共用
2. [`docs/02-真實環境資料怎麼拿.md`](docs/02-真實環境資料怎麼拿.md)：nginx / Apache / Cloudflare / GA4 / Search Console / GBP 的接法，爬蟲驗證，常見坑
3. [`docs/03-量化成果與提案Demo.md`](docs/03-量化成果與提案Demo.md)：指標定義、before / after 怎麼做、給客戶的 demo 腳本、交付物清單
4. [`docs/04-動手玩.md`](docs/04-動手玩.md)：這個 lab 可以玩的幾個實驗
5. [`docs/05-關鍵字測試_宜蘭包棟.md`](docs/05-關鍵字測試_宜蘭包棟.md)：**實際測一組字怎麼做**，含 2026-10-14 的真實基準快照
6. [`docs/06-包棟訂房平台_讓AI引用的做法.md`](docs/06-包棟訂房平台_讓AI引用的做法.md)：做一個包棟訂房平台要怎麼讓 AI 引用，資料層、頁面樹、獨家資料、技術、站外、量測、進行順序

## 測一組關鍵字（例：宜蘭包棟）

```bash
# 零預算：自己問 ChatGPT / Perplexity / Gemini，把回答貼進 CSV
python3 lab/citation_check.py lab/queries/宜蘭包棟.json --backend manual --input answers.csv --platform ChatGPT
# 有 API：自動跑整份題庫
python3 lab/citation_check.py lab/queries/宜蘭包棟.json --backend anthropic
open output/citations/宜蘭包棟/report.html
```

算出引用率、提及率、誰的網站被引用、品牌聲量佔比。每週跑一次就是趨勢。

## 三分鐘看懂產出

跑完 `./run.sh` 之後，`output/dashboard.html` 上半部就是原圖的四列：

- **來了幾次**：各領域的爬蟲造訪次數，右邊的 `+224%` 之類是對照「優化前」的變化
- **來訪者種類**：有幾家平台來過（Anthropic、OpenAI、Apple…）
- **來最多的**：前四名平台與次數

下半部是給提案用的三張表：

- **優化前後對照**：每個領域的次數變化
- **AI 導流**：真人從 ChatGPT / Perplexity / Copilot 點進來的次數。**這是跟客戶談成果最重要的一張表**，爬蟲多只代表被讀到，導流才代表被引用、被點擊
- **AI 爬蟲最常抓的頁面 / 被阻擋的爬蟲**：決定要先優化哪些頁、要放行誰

## 從模擬走到真實客戶：三步

1. 拿到客戶的 access log（或 Cloudflare Logpush），`python3 lab/classify.py access.log* --out output/client.json`
2. 做優化（放行 AI 爬蟲、`llms.txt`、Schema、FAQ 結構、內容更新）
3. 一個月後再抓一次，`python3 lab/report.py 後.json --compare 前.json`，儀表板就是提案裡的成果頁
