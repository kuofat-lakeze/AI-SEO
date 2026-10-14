# 08・Web App 設計：包棟訂房平台（以被 AI 引用為目標）

目標只有一句話：**當有人問 AI「宜蘭包棟」「台中包棟」「20人包棟」，AI 引用我們。**
所以這個 app 有三種使用者，第三種是設計的主角：

| 使用者 | 要什麼 | 設計重點 |
|---|---|---|
| 旅客 | 找到合適的包棟、看到價格、訂房 | 篩選、比較表、空房 |
| 民宿主 | 上架、管理價格與空房、接訂單 | 後台填事實表、價格日曆 |
| **AI 與爬蟲** | 一個網址回答一個問題、資料結構化、新鮮、抓得到 | 題型頁、JSON-LD、llms.txt、SSR |

原型在 `app/`，用示範資料跑 `python3 app/build_site.py` 就能看到所有頁面長什麼樣。

## 一、整體架構

```
                ┌──────────────── 後台（民宿主 / 平台審核）────────────────┐
                │ 事實表表單 → 價格日曆 → 空房日曆 → 審核 → 發布          │
                └──────────────────────────┬───────────────────────────┘
                                           ▼
┌────────────────────────── 資料層 PostgreSQL ──────────────────────────┐
│ villas  rooms  amenities  price_rules  availability  reviews  bookings │
│ regions  ── 每晚重算 ──▶ region_stats / size_stats（間數、中位價、空房）  │
└──────────────────────────┬────────────────────────────────────────────┘
                           ▼
┌──────────────── 內容層（SSR / ISR，一題型一頁）────────────────┐
│ /宜蘭包棟/  /台中包棟/  /20人包棟/  /宜蘭包棟/20人/  /包棟/泳池/      │
│ /民宿/<slug>/   /包棟價格/   /報告/2026-Q4/                       │
│ 每頁：一句話結論 → 比較表 → 怎麼選 → FAQ → JSON-LD → 交叉連結    │
└──────────────────────────┬────────────────────────────────────────┘
                           ▼
┌──────────────── AI 可讀層 ────────────────┐   ┌──── 訂房層 ────┐
│ robots.txt  llms.txt  sitemap(lastmod)     │   │ 詢價 / 訂房      │
│ /api/public/villas.json  MCP server（第三期）│   │ LINE 通知 / 金流 │
└───────────────────────────────────────────┘   └─────────────────┘
                           ▼
┌──────────────── 量測層 ────────────────┐
│ access log → lab/classify.py（被讀到）    │
│ 題庫 → lab/citation_check.py（被引用）    │
│ GA4 AI 導流 → 訂房轉換（被點擊）           │
│ 後台儀表板：每個關鍵字三層指標的週趨勢       │
└────────────────────────────────────────┘
```

## 二、資料模型：事實表是整個平台的核心

AI 回答的每一句都是「地區 × 人數 × 設施 × 價格 × 距離」，資料模型就照這五個維度設計，而且每個欄位都要**可驗證、有更新時間**。

```sql
villas
  id, slug, name, name_aliases[]          -- 別名：跟食尚玩家、Google 地圖上的名稱對得上
  region_id, district, address, lat, lng
  capacity_base, capacity_max, extra_person_fee
  room_count, bed_summary                 -- "2 雙人 3 四人"
  checkin_time, checkout_time
  pet_allowed, pet_rule
  description_short (60 字內，給 AI 摘要用)
  verified_at, verified_by                -- 平台驗證日期，頁面上要顯示
  updated_at

rooms          villa_id, name, bed_type, capacity, has_bath
amenities      villa_id, kind (pool|ktv|mahjong|bbq|kitchen|elevator|parking|...), detail, seasonal
price_rules    villa_id, day_type (weekday|saturday|holiday|cny), price, valid_from, valid_to
availability   villa_id, date, status (open|booked|closed), price_override
distances      villa_id, poi (羅東夜市|礁溪轉運站|...), minutes_by_car
reviews        villa_id, source (platform|google), rating, count, latest_at
media          villa_id, url, alt, is_cover

regions        id, name (宜蘭|冬山|礁溪|台中|台南...), parent_id, intro_short
region_stats   region_id, size_bucket (10|15|20|30), villa_count,
               median_weekday, median_saturday, median_holiday,
               open_count_next_weekend, computed_at        -- 每晚重算
size_stats     size_bucket, region_id NULL=全台, 同上

bookings       villa_id, checkin, checkout, guests, status, source (web|line|agent)
```

幾個設計上的堅持：

- **價格一定是數字**。後台不允許「請來電」。沒填價格的民宿不會出現在題型頁的比較表。
- **人數是兩個數字**：基本人數與最多人數。「20人包棟」頁要能精確篩 `capacity_max >= 20`。
- **別名欄位**。AI 會比對「135會館」在不同來源是不是同一間，別名讓實體對得上。
- **verified_at 顯示在頁面上**。「平台於 2026-10-14 驗證」是 AI 判斷可信度的訊號。
- **stats 表每晚重算**，題型頁的「一句話結論」從這裡來，不是手寫。

## 三、頁面與路由：一題型一頁

| 路由 | 回答的問題 | 資料來源 |
|---|---|---|
| `/` | 全台包棟總覽、各地區間數與中位價 | region_stats |
| `/{地區}包棟/` | 該地區有哪些、各區差異、價格 | villas × region_stats |
| `/{N}人包棟/` | 全台哪裡能住 N 人、各地價格 | villas (capacity_max ≥ N) × size_stats |
| `/{地區}包棟/{N}人/` | 交集 | 同上 |
| `/包棟/{設施}/` | 有泳池 / KTV / 寵物的包棟 | amenities |
| `/民宿/{slug}/` | 一間民宿的完整事實表 | villas 全表 |
| `/包棟價格/` | 全台包棟行情：地區 × 人數 × 平假日的中位數 | stats |
| `/報告/{季}/` | 季度報告：價格、熱門設施、旺季 | stats 歷史 |
| `/llms.txt` `/sitemap.xml` `/robots.txt` | 給 AI 的導覽 | 自動產生 |
| `/api/public/villas.json` | 開放資料，給 Agent 與整理站 | villas |

**題型頁的版型**（每一頁都一樣，`app/templates/` 有原型）：

1. **H1 = 關鍵字本身**：「台中包棟民宿」
2. **一句話結論**：由 stats 自動組句，含間數、中位價、更新日期
3. **比較表**：民宿、區、人數、房數、平日、假日、泳池、KTV、麻將、烤肉、寵物、距主要地標。HTML `<table>`，可排序但預設就是完整渲染
4. **怎麼選**：3 到 5 條，從 stats 算出來的規則（例：有泳池的中位數高 5,000）
5. **FAQ**：6 到 10 題，問題用使用者原話，答案帶數字
6. **交叉連結**：地區 ↔ 人數 ↔ 設施
7. **JSON-LD**：`ItemList` + `FAQPage` + `BreadcrumbList`
8. **更新時間與驗證說明**：「資料由平台驗證，最後更新 2026-10-14」

**民宿頁**：H1 = 民宿名稱 + 地區，事實表（同欄位）、價格表、空房日曆、設施清單、距離表、評價、FAQ、`LodgingBusiness` + `Offer` + `AggregateRating` JSON-LD，底部「在本平台訂房」。

## 四、AI 可讀性規則（每頁上線前的檢查清單）

- [ ] 首屏 HTML 裡就有結論、表格、FAQ，**不靠 JavaScript 載入**（SSR 或靜態）
- [ ] 表格是 `<table>`，價格是數字，不是圖片或「洽詢」
- [ ] JSON-LD 與頁面內容一致（AI 會比對）
- [ ] `<title>` 與 H1 含關鍵字，`meta description` 是那句一句話結論
- [ ] 頁面上有「更新日期」與「驗證日期」
- [ ] 民宿名稱與 Google 地圖、其他整理站一致
- [ ] `sitemap.xml` 的 lastmod 跟 `updated_at` 連動
- [ ] `llms.txt` 列出所有題型頁，一句話說明每頁回答什麼
- [ ] robots 放行 OAI-SearchBot、ChatGPT-User、PerplexityBot、Perplexity-User、Claude-SearchBot、Claude-User、Applebot、Googlebot、Bingbot、GPTBot、ClaudeBot
- [ ] Cloudflare 關閉「封鎖 AI 爬蟲」，保留速率限制
- [ ] 首屏 HTML < 200 KB，TTFB < 500 ms（AI 抓取有逾時）
- [ ] 每頁一個 canonical，同一間民宿只有一個網址

## 五、後台流程：資料品質就是被引用的機率

**民宿主上架**（表單，不是自由文字）：
1. 基本資料與別名、地址（自動帶經緯度）
2. 人數（基本 / 最多 / 加人費）、房數與床型
3. 價格表：平日 / 週六 / 連假 / 春節，四個數字必填
4. 設施勾選 + 細節（泳池：戶外、開放月份）
5. 距離表：平台預設該地區 3 到 5 個地標，自動算車程
6. 寵物政策、入退房時間
7. 照片（alt 文字必填）

**平台審核**：核對 Google 地圖、照片、價格合理性 → `verified_at` 蓋章 → 發布 → 題型頁下次重建就納入。

**維護機制**：
- 價格 90 天沒更新 → 提醒民宿主；180 天 → 從比較表降權並標「價格可能已變動」
- 空房日曆用 iCal 同步 Airbnb / Booking，或民宿主手動
- 每晚 02:00：重算 stats → 重建題型頁 → 更新 sitemap lastmod

## 六、量測層：內建在後台的「AI 可見度」頁

把這個 repo 的三支工具接進後台排程：

| 排程 | 做什麼 | 後台顯示 |
|---|---|---|
| 每天 | `classify.py` 跑前一天的 access log | 各 AI 爬蟲抓了哪些題型頁、民宿頁；有沒有 403 |
| 每週一 | `citation_check.py` 跑全部題庫（`make_queries.py` 產生） | 每個關鍵字的提及率、引用率、聲量佔比、來源結構的週趨勢 |
| 每天 | GA4 Data API 拉 AI 來源工作階段 | AI 導流、到達頁、訂房轉換 |

後台「AI 可見度」頁：一個關鍵字一列，三層指標各一欄，點進去看曲線。這一頁也是給合作民宿看的報表：「你的民宿這週在 AI 回答裡被提到 N 次」，是平台對民宿主的價值主張。

## 七、技術選型（建議）

| 層 | 建議 | 理由 |
|---|---|---|
| 前端 + SSR | **Next.js（App Router）** 或 **Astro** | 題型頁要 SSR / ISR 輸出完整 HTML；Astro 更輕，Next.js 生態更大 |
| 資料庫 | **PostgreSQL**（Supabase 或 Neon） | 關聯清楚，stats 用 SQL 重算 |
| ORM | Prisma 或 Drizzle | 跟上面搭配 |
| 後台 | Next.js 同專案的 `/admin`，或 Payload CMS | 表單為主，不需要另起專案 |
| 部署 | Vercel 或 Cloudflare Pages | **注意 Cloudflare 預設會擋 AI 爬蟲，要手動關** |
| Log | 部署平台的 log drain → S3 / R2 → `classify.py` | 沒有 log 就沒有第二層指標 |
| 排程 | Vercel Cron / GitHub Actions | 每晚重算、每週題庫 |
| 訂房通知 | LINE Messaging API | 台灣民宿主習慣 |
| 金流（第二期） | 藍新 / 綠界 | 先做詢價，再做線上付款 |
| Agent 介面（第三期） | MCP server（查空房、報價、下訂） | AAIO：讓 ChatGPT / Claude 直接幫旅客查與訂 |

## 八、分期

**第一期（1 到 2 個月）：讓 AI 有東西可引用**
- 資料模型 + 民宿主後台表單 + 審核
- 題型頁產生器：先做台中、20人、30人、台南、宜蘭五組（依 07 的優先順序）
- 民宿頁、價格行情頁
- robots、llms.txt、sitemap、JSON-LD
- 詢價表單 + LINE 通知（先不做金流）
- 接上量測層，跑第一次基準
- 目標：每個地區 15 間以上有完整事實表

**第二期（3 到 4 個月）：讓引用發生、讓訂房成交**
- 空房日曆與 iCal 同步、線上付款
- 季度報告頁 + 媒體投放
- 後台 AI 可見度頁對民宿主開放
- 擴地區：礁溪、墾丁、南投、花蓮、台東

**第三期（5 到 6 個月）：讓 Agent 直接用**
- `/api/public/villas.json` 開放資料
- MCP server：`search_villas`、`get_availability`、`request_booking`
- 平台內嵌 AI 助理（用自家結構化資料回答，順便收集真人問法回灌題庫）

## 九、原型怎麼看

```bash
python3 app/build_site.py          # 用 app/data/villas.json 的示範資料產出 app/site/
open app/site/台中包棟/index.html
```

原型是靜態產生器，示範的是**頁面結構、JSON-LD、llms.txt、sitemap 長什麼樣**，不是正式程式碼。正式版把 `build_site.py` 的邏輯換成 Next.js 的頁面元件，資料來源換成 PostgreSQL，就是第一期。
