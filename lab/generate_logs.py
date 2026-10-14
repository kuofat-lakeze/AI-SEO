#!/usr/bin/env python3
"""
產生模擬的 nginx access.log（combined 格式），內容包含：
  * 真人流量（看 Referer 分搜尋 / AI / 地圖 / 社群 / 直接）
  * 搜尋引擎、AI 訓練、生成式搜尋、即時答案抓取、Agent、SEO 工具等爬蟲

用法：
  python3 generate_logs.py --scenario baseline  --days 30 --out ../output/baseline.log
  python3 generate_logs.py --scenario optimized --days 30 --out ../output/optimized.log

--scenario optimized 模擬「做完 AI SEO 之後」：llms.txt、Schema、robots 放行後
AI 即時抓取與 AI 導流明顯上升，用來做 before / after 的量化對照。
只用標準函式庫，不需要安裝任何套件。
"""
import argparse
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent

# 網站頁面池：(path, 一般權重, AI 爬蟲偏好權重)
PAGES = [
    ("/",                                   30, 20),
    ("/products/",                          15, 10),
    ("/products/ai-seo-audit",              12, 14),
    ("/products/geo-monitoring",             8, 12),
    ("/pricing",                            10,  9),
    ("/faq",                                 6, 18),
    ("/blog/",                               8,  8),
    ("/blog/what-is-geo",                    7, 16),
    ("/blog/llms-txt-guide",                 6, 15),
    ("/blog/ai-overview-ranking-factors",    6, 14),
    ("/blog/aeo-vs-seo",                     5, 12),
    ("/about",                               4,  5),
    ("/contact",                             4,  3),
    ("/case-studies/",                       3,  6),
    ("/llms.txt",                            0, 10),
    ("/robots.txt",                          0,  8),
    ("/sitemap.xml",                         0,  6),
]

HUMAN_UAS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
]

# 「做完優化」的情境：各領域流量倍率
SCENARIOS = {
    "baseline": {
        "domain_mult": {},
        "referrer_type_mult": {},
        "blocked_bots": {"Bytespider", "CCBot"},     # 一開始 WAF 擋掉的爬蟲
        "blocked_ratio": 0.9,
    },
    "optimized": {
        "domain_mult": {"aeo_fetch": 3.2, "geo": 1.6, "seo": 1.15, "llmo": 1.25, "aeo_agent": 1.1},
        "referrer_type_mult": {"ai": 4.5, "search": 1.2, "map": 1.3},
        "blocked_bots": {"Bytespider"},
        "blocked_ratio": 0.9,
    },
}


def rand_ip(rng):
    return ".".join(str(rng.randint(1, 254)) for _ in range(4))


def pick_page(rng, ai=False):
    weights = [p[2] if ai else p[1] for p in PAGES]
    return rng.choices(PAGES, weights=weights, k=1)[0][0]


def nginx_line(ip, ts, path, status, size, referer, ua):
    return (f'{ip} - - [{ts.strftime("%d/%b/%Y:%H:%M:%S")} +0800] '
            f'"GET {path} HTTP/1.1" {status} {size} "{referer}" "{ua}"')


def daily_counts(rng, total, days):
    """把 total 次拆到每天，週末少一點，加上雜訊。"""
    base = []
    for d in range(days):
        w = 0.7 if (d % 7) in (5, 6) else 1.0
        base.append(max(0.05, w * rng.gauss(1.0, 0.18)))
    s = sum(base)
    return [int(round(total * b / s)) for b in base]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", choices=SCENARIOS.keys(), default="baseline")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--start", default="2026-09-01", help="起始日期 YYYY-MM-DD")
    ap.add_argument("--bot-scale", type=float, default=0.001,
                    help="bots.json weight × 這個倍率 = 模擬期間的爬蟲次數")
    ap.add_argument("--human-scale", type=float, default=0.1,
                    help="referrers weight × 這個倍率 = 模擬期間的真人次數")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(HERE.parent / "output" / "access.log"))
    args = ap.parse_args()

    rng = random.Random(args.seed + (1 if args.scenario == "optimized" else 0))
    cfg = json.loads((HERE / "bots.json").read_text(encoding="utf-8"))
    sc = SCENARIOS[args.scenario]
    start = datetime.strptime(args.start, "%Y-%m-%d")

    lines = []  # (timestamp, line)

    # ---- 爬蟲 ----
    for bot in cfg["bots"]:
        mult = sc["domain_mult"].get(bot["domain"], 1.0)
        total = max(1, int(bot["weight"] * args.bot_scale * mult))
        ai_pref = bot["domain"] in ("llmo", "geo", "aeo_fetch")
        for d, n in enumerate(daily_counts(rng, total, args.days)):
            day = start + timedelta(days=d)
            for _ in range(n):
                ts = day + timedelta(seconds=rng.randint(0, 86399))
                blocked = bot["name"] in sc["blocked_bots"] and rng.random() < sc["blocked_ratio"]
                status = 403 if blocked else rng.choices([200, 304, 404], weights=[90, 7, 3])[0]
                size = 0 if status in (304, 403) else rng.randint(2000, 60000)
                lines.append((ts, nginx_line(rand_ip(rng), ts, pick_page(rng, ai=ai_pref),
                                             status, size, "-", bot["ua"])))

    # ---- 真人 ----
    for host, ref in cfg["referrers"].items():
        if host.startswith("_"):
            continue
        mult = sc["referrer_type_mult"].get(ref["type"], 1.0)
        total = int(ref["weight"] * args.human_scale * mult)
        referer = "-" if host == "-" else f"https://{host}/"
        for d, n in enumerate(daily_counts(rng, total, args.days)):
            day = start + timedelta(days=d)
            for _ in range(n):
                ts = day + timedelta(seconds=rng.randint(0, 86399))
                lines.append((ts, nginx_line(rand_ip(rng), ts, pick_page(rng),
                                             200, rng.randint(5000, 90000), referer, rng.choice(HUMAN_UAS))))

    lines.sort(key=lambda x: x[0])
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(l for _, l in lines) + "\n", encoding="utf-8")
    print(f"[{args.scenario}] 寫出 {len(lines):,} 行 → {out}")


if __name__ == "__main__":
    main()
