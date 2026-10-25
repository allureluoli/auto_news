"""抓取当天新闻，写入 data/YYYY-MM-DD.json。

用法：
    python scripts/fetch_news.py                 # 抓今天
    python scripts/fetch_news.py --date 2026-10-24
    python scripts/fetch_news.py --check         # 只检查连通性，不写文件
"""

from __future__ import annotations

import argparse
from collections import OrderedDict

from common import DATA_DIR, WEEKDAYS, load_config, log, now, read_json, tidy_summary, write_json
from sources import fetch_all

CAT_EN = {
    "科技资讯": "TECHNOLOGY",
    "技术社区": "DEVELOPERS",
    "热点": "TRENDING",
    "AI 前沿": "AI FRONTIER",
}
CAT_ORDER = ["科技资讯", "技术社区", "热点", "AI 前沿"]


def build_day(date_str: str, results: list[dict], brief: dict, errors: list[str], cfg: dict) -> dict:
    grouped: "OrderedDict[str, list]" = OrderedDict()
    for cat in CAT_ORDER:
        grouped[cat] = []

    seen: set[str] = set()
    for res in results:
        cat = res.get("cat") or "科技资讯"
        grouped.setdefault(cat, [])
        items = []
        for it in res["items"]:
            key = (it.get("url") or it.get("title", "")).strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            items.append({
                "title": it["title"],
                "url": it.get("url", ""),
                "summary": tidy_summary(it.get("summary", ""), res["name"]),
                "time": it.get("time", ""),
                "hot": it.get("hot", ""),
            })
        grouped[cat].append({
            "name": res["name"],
            "count": len(items),
            "items": items,
            "error": res.get("error", ""),
        })

    sections = []
    total = 0
    used_sources = 0
    for cat, srcs in grouped.items():
        srcs = [s for s in srcs if s["items"]]
        if not srcs:
            continue
        count = sum(s["count"] for s in srcs)
        total += count
        used_sources += len(srcs)
        sections.append({
            "cat": cat,
            "en": CAT_EN.get(cat, cat.upper()),
            "count": count,
            "sources": srcs,
        })

    dt = now()
    return {
        "date": date_str,
        "weekday": WEEKDAYS[dt.weekday()],
        "generated_at": dt.isoformat(timespec="seconds"),
        "brief": brief,
        "sections": sections,
        "stats": {
            "total": total,
            "sources": used_sources,
            "sections": len(sections),
        },
        "errors": errors,
    }


def carry_over(results: list[dict], brief: dict, existing: dict | None) -> None:
    """同一天重跑时，某个源这次没抓到、但上次抓到过 —— 沿用上次的，别把数据弄丢。"""
    if not existing:
        return
    old = {}
    for sec in existing.get("sections", []):
        for src in sec.get("sources", []):
            if src.get("items"):
                old[(sec.get("cat"), src.get("name"))] = src["items"]

    for res in results:
        if res["items"]:
            continue
        prev = old.get((res.get("cat"), res["name"]))
        if prev:
            res["items"] = prev
            res["error"] = (res.get("error") or "") + "（沿用上次结果）"
            log(f"{res['name']:<14} 本次为空，沿用上次 {len(prev)} 条")

    if not brief.get("items"):
        prev_brief = existing.get("brief") or {}
        if prev_brief.get("items"):
            brief.update(prev_brief)
            log("每日 60 秒本次为空，沿用上次结果")


def main() -> None:
    ap = argparse.ArgumentParser(description="抓取今日新闻")
    ap.add_argument("--date", help="YYYY-MM-DD，默认今天")
    ap.add_argument("--check", action="store_true", help="只检查连通性")
    ap.add_argument("--fresh", action="store_true", help="不沿用上一次的结果，整份覆盖")
    ap.add_argument("--strict", action="store_true", help="全部源失败时以非 0 退出")
    args = ap.parse_args()

    cfg = load_config()
    date_str = args.date or now().strftime("%Y-%m-%d")

    log(f"开始抓取 {date_str}")
    results, brief, errors = fetch_all(cfg)

    if args.check:
        for res in results:
            flag = "ok" if res["items"] else "空"
            print(f"  {res['name']:<16} {flag:<3} {len(res['items'])} 条  {res['error']}")
        print(f"  60s 简报 {len(brief['items'])} 条")
        return

    path = DATA_DIR / f"{date_str}.json"
    existing = None if args.fresh else read_json(path)
    carry_over(results, brief, existing)

    day = build_day(date_str, results, brief, errors, cfg)
    if day["stats"]["total"] == 0:
        log("所有来源都空了，放弃写入")
        if args.strict:
            raise SystemExit(1)
        return

    path = DATA_DIR / f"{date_str}.json"
    write_json(path, day)
    log(f"已写入 {path.relative_to(path.parents[1])}：{day['stats']['total']} 条 / "
        f"{day['stats']['sources']} 个来源 / {len(day['brief']['items'])} 条简报")
    if errors:
        log("有来源失败：" + "；".join(errors))


if __name__ == "__main__":
    main()
