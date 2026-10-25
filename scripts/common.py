"""公共工具：路径、时间、HTTP、文本清洗。"""

from __future__ import annotations

import html
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
WEB_DIR = ROOT / "web"
DOCS_DIR = ROOT / "docs"
CONFIG_PATH = ROOT / "config.json"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def tz() -> ZoneInfo:
    try:
        return ZoneInfo(load_config()["site"].get("timezone", "Asia/Shanghai"))
    except Exception:
        return ZoneInfo("Asia/Shanghai")


def now() -> datetime:
    return datetime.now(tz())


def log(msg: str) -> None:
    print(f"[{now().strftime('%H:%M:%S')}] {msg}", flush=True)


def http_get(url: str, timeout: int = 15, retries: int = 2, **kwargs):
    """带重试的 GET。超时/重试次数可用环境变量临时压低（CI 里很有用）。"""
    import requests

    timeout = int(os.environ.get("NEWS_HTTP_TIMEOUT", timeout))
    retries = int(os.environ.get("NEWS_HTTP_RETRIES", retries))

    headers = kwargs.pop("headers", {})
    headers.setdefault("User-Agent", UA)
    headers.setdefault("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
    last = None
    for i in range(retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout, **kwargs)
            if resp.status_code >= 400:
                raise RuntimeError(f"HTTP {resp.status_code}")
            return resp
        except Exception as exc:  # noqa: BLE001
            last = exc
            if i < retries:
                time.sleep(1.2 * (i + 1))
    raise RuntimeError(str(last))


_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


def clean_text(raw: str | None, limit: int = 0) -> str:
    if not raw:
        return ""
    text = html.unescape(raw)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = _SPACE_RE.sub(" ", text).strip()
    if limit and len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text


_NOISE_PATTERNS = [
    re.compile(r"^(?:查看全文|阅读原文|点击查看|查看更多|原文链接)[。.!！]?\s*$"),
    re.compile(r"\s*(?:查看全文|阅读原文|点击查看|查看更多)\s*$"),
    re.compile(r"^(?:\d{1,2}\s*月\s*\d{1,2}\s*日)[^，,。]{0,8}[，,：:]\s*"),
    re.compile(r"^(?:消息|快讯|据[^，。]{0,14}?(?:报道|消息|获悉))[，,：:]\s*"),
    re.compile(r"Matrix首页推荐.*?挑选[^。]*。\s*"),
]

_BOILERPLATE = re.compile(
    r"^(?:文章代表作者个人观点|本文仅代表作者|版权归原作者所有|转载请注明|点击查看原文)"
)


def tidy_summary(text: str, source: str = "") -> str:
    """去掉各站摘要里的固定开头/尾巴，剩下的才是正文。"""
    out = (text or "").strip()
    if not out:
        return ""
    if source:
        out = re.sub(rf"^{re.escape(source)}\s*(?:讯|消息|报道)?[，,：:]?\s*", "", out)
    prev = None
    while prev != out:
        prev = out
        for pat in _NOISE_PATTERNS:
            out = pat.sub("", out).strip()
        out = re.sub(r"^[\s|·・\-—:：]+", "", out)

    if len(out) < 6 or _BOILERPLATE.match(out):
        return ""
    return out


def parse_time(value: str | None):
    """RSS 的 pubDate / Atom 的 updated 统一成东八区时间。"""
    if not value:
        return None
    text = value.strip()
    fmts = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in fmts:
        try:
            dt = datetime.strptime(text, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=tz())
            return dt.astimezone(tz())
        except ValueError:
            continue
    return None


def read_json(path: Path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp, path)


def die(msg: str) -> None:
    print(f"[x] {msg}", file=sys.stderr)
    sys.exit(1)
