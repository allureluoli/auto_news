"""抓取 → 生成 → 提交推送。VPS 上定时跑这一个脚本就够了。

用法：
    python scripts/publish.py                 # 抓今天、生成、推送
    python scripts/publish.py --no-push       # 只抓取和生成，本地看效果
    python scripts/publish.py --date 2026-10-24   # 补某一天的历史
    python scripts/publish.py --rebuild       # 不抓取，只按现有数据重建页面

认证（三选一，按优先级）：
    1. 环境变量 GITHUB_TOKEN=ghp_xxx   → 用 https 临时 token 推送，不写进 git 配置
    2. 仓库已配置 SSH deploy key       → 直接用 git push
    3. 仓库 remote 里带好了凭据        → 直接用 git push
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from common import DOCS_DIR, ROOT, load_config, log, read_json

PY = sys.executable


def run(cmd: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        check=check,
        text=True,
        capture_output=capture,
    )


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run(["git", *args], check=check, capture=True)


def is_repo() -> bool:
    try:
        git("rev-parse", "--is-inside-work-tree")
        return True
    except Exception:
        return False


def ensure_repo() -> None:
    if not is_repo():
        raise SystemExit("当前目录不是 git 仓库：请先 clone auto_news 仓库，或加 --no-push 只做本地生成")


def fetch(date_str: str | None, strict: bool) -> bool:
    cmd = [PY, "scripts/fetch_news.py"]
    if date_str:
        cmd += ["--date", date_str]
    if strict:
        cmd += ["--strict"]
    log("① 抓取新闻")
    return run(cmd, check=False).returncode == 0


def build(clean: bool = False) -> None:
    log("② 生成页面")
    cmd = [PY, "scripts/build_site.py"]
    if clean:
        cmd.append("--clean")
    run(cmd)


def push(date_str: str, total: int, no_push: bool) -> None:
    if not is_repo():
        log("④ 不在 git 仓库里，跳过提交（页面已生成在 docs/）")
        return

    status = git("status", "--porcelain").stdout.strip()
    if not status:
        log("④ 没有变化，跳过提交")
        return

    log("④ 提交并推送")
    git("add", "-A")
    git("commit", "-m", f"news: {date_str} · {total} 条")

    if no_push:
        log("已提交到本地（--no-push，未推送）")
        return

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        cfg = load_config()
        repo = cfg["site"]["repo"].rstrip("/").replace("https://github.com/", "")
        url = f"https://x-access-token:{token}@github.com/{repo}.git"
        result = run(["git", "push", url, "HEAD:main"], check=False, capture=True)
        if result.returncode != 0:
            log("推送失败：" + (result.stderr or result.stdout).strip()[:400])
            raise SystemExit(1)
    else:
        result = run(["git", "push"], check=False, capture=True)
        if result.returncode != 0:
            log("推送失败：" + (result.stderr or result.stdout).strip()[:400])
            raise SystemExit(1)
    log("已推送，GitHub Pages 大约 30 秒后更新")


def main() -> None:
    ap = argparse.ArgumentParser(description="新闻早报：抓取 + 生成 + 发布")
    ap.add_argument("--date", help="指定日期 YYYY-MM-DD（默认今天）")
    ap.add_argument("--no-push", action="store_true", help="只生成，不推送")
    ap.add_argument("--rebuild", action="store_true", help="跳过抓取，只重建页面")
    ap.add_argument("--clean", action="store_true", help="重建前清空 docs/")
    ap.add_argument("--strict", action="store_true", help="抓取全失败时中断")
    args = ap.parse_args()

    if args.no_push:
        if not is_repo():
            log("提示：当前不是 git 仓库，按 --no-push 只做本地生成")
    else:
        ensure_repo()

    if args.rebuild:
        log("跳过抓取，直接重建")
    else:
        ok = fetch(args.date, args.strict)
        if not ok and args.strict:
            raise SystemExit("抓取失败")

    build(clean=args.clean)

    # 取最新一天的信息做提交信息
    days = sorted(DOCS_DIR.glob("day/*/data.json"))
    if not days:
        raise SystemExit("docs/ 里没有数据，构建可能失败了")
    latest = read_json(days[-1], {}) or {}
    date_str = latest.get("date", args.date or "")
    total = (latest.get("stats") or {}).get("total", 0)

    push(date_str, total, args.no_push)
    log(f"完成：{date_str} · {total} 条")


if __name__ == "__main__":
    main()
