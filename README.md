# cotc-daily-news

定时爬取指定资讯源、整理成统一格式并推送至飞书群机器人。一期实现「每日 AI 资讯」的爬取与飞书推送，后续可扩展其他资讯类型。

---

## 项目定位

- **独立项目**：与 COTC 主仓同级，可单独部署、独立演进，不依赖 COTC 其他子项目。
- **资讯聚合**：多数据源、多类型资讯（先 AI 资讯，后可按需增加其它品类）。
- **推送**：通过飞书自定义机器人 Webhook 发送纯文本到群；配置方式与 [cotc-server-python](../cotc-server-python) 一致（`--env-file` 注入 `.env`）。

---

## 目录结构

```
cotc-daily-news/
├── README.md
├── docs/
│   ├── 01-daily-ai-news.md   # 一期：需求与实现设计
│   └── 02-推送消息到openclaw-qq-小龙虾.md
├── requirements.txt
├── .env.example              # 复制为 .env 并填写 FEISHU_WEBHOOK_URL
├── Dockerfile
├── Jenkinsfile               # 仅构建镜像，不启动常驻容器
├── .dockerignore
├── src/
│   ├── __init__.py
│   ├── main.py               # 入口：爬取 → 格式化 → 飞书推送
│   ├── ai_news/
│   │   ├── __init__.py
│   │   ├── crawler.py
│   │   ├── formatter.py
│   │   └── config.py
│   └── common/
│       ├── __init__.py
│       └── feishu.py         # 飞书 Webhook 发送纯文本
```

---

## 一期：每日 AI 资讯

- **数据来源**：<https://ai-bot.cn/daily-ai-news/>
- **内容范围**：每天 14:00 定时任务跑时，抓取**前一天**的日期分组下的所有条目，最多 **5 条**。
- **每条包含**：标题、摘要、日期标签、来源、详情页 URL。
- **输出**：整理为纯文本后推送至飞书群（不写本地文件）。

详见 [docs/01-daily-ai-news.md](docs/01-daily-ai-news.md)。

---

## 配置

复制 `.env.example` 为 `.env`，填写飞书机器人 Webhook：

```bash
cp .env.example .env
# 编辑 .env，填入 FEISHU_WEBHOOK_URL（飞书群 → 设置 → 群机器人 → 自定义机器人 → 复制 Webhook 地址）
```

---

## 本地运行

与 [cotc-server-python](../cotc-server-python) 一致，建议使用虚拟环境：

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows PowerShell
pip install -r requirements.txt
# 设置环境变量或使用 .env（需自行 load），例如：
# $env:FEISHU_WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
python -m src.main
```

---

## Docker 部署（CentOS 服务器）

### 构建镜像

在项目根目录（或通过 Jenkins 执行 `cotc-daily-news` 的 Jenkinsfile）：

```bash
cd cotc-daily-news
docker build -t cotc-daily-news:latest .
```

### 服务器路径与 .env

- 代码与 `.env` 放在 **`/usr/share/nginx/cotc-daily-news`**（与 cotc-server-python 类似，使用 `--env-file` 注入变量，不挂载 .env 文件）。
- 确保该目录下有 `.env`，且包含 `FEISHU_WEBHOOK_URL=...`。

### 定时任务（cron 每天 14:00）

服务器时区需为 **Asia/Shanghai**。添加 crontab：

```bash
crontab -e
# 添加一行（每天 14:00 执行一次）：
0 14 * * * docker run --rm --env-file /usr/share/nginx/cotc-daily-news/.env cotc-daily-news:latest
```

- `--rm`：跑完即删容器；镜像保留，下次 cron 再起新容器。
- 若 Jenkins 与 cron 不在同一台机，需在部署机先 `docker pull` 或本地 `docker build` 后再用上述命令。

---

## Jenkins

仓库中的 `Jenkinsfile` 仅做 **构建镜像**（Checkout + Build Image + Cleanup），不启动常驻容器。部署机在构建完成后，由 cron 按点执行 `docker run --rm ...` 即可。

---

## 技术栈与依赖

- **语言**：Python 3.11（Docker 使用 `python:3.11-slim`，与 cotc-server-python 一致）
- **依赖**：`requests`、`beautifulsoup4`（见 `requirements.txt`）

---

## 注意事项

- 爬取频率：仅定时每日一次，避免对目标站造成压力。
- 合规：仅做个人/内部使用，尊重目标站版权与使用条款；后续若商用需自行评估。
- 飞书 Webhook 请勿提交到仓库，仅通过 `.env` 与 `--env-file` 使用。
