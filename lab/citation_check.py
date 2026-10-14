#!/usr/bin/env python3
"""
AI 引用追蹤：拿同一組問題去問各個 AI 平台，記錄「誰被引用、誰被提到」，算出引用率與聲量佔比。
這是「被引用」那一層的量化工具，對應 docs/05。

用法：
  # 1. 用 Claude（web search）跑題庫，需要 pip install anthropic 與 ANTHROPIC_API_KEY
  python3 citation_check.py queries/宜蘭包棟.json --backend anthropic

  # 2. 用 Perplexity API（PERPLEXITY_API_KEY）或 OpenAI（OPENAI_API_KEY）
  python3 citation_check.py queries/宜蘭包棟.json --backend perplexity
  python3 citation_check.py queries/宜蘭包棟.json --backend openai

  # 3. 零預算：自己去 ChatGPT / Perplexity / Gemini 問，把回答貼進 CSV，再餵進來
  python3 citation_check.py queries/宜蘭包棟.json --backend manual --input answers.csv --platform ChatGPT

  # 產生比較報告（所有快照放在 output/citations/<keyword>/）
  python3 citation_check.py queries/宜蘭包棟.json --report

每次執行會存一份快照 output/citations/<keyword>/<日期>-<平台>.json，
之後每週跑一次，就能畫出「引用率」的趨勢，也就是給客戶看的成果。
"""
import argparse
import csv
import html
import json
import os
import re
import sys
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
OUT_ROOT = HERE.parent / "output" / "citations"

SYSTEM = ("你是一般使用者在用的 AI 搜尋助理。請用繁體中文回答，像平常一樣列出具體的店家或網站名稱，"
          "並盡量附上來源連結。不要詢問額外條件，直接給推薦。")


# ---------- 各平台後端：都回傳 {"answer": str, "citations": [url, ...]} ----------

def ask_anthropic(query, model):
    try:
        import anthropic
    except ImportError:
        sys.exit("需要 Anthropic SDK：pip install anthropic")
    client = anthropic.Anthropic()
    with client.beta.messages.stream(
        model=model,
        max_tokens=16000,
        system=SYSTEM,
        messages=[{"role": "user", "content": query}],
        tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 5}],
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    ) as stream:
        resp = stream.get_final_message()
    if resp.stop_reason == "refusal":
        return {"answer": "(refused)", "citations": []}
    answer, cites = [], []
    for block in resp.content:
        if block.type == "text":
            answer.append(block.text)
            for c in (getattr(block, "citations", None) or []):
                u = getattr(c, "url", None)
                if u:
                    cites.append(u)
        elif block.type == "web_search_tool_result" and isinstance(block.content, list):
            for r in block.content:
                u = getattr(r, "url", None)
                if u:
                    cites.append(("search", u))
    # 回答內文有引用的放前面；搜尋到但沒引用的另外記
    cited = [c for c in cites if isinstance(c, str)]
    searched = [c[1] for c in cites if isinstance(c, tuple)]
    return {"answer": "".join(answer), "citations": dedupe(cited), "searched": dedupe(searched)}


def _post_json(url, headers, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def ask_perplexity(query, model):
    key = os.environ.get("PERPLEXITY_API_KEY") or sys.exit("需要 PERPLEXITY_API_KEY")
    data = _post_json("https://api.perplexity.ai/chat/completions",
                      {"Authorization": f"Bearer {key}"},
                      {"model": model or "sonar", "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": query}]})
    answer = data["choices"][0]["message"]["content"]
    cites = data.get("citations") or [r.get("url") for r in data.get("search_results", []) if r.get("url")]
    return {"answer": answer, "citations": dedupe(cites)}


def ask_openai(query, model):
    key = os.environ.get("OPENAI_API_KEY") or sys.exit("需要 OPENAI_API_KEY")
    data = _post_json("https://api.openai.com/v1/responses",
                      {"Authorization": f"Bearer {key}"},
                      {"model": model or "gpt-5", "tools": [{"type": "web_search"}],
                       "instructions": SYSTEM, "input": query})
    answer, cites = [], []
    for item in data.get("output", []):
        if item.get("type") != "message":
            continue
        for part in item.get("content", []):
            answer.append(part.get("text", ""))
            for a in part.get("annotations", []):
                if a.get("type") == "url_citation" and a.get("url"):
                    cites.append(a["url"])
    return {"answer": "".join(answer), "citations": dedupe(cites)}


def read_manual(path, queries):
    """CSV 欄位：query_id, answer, citations（多個網址用空白或換行分隔）"""
    rows = {}
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            rows[r["query_id"].strip()] = {
                "answer": r.get("answer", ""),
                "citations": dedupe(re.split(r"[\s,]+", r.get("citations", "").strip())),
            }
    return rows


BACKENDS = {"anthropic": ask_anthropic, "perplexity": ask_perplexity, "openai": ask_openai}
DEFAULT_MODEL = {"anthropic": "claude-opus-5-5", "perplexity": "sonar", "openai": "gpt-5"}


# ---------- 分析 ----------

def dedupe(items):
    seen, out = set(), []
    for x in items:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def host(url):
    h = urlparse(url).netloc.lower()
    return h[4:] if h.startswith("www.") else h


def analyse(spec, results):
    """results: {query_id: {"answer", "citations"}} → 每題與整體的引用分析"""
    target_domains = [d.lower() for d in spec["target"]["domains"]]
    target_brands = spec["target"]["brands"]
    comps = spec.get("competitors", {})
    per_query, domain_counter, brand_counter = [], Counter(), Counter()
    for q in spec["queries"]:
        r = results.get(q["id"])
        if not r:
            continue
        hosts = [host(u) for u in r["citations"]]
        t_cited = [i + 1 for i, h in enumerate(hosts) if any(h == d or h.endswith("." + d) for d in target_domains)]
        t_mentioned = any(b in r["answer"] for b in target_brands)
        mentioned = [name for name, aliases in comps.items() if any(a in r["answer"] for a in aliases)]
        if t_mentioned:
            mentioned.insert(0, target_brands[0])
        for h in dedupe(hosts):
            domain_counter[h] += 1
        for m in mentioned:
            brand_counter[m] += 1
        per_query.append({
            "id": q["id"], "intent": q.get("intent", ""), "text": q["text"],
            "target_cited": bool(t_cited), "target_position": t_cited[0] if t_cited else None,
            "target_mentioned": t_mentioned,
            "cited_domains": dedupe(hosts), "brands_mentioned": mentioned,
            "answer_excerpt": r["answer"][:300],
        })
    n = len(per_query) or 1
    return {
        "queries": per_query,
        "summary": {
            "n_queries": len(per_query),
            "citation_rate": sum(q["target_cited"] for q in per_query) / n,
            "mention_rate": sum(q["target_mentioned"] for q in per_query) / n,
            "top_domains": domain_counter.most_common(15),
            "brand_share": brand_counter.most_common(),
        },
    }


# ---------- 報告 ----------

def load_snapshots(keyword):
    d = OUT_ROOT / keyword
    snaps = []
    for f in sorted(d.glob("*.json")) if d.exists() else []:
        snaps.append(json.loads(f.read_text(encoding="utf-8")))
    return snaps


def pct(x):
    return f"{x * 100:.0f}%"


def write_report(spec, snaps, out):
    kw = spec["keyword"]
    target = "、".join(spec["target"]["brands"])
    rows_trend = "".join(
        f"<tr><td>{s['date']}</td><td>{html.escape(s['platform'])}</td><td class=num>{s['summary']['n_queries']}</td>"
        f"<td class=num>{pct(s['summary']['citation_rate'])}</td><td class=num>{pct(s['summary']['mention_rate'])}</td></tr>"
        for s in snaps)
    latest = snaps[-1] if snaps else None
    dom_rows = brand_rows = q_rows = ""
    if latest:
        total_q = latest["summary"]["n_queries"] or 1
        dom_rows = "".join(f"<tr><td>{html.escape(d)}</td><td class=num>{n}</td><td class=num>{pct(n / total_q)}</td></tr>"
                           for d, n in latest["summary"]["top_domains"])
        brand_rows = "".join(f"<tr><td>{html.escape(b)}</td><td class=num>{n}</td><td class=num>{pct(n / total_q)}</td></tr>"
                             for b, n in latest["summary"]["brand_share"])
        for q in latest["queries"]:
            mark = "✓" if q["target_cited"] else ("提到" if q["target_mentioned"] else "—")
            q_rows += (f"<tr><td>{q['id']}</td><td>{html.escape(q['intent'])}</td><td>{html.escape(q['text'])}</td>"
                       f"<td class=num>{mark}</td><td>{html.escape('、'.join(q['brands_mentioned'][:6]))}</td>"
                       f"<td>{html.escape('、'.join(q['cited_domains'][:5]))}</td></tr>")
    page = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI 引用追蹤：{html.escape(kw)}</title>
<style>
:root{{color-scheme:light;--page:#f4f6f3;--surface:#fff;--ink:#0b0b0b;--ink2:#52514e;--hair:#e1e0d9;--brand:#1f6f5c;--ring:rgba(11,11,11,.1)}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--hair:#2c2c2a;--brand:#5fc3a8;--ring:rgba(255,255,255,.1)}}}}
:root[data-theme="dark"]{{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--hair:#2c2c2a;--brand:#5fc3a8;--ring:rgba(255,255,255,.1)}}
body{{margin:0;padding:24px 16px;background:var(--page);color:var(--ink);font:14px/1.5 system-ui,-apple-system,"Segoe UI","Noto Sans TC","PingFang TC",sans-serif}}
main{{max-width:1100px;margin:0 auto}} h1{{font-size:20px;margin:0 0 4px}} .meta{{color:var(--ink2);margin-bottom:16px}}
section{{background:var(--surface);border:1px solid var(--ring);border-radius:12px;padding:16px;margin-top:16px}}
h2{{font-size:16px;margin:0 0 10px}} .kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}}
.kpi{{border:1px solid var(--ring);border-radius:10px;padding:12px;text-align:center}} .kpi b{{display:block;font-size:26px}} .kpi span{{color:var(--ink2);font-size:12px}}
table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}} th,td{{padding:6px 8px;border-bottom:1px solid var(--hair);text-align:left;vertical-align:top}}
th{{color:var(--ink2);font-size:12px}} td.num,th.num{{text-align:right;white-space:nowrap}} .two{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}
.hint{{color:var(--ink2);font-size:12px;margin-top:8px}} @media(max-width:800px){{.two{{grid-template-columns:1fr}}}}
</style></head><body><main>
<h1>AI 引用追蹤：{html.escape(kw)}</h1>
<div class="meta">目標：{html.escape(target)}・快照 {len(snaps)} 份・最新 {latest['date'] + '・' + html.escape(latest['platform']) if latest else '無'}</div>
<section><div class="kpis">
  <div class="kpi"><b>{pct(latest['summary']['citation_rate']) if latest else '—'}</b><span>引用率（回答附上目標網址）</span></div>
  <div class="kpi"><b>{pct(latest['summary']['mention_rate']) if latest else '—'}</b><span>提及率（回答提到目標品牌）</span></div>
  <div class="kpi"><b>{latest['summary']['n_queries'] if latest else '—'}</b><span>題數</span></div>
  <div class="kpi"><b>{len(latest['summary']['top_domains']) if latest else '—'}</b><span>被引用的網域數</span></div>
</div></section>
<section><h2>趨勢（每份快照）</h2><table><thead><tr><th>日期</th><th>平台</th><th class=num>題數</th><th class=num>引用率</th><th class=num>提及率</th></tr></thead><tbody>{rows_trend}</tbody></table>
<p class="hint">每週跑一次同一份題庫，這張表就是「做了優化之後 AI 有沒有開始引用」的證據。</p></section>
<section class="two"><div><h2>誰的網站被引用（最新快照）</h2><table><thead><tr><th>網域</th><th class=num>題數</th><th class=num>佔比</th></tr></thead><tbody>{dom_rows}</tbody></table>
<p class="hint">這些是 AI 真正拿來當依據的來源。若都是媒體與整理站，策略就是「讓客戶出現在這些文章裡」加上「讓客戶官網本身變成可引用的來源」。</p></div>
<div><h2>品牌聲量（最新快照）</h2><table><thead><tr><th>品牌</th><th class=num>被提到的題數</th><th class=num>佔比</th></tr></thead><tbody>{brand_rows}</tbody></table></div></section>
<section><h2>逐題結果（最新快照）</h2><table><thead><tr><th>#</th><th>意圖</th><th>問題</th><th class=num>目標</th><th>提到的品牌</th><th>引用網域</th></tr></thead><tbody>{q_rows}</tbody></table></section>
</main></body></html>"""
    out.write_text(page, encoding="utf-8")


# ---------- 主程式 ----------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", help="題庫 JSON，例如 queries/宜蘭包棟.json")
    ap.add_argument("--backend", choices=[*BACKENDS, "manual"], default="manual")
    ap.add_argument("--model", help="覆寫模型名稱")
    ap.add_argument("--platform", help="manual 模式下這批回答來自哪個平台，例如 ChatGPT")
    ap.add_argument("--input", help="manual 模式的 CSV：query_id, answer, citations")
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--report", action="store_true", help="只產生報告，不新增快照")
    args = ap.parse_args()

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    kw = spec["keyword"]
    out_dir = OUT_ROOT / kw
    out_dir.mkdir(parents=True, exist_ok=True)

    if not args.report:
        if args.backend == "manual":
            if not args.input or not args.platform:
                sys.exit("manual 模式需要 --input answers.csv 與 --platform 平台名")
            results = read_manual(args.input, spec["queries"])
            platform = args.platform
        else:
            model = args.model or DEFAULT_MODEL[args.backend]
            platform = f"{args.backend}:{model}"
            results = {}
            for q in spec["queries"]:
                print(f"  問 {platform}：{q['text']}", flush=True)
                results[q["id"]] = BACKENDS[args.backend](q["text"], model)
        snap = {"keyword": kw, "date": args.date, "platform": platform,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "raw": results, **analyse(spec, results)}
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", platform)
        path = out_dir / f"{args.date}-{safe}.json"
        path.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
        s = snap["summary"]
        print(f"\n{kw}・{platform}・{args.date}")
        print(f"  題數 {s['n_queries']}  引用率 {pct(s['citation_rate'])}  提及率 {pct(s['mention_rate'])}")
        print("  被引用最多的網域：" + "、".join(f"{d}({n})" for d, n in s["top_domains"][:6]))
        print("  被提到最多的品牌：" + "、".join(f"{b}({n})" for b, n in s["brand_share"][:6]))
        print(f"→ {path}")

    snaps = load_snapshots(kw)
    report = out_dir / "report.html"
    write_report(spec, snaps, report)
    print(f"→ {report}")


if __name__ == "__main__":
    main()
