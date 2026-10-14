#!/usr/bin/env python3
"""
把「地區 × 包棟」「人數 × 包棟」「設施 × 包棟」整個矩陣展開成題庫，每個關鍵字一個 queries/<關鍵字>.json。
之後用 citation_check.py 逐一追蹤，看 AI 回答這些題型時有沒有引用你的平台。

用法：
  python3 make_queries.py --target-brand 包棟網 --target-domain baodong.tw
  python3 make_queries.py --regions 宜蘭 台中 台南 --sizes 10 15 20 30 --target-brand 包棟網 --target-domain baodong.tw

每個關鍵字產生 8 題：同一題型用不同的問法，涵蓋資訊 / 比較 / 交易三種意圖，
因為 AI 的回答會隨問法變，題數夠才看得出趨勢。
"""
import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "queries"

REGION_TEMPLATES = [
    ("資訊", "{r}包棟"),
    ("資訊", "{r}包棟民宿推薦"),
    ("資訊", "{r}有哪些包棟民宿？幫我列出來"),
    ("比較", "{r}包棟民宿 有泳池 KTV 麻將 的推薦"),
    ("比較", "{r}親子包棟民宿推薦"),
    ("交易", "{r}包棟一晚多少錢？平日和假日的價格"),
    ("交易", "{r}包棟民宿 可以帶寵物 怎麼訂"),
    ("交易", "這個週末{r}包棟還有空房嗎？12個人"),
]
SIZE_TEMPLATES = [
    ("資訊", "{n}人包棟"),
    ("資訊", "{n}人包棟民宿推薦"),
    ("資訊", "全台可以住{n}人的包棟民宿有哪些"),
    ("比較", "{n}人包棟 宜蘭 台中 台南 哪裡比較好"),
    ("比較", "{n}人包棟民宿 有泳池 烤肉"),
    ("交易", "{n}人包棟一晚多少錢"),
    ("交易", "公司旅遊{n}人 包棟民宿 推薦 含價格"),
    ("交易", "{n}人包棟 可以刷卡 線上訂房"),
]
AMENITY_TEMPLATES = [
    ("資訊", "有{a}的包棟民宿"),
    ("資訊", "包棟民宿 {a} 推薦"),
    ("比較", "宜蘭 台中 台南 有{a}的包棟民宿 比較"),
    ("交易", "有{a}的包棟民宿 一晚多少錢"),
]


def build(keyword, templates, fill, target, competitors):
    queries = [{"id": f"q{i + 1:02d}", "intent": intent, "text": tpl.format(**fill)}
               for i, (intent, tpl) in enumerate(templates)]
    return {"keyword": keyword, "target": target, "competitors": competitors, "queries": queries}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--regions", nargs="*", default=["宜蘭", "台中", "台南", "礁溪", "墾丁", "南投", "花蓮", "台東"])
    ap.add_argument("--sizes", nargs="*", default=["10", "15", "20", "30"])
    ap.add_argument("--amenities", nargs="*", default=["泳池", "KTV", "寵物友善", "烤肉"])
    ap.add_argument("--target-brand", required=True, help="平台名稱，可多個用逗號分隔")
    ap.add_argument("--target-domain", required=True, help="平台網域，可多個用逗號分隔")
    ap.add_argument("--competitors", default=str(HERE / "competitors.json"),
                    help="競品別名 JSON（{品牌: [別名...]}），沒有就留空")
    args = ap.parse_args()

    target = {"brands": [b.strip() for b in args.target_brand.split(",")],
              "domains": [d.strip() for d in args.target_domain.split(",")]}
    comp_path = Path(args.competitors)
    competitors = json.loads(comp_path.read_text(encoding="utf-8")) if comp_path.exists() else {}

    OUT.mkdir(exist_ok=True)
    specs = []
    for r in args.regions:
        specs.append(build(f"{r}包棟", REGION_TEMPLATES, {"r": r}, target, competitors))
    for n in args.sizes:
        specs.append(build(f"{n}人包棟", SIZE_TEMPLATES, {"n": n}, target, competitors))
    for a in args.amenities:
        specs.append(build(f"{a}包棟", AMENITY_TEMPLATES, {"a": a}, target, competitors))

    for s in specs:
        p = OUT / f"{s['keyword']}.json"
        if p.exists() and s["keyword"] == "宜蘭包棟":
            continue  # 手工調過的範例題庫不覆蓋
        p.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  {p.name}  {len(s['queries'])} 題")
    print(f"共 {len(specs)} 個關鍵字 → {OUT}")
    print("追蹤全部：for f in lab/queries/*.json; do python3 lab/citation_check.py \"$f\" --backend anthropic; done")


if __name__ == "__main__":
    main()
