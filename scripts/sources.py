"""新闻源抓取：把各家 RSS / 接口 / 页面统一成同一结构的条目。

统一条目：
    {"title": str, "url": str, "summary": str, "time": "HH:MM" | "", "hot": str}
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from html import unescape

from common import clean_text, http_get, log, now, parse_time

SIXTY_BASE = "https://60s.viki.moe"


# ---------------------------------------------------------------- RSS / Atom
def _strip_ns(tag: str) -> str:
    return tag.split("}")[-1].lower()


_BARE_AMP = re.compile(r"&(?!(?:#\d+|#x[0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]*);)")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def sanitize_xml(content: bytes) -> bytes:
    """有的源会带裸 & 或控制字符，先修一遍再解析。"""
    if content[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = content.decode("utf-16", "replace")
    else:
        text = content.decode("utf-8", "replace")
    text = _CTRL.sub("", text)
    text = _BARE_AMP.sub("&amp;", text)
    return text.encode("utf-8")


def parse_feed(content: bytes) -> list[dict]:
    root = ET.fromstring(sanitize_xml(content))
    items: list[dict] = []
    for node in root.iter():
        if _strip_ns(node.tag) not in ("item", "entry"):
            continue
        title = link = summary = published = ""
        alt_link = ""
        for child in node:
            tag = _strip_ns(child.tag)
            if tag == "title":
                title = child.text or ""
            elif tag == "link":
                href = (child.text or "").strip() or child.attrib.get("href", "")
                rel = (child.attrib.get("rel") or "alternate").lower()
                if rel in ("self", "replies", "edit"):
                    continue
                if not alt_link:
                    alt_link = href
            elif tag in ("description", "summary", "content", "encoded"):
                if not summary:
                    summary = child.text or ""
            elif tag in ("pubdate", "published", "updated", "date"):
                if not published:
                    published = child.text or ""
        title = clean_text(title)
        if not title:
            continue
        dt = parse_time(published)
        items.append({
            "title": title,
            "url": alt_link.strip(),
            "summary": clean_text(summary, 120),
            "time": dt.strftime("%H:%M") if dt else "",
            "hot": "",
            "_ts": dt.timestamp() if dt else 0,
        })
    return items


def fetch_rss(src: dict) -> list[dict]:
    resp = http_get(src["url"], timeout=18)
    items = parse_feed(resp.content)[: int(src.get("limit", 8))]
    items.sort(key=lambda x: x.get("_ts", 0), reverse=True)
    return items


# ---------------------------------------------------------------- GitHub Trending
_REPO_RE = re.compile(r'<h2[^>]*>\s*<a[^>]*href="/([^"]+)"', re.S)
_DESC_RE = re.compile(r'<p[^>]*class="[^"]*col-9[^"]*"[^>]*>(.*?)</p>', re.S)
_STARS_RE = re.compile(r'(\d[\d,]*)\s+stars?\s+today', re.I)
_LANG_RE = re.compile(r'itemprop="programmingLanguage">([^<]+)<')


def fetch_github(src: dict) -> list[dict]:
    resp = http_get("https://github.com/trending?since=daily", timeout=20)
    html = resp.text
    blocks = re.split(r'<article class="Box-row', html)[1:]
    out: list[dict] = []
    for block in blocks[: int(src.get("limit", 8))]:
        m = _REPO_RE.search(block)
        if not m:
            continue
        repo = m.group(1).strip()
        d = _DESC_RE.search(block)
        desc = clean_text(unescape(d.group(1)), 110) if d else ""
        stars = ""
        sm = _STARS_RE.search(block)
        if sm:
            stars = f"+{sm.group(1)}"
        lang = ""
        lm = _LANG_RE.search(block)
        if lm:
            lang = unescape(lm.group(1)).strip()
        bits = [b for b in (lang, stars and f"{stars} stars today") if b]
        out.append({
            "title": repo,
            "url": f"https://github.com/{repo}",
            "summary": desc,
            "time": "",
            "hot": " · ".join(bits),
        })
    return out


# ---------------------------------------------------------------- Hacker News
def fetch_hn(src: dict) -> list[dict]:
    """HN 官方 RSS 会偶尔 419，直接用 Algolia 首页接口。"""
    resp = http_get(
        "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=20",
        timeout=18,
        headers={"Accept": "application/json"},
    )
    hits = resp.json().get("hits", [])[: int(src.get("limit", 8))]
    out: list[dict] = []
    for hit in hits:
        title = clean_text(hit.get("title") or hit.get("story_title") or "")
        if not title:
            continue
        url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
        points = hit.get("points") or 0
        comments = hit.get("num_comments") or 0
        dt = parse_time(hit.get("created_at"))
        out.append({
            "title": title,
            "url": url,
            "summary": clean_text(hit.get("story_text") or "", 110),
            "time": dt.strftime("%H:%M") if dt else "",
            "hot": f"{points} 分 · {comments} 评论",
        })
    return out


# ---------------------------------------------------------------- 知乎热榜
def fetch_zhihu(src: dict) -> list[dict]:
    resp = http_get(
        "https://api.zhihu.com/topstory/hot-list?limit=20",
        timeout=15,
        headers={"Accept": "application/json"},
    )
    data = resp.json().get("data", [])
    out: list[dict] = []
    for rank, item in enumerate(data[: int(src.get("limit", 8))], 1):
        target = item.get("target") or {}
        title = clean_text(target.get("title") or item.get("title") or "")
        if not title:
            continue
        qid = target.get("id") or ""
        url = f"https://www.zhihu.com/question/{qid}" if qid else ""
        excerpt = clean_text(target.get("excerpt") or "", 110)
        out.append({
            "title": title,
            "url": url,
            "summary": excerpt,
            "time": "",
            "hot": f"热度 {rank}",
        })
    return out


# ---------------------------------------------------------------- 60s 热榜
def fetch_sixty(src: dict) -> list[dict]:
    endpoint = src["endpoint"]
    resp = http_get(f"{SIXTY_BASE}{endpoint}", timeout=18)
    try:
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"返回非 JSON（{exc}）") from exc
    if payload.get("code") != 200:
        raise RuntimeError(f"接口 code={payload.get('code')}")
    data = payload.get("data")
    rows: list = []
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        for key in ("news", "data", "items", "list"):
            if isinstance(data.get(key), list):
                rows = data[key]
                break
    out: list[dict] = []
    for row in rows[: int(src.get("limit", 8))]:
        if isinstance(row, str):
            out.append({"title": clean_text(row), "url": "", "summary": "", "time": "", "hot": ""})
            continue
        if not isinstance(row, dict):
            continue
        title = clean_text(row.get("title") or row.get("name") or "")
        if not title:
            continue
        hot = row.get("score_desc") or row.get("hot_value") or row.get("hot") or ""
        if isinstance(hot, int):
            hot = f"{hot / 10000:.1f}w" if hot >= 10000 else str(hot)
        out.append({
            "title": title,
            "url": row.get("url") or row.get("link") or "",
            "summary": clean_text(row.get("desc") or row.get("detail") or "", 120),
            "time": "",
            "hot": str(hot),
        })
    return out


# ---------------------------------------------------------------- 每日 60 秒
def fetch_brief() -> dict:
    resp = http_get(f"{SIXTY_BASE}/v2/60s", timeout=18)
    payload = resp.json()
    if payload.get("code") != 200:
        raise RuntimeError(f"60s code={payload.get('code')}")
    data = payload.get("data") or {}
    news = [clean_text(n) for n in (data.get("news") or []) if clean_text(n)]
    return {
        "date": data.get("date", ""),
        "tip": clean_text(data.get("tip") or ""),
        "items": news,
    }


KINDS = {
    "rss": fetch_rss,
    "github": fetch_github,
    "hn": fetch_hn,
    "zhihu": fetch_zhihu,
    "sixty": fetch_sixty,
}


def fetch_source(src: dict, delay: float = 0.0) -> dict:
    fn = KINDS.get(src["kind"])
    if not fn:
        return {"name": src["name"], "cat": src["cat"], "items": [], "error": f"未知类型 {src['kind']}"}
    if delay:
        time.sleep(delay)
    t0 = time.time()
    try:
        items = fn(src)
        items = [i for i in items if i.get("title")]
        for it in items:
            it.pop("_ts", None)
        log(f"{src['name']:<14} {len(items):>2} 条  {int((time.time() - t0) * 1000)}ms")
        return {"name": src["name"], "cat": src["cat"], "items": items, "error": ""}
    except Exception as exc:  # noqa: BLE001
        log(f"{src['name']:<14} 失败  {exc}")
        return {"name": src["name"], "cat": src["cat"], "items": [], "error": str(exc)[:160]}


def fetch_all(config: dict) -> tuple[list[dict], dict, list[str]]:
    """抓取全部来源，返回 (按分类分组的来源列表, 60s 简报, 错误列表)。"""
    sources = config.get("sources", [])
    results: list[dict] = []
    errors: list[str] = []
    for idx, src in enumerate(sources):
        res = fetch_source(src, delay=0.8 if src["kind"] == "sixty" and idx else 0)
        if res["error"]:
            errors.append(f"{res['name']}: {res['error']}")
            if src.get("optional"):
                continue
        results.append(res)

    brief = {"date": "", "tip": "", "items": []}
    try:
        brief = fetch_brief()
        log(f"{'每日 60 秒':<14} {len(brief['items']):>2} 条")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"每日 60 秒: {exc}")
        log(f"{'每日 60 秒':<14} 失败  {exc}")

    return results, brief, errors
