# 新闻早报 · auto_news

每天 7:00 自动抓取新闻源，生成一个静态页面，推到 GitHub Pages。
数据逐日留档，历史不会丢；页面只是 `data/` 的渲染结果，随时可以整站重建。

线上地址：<https://allureluoli.github.io/auto_news/>
（项目页继承了账号的自定义域名，<https://blog.curesky.site/auto_news/> 同样可用）

![预览](preview.png)

---

## 它长什么样

- 报头：期号、日期、当日条数，前一天 / 后一天切换
- 每日 60 秒：15 条国内要闻，双栏排版，末尾一句隽语
- 三个板块：科技资讯 / 技术社区 / 热点，按来源分组，条目标题可跳转原文
- 侧栏：今日来源计数、往回翻 8 天、RSS 订阅
- 归档页：按月分组 + 标题搜索（`/` 快速聚焦）
- 深浅色自动跟随系统，可手动切换并记住

设计沿用博客那套：暖纸底、墨色正文、单一朱砂强调色、发丝边框，没有渐变和光晕。

## 目录结构

```
auto_news/
├── config.json              # 站名、来源列表、每条抓多少
├── requirements.txt         # 只有 requests
├── data/                    # 每日原始数据（唯一真相，永久保留）
│   └── 2026-10-25.json
├── docs/                    # 生成的静态站（GitHub Pages 发布目录）
│   ├── index.html           # 最新一天
│   ├── day/2026-10-25/      # 每一天一页 + data.json
│   ├── archive/             # 归档 + 搜索
│   ├── assets/              # site.css / site.js
│   ├── feed.xml             # RSS
│   └── search.json
├── scripts/
│   ├── fetch_news.py        # 抓取 → data/
│   ├── build_site.py        # data/ → docs/
│   ├── publish.py           # 抓取 + 生成 + 提交推送（定时任务跑这个）
│   ├── sources.py           # 各来源的抓取实现
│   └── common.py            # 工具函数
└── web/assets/              # 样式与脚本源文件（构建时复制进 docs/）
```

## 本地跑一遍

```bash
pip install -r requirements.txt

python scripts/fetch_news.py        # 抓今天的新闻 → data/2026-10-25.json
python scripts/build_site.py        # 生成 → docs/
python -m http.server 4321 -d docs  # 打开 http://127.0.0.1:4321
```

只想看站点长什么样、不抓数据：

```bash
python scripts/build_site.py
```

## 首次发布

在 GitHub 上新建 **public** 仓库 `allureluoli/auto_news`（Pages 免费版要求公开仓库），然后：

```bash
cd auto_news
git init -b main
git add -A
git commit -m "init: daily news site"
git remote add origin https://github.com/allureluoli/auto_news.git
git push -u origin main
```

**开启 Pages**：仓库 Settings → Pages → Build and deployment → Source 选 `Deploy from a branch`，分支 `main`，目录 **`/docs`**，保存。
首次构建约 1 分钟，之后每次 `git push` 都会自动重新发布。

## 放到 VPS 上每天自动跑

```bash
# 1. 拉仓库
git clone https://github.com/allureluoli/auto_news.git
cd auto_news

# 2. 装依赖（建议给个独立虚拟环境）
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# 3. 先手动跑一次，确认抓取和推送都正常
GITHUB_TOKEN=ghp_xxxx python scripts/publish.py
```

### 定时任务

`crontab -e`：

```cron
# 每天 07:00（服务器为北京时间时）
0 7 * * * cd /root/auto_news && GITHUB_TOKEN=ghp_xxxx /root/auto_news/.venv/bin/python scripts/publish.py >> /var/log/auto_news.log 2>&1

# 如果服务器是 UTC 时区，用下面这行代替
0 23 * * * cd /root/auto_news && CRON_TZ=Asia/Shanghai ...
```

> 时区不确定就跑 `date` 看一眼；也可以整条命令前加 `TZ=Asia/Shanghai`。

### 推送认证，三种方式任选

| 方式 | 做法 | 适用 |
|---|---|---|
| **Token（最省事）** | 生成一个 fine-grained PAT，只勾选 `auto_news` 仓库的 **Contents: Read and write**，作为 `GITHUB_TOKEN` 环境变量传入 | VPS、临时机器 |
| SSH deploy key | `ssh-keygen -t ed25519 -C auto_news`，把公钥加到仓库 Settings → Deploy keys（勾 Allow write） | 长期跑的机器，最安全 |
| remote 带凭据 | `git remote set-url origin https://<user>:<token>@github.com/allureluoli/auto_news.git` | 图省事但 token 会落盘 |

`publish.py` 的行为：环境里有 `GITHUB_TOKEN` 就走临时 URL 推送（不写进 `.git/config`），没有就用现有 remote（SSH / 凭据助手）。

### 推送成功后

- Pages 一般 30 秒内更新
- 没有变化时不会产生空提交
- 抓取全部失败时默认不写数据、不提交（加 `--strict` 才会中断退出，方便监控报警）

## 不部署 VPS：全在 GitHub 上跑

仓库自带 `.github/workflows/daily.yml`，Actions 每天自己抓、自己提交、Pages 自动重新发布，**不需要任何服务器**。

开启步骤：

1. 仓库 Settings → **Actions → General → Workflow permissions** 选 **Read and write permissions**（否则 bot 推不上去）
2. Settings → **Pages** → Source: `Deploy from a branch` → `main` / **`/docs`**
3. Actions 标签页 → 左侧 `daily-news` → **Run workflow** 手动跑一次，确认能出报

跑完 Actions 里会有一行 commit（`news: 2026-10-25`），Pages 30 秒后更新。免费额度：私有仓库 2000 分钟/月，这个任务一次约 1 分钟，**一天 1 分钟，一个月 30 分钟**。

### 需要知道的三个坑

| 坑 | 说明 | 对策 |
|---|---|---|
| **国内接口** | 首次实测（2026-10-25，GitHub 官方 runner）：**10 个源全部抓通**，知乎 / 百度 / 微博 / 60s 都没问题 | 之后若某个源开始 403 或超时，抓不到会自动跳过，页面照常生成；要补全就加 `NEWS_PROXY` |
| **定时不准** | GitHub 的 cron 高峰期会延迟 5~30 分钟，极端情况当天跳过 | 早报对分钟不敏感；要准点就配 VPS |
| **中文源为空** | 连续几天某个源都是 0，说明被区域限制 | 改 `config.json` 换源，或加代理 |

### 可选：给 Actions 配代理

Settings → Secrets and variables → Actions → New repository secret，名字 `NEWS_PROXY`，值形如 `http://user:pass@host:port`。
Workflow 会把 `HTTP_PROXY` / `HTTPS_PROXY` 传进去，抓取脚本自动走代理，不用改代码。没配也不影响。

### 代理要不要配？怎么判断

手动跑一次 workflow，看日志里每个源那一行：`IT之家  8 条  447ms` 这种是好的，`失败 HTTP 403` / `timed out` 就是不通。
再跑 `python scripts/fetch_news.py --check`（可以临时加一个 step 跑它）能一次性列出全部源的连通性。

## 两种方案怎么选

| | 纯 GitHub Actions | VPS 定时 |
|---|---|---|
| 成本 | 免费 | 一台机器常驻 |
| 准点 | ±30 分钟，偶尔跳过 | 准 |
| 国内源 | 可能拿不全 | 全（尤其你机器上有代理时） |
| 维护 | 什么都不用管 | 机器、依赖、日志 |

建议：**先只用 Actions**，跑一周看日志里哪些源稳定；哪天嫌国内源缺得多了，再在 VPS 上 `git clone` 一份、加 cron，两边用同一天的数据，脚本会**沿用上一次已抓到的源**，不会互相清空。

## 常用命令

```bash
python scripts/publish.py                  # 抓今天 + 生成 + 推送
python scripts/publish.py --no-push        # 只生成，不推送
python scripts/publish.py --rebuild        # 不抓取，按现有 data/ 重建
python scripts/publish.py --date 2026-09-01   # 补抓某一天python scripts/build_site.py --clean       # 清空 docs/ 重来
python scripts/fetch_news.py --check       # 只测连通性，各源能用不能用
```

## 数据怎么保留

- 每天一个 `data/YYYY-MM-DD.json`，只追加、不覆盖历史
- `docs/` 每次由 `data/` **全量重建**，所以改样式、改排版后 `--rebuild` 一下，历史页面全部跟着更新
- 想删某一天：删掉对应的 `data/*.json` 再重建即可
- 想接别的消费端（小程序、机器人、API）：直接读 `docs/day/<date>/data.json`

## 自定义

`config.json`：

```jsonc
{
  "site": {
    "title": "新闻早报",
    "subtitle": "DAILY BRIEF",
    "description": "……",
    "home": "https://allureluoli.github.io/auto_news/",   // 用于 RSS / canonical
    "timezone": "Asia/Shanghai"
  },
  "sources": [
    { "name": "IT之家", "kind": "rss", "url": "https://www.ithome.com/rss/", "cat": "科技资讯", "limit": 8 }
  ]
}
```

- `kind` 支持：`rss`、`github`（Trending）、`hn`、`zhihu`、`sixty`（60s API 的热榜）
- `cat` 相同的来源会合并进同一个板块；`optional: true` 表示抓不到就静默跳过
- 换域名：把 `site.home` 改成新域名，重建即可（站内链接都是相对路径，不依赖它）

## 同一天重复跑会怎样

不会把已有数据弄丢：某个源这次没抓到、但上一次抓到过，脚本会沿用上一次的结果并记一条日志。
想强制整份覆盖就加 `--fresh`。

VPS 和 GitHub Actions 同时开着也不会互相清空数据，谁跑都行。

## 常见问题

**某个源抓不到？** 跑 `python scripts/fetch_news.py --check` 看是哪一家，多半是对方改了接口或被墙。改 `config.json` 换源即可，页面不会因为少一个源而坏掉。

**60s 接口返回 429？** 它对短时间高频请求有限流，脚本里已经加了间隔；手动反复调试时等一下再跑。

**页面是空的 / 只有一天？** 只跑过 `fetch_news.py` 没跑 `build_site.py`，或者 `docs/` 被清过。重建即可。

**中文字体不好看？** 页面走系统字体（苹方 / 微软雅黑 / 思源），没有外链字体，不拖慢首屏。
