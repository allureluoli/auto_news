"""把 data/ 下的每日 JSON 编译成静态站点（docs/）。

用法：
    python scripts/build_site.py
    python scripts/build_site.py --clean     # 先清空 docs/
"""

from __future__ import annotations

import argparse
import html
import json
import shutil
from datetime import datetime
from pathlib import Path

from common import DATA_DIR, DOCS_DIR, WEB_DIR, load_config, log, now, read_json, write_json

WEEK_SHORT = ["一", "二", "三", "四", "五", "六", "日"]


# ------------------------------------------------------------------ 小工具
def esc(value) -> str:
    return html.escape(str(value or ""), quote=True)


def read_days() -> list[dict]:
    days = []
    for path in sorted(DATA_DIR.glob("*.json")):
        payload = read_json(path)
        if payload and payload.get("date"):
            days.append(payload)
    days.sort(key=lambda d: d["date"], reverse=True)
    return days


def fmt_cn(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return f"{dt.year} 年 {dt.month} 月 {dt.day} 日"


def fmt_dot(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return f"{dt.month:02d}.{dt.day:02d}"


def fmt_week(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return "星期" + WEEK_SHORT[dt.weekday()]


def asset_version() -> str:
    """用文件 mtime 做缓存戳，改样式后自动失效。"""
    stamps = []
    for name in ("site.css", "site.js"):
        p = WEB_DIR / "assets" / name
        if p.exists():
            stamps.append(str(int(p.stat().st_mtime)))
    return "".join(stamps)[-8:] or "1"


def rel_prefix(depth: int) -> str:
    return "../" * depth


def day_url(depth: int, date_str: str) -> str:
    return f"{rel_prefix(depth)}day/{date_str}/"


# ------------------------------------------------------------------ 片段
def render_topbar(depth: int, cfg: dict, active: str) -> str:
    p = rel_prefix(depth)
    home = p or "./"

    def cls(key: str) -> str:
        return ' class="is-active"' if key == active else ""

    return f"""<header class="topbar" id="topbar">
  <div class="topbar-inner">
    <a class="brand" href="{home}" aria-label="回到今日">
      <span class="seal" aria-hidden="true">早</span>
      <span class="brand-text"><b>{esc(cfg['site']['title'])}</b><em>{esc(cfg['site']['subtitle'])}</em></span>
    </a>
    <nav class="nav" aria-label="主导航">
      <a href="{home}"{cls('today')}>今日</a>
      <a href="{p}archive/"{cls('archive')}>归档</a>
      <a href="{p}feed.xml">RSS</a>
    </nav>
    <button class="icon-btn" id="theme-toggle" type="button" aria-label="切换深浅色" title="切换深浅色">
      <svg class="i-moon" viewBox="0 0 24 24" aria-hidden="true"><path d="M21 13.2A8.5 8.5 0 1 1 10.8 3a7 7 0 1 0 10.2 10.2z" fill="currentColor"/></svg>
      <svg class="i-sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.2" fill="currentColor"/><path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.2 5.2l1.6 1.6M17.2 17.2l1.6 1.6M18.8 5.2l-1.6 1.6M6.8 17.2l-1.6 1.6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
    </button>
  </div>
</header>"""


def render_footer(cfg: dict, day: dict, depth: int) -> str:
    p = rel_prefix(depth)
    generated = day.get("generated_at", "")[:16].replace("T", " ")
    repo = cfg["site"]["repo"]
    return f"""<footer class="foot">
  <div class="foot-inner">
    <p class="foot-note">数据抓取于 {esc(generated)}，每日 {cfg['site'].get('fetch_hour', 7)}:00 自动生成，历史全部保留。</p>
    <p class="foot-meta">
      <a href="{repo}" target="_blank" rel="noopener">GitHub</a>
      <span aria-hidden="true">·</span>
      <a href="{p}feed.xml">RSS</a>
      <span aria-hidden="true">·</span>
      <span>{esc(cfg['site'].get('author', ''))} 维护</span>
    </p>
  </div>
</footer>"""


def render_brief(brief: dict) -> str:
    items = brief.get("items") or []
    if not items:
        return ""
    rows = "\n".join(
        f'      <li><span class="b-n">{i:02d}</span><span class="b-t">{esc(text)}</span></li>'
        for i, text in enumerate(items, 1)
    )
    tip = brief.get("tip") or ""
    tip_html = f'\n    <p class="brief-tip">{esc(tip)}</p>' if tip else ""
    date_label = brief.get("date") or ""
    return f"""<section class="brief" data-reveal>
    <div class="brief-head">
      <h2>每日 60 秒</h2>
      <span class="mono">THE 60-SECOND BRIEF</span>
      <span class="brief-date">{esc(date_label)}</span>
    </div>
    <ol class="brief-list">
{rows}
    </ol>{tip_html}
  </section>"""


def render_sections(day: dict) -> str:
    blocks = []
    for sec in day.get("sections", []):
        groups = []
        for src in sec.get("sources", []):
            if not src.get("items"):
                continue
            rows = []
            for idx, item in enumerate(src["items"], 1):
                title = esc(item.get("title"))
                url = item.get("url") or ""
                summary = item.get("summary") or ""
                meta_bits = [b for b in (item.get("hot"), item.get("time")) if b]
                meta = " · ".join(esc(b) for b in meta_bits)
                link = (
                    f'<a class="item-title" href="{esc(url)}" target="_blank" rel="noopener">{title}</a>'
                    if url else f'<span class="item-title">{title}</span>'
                )
                summary_html = f'\n            <p class="item-sum">{esc(summary)}</p>' if summary else ""
                rows.append(f"""        <li class="item" style="--i:{min(idx, 12)}">
          <span class="item-n">{idx:02d}</span>
          <div class="item-body">
            {link}{summary_html}
          </div>
          <span class="item-meta">{meta}</span>
        </li>""")
            groups.append(f"""      <div class="src">
        <h3 class="src-name">{esc(src['name'])}<span>{len(src['items'])}</span></h3>
        <ol class="item-list">
{chr(10).join(rows)}
        </ol>
      </div>""")
        if not groups:
            continue
        blocks.append(f"""  <section class="sec" data-reveal id="sec-{esc(sec['cat'])}">
    <div class="sec-head">
      <h2>{esc(sec['cat'])}</h2>
      <span class="sec-en">{esc(sec.get('en', ''))}</span>
      <span class="sec-count">{sec.get('count', 0)}</span>
    </div>
{chr(10).join(groups)}
  </section>""")
    return "\n".join(blocks)


def render_aside(days: list[dict], day: dict, depth: int) -> str:
    p = rel_prefix(depth)
    src_rows = []
    for sec in day.get("sections", []):
        for src in sec.get("sources", []):
            src_rows.append(
                f'<li><span>{esc(src["name"])}</span><b>{src.get("count", len(src.get("items", [])))}</b></li>'
            )
    stat = f"""<div class="card">
      <p class="card-title">今日来源<span class="mono">{len(src_rows)} SOURCES</span></p>
      <ul class="stat-list">
        {''.join(src_rows)}
      </ul>
    </div>"""

    recent = [d for d in days if d["date"] <= day["date"]][:8]
    day_rows = []
    for d in recent:
        active = ' class="is-current"' if d["date"] == day["date"] else ""
        day_rows.append(
            f'<li{active}><a href="{day_url(depth, d["date"])}">'
            f'<span class="d">{fmt_dot(d["date"])}</span>'
            f'<span class="w">{fmt_week(d["date"])}</span>'
            f'<span class="c">{d.get("stats", {}).get("total", 0)}</span></a></li>'
        )
    back = f"""<div class="card">
      <p class="card-title">往回翻<span class="mono">RECENT</span></p>
      <ul class="day-list">
        {''.join(day_rows)}
      </ul>
      <a class="card-link" href="{p}archive/">全部归档 →</a>
    </div>"""

    sub = f"""<div class="card card-quiet">
      <p class="card-title">订阅</p>
      <p class="card-p">把 <a href="{p}feed.xml">RSS</a> 丢进阅读器，每天 7 点更新。</p>
      <p class="card-p mono">更新于 {esc(day.get("generated_at", "")[11:16])}</p>
    </div>"""

    return f'<aside class="side">\n    {stat}\n    {back}\n    {sub}\n  </aside>'


# ------------------------------------------------------------------ 页面
def page_shell(title: str, description: str, depth: int, cfg: dict, body: str,
               active: str, canonical: str, extra_head: str = "") -> str:
    p = rel_prefix(depth)
    v = asset_version()
    theme = "light"
    return f"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="{theme}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<meta name="author" content="{esc(cfg['site'].get('author', ''))}">
<meta name="theme-color" content="#faf9f5">
<link rel="canonical" href="{esc(canonical)}">
<meta property="og:type" content="website">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:site_name" content="{esc(cfg['site']['title'])}">
<link rel="alternate" type="application/rss+xml" title="{esc(cfg['site']['title'])}" href="{p}feed.xml">
<link rel="icon" href="{p}assets/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="{p}assets/site.css?v={v}">
<script>
(function () {{
  try {{
    var t = localStorage.getItem('brief-theme');
    if (t !== 'dark' && t !== 'light') {{
      t = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }}
    document.documentElement.setAttribute('data-theme', t);
    document.documentElement.style.colorScheme = t;
  }} catch (e) {{}}
}})();
</script>
{extra_head}
</head>
<body>
<a class="skip" href="#main">跳到正文</a>
{render_topbar(depth, cfg, active)}
{body}
<script src="{p}assets/site.js?v={v}" defer></script>
</body>
</html>
"""


def render_day_page(day: dict, days: list[dict], cfg: dict, depth: int = 2) -> str:
    date_str = day["date"]
    stats = day.get("stats", {})
    index_today = [i for i, d in enumerate(days, 1) if d["date"] == date_str]
    issue = len(days) - (index_today[0] - 1) if index_today else 1
    newer = next((d for d in days if d["date"] > date_str), None)
    older = next((d for d in days if d["date"] < date_str), None)

    nav = []
    nav.append(
        f'<a class="daynav-prev" href="{day_url(depth, newer["date"])}" title="{fmt_cn(newer["date"])}">← {fmt_dot(newer["date"])}</a>'
        if newer else '<span class="daynav-prev is-off">← 最新</span>'
    )
    nav.append('<span class="daynav-sep" aria-hidden="true">/</span>')
    nav.append(
        f'<a class="daynav-next" href="{day_url(depth, older["date"])}" title="{fmt_cn(older["date"])}">{fmt_dot(older["date"])} →</a>'
        if older else '<span class="daynav-next is-off">最早 →</span>'
    )

    brief_bits = day.get("brief", {}).get("items") or []
    lead = brief_bits[0] if brief_bits else ""
    body = f"""<main class="wrap" id="main">
  <header class="masthead" data-reveal>
    <p class="kicker"><span>第 {issue:03d} 期</span><span class="dot"></span><span>{fmt_cn(date_str)} · {fmt_week(date_str)}</span><span class="dot"></span><span class="mono">ISSUE {date_str.replace('-', '')}</span></p>
    <h1 class="paper-title">{esc(cfg['site']['title'])}</h1>
    <p class="dek">今天收录 <b>{stats.get('total', 0)}</b> 条，来自 <b>{stats.get('sources', 0)}</b> 个来源。{esc(lead) and '<br>' + esc(lead[:46]) + ('…' if len(lead) > 46 else '')}</p>
    <div class="daynav">{''.join(nav)}</div>
  </header>

  <div class="layout">
    <div class="main-col">
      {render_brief(day.get('brief', {}))}
      {render_sections(day)}
    </div>
    {render_aside(days, day, depth)}
  </div>
</main>
{render_footer(cfg, day, depth)}"""

    title = f"{fmt_dot(date_str)} 新闻早报 · {stats.get('total', 0)} 条"
    desc = f"{fmt_cn(date_str)}的新闻汇总：{lead[:60]}" if lead else f"{fmt_cn(date_str)}的新闻汇总"
    base = cfg["site"]["home"].rstrip("/")
    canonical = base + "/" if depth == 0 else base + f"/day/{date_str}/"
    return page_shell(title, desc, depth, cfg, body, "today", canonical)


def render_archive(days: list[dict], cfg: dict) -> str:
    depth = 1
    months: dict[str, list[dict]] = {}
    for d in days:
        months.setdefault(d["date"][:7], []).append(d)

    blocks = []
    for month in sorted(months, reverse=True):
        rows = []
        for d in months[month]:
            titles = []
            for sec in d.get("sections", []):
                for src in sec.get("sources", []):
                    for item in src.get("items", [])[:2]:
                        titles.append(item.get("title", ""))
                if len(titles) >= 4:
                    break
            preview = " ／ ".join(t for t in titles[:3] if t)
            search_key = " ".join(
                item.get("title", "")
                for sec in d.get("sections", [])
                for src in sec.get("sources", [])
                for item in src.get("items", [])
            )[:600]
            rows.append(f"""      <li class="day-row" data-k="{esc(search_key)}">
        <a href="{day_url(depth, d['date'])}">
          <span class="dr-date"><b>{fmt_dot(d['date'])}</b><em>{fmt_week(d['date'])}</em></span>
          <span class="dr-body">
            <span class="dr-title">{esc(preview)}</span>
            <span class="dr-meta">{d.get('stats', {}).get('total', 0)} 条 · {d.get('stats', {}).get('sources', 0)} 个来源</span>
          </span>
          <span class="dr-go" aria-hidden="true">→</span>
        </a>
      </li>""")
        y, m = month.split("-")
        blocks.append(f"""  <section class="month" data-reveal>
    <h2 class="month-title">{y} 年 {int(m)} 月<span class="mono">{len(months[month])} DAYS</span></h2>
    <ul class="day-rows">
{chr(10).join(rows)}
    </ul>
  </section>""")

    body = f"""<main class="wrap" id="main">
  <header class="masthead masthead--archive" data-reveal>
    <p class="kicker"><span>ARCHIVE</span><span class="dot"></span><span>共 {len(days)} 天</span></p>
    <h1 class="paper-title">归档</h1>
    <p class="dek">从 {fmt_cn(days[-1]['date'])} 到今天，每天的早报都留在这里。</p>
    <div class="search">
      <input id="archive-search" type="search" placeholder="在往期标题里找找看…" autocomplete="off" aria-label="搜索往期标题">
      <span class="search-count" id="search-count"></span>
    </div>
  </header>
  <div class="months">
{chr(10).join(blocks)}
  </div>
  <p class="empty" id="archive-empty" hidden>没有匹配的日期，换个词试试。</p>
</main>
{render_footer(cfg, days[0], depth)}"""

    return page_shell("归档 · 新闻早报", f"共 {len(days)} 天的新闻早报存档", depth, cfg,
                      body, "archive", cfg["site"]["home"].rstrip("/") + "/archive/")


def render_404(cfg: dict) -> str:
    body = """<main class="wrap" id="main">
  <header class="masthead masthead--archive">
    <p class="kicker"><span>404</span><span class="dot"></span><span>NOT FOUND</span></p>
    <h1 class="paper-title">这一页不存在</h1>
    <p class="dek">大概是链接被改过了，或者那天的早报还没生成。</p>
    <p class="empty"><a href="./">回今天的早报</a> · <a href="archive/">翻归档</a></p>
  </header>
</main>"""
    return page_shell("页面不存在 · 新闻早报", "404", 0, cfg, body, "", cfg["site"]["home"])


def render_feed(days: list[dict], cfg: dict) -> str:
    items = []
    for d in days[:30]:
        lead = (d.get("brief", {}).get("items") or [""])[0]
        desc = f"{d.get('stats', {}).get('total', 0)} 条 · {lead}"
        link = cfg["site"]["home"].rstrip("/") + f"/day/{d['date']}/"
        pub = datetime.strptime(d["date"], "%Y-%m-%d").strftime("%a, %d %b %Y 00:00:00 +0800")
        items.append(f"""  <item>
    <title>{esc(fmt_dot(d['date']))} 新闻早报</title>
    <link>{esc(link)}</link>
    <guid isPermaLink="true">{esc(link)}</guid>
    <pubDate>{pub}</pubDate>
    <description>{esc(desc)}</description>
  </item>""")
    last = days[0]["date"] if days else now().strftime("%Y-%m-%d")
    pub = datetime.strptime(last, "%Y-%m-%d").strftime("%a, %d %b %Y 00:00:00 +0800")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>{esc(cfg['site']['title'])}</title>
  <link>{esc(cfg['site']['home'])}</link>
  <description>{esc(cfg['site']['description'])}</description>
  <language>zh-CN</language>
  <lastBuildDate>{pub}</lastBuildDate>
{chr(10).join(items)}
</channel>
</rss>
"""


# ------------------------------------------------------------------ 主流程
def build(clean: bool = False) -> None:
    cfg = load_config()
    days = read_days()
    if not days:
        log("data/ 里还没有任何一天的 JSON，先跑 fetch_news.py")
        return

    if clean and DOCS_DIR.exists():
        shutil.rmtree(DOCS_DIR)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    assets_src = WEB_DIR / "assets"
    assets_dst = DOCS_DIR / "assets"
    if assets_dst.exists():
        shutil.rmtree(assets_dst)
    shutil.copytree(assets_src, assets_dst)

    latest = days[0]
    (DOCS_DIR / "index.html").write_text(render_day_page(latest, days, cfg, depth=0), encoding="utf-8")

    for day in days:
        out = DOCS_DIR / "day" / day["date"] / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_day_page(day, days, cfg, depth=2), encoding="utf-8")

        data_out = DOCS_DIR / "day" / day["date"] / "data.json"
        write_json(data_out, day)

    # 数据里已经删掉的日期，页面也一并清掉
    day_root = DOCS_DIR / "day"
    keep = {d["date"] for d in days}
    removed = 0
    for child in sorted(day_root.iterdir()) if day_root.exists() else []:
        if child.is_dir() and child.name not in keep:
            shutil.rmtree(child)
            removed += 1
    if removed:
        log(f"清理了 {removed} 个已无数据的日期目录")

    archive_dir = DOCS_DIR / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / "index.html").write_text(render_archive(days, cfg), encoding="utf-8")

    (DOCS_DIR / "feed.xml").write_text(render_feed(days, cfg), encoding="utf-8")
    (DOCS_DIR / "404.html").write_text(render_404(cfg), encoding="utf-8")

    search_index = [
        {
            "date": d["date"],
            "total": d.get("stats", {}).get("total", 0),
            "items": [
                item.get("title", "")
                for sec in d.get("sections", [])
                for src in sec.get("sources", [])
                for item in src.get("items", [])
            ][:80],
        }
        for d in days[:120]
    ]
    write_json(DOCS_DIR / "search.json", search_index)

    (DOCS_DIR / ".nojekyll").write_text("", encoding="utf-8")
    (DOCS_DIR / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")

    total_items = sum(d.get("stats", {}).get("total", 0) for d in days)
    log(f"生成完成：{len(days)} 天 / {total_items} 条 → {DOCS_DIR.relative_to(DOCS_DIR.parent)}")


def main() -> None:
    ap = argparse.ArgumentParser(description="生成静态新闻站")
    ap.add_argument("--clean", action="store_true", help="清空 docs/ 后重建")
    args = ap.parse_args()
    build(clean=args.clean)


if __name__ == "__main__":
    main()
