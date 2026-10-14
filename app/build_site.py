#!/usr/bin/env python3
"""
包棟訂房平台原型：靜態產生器。
從 data/villas.json 產出「一題型一頁」的所有頁面，示範 AI 會讀到的 HTML、JSON-LD、llms.txt、sitemap。

  python3 app/build_site.py
  open app/site/台中包棟/index.html

正式版把這裡的邏輯搬到 Next.js / Astro，資料來源換成 PostgreSQL。頁面結構與 JSON-LD 原樣沿用。
"""
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = json.loads((HERE / "data" / "villas.json").read_text(encoding="utf-8"))
SITE = DATA["site"]
OUT = HERE / "site"
SIZES = [10, 20, 30]
AMENITIES = {"pool": "泳池", "ktv": "KTV", "mahjong": "麻將", "bbq": "烤肉", "pet": "寵物友善"}

pages = []  # (路徑, 標題, 一句話) 給 llms.txt 與 sitemap 用


# ---------- 小工具 ----------

def money(n):
    return f"{n:,}"


def amen(v, key):
    val = v["amenities"].get(key)
    if val is True:
        return "有"
    if not val:
        return "—"
    return val


def median(vals):
    return int(statistics.median(vals)) if vals else 0


def stats(villas):
    """題型頁「一句話結論」用的數字。正式版來自每晚重算的 region_stats / size_stats。"""
    if not villas:
        return None
    return {
        "count": len(villas),
        "weekday": median([v["price"]["weekday"] for v in villas]),
        "saturday": median([v["price"]["saturday"] for v in villas]),
        "holiday": median([v["price"]["holiday"] for v in villas]),
        "max_cap": max(v["capacity_max"] for v in villas),
        "pool": sum(1 for v in villas if v["amenities"].get("pool")),
        "pet": sum(1 for v in villas if v["amenities"].get("pet")),
        "per_person_weekday": median([v["price"]["weekday"] / v["capacity_base"] for v in villas]),
    }


def villa_url(v):
    return f"/民宿/{v['slug']}/"


# ---------- 版型 ----------

CSS = """
:root{color-scheme:light;--page:#f6f7f4;--surface:#fff;--ink:#111;--ink2:#54534f;--hair:#e2e1da;--brand:#1f6f5c;--ring:rgba(0,0,0,.1)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0e0e0e;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--hair:#2c2c2a;--brand:#5fc3a8;--ring:rgba(255,255,255,.1)}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0e0e0e;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--hair:#2c2c2a;--brand:#5fc3a8;--ring:rgba(255,255,255,.1)}
*{box-sizing:border-box}body{margin:0;background:var(--page);color:var(--ink);font:15px/1.6 system-ui,-apple-system,"Segoe UI","Noto Sans TC","PingFang TC",sans-serif}
header{border-bottom:1px solid var(--hair);background:var(--surface)}header .in{max-width:1080px;margin:0 auto;padding:12px 16px;display:flex;gap:16px;flex-wrap:wrap;align-items:center}
header a{color:var(--ink);text-decoration:none}header .logo{font-weight:700;color:var(--brand)}nav a{color:var(--ink2);margin-right:12px;font-size:14px}
main{max-width:1080px;margin:0 auto;padding:24px 16px}h1{font-size:26px;margin:0 0 8px}h2{font-size:19px;margin:28px 0 10px}
.lead{font-size:17px;background:var(--surface);border:1px solid var(--ring);border-left:4px solid var(--brand);border-radius:8px;padding:12px 16px}
.meta{color:var(--ink2);font-size:13px;margin:8px 0 0}
.tbl{overflow-x:auto;background:var(--surface);border:1px solid var(--ring);border-radius:10px}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:14px}th,td{padding:8px 10px;border-bottom:1px solid var(--hair);text-align:left;white-space:nowrap}
th{color:var(--ink2);font-size:12px}td.n,th.n{text-align:right}tr:last-child td{border-bottom:0}a{color:var(--brand)}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px}.fact{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:12px}
.fact b{display:block;font-size:12px;color:var(--ink2);font-weight:600}
ul.tips li{margin:4px 0}details{background:var(--surface);border:1px solid var(--ring);border-radius:8px;padding:10px 14px;margin:6px 0}summary{font-weight:600;cursor:pointer}
.links a{display:inline-block;margin:4px 8px 4px 0;padding:4px 10px;border:1px solid var(--hair);border-radius:999px;font-size:13px;text-decoration:none;color:var(--ink2);background:var(--surface)}
.cta{display:inline-block;background:var(--brand);color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:600}
footer{max-width:1080px;margin:32px auto;padding:0 16px;color:var(--ink2);font-size:13px}
"""

NAV = "".join(f'<a href="/{r}包棟/">{r}包棟</a>' for r in DATA["regions"]) + \
      "".join(f'<a href="/{n}人包棟/">{n}人包棟</a>' for n in SIZES) + '<a href="/包棟價格/">價格行情</a>'


def page(path, title, desc, body, jsonld, h1=None):
    html = f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}｜{SITE['name']}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{SITE['domain']}{path}">
<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>
<style>{CSS}</style></head>
<body><header><div class="in"><a class="logo" href="/">{SITE['name']}</a><nav>{NAV}</nav></div></header>
<main><h1>{h1 or title}</h1>{body}</main>
<footer>資料由平台驗證，最後更新 {SITE['updated']}。本頁為示範原型，民宿與價格皆為虛構。</footer></body></html>"""
    out = OUT / path.strip("/") / "index.html" if path != "/" else OUT / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    pages.append((path, title, desc))


def compare_table(villas, poi=None):
    head = "<tr><th>民宿</th><th>區</th><th class=n>人數</th><th class=n>房數</th><th class=n>平日</th><th class=n>週六</th><th class=n>連假</th>" \
           "<th>泳池</th><th>KTV</th><th>麻將</th><th>烤肉</th><th>寵物</th>" + (f"<th class=n>距{poi}</th>" if poi else "<th>地區</th>") + "<th class=n>評價</th></tr>"
    rows = ""
    for v in sorted(villas, key=lambda x: x["price"]["weekday"]):
        last = f"<td class=n>{v['distances'].get(poi, '—')} 分鐘</td>" if poi else f"<td>{v['region']}</td>"
        rows += (f"<tr><td><a href='{villa_url(v)}'>{v['name']}</a></td><td>{v['district']}</td>"
                 f"<td class=n>{v['capacity_base']}–{v['capacity_max']}</td><td class=n>{v['rooms']}</td>"
                 f"<td class=n>{money(v['price']['weekday'])}</td><td class=n>{money(v['price']['saturday'])}</td><td class=n>{money(v['price']['holiday'])}</td>"
                 f"<td>{amen(v,'pool')}</td><td>{amen(v,'ktv')}</td><td>{amen(v,'mahjong')}</td><td>{amen(v,'bbq')}</td><td>{'可' if v['amenities'].get('pet') else '不可'}</td>"
                 f"{last}<td class=n>{v['rating']}（{v['reviews']}）</td></tr>")
    return f"<div class='tbl'><table><thead>{head}</thead><tbody>{rows}</tbody></table></div>"


def faq_block(items):
    html = "".join(f"<details><summary>{q}</summary><p>{a}</p></details>" for q, a in items)
    ld = {"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in items]}
    return html, ld


def item_list(villas):
    return {"@type": "ItemList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "url": SITE["domain"] + villa_url(v), "name": v["name"]} for i, v in enumerate(villas)]}


def crumbs(*parts):
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": n, "item": SITE["domain"] + u} for i, (n, u) in enumerate(parts)]}


def cross_links(exclude=None):
    links = [(f"/{r}包棟/", f"{r}包棟") for r in DATA["regions"]] + [(f"/{n}人包棟/", f"{n}人包棟") for n in SIZES] + \
            [(f"/包棟/{z}/", f"有{z}的包棟") for z in AMENITIES.values()] + [("/包棟價格/", "全台包棟價格行情")]
    return "<div class='links'>" + "".join(f"<a href='{u}'>{t}</a>" for u, t in links if u != exclude) + "</div>"


# ---------- 題型頁 ----------

def topic_page(path, keyword, villas, intro, poi=None, crumb_parts=()):
    s = stats(villas)
    if not s:
        return
    lead = (f"{keyword}目前有 {s['count']} 間可包棟民宿，最多可住 {s['max_cap']} 人；"
            f"平日中位價 {money(s['weekday'])} 元、週六 {money(s['saturday'])} 元、連假 {money(s['holiday'])} 元，"
            f"其中 {s['pool']} 間有泳池、{s['pet']} 間可帶寵物。資料更新於 {SITE['updated']}。")
    tips = [
        f"以基本人數計，平日每人約 {int(s['per_person_weekday']):,} 元，假日約為平日的 1.5 倍。",
        "有泳池的民宿通常比同人數的貴 4,000 到 6,000 元，泳池多為 5 到 10 月開放。",
        "連假與春節多為定價不折扣，提早 2 到 3 個月訂房才有選擇。",
        "人數超過基本人數時加人費 600 到 1,000 元，先確認床位數再確認加人上限。",
    ]
    faq = [
        (f"{keyword}一晚多少錢？", f"平日中位數 {money(s['weekday'])} 元、週六 {money(s['saturday'])} 元、連假 {money(s['holiday'])} 元，依人數與設施不同，範圍約 {money(min(v['price']['weekday'] for v in villas))} 到 {money(max(v['price']['holiday'] for v in villas))} 元。"),
        (f"{keyword}最多可以住幾個人？", f"目前最多可住 {s['max_cap']} 人，{sum(1 for v in villas if v['capacity_max'] >= 20)} 間可住 20 人以上。"),
        (f"{keyword}有哪些有泳池？", "、".join(v["name"] for v in villas if v["amenities"].get("pool")) or "目前沒有。"),
        (f"{keyword}可以帶寵物嗎？", ("可以，" + "、".join(v["name"] for v in villas if v["amenities"].get("pet")) + " 允許寵物，請於訂房時告知數量。") if s["pet"] else "目前列出的民宿皆不接受寵物。"),
        (f"{keyword}平日和假日差多少？", f"中位數來看，週六比平日貴 {money(s['saturday'] - s['weekday'])} 元，連假再多 {money(s['holiday'] - s['saturday'])} 元。"),
        (f"怎麼在平台訂{keyword}？", "點進民宿頁查看空房日曆，送出詢價後民宿主 24 小時內回覆，確認後線上付訂金。"),
    ]
    faq_html, faq_ld = faq_block(faq)
    body = f"""<p class="lead">{lead}</p><p class="meta">{intro}</p>
<h2>{keyword}民宿比較表（{s['count']} 間，依平日價排序）</h2>{compare_table(villas, poi)}
<h2>怎麼選</h2><ul class="tips">{''.join(f'<li>{t}</li>' for t in tips)}</ul>
<h2>常見問題</h2>{faq_html}
<h2>相關</h2>{cross_links(path)}"""
    jsonld = {"@context": "https://schema.org", "@graph": [item_list(villas), faq_ld, crumbs(("首頁", "/"), *crumb_parts, (keyword, path))]}
    page(path, f"{keyword}民宿推薦與價格比較", lead[:150], body, jsonld, h1=f"{keyword}民宿：{s['count']} 間比較、價格、設施")


# ---------- 民宿頁 ----------

def villa_page(v):
    path = villa_url(v)
    p = v["price"]
    lead = (f"{v['name']}位於{v['region']}{v['district']}，基本 {v['capacity_base']} 人、最多 {v['capacity_max']} 人，{v['rooms']} 間房（{v['beds']}），"
            f"平日 {money(p['weekday'])} 元、週六 {money(p['saturday'])} 元、連假 {money(p['holiday'])} 元，"
            f"{'有泳池' if v['amenities'].get('pool') else '無泳池'}、{'可帶寵物' if v['amenities'].get('pet') else '不可帶寵物'}。平台於 {v['verified']} 驗證。")
    facts = [("人數", f"基本 {v['capacity_base']} 人，最多 {v['capacity_max']} 人，加人 {money(v['extra_fee'])} 元/人"),
             ("房數與床型", f"{v['rooms']} 房，{v['beds']}"),
             ("平日 / 週六 / 連假 / 春節", f"{money(p['weekday'])} / {money(p['saturday'])} / {money(p['holiday'])} / {money(p['cny'])} 元"),
             ("設施", "、".join(f"{AMENITIES.get(k, k)}：{amen(v, k)}" for k in v["amenities"] if v["amenities"][k])),
             ("車程", "、".join(f"{k} {m} 分鐘" for k, m in v["distances"].items())),
             ("評價", f"{v['rating']} / 5（{v['reviews']} 則）"),
             ("寵物", "可，訂房時告知" if v["amenities"].get("pet") else "不可")]
    facts_html = "".join(f"<div class='fact'><b>{k}</b>{val}</div>" for k, val in facts)
    faq = [(f"{v['name']}可以住幾個人？", f"基本 {v['capacity_base']} 人，最多 {v['capacity_max']} 人，超過基本人數每人加 {money(v['extra_fee'])} 元。"),
           (f"{v['name']}一晚多少錢？", f"平日 {money(p['weekday'])} 元、週六 {money(p['saturday'])} 元、連假 {money(p['holiday'])} 元、春節 {money(p['cny'])} 元，以基本人數計。"),
           (f"{v['name']}離{list(v['distances'])[0]}多遠？", f"開車約 {list(v['distances'].values())[0]} 分鐘。")]
    faq_html, faq_ld = faq_block(faq)
    body = f"""<p class="lead">{lead}</p>
<h2>事實表</h2><div class="facts">{facts_html}</div>
<h2>常見問題</h2>{faq_html}
<p style="margin-top:24px"><a class="cta" href="#inquiry">查空房・詢價</a></p>
<h2>相關</h2>{cross_links()}"""
    lodging = {"@type": "LodgingBusiness", "name": v["name"], "alternateName": v["aliases"], "url": SITE["domain"] + path,
               "address": {"@type": "PostalAddress", "addressRegion": v["region"], "addressLocality": v["district"], "addressCountry": "TW"},
               "petsAllowed": bool(v["amenities"].get("pet")),
               "amenityFeature": [{"@type": "LocationFeatureSpecification", "name": AMENITIES.get(k, k), "value": True} for k in v["amenities"] if v["amenities"][k]],
               "aggregateRating": {"@type": "AggregateRating", "ratingValue": v["rating"], "reviewCount": v["reviews"]},
               "makesOffer": [{"@type": "Offer", "name": n, "price": pr, "priceCurrency": "TWD", "eligibleQuantity": {"@type": "QuantitativeValue", "minValue": v["capacity_base"], "maxValue": v["capacity_max"], "unitText": "人"}}
                              for n, pr in (("平日", p["weekday"]), ("週六", p["saturday"]), ("連假", p["holiday"]), ("春節", p["cny"]))]}
    jsonld = {"@context": "https://schema.org", "@graph": [lodging, faq_ld, crumbs(("首頁", "/"), (f"{v['region']}包棟", f"/{v['region']}包棟/"), (v["name"], path))]}
    page(path, f"{v['name']}｜{v['region']}{v['district']}包棟 {v['capacity_base']}–{v['capacity_max']} 人", lead[:150], body, jsonld, h1=f"{v['name']}（{v['region']}{v['district']}包棟）")


# ---------- 價格行情頁、首頁、AI 檔案 ----------

def price_page():
    rows = ""
    for r in DATA["regions"]:
        for n in SIZES:
            vs = [v for v in DATA["villas"] if v["region"] == r and v["capacity_max"] >= n]
            s = stats(vs)
            if s:
                rows += f"<tr><td><a href='/{r}包棟/{n}人/'>{r} {n} 人</a></td><td class=n>{s['count']}</td><td class=n>{money(s['weekday'])}</td><td class=n>{money(s['saturday'])}</td><td class=n>{money(s['holiday'])}</td><td class=n>{int(s['per_person_weekday']):,}</td></tr>"
    s_all = stats(DATA["villas"])
    lead = f"全台 {s_all['count']} 間包棟民宿的行情：平日中位價 {money(s_all['weekday'])} 元、週六 {money(s_all['saturday'])} 元、連假 {money(s_all['holiday'])} 元，每人平日約 {int(s_all['per_person_weekday']):,} 元。每月依平台掛牌價重算，更新於 {SITE['updated']}。"
    faq_html, faq_ld = faq_block([
        ("包棟民宿一晚多少錢？", lead),
        ("包棟是平日便宜還是假日便宜？", f"平日最便宜，週六約為平日 1.5 倍，連假再高 10% 到 15%。"),
        ("包棟每人平均多少錢？", f"以基本人數計，平日中位數每人約 {int(s_all['per_person_weekday']):,} 元，人數越多越划算。"),
    ])
    body = f"""<p class="lead">{lead}</p>
<h2>地區 × 人數 中位價（元 / 晚）</h2><div class="tbl"><table><thead><tr><th>地區・人數</th><th class=n>間數</th><th class=n>平日</th><th class=n>週六</th><th class=n>連假</th><th class=n>每人平日</th></tr></thead><tbody>{rows}</tbody></table></div>
<p class="meta">方法：取各民宿以基本人數計的掛牌價中位數，不含加人費與清潔費。</p>
<h2>常見問題</h2>{faq_html}<h2>相關</h2>{cross_links('/包棟價格/')}"""
    page("/包棟價格/", "全台包棟民宿價格行情", lead[:150], body, {"@context": "https://schema.org", "@graph": [faq_ld, crumbs(("首頁", "/"), ("包棟價格", "/包棟價格/"))]}, h1="全台包棟民宿價格行情（地區 × 人數）")


def home():
    rows = ""
    for r in DATA["regions"]:
        s = stats([v for v in DATA["villas"] if v["region"] == r])
        rows += f"<tr><td><a href='/{r}包棟/'>{r}包棟</a></td><td class=n>{s['count']}</td><td class=n>{s['max_cap']}</td><td class=n>{money(s['weekday'])}</td><td class=n>{money(s['saturday'])}</td></tr>"
    s_all = stats(DATA["villas"])
    lead = f"{SITE['name']}只做包棟：全台 {s_all['count']} 間經平台驗證的包棟民宿，每間都有人數、房數、平日假日價格、設施與車程，依地區與人數整理。"
    body = f"""<p class="lead">{lead}</p>
<h2>依地區</h2><div class="tbl"><table><thead><tr><th>地區</th><th class=n>間數</th><th class=n>最多人數</th><th class=n>平日中位</th><th class=n>週六中位</th></tr></thead><tbody>{rows}</tbody></table></div>
<h2>依人數</h2>{cross_links()}"""
    page("/", f"{SITE['name']}：全台包棟民宿比較與訂房", lead, body, {"@context": "https://schema.org", "@type": "WebSite", "name": SITE["name"], "url": SITE["domain"]}, h1="全台包棟民宿：依地區、人數、設施比較")


def ai_files():
    lines = [f"# {SITE['name']}", "", "> 只做包棟的訂房平台。每間民宿都有平台驗證的人數、房數、平日假日價格、設施、車程。題型頁依地區與人數整理，有比較表與價格中位數。", "", "## 題型頁"]
    for path, title, desc in pages:
        if path.count("/") <= 3 and "/民宿/" not in path and path != "/":
            lines.append(f"- [{title}]({SITE['domain']}{path}): {desc[:80]}")
    lines += ["", "## 民宿頁"] + [f"- [{title}]({SITE['domain']}{path}): {desc[:80]}" for path, title, desc in pages if "/民宿/" in path]
    lines += ["", "## 開放資料", f"- [villas.json]({SITE['domain']}/api/public/villas.json): 全部民宿的結構化資料"]
    (OUT / "llms.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += [f"  <url><loc>{SITE['domain']}{p}</loc><lastmod>{SITE['updated']}</lastmod></url>" for p, _, _ in pages]
    sm.append("</urlset>")
    (OUT / "sitemap.xml").write_text("\n".join(sm), encoding="utf-8")

    (OUT / "robots.txt").write_text((HERE.parent / "templates" / "robots.txt").read_text(encoding="utf-8")
                                     .replace("https://example.com", SITE["domain"])
                                     .replace("# ---- 模型訓練（LLMO）：示範「不給訓練」。若客戶希望被模型「記得」，改成 Allow ----", "# ---- 模型訓練（LLMO）：平台要被模型記得，放行 ----")
                                     .replace("Disallow: /\n\n# ---- 其他", "Allow: /\n\n# ---- 其他"), encoding="utf-8")

    api = OUT / "api" / "public"
    api.mkdir(parents=True, exist_ok=True)
    (api / "villas.json").write_text(json.dumps({"updated": SITE["updated"], "villas": [
        {k: v[k] for k in ("slug", "name", "region", "district", "capacity_base", "capacity_max", "rooms", "price", "amenities", "distances", "rating", "reviews", "verified")} | {"url": SITE["domain"] + villa_url(v)}
        for v in DATA["villas"]]}, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------- 產生全部 ----------

def main():
    V = DATA["villas"]
    home()
    for r, meta in DATA["regions"].items():
        rv = [v for v in V if v["region"] == r]
        topic_page(f"/{r}包棟/", f"{r}包棟", rv, meta["intro"], poi=meta["pois"][0])
        for n in SIZES:
            topic_page(f"/{r}包棟/{n}人/", f"{r} {n} 人包棟", [v for v in rv if v["capacity_max"] >= n], meta["intro"], poi=meta["pois"][0], crumb_parts=((f"{r}包棟", f"/{r}包棟/"),))
    for n in SIZES:
        topic_page(f"/{n}人包棟/", f"{n}人包棟", [v for v in V if v["capacity_max"] >= n], f"全台可容納 {n} 人的包棟民宿，依地區與平日價整理。")
    for key, zh in AMENITIES.items():
        topic_page(f"/包棟/{zh}/", f"有{zh}的包棟", [v for v in V if v["amenities"].get(key)], f"全台有{zh}的包棟民宿。")
    for v in V:
        villa_page(v)
    price_page()
    ai_files()
    print(f"產出 {len(pages)} 頁 + llms.txt + sitemap.xml + robots.txt + api/public/villas.json → {OUT}")


if __name__ == "__main__":
    main()
