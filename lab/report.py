#!/usr/bin/env python3
"""
把 classify.py 產出的 stats.json 畫成一頁式儀表板（純 HTML，無外部依賴）。
排版對照「六大優化領域」資訊圖：優化領域 / 來了幾次 / 來訪者種類 / 來最多的，
再加上每日趨勢、AI 導流、AI 爬蟲最愛頁面、被阻擋的爬蟲，以及優化前後對照。

用法：
  python3 report.py ../output/optimized.json --compare ../output/baseline.json --out ../output/dashboard.html
"""
import argparse
import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

# 欄位順序與圖片一致；seo 的資料格橫跨 SEO + AIO/AEO 兩個標題格
COLUMNS = [
    ("organic",   "自然流量",   "Organic",  "六大優化的成果", ""),
    ("meo",       "MEO",        "Map Engine Optimization", "地圖引擎優化", "Local SEO・GBP 優化"),
    ("seo",       "SEO",        "Search Engine Optimization", "搜尋引擎優化", "SXO・Technical SEO"),
    ("aio",       "AIO / AEO",  "AI Overview / Answer Engine", "AI 摘要優化・答案引擎", "SGE 優化"),
    ("llmo",      "LLMO",       "Large Language Model Optimization", "大型語言模型優化", "LLM SEO"),
    ("geo",       "GEO",        "Generative Engine Optimization", "生成式引擎優化", "GAIO・AISO・AI SEO・AIEO"),
    ("aeo",       "AEO",        "Answer Engine Optimization", "答案引擎優化", "VSO（語音搜尋）・AAO・AXO・AAIO（AI Agent 優化）"),
]
DATA_CELLS = [  # (bucket key, grid-column span, 小標)
    ("organic",   1, "自然流量"),
    ("meo",       1, "在地搜尋"),
    ("seo",       2, "同一批爬蟲，搜尋與 AI 摘要共用"),
    ("llmo",      1, "訓練爬蟲"),
    ("geo",       1, "生成式搜尋索引"),
    ("aeo_fetch", 1, "即時答案抓取"),
    ("aeo_agent", 1, "AI Agent・自動瀏覽"),
    ("aeo_tool",  1, "AI 工具・SEO 工具・預覽"),
]
TYPE_LABEL = {"search": "搜尋", "ai": "AI", "map": "地圖", "social": "社群", "direct": "直接", "other": "其他"}


def fmt(n):
    """回傳 (數字, 單位)；超過一萬用「萬」。"""
    if n >= 10000:
        s = f"{n / 10000:,.1f}".rstrip("0").rstrip(".")
        return s, "萬"
    return f"{n:,}", ""


def esc(s):
    return html.escape(str(s))


def delta_badge(now, before):
    if not before:
        return ""
    pct = (now - before) / before * 100
    cls = "up" if pct >= 0 else "down"
    sign = "+" if pct >= 0 else ""
    return f'<span class="delta {cls}" title="優化前 {before:,} 次">{sign}{pct:.0f}%</span>'


def sparkline(daily, key):
    vals = list(daily.values())
    days = list(daily.keys())
    if len(vals) < 2:
        return '<div class="spark empty">資料不足</div>'
    w, h, pad = 220, 56, 4
    mx = max(vals) or 1
    pts = []
    for i, v in enumerate(vals):
        x = pad + i * (w - 2 * pad) / (len(vals) - 1)
        y = h - pad - (v / mx) * (h - 2 * pad)
        pts.append((round(x, 1), round(y, 1)))
    poly = " ".join(f"{x},{y}" for x, y in pts)
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" data-key="{esc(key)}" '
            f'data-days=\'{json.dumps(days)}\' data-vals=\'{json.dumps(vals)}\' role="img" '
            f'aria-label="每日次數趨勢，最高 {mx:,}">'
            f'<line class="base" x1="{pad}" y1="{h - pad}" x2="{w - pad}" y2="{h - pad}"/>'
            f'<polyline class="line" points="{poly}"/>'
            f'<circle class="dot" r="4" cx="{pts[-1][0]}" cy="{pts[-1][1]}"/></svg>')


def render(stats, before):
    B = stats["buckets"]
    BB = before["buckets"] if before else {}
    period = stats["period"]
    label = stats.get("label") or "本期"
    blabel = (before or {}).get("label") or "上期"

    def bucket(k):
        return B.get(k, {"visits": 0, "visitor_types": 0, "platforms": [], "bots": [], "daily": {}, "top_paths": [], "blocked_by_bot": {}, "status": {}})

    # ---- 第 1 列：優化領域 ----
    head = []
    for key, big, en, zh, alias in COLUMNS:
        span = 3 if key == "aeo" else 1
        if key == "organic":
            head.append(f'<div class="card head" style="grid-column: span {span}"><div class="zh big">{big}</div><div class="sub">{zh}</div></div>')
        else:
            head.append(f'<div class="card head" style="grid-column: span {span}"><div class="abbr">{big}</div>'
                        f'<div class="zh">{zh}</div><div class="en">{en}</div><div class="alias">{alias}</div></div>')

    # ---- 第 2 列：來了幾次 ----
    visits = []
    for key, span, note in DATA_CELLS:
        if key == "meo":
            visits.append(f'<div class="card num" style="grid-column: span {span}"><div class="n text">實測追蹤中</div><div class="note">{note}<br><small>GBP 後台資料，不在 log 裡</small></div></div>')
            continue
        b = bucket(key)
        n, unit = fmt(b["visits"])
        d = delta_badge(b["visits"], BB.get(key, {}).get("visits", 0)) if before else ""
        visits.append(f'<div class="card num" style="grid-column: span {span}"><div class="n">{n}<span class="unit">{unit}次</span></div>{d}<div class="note">{note}</div></div>')

    # ---- 第 3 列：來訪者種類 ----
    kinds = []
    for key, span, _ in DATA_CELLS:
        if key == "meo":
            kinds.append(f'<div class="card kinds" style="grid-column: span {span}"><div class="k text">—</div><div class="note">Google 地圖・Apple 地圖</div></div>')
            continue
        b = bucket(key)
        if key == "organic":
            types = stats.get("organic_types", {})
            chips = "".join(f'<span class="chip">{TYPE_LABEL.get(t, t)}</span>' for t in types)
            kinds.append(f'<div class="card kinds" style="grid-column: span {span}"><div class="k">{len(types)} <small>種</small></div><div class="chips">{chips}</div></div>')
            continue
        chips = "".join(f'<span class="chip" title="{n:,} 次">{esc(p)}</span>' for p, n in b["platforms"][:14])
        more = f'<span class="chip more">+{len(b["platforms"]) - 14}</span>' if len(b["platforms"]) > 14 else ""
        kinds.append(f'<div class="card kinds" style="grid-column: span {span}"><div class="k">{b["visitor_types"]} <small>種</small></div><div class="chips">{chips}{more}</div></div>')

    # ---- 第 4 列：來最多的 ----
    tops = []
    for key, span, _ in DATA_CELLS:
        if key == "meo":
            tops.append(f'<div class="card top" style="grid-column: span {span}"><div class="row muted"><span>GBP 曝光</span><span>—</span></div><div class="row muted"><span>路線查詢</span><span>—</span></div><div class="row muted"><span>來電</span><span>—</span></div><div class="row muted"><span>網站點擊</span><span>—</span></div></div>')
            continue
        b = bucket(key)
        rows = ""
        plats = [(p, n) for p, n in b["platforms"] if p != "Direct"]  # 直接流量不算「來源平台」
        for p, n in plats[:4]:
            v, u = fmt(n)
            rows += f'<div class="row"><span class="p">{esc(p)}</span><span class="v">{v} <small>{u}</small></span></div>'
        tops.append(f'<div class="card top" style="grid-column: span {span}">{rows or "<div class=row muted>尚無資料</div>"}</div>')

    # ---- 第 5 列：每日趨勢 ----
    trend = []
    for key, span, _ in DATA_CELLS:
        if key == "meo":
            trend.append(f'<div class="card trend" style="grid-column: span {span}"><div class="spark empty">—</div></div>')
            continue
        trend.append(f'<div class="card trend" style="grid-column: span {span}">{sparkline(bucket(key)["daily"], key)}</div>')

    # ---- 下方：對照表 ----
    compare_html = ""
    if before:
        rows = ""
        for key, _, note in DATA_CELLS:
            if key == "meo":
                continue
            now, old = bucket(key)["visits"], BB.get(key, {}).get("visits", 0)
            lab = stats["domains"].get(key, {}).get("label", key)
            rows += f"<tr><td>{esc(lab)}</td><td class=num>{old:,}</td><td class=num>{now:,}</td><td class=num>{delta_badge(now, old)}</td></tr>"
        # AI 導流
        def ai_ref(st):
            return {p: n for p, n in st["buckets"].get("organic", {}).get("platforms", []) if p in AI_PLATFORMS}
        a_now, a_old = ai_ref(stats), ai_ref(before)
        ai_rows = ""
        for p in sorted(set(a_now) | set(a_old), key=lambda p: -a_now.get(p, 0)):
            ai_rows += f"<tr><td>{esc(p)}</td><td class=num>{a_old.get(p, 0):,}</td><td class=num>{a_now.get(p, 0):,}</td><td class=num>{delta_badge(a_now.get(p, 0), a_old.get(p, 0))}</td></tr>"
        tot_old, tot_now = sum(a_old.values()), sum(a_now.values())
        compare_html = f"""
<section class="panel">
  <h2>優化前後對照 <small>{esc(blabel)} {before['period']['from']}～{before['period']['to']} vs {esc(label)} {period['from']}～{period['to']}</small></h2>
  <div class="two">
    <table><thead><tr><th>領域</th><th class=num>{esc(blabel)}</th><th class=num>{esc(label)}</th><th class=num>變化</th></tr></thead><tbody>{rows}</tbody></table>
    <div>
      <h3>AI 導流（真人從 AI 平台點進來）</h3>
      <table><thead><tr><th>平台</th><th class=num>{esc(blabel)}</th><th class=num>{esc(label)}</th><th class=num>變化</th></tr></thead>
      <tbody>{ai_rows}<tr class=total><td>合計</td><td class=num>{tot_old:,}</td><td class=num>{tot_now:,}</td><td class=num>{delta_badge(tot_now, tot_old)}</td></tr></tbody></table>
      <p class="hint">這一張才是跟客戶談「成果」的表：爬蟲來得多只代表「被讀到」，AI 導流才代表「被引用、被點擊」。</p>
    </div>
  </div>
</section>"""

    # ---- 下方：AI 爬蟲最愛頁面 / 被阻擋 ----
    path_counter = {}
    for key in ("llmo", "geo", "aeo_fetch"):
        for p, n in bucket(key)["top_paths"]:
            path_counter[p] = path_counter.get(p, 0) + n
    path_rows = "".join(f"<tr><td><code>{esc(p)}</code></td><td class=num>{n:,}</td></tr>"
                        for p, n in sorted(path_counter.items(), key=lambda x: -x[1])[:10])
    blocked = {}
    for key, b in B.items():
        for name, n in b.get("blocked_by_bot", {}).items():
            blocked[name] = blocked.get(name, 0) + n
    blocked_rows = "".join(f"<tr><td>{esc(k)}</td><td class=num>{v:,}</td></tr>" for k, v in sorted(blocked.items(), key=lambda x: -x[1])) or "<tr><td colspan=2 class=muted>沒有被擋的爬蟲</td></tr>"

    bots_rows = ""
    for key, _, _ in DATA_CELLS:
        if key in ("meo", "organic"):
            continue
        for name, n in bucket(key)["bots"][:6]:
            bots_rows += f"<tr><td>{esc(stats['domains'][key]['label'])}</td><td>{esc(name)}</td><td class=num>{n:,}</td></tr>"

    detail_html = f"""
<section class="panel three">
  <div><h2>AI 爬蟲最常抓的頁面</h2><table><thead><tr><th>頁面</th><th class=num>次數</th></tr></thead><tbody>{path_rows}</tbody></table>
    <p class="hint">LLMO + GEO + 即時答案抓取合計。這些頁面就是要優先補 Schema、FAQ、llms.txt 引導的頁面。</p></div>
  <div><h2>被阻擋（403）的爬蟲</h2><table><thead><tr><th>爬蟲</th><th class=num>次數</th></tr></thead><tbody>{blocked_rows}</tbody></table>
    <p class="hint">WAF / robots 擋掉的 AI 爬蟲。想被 AI 引用，就要有意識地決定放行誰。</p></div>
  <div><h2>各領域前幾名爬蟲（UA 名稱）</h2><table><thead><tr><th>領域</th><th>爬蟲</th><th class=num>次數</th></tr></thead><tbody>{bots_rows}</tbody></table></div>
</section>"""

    grid = "".join([
        '<div class="rowlabel"><b>優化領域</b><span>Optimization Domains</span><span>六大</span></div>', *head,
        f'<div class="rowlabel"><b>來了幾次</b><span>Visits</span><span>{period["from"]}～{period["to"]}</span></div>', *visits,
        '<div class="rowlabel"><b>來訪者種類</b><span>Visitor Types</span></div>', *kinds,
        '<div class="rowlabel"><b>來最多的</b><span>Top Platforms</span><span>前四家・次數</span></div>', *tops,
        '<div class="rowlabel"><b>每日趨勢</b><span>Daily</span><span>滑過去看數字</span></div>', *trend,
    ])

    return TEMPLATE.replace("{{GRID}}", grid).replace("{{COMPARE}}", compare_html).replace("{{DETAIL}}", detail_html) \
        .replace("{{LABEL}}", esc(label)).replace("{{PERIOD}}", f'{period["from"]}～{period["to"]}（{period["days"]} 天）') \
        .replace("{{LINES}}", f'{stats["lines"]["parsed"]:,}')


AI_PLATFORMS = {"OpenAI", "Perplexity", "Anthropic", "Google Gemini", "Microsoft Copilot"}

TEMPLATE = r"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI SEO 六大領域儀表板</title>
<style>
:root{
  color-scheme: light;
  --page:#f4f6f3; --surface:#ffffff; --surface-2:#fbfbf9;
  --ink:#0b0b0b; --ink-2:#52514e; --muted:#898781; --hair:#e1e0d9; --ring:rgba(11,11,11,.10);
  --brand:#1f6f5c; --brand-soft:#e6f1ee; --series:#2a78d6;
  --good:#006300; --bad:#d03b3b;
}
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){
  color-scheme: dark;
  --page:#0d0d0d; --surface:#1a1a19; --surface-2:#202020;
  --ink:#f0efec; --ink-2:#c3c2b7; --muted:#898781; --hair:#2c2c2a; --ring:rgba(255,255,255,.10);
  --brand:#5fc3a8; --brand-soft:#1d2d29; --series:#3987e5; --good:#0ca30c; --bad:#e66767;
}}
:root[data-theme="dark"]{
  color-scheme: dark;
  --page:#0d0d0d; --surface:#1a1a19; --surface-2:#202020;
  --ink:#f0efec; --ink-2:#c3c2b7; --muted:#898781; --hair:#2c2c2a; --ring:rgba(255,255,255,.10);
  --brand:#5fc3a8; --brand-soft:#1d2d29; --series:#3987e5; --good:#0ca30c; --bad:#e66767;
}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"Segoe UI","Noto Sans TC","PingFang TC",sans-serif;padding:24px 16px}
header{max-width:1400px;margin:0 auto 16px;display:flex;flex-wrap:wrap;gap:8px 24px;align-items:baseline}
header h1{font-size:20px;margin:0}
header .meta{color:var(--ink-2)}
.grid{max-width:1400px;margin:0 auto;display:grid;grid-template-columns:150px repeat(9,minmax(0,1fr));gap:8px;align-items:stretch}
.rowlabel{padding:8px 0 8px 12px;border-left:3px solid var(--brand);display:flex;flex-direction:column;gap:2px}
.rowlabel b{font-size:17px}
.rowlabel span{color:var(--ink-2);font-size:12px}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:12px 10px;min-width:0}
.card.head{text-align:center}
.card.head .abbr{color:var(--brand);font-size:22px;font-weight:700;letter-spacing:.02em}
.card.head .zh{font-weight:700;margin-top:2px}
.card.head .zh.big{font-size:18px;margin-top:22px}
.card.head .en,.card.head .sub{color:var(--ink-2);font-size:12px;margin-top:4px}
.card.head .alias{color:var(--muted);font-size:11px;margin-top:10px;padding-top:8px;border-top:1px solid var(--hair)}
.card.num{text-align:center;display:flex;flex-direction:column;justify-content:center;gap:6px}
.card.num .n{font-size:26px;font-weight:700;letter-spacing:-.01em}
.card.num .n.text{font-size:18px}
.card.num .unit{font-size:13px;font-weight:500;color:var(--ink-2);margin-left:4px}
.card.num .note,.card.kinds .note{color:var(--ink-2);font-size:12px}
.delta{display:inline-block;align-self:center;font-size:12px;font-weight:600;padding:1px 8px;border-radius:999px;background:var(--brand-soft)}
.delta.up{color:var(--good)} .delta.down{color:var(--bad)}
.card.kinds{text-align:center}
.card.kinds .k{font-size:22px;font-weight:700}
.card.kinds .k small{font-size:14px;font-weight:500}
.chips{display:flex;flex-wrap:wrap;gap:4px;justify-content:center;margin-top:8px}
.chip{font-size:11px;padding:2px 7px;border-radius:999px;border:1px solid var(--hair);background:var(--surface-2);color:var(--ink-2);white-space:nowrap}
.chip.more{border-style:dashed}
.card.top .row{display:flex;justify-content:space-between;gap:6px;padding:7px 0;border-bottom:1px solid var(--hair);font-variant-numeric:tabular-nums}
.card.top .row:last-child{border-bottom:0}
.card.top .p{color:var(--ink-2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.card.top .v{font-weight:700;white-space:nowrap}
.card.top .v small{font-weight:500;color:var(--ink-2)}
.muted{color:var(--muted)}
.card.trend{padding:8px}
.spark{width:100%;height:56px;display:block;cursor:crosshair}
.spark .line{fill:none;stroke:var(--series);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.spark .base{stroke:var(--hair);stroke-width:1}
.spark .dot{fill:var(--series);stroke:var(--surface);stroke-width:2}
.spark .hover{fill:var(--series);stroke:var(--surface);stroke-width:2}
.spark.empty{display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:12px}
#tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--page);font-size:12px;padding:4px 8px;border-radius:6px;display:none;z-index:9;white-space:nowrap}
.panel{max-width:1400px;margin:24px auto 0;background:var(--surface);border:1px solid var(--ring);border-radius:12px;padding:16px}
.panel h2{font-size:16px;margin:0 0 10px}
.panel h2 small{color:var(--ink-2);font-weight:400;margin-left:8px;font-size:12px}
.panel h3{font-size:14px;margin:0 0 8px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:24px}
.three{display:grid;grid-template-columns:1fr 1fr 1.2fr;gap:24px}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
th,td{padding:6px 8px;border-bottom:1px solid var(--hair);text-align:left;vertical-align:top}
th{color:var(--ink-2);font-weight:600;font-size:12px}
td.num,th.num{text-align:right;white-space:nowrap}
tr.total td{font-weight:700;border-top:2px solid var(--hair)}
code{font-size:12px;background:var(--surface-2);padding:1px 4px;border-radius:4px}
.hint{color:var(--ink-2);font-size:12px;margin:10px 0 0}
footer{max-width:1400px;margin:24px auto 0;color:var(--muted);font-size:12px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}
@media (max-width:1100px){
  .grid{grid-template-columns:1fr 1fr;}
  .grid > *{grid-column:span 1 !important}
  .rowlabel{grid-column:span 2 !important;border-left:0;border-top:3px solid var(--brand);padding:12px 0 4px}
  .two,.three{grid-template-columns:1fr}
}
@media (max-width:560px){ .grid{grid-template-columns:1fr} .grid > *{grid-column:span 1 !important} .rowlabel{grid-column:span 1 !important} }
</style>
</head>
<body>
<header>
  <h1>AI SEO 六大領域儀表板</h1>
  <span class="meta">資料：{{LABEL}}・{{PERIOD}}・解析 {{LINES}} 行 log</span>
</header>
<div class="grid">{{GRID}}</div>
{{COMPARE}}
{{DETAIL}}
<footer><span>AI SEO Lab・由 lab/report.py 產生</span><span>模擬資料僅供 demo 流程演練</span></footer>
<div id="tip"></div>
<script>
(function(){
  const tip=document.getElementById('tip');
  document.querySelectorAll('svg.spark').forEach(svg=>{
    const days=JSON.parse(svg.dataset.days), vals=JSON.parse(svg.dataset.vals);
    const pts=[...svg.querySelector('polyline').points].map(p=>[p.x,p.y]);
    const hv=document.createElementNS('http://www.w3.org/2000/svg','circle');
    hv.setAttribute('r','4'); hv.setAttribute('class','hover'); hv.style.display='none'; svg.appendChild(hv);
    svg.addEventListener('mousemove',e=>{
      const r=svg.getBoundingClientRect(); const x=(e.clientX-r.left)/r.width*220;
      let i=0,best=1e9; pts.forEach((p,k)=>{const d=Math.abs(p[0]-x); if(d<best){best=d;i=k;}});
      hv.setAttribute('cx',pts[i][0]); hv.setAttribute('cy',pts[i][1]); hv.style.display='';
      tip.textContent=days[i]+'：'+vals[i].toLocaleString()+' 次';
      tip.style.display='block'; tip.style.left=(e.clientX+12)+'px'; tip.style.top=(e.clientY-28)+'px';
    });
    svg.addEventListener('mouseleave',()=>{hv.style.display='none'; tip.style.display='none';});
  });
})();
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stats", help="classify.py 產出的 stats.json（本期 / 優化後）")
    ap.add_argument("--compare", help="另一份 stats.json 當對照（上期 / 優化前）")
    ap.add_argument("--out", default=str(HERE.parent / "output" / "dashboard.html"))
    args = ap.parse_args()

    stats = json.loads(Path(args.stats).read_text(encoding="utf-8"))
    before = json.loads(Path(args.compare).read_text(encoding="utf-8")) if args.compare else None
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(stats, before), encoding="utf-8")
    print(f"→ {out}")


if __name__ == "__main__":
    main()
