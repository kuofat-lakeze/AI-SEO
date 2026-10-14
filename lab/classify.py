#!/usr/bin/env python3
"""
讀取 nginx / Apache combined 格式的 access log，把每一行分到六大優化領域，輸出 stats.json。

用法：
  python3 classify.py ../output/baseline.log --out ../output/baseline.json
  python3 classify.py /var/log/nginx/access.log*  --out stats.json      # 真實環境也能直接用

分類邏輯（跟 bots.json 對應）：
  1. User-Agent 含有 bots.json 裡的特徵字串 → 該爬蟲所屬的領域（seo / llmo / geo / aeo_*）
  2. 否則若 UA 看起來是瀏覽器 → 真人；再用 Referer 分成 搜尋 / AI / 地圖 / 社群 / 直接
  3. 其他 → unknown（通常是沒帶 UA 的程式，實務上可併入 aeo_agent）
"""
import argparse
import glob
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent

LOG_RE = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<ts>[^\]]+)\] "(?P<method>\S+) (?P<path>\S+) [^"]*" '
    r'(?P<status>\d{3}) (?P<size>\S+) "(?P<referer>[^"]*)" "(?P<ua>[^"]*)"'
)
BROWSER_HINT = re.compile(r"Mozilla/5\.0 \((iPhone|Windows|Macintosh|Linux; Android|X11)", re.I)


def load_rules():
    cfg = json.loads((HERE / "bots.json").read_text(encoding="utf-8"))
    bots = [(b["match"].lower(), b) for b in cfg["bots"]]
    refs = {k: v for k, v in cfg["referrers"].items() if not k.startswith("_")}
    return cfg, bots, refs


def classify_ua(ua, bots):
    low = ua.lower()
    for needle, bot in bots:
        if needle.lower() in low:
            return bot
    return None


def referer_type(referer, refs):
    if not referer or referer == "-":
        return refs["-"]
    host = urlparse(referer).netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    for k, v in refs.items():
        if k != "-" and (host == k or host.endswith("." + k)):
            return v
    return {"platform": host or "unknown", "type": "other"}


def new_bucket():
    return {
        "visits": 0,
        "platforms": Counter(),
        "bots": Counter(),
        "daily": Counter(),
        "status": Counter(),
        "paths": Counter(),
        "blocked_by_bot": Counter(),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logs", nargs="+", help="log 檔案或 glob 樣式")
    ap.add_argument("--out", default=str(HERE.parent / "output" / "stats.json"))
    ap.add_argument("--label", default="", help="這份資料的名稱（例如 優化前 / 優化後）")
    args = ap.parse_args()

    cfg, bots, refs = load_rules()
    buckets = defaultdict(new_bucket)
    organic_types = Counter()
    days = set()
    total_lines = parsed = 0

    files = [f for pat in args.logs for f in sorted(glob.glob(pat))] or args.logs
    for fn in files:
        with open(fn, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                total_lines += 1
                m = LOG_RE.match(line)
                if not m:
                    continue
                parsed += 1
                ua, ref, path = m["ua"], m["referer"], m["path"].split("?")[0]
                status = m["status"]
                try:
                    day = datetime.strptime(m["ts"].split(":")[0], "%d/%b/%Y").strftime("%Y-%m-%d")
                except ValueError:
                    day = "unknown"
                days.add(day)

                bot = classify_ua(ua, bots)
                if bot:
                    b = buckets[bot["domain"]]
                    b["platforms"][bot["platform"]] += 1
                    b["bots"][bot["name"]] += 1
                    if status == "403":
                        b["blocked_by_bot"][bot["name"]] += 1
                elif BROWSER_HINT.search(ua):
                    r = referer_type(ref, refs)
                    b = buckets["organic"]
                    b["platforms"][r["platform"]] += 1
                    b["bots"][r["type"]] += 1
                    organic_types[r["type"]] += 1
                else:
                    b = buckets["unknown"]
                    b["platforms"]["unknown"] += 1
                    b["bots"][ua[:40] or "(empty UA)"] += 1

                b["visits"] += 1
                b["daily"][day] += 1
                b["status"][status] += 1
                b["paths"][path] += 1

    days.discard("unknown")
    out = {
        "label": args.label,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "period": {"from": min(days) if days else None, "to": max(days) if days else None, "days": len(days)},
        "lines": {"total": total_lines, "parsed": parsed},
        "domains": cfg["domains"],
        "organic_types": dict(organic_types),
        "buckets": {},
    }
    for key, b in buckets.items():
        out["buckets"][key] = {
            "visits": b["visits"],
            "visitor_types": len(b["platforms"]),
            "platforms": b["platforms"].most_common(),
            "bots": b["bots"].most_common(),
            "daily": dict(sorted(b["daily"].items())),
            "status": dict(b["status"]),
            "top_paths": b["paths"].most_common(10),
            "blocked_by_bot": dict(b["blocked_by_bot"]),
        }

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # 終端機摘要
    print(f"讀取 {total_lines:,} 行，成功解析 {parsed:,} 行，期間 {out['period']['from']} ~ {out['period']['to']}")
    for key in ["organic", "seo", "llmo", "geo", "aeo_fetch", "aeo_agent", "aeo_tool", "unknown"]:
        if key in out["buckets"]:
            bk = out["buckets"][key]
            label = cfg["domains"].get(key, {}).get("label", key)
            top = ", ".join(f"{p} {n:,}" for p, n in bk["platforms"][:4])
            print(f"  {label:<22} {bk['visits']:>10,} 次  {bk['visitor_types']:>2} 種  | {top}")
    print(f"→ {args.out}")


if __name__ == "__main__":
    main()
