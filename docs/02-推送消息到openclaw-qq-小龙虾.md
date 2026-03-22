# 推送消息到openclaw-qq-小龙虾

按顺序完成以下步骤，即可实现「每日 AI 资讯」通过小龙虾推送到 QQ（方案 A：文件 + 宿主机 cron）。

![QQ小龙虾推送每日资讯](https://i.mji.rip/2026/03/22/6b8a41861924bfd4a027ac1ebca25908.png)

---

## 前置条件

- 服务器已安装 Docker、Docker Compose v2
- 服务器时区为 `Asia/Shanghai`（与现有 cotc-daily-news cron 一致）
- 已有 cotc-daily-news 项目在 `/usr/share/nginx/server/cotc-daily-news` 并正常跑飞书推送

---

## 第一步：在服务器上部署 OpenClaw（Docker）

以下为**实际采用的操作步骤**：使用预构建镜像 + 持久化目录，避免本机 build 导致 OOM（2C4G 等小内存机器）。若你机器内存充足且希望从源码构建，可参考文末「踩坑与解决记录」中的说明。

1. **先做持久化目录（配置不丢）**

   在服务器上执行，与 cotc-daily-news 同机同层级，便于维护：

   ```bash
   mkdir -p /usr/share/nginx/server/openclaw/data
   mkdir -p /usr/share/nginx/server/openclaw/workspace
   ```

2. **用预构建镜像启动 OpenClaw**

   ```bash
   docker run -d \
     --name openclaw-gateway \
     --restart unless-stopped \
     -v /usr/share/nginx/server/openclaw/data:/root/.openclaw \
     -v /usr/share/nginx/server/openclaw/workspace:/root/workspace \
     -p 18789:18789 \
     -p 18791:18791 \
     swr.cn-north-4.myhuaweicloud.com/ddn-k8s/ghcr.io/openclaw/openclaw:latest
   ```

   确认在跑：

   ```bash
   docker ps | grep openclaw
   ```

3. **拿到网关 token（用于配对 / 控制台）**

   - **从控制台链接取**  
     ```bash
     docker exec openclaw-gateway openclaw dashboard --no-open
     ```  
     输出里会有一条带 token 的 URL，token 即 URL 中 `#token=` 后面的那串字符。

4. **完成配对（无桌面时用 TUI，全在 SSH 里操作）**

   - **若用本机浏览器**：先做 SSH 端口转发（**必须同时映射 18789 和 18791**），再打开控制台给出的带 token 的链接：
     ```bash
     # 在本机执行
     ssh -L 18789:127.0.0.1:18789 -L 18791:127.0.0.1:18791 root@你的服务器
     ```

   - **若服务器无桌面，用 TUI**：在同一 SSH 会话里执行（需交互式终端）：
     ```bash
     docker exec -it openclaw-gateway openclaw tui --url ws://127.0.0.1:18789 --token "你上一步拿到的token"
     ```

5. **安全建议（必读）**

   - 不要将 18789、18791 暴露到公网（仅 `127.0.0.1` 或内网）。
   - 若需远程管理，用 Nginx 反向代理 + HTTPS + 鉴权，并限制 IP。

---

## 第二步：在 OpenClaw 中配置 QQ 小龙虾通道

以下命令按「第一步用预构建镜像、容器名为 `openclaw-gateway`」的方式书写，均在**宿主机**执行，通过 `docker exec openclaw-gateway openclaw ...` 调用 CLI。

1. **在 QQ 开放平台创建机器人并获取 token**

   - 打开：<https://q.qq.com/qqbot/openclaw/login.html>
   - 按页面流程创建/登录，获取 **token**（或 AppID:AppSecret，以页面说明为准）。

2. **安装 QQ Bot 插件**

   ```bash
   docker exec openclaw-gateway openclaw plugins install @sliverp/qqbot@latest
   ```

   若依赖安装报错或超时，见文末「踩坑与解决记录」第 5 条：先删掉已有 qqbot 目录，再用国内 npm 源重装。

3. **添加 QQ 通道**

   ```bash
   docker exec openclaw-gateway openclaw channels add --channel qqbot --token "这里粘贴你的 token"
   ```

4. **重启 Gateway 使通道生效**

   ```bash
   docker restart openclaw-gateway
   ```

---

## 第三步：确定 QQ 推送目标（target）

要定时把每日资讯发到「哪个 QQ 群或哪个私聊」，需要知道对应的 **target**。

- **私聊（C2C）** 格式：`qqbot:c2c:<用户 openid>`（**冒号之间不能有空格**）
- **群聊** 格式：`qqbot:group:<群 openid>`（同样无空格）

**如何获取你的 openid：**

1. 用你的 QQ 给小龙虾机器人发一条消息（如「你好」），确保该 QQ 已在 QQ 开放平台沙箱中加为测试用户。
2. 在服务器上执行：`docker logs openclaw-gateway --tail 200`
3. 在日志里搜索 `Processing message from`，后面紧跟的那串即该私聊的 openid，例如：
   ```text
   [qqbot] [qqbot:default] Processing message from E3E164A8E23D16F691F59DDCED354F5B: 你好
   ```
   则你的私聊 target 为：`qqbot:c2c:E3E164A8E23D16F691F59DDCED354F5B`。

也可在 QQ 开放平台 / 开发者后台的「测试用户」或机器人所在群列表中查看 openid。

把得到的 target 记下来，例如：`QQ_TARGET="qqbot:c2c:E3E164A8E23D16F691F59DDCED354F5B"`，下一步写脚本和 cron 时会用到。

---

## 第四步：让 cotc-daily-news 把内容写入宿主机文件

1. **在宿主机上创建供 cotc-daily-news 写入的目录**

   ```bash
   sudo mkdir -p /usr/share/nginx/server/cotc-daily-news/output
   sudo chown -R $USER:$USER /usr/share/nginx/server/cotc-daily-news/output
   ```

2. **在 .env 中增加 OpenClaw 写文件配置**

   编辑 `/usr/share/nginx/server/cotc-daily-news/.env`，新增一行（路径为**容器内**路径，对应下面挂载的 `/output`）：

   ```bash
   OPENCLAW_MESSAGE_FILE=/output/news.txt
   ```

3. **重新构建 cotc-daily-news 镜像（若代码有更新）**

   ```bash
   cd /usr/share/nginx/server/cotc-daily-news
   docker build -t cotc-daily-news:latest .
   ```

4. **手动试跑一次（带挂载 + 环境变量）**

   ```bash
   docker run --rm \
     --env-file /usr/share/nginx/server/cotc-daily-news/.env \
     -v /usr/share/nginx/server/cotc-daily-news/output:/output \
     cotc-daily-news:latest
   ```

   然后检查宿主机是否有新文件且内容正确：

   ```bash
   cat /usr/share/nginx/server/cotc-daily-news/output/news.txt
   ```

   若能看到《每日最新AI资讯》的正文，说明写文件成功。若没有生成 `news.txt` 且日志里没有 `Content written to OPENCLAW_MESSAGE_FILE`，说明容器内代码可能是旧版，需在服务器上更新 `src/main.py`（确保包含 OPENCLAW_MESSAGE_FILE 写文件逻辑）后执行 `docker build --no-cache -t cotc-daily-news:latest .` 再试。

---

## 第五步：用 cron 串联「cotc-daily-news → OpenClaw 发 QQ」

每天 14:00 先跑 cotc-daily-news（写文件），再让 OpenClaw 用该文件内容发一条消息到 QQ。

1. **确认 OpenClaw 容器与路径**

   假设 Gateway 容器名为 `openclaw-gateway`（第一步用预构建镜像时的名字），且 cotc-daily-news 在 `/usr/share/nginx/server/cotc-daily-news`。若你放在别处，下面命令中的路径请改成你的。

2. **编辑 crontab**

   ```bash
   crontab -e
   ```

3. **添加或合并每日 14:00 的任务**

   下面是一行式写法（先跑 cotc-daily-news 写文件，再在 OpenClaw 目录下用 `openclaw-cli` 发 QQ）。**请把 `QQ_TARGET` 换成你在第三步得到的 target**（注意 shell 引号）。

   ```cron
   0 14 * * * docker run --rm --env-file /usr/share/nginx/server/cotc-daily-news/.env -v /usr/share/nginx/server/cotc-daily-news/output:/output cotc-daily-news:latest && docker exec openclaw-gateway openclaw message send --channel qqbot --target "qqbot:c2c:你的openid" --message "$(cat /usr/share/nginx/server/cotc-daily-news/output/news.txt)"
   ```

   **注意：**

   - `--target` 必须换成你实际的 target，格式为 `qqbot:c2c:openid`（私聊）或 `qqbot:group:groupid`（群），**冒号之间不能有空格**，否则会报 Unknown target。
   - 若内容含特殊字符，`$(cat ...)` 可能有问题，建议用下面「用脚本包装」方式。

4. **可选：用脚本包装（推荐，便于维护）**

   在宿主机创建脚本，例如：

   ```bash
   sudo tee /usr/share/nginx/server/cotc-daily-news/send-daily-openclaw.sh << 'EOF'
   #!/bin/bash
   set -e
   NEWS_FILE="/usr/share/nginx/server/cotc-daily-news/output/news.txt"
   # 替换为你的 QQ 推送 target：私聊 qqbot:c2c:openid，群 qqbot:group:groupid（冒号之间无空格）
   QQ_TARGET="qqbot:c2c:你的openid"

   docker run --rm --env-file /usr/share/nginx/server/cotc-daily-news/.env \
     -v /usr/share/nginx/server/cotc-daily-news/output:/output \
     cotc-daily-news:latest

   [ -f "$NEWS_FILE" ] || exit 1
   docker exec openclaw-gateway openclaw message send --channel qqbot --target "$QQ_TARGET" --message "$(cat "$NEWS_FILE")"
   EOF
   sudo chmod +x /usr/share/nginx/server/cotc-daily-news/send-daily-openclaw.sh
   ```

   在脚本里把 `QQ_TARGET` 改成你在第三步得到的 target（**无空格**格式），然后 crontab 只填：

   ```cron
   0 14 * * * /usr/share/nginx/server/cotc-daily-news/send-daily-openclaw.sh
   ```

5. **确认 crontab**

   ```bash
   crontab -l
   ```

---

## 第六步：验证与日常使用

- **定时**：等到 14:00 或临时把 cron 改成「下一分钟」跑一次，看 QQ 里小龙虾是否收到当日《每日最新AI资讯》。
- **平时**：小龙虾容器（OpenClaw Gateway）一直运行，QQ 里可照常与小龙虾聊天、使用其他功能；定时推送只是每天多发一条，互不影响。

若某一步报错，可先看：  
- cotc-daily-news：`docker run ...` 的终端输出或日志；  
- OpenClaw：`docker logs openclaw-gateway` 或 `openclaw message send` 的报错信息；  
- 再对照 [04-openclaw-qq-小龙虾-integration.md](04-openclaw-qq-小龙虾-integration.md) 的安全与故障排查部分。

---

## 踩坑与解决记录

以下为实际部署过程中遇到的问题、排查思路和解决步骤，供后续参考。

### 1. 硅基流动 403：根因是欠费，不是模型选错

**现象**：QQ 里给小龙虾发消息后，网关能收到并触发 agent，但调用硅基流动 API 返回 **403**，日志类似：

```text
[agent/embedded] embedded run agent end: ... isError=true error=403 status code (no body)
```

**排查过程**：

- 先用 curl 单独测硅基流动同一模型（如 `Pro/deepseek-ai/DeepSeek-V3`），若也返回 403，说明问题在 API/账号侧，不在 OpenClaw。
- 一度怀疑是模型被弃用（Deprecated）或权限变更，尝试更换模型：
  - 换 **Kimi**（`moonshotai/Kimi-K2.5`）→ 返回 `{"code":30004,"message":"Model is private. You can not access it"}`，表示该模型需在硅基流动控制台单独开通，与 403 无关。
  - 换 **DeepSeek-V3.2**、**Qwen3-VL-32B-Thinking**、**Pro/Qwen/Qwen2.5-7B-Instruct** 等，若账号欠费，同样会 403。

**结论与解决**：根本原因是 **硅基流动账号欠费**。在 [硅基流动控制台](https://cloud.siliconflow.cn) 完成余额充值/续费后，不换模型也可恢复正常；QQ 小龙虾即可正常回复。

**建议**：遇到 403 时，先到硅基流动查看「余额」「费用明细」，再考虑模型或 API Key 问题。

**在服务器上直接测 Key（推荐）**：在服务器执行下面命令可快速判断是 Key/余额问题还是模型问题（把 `你的硅基流动key` 换成真实 key，注意不要泄露到别处）：

```bash
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer 你的硅基流动key" \
  -H "Content-Type: application/json" \
  -d '{"model":"Pro/deepseek-ai/DeepSeek-V3","messages":[{"role":"user","content":"hi"}],"max_tokens":10}' \
  https://api.siliconflow.cn/v1/chat/completions
```

- 输出 `200` 表示 Key 和余额正常；输出 `403` 多为欠费或无权限；`401` 多为 Key 错误。

---

### 2. 无桌面环境时用 TUI 完成配对与配置

**现象**：服务器无图形界面，无法在「本机浏览器」打开控制台。

**解决**：

1. **拿到网关 token**（二选一）  
   - 从配置文件：`docker exec openclaw-gateway cat /root/.openclaw/openclaw.json | grep -A1 "auth"`（或直接 `cat /root/.openclaw/openclaw.json`），记下 `gateway.auth.token` 的值。  
   - 从控制台链接：执行 `docker exec openclaw-gateway openclaw dashboard --no-open`，输出 URL 里 `#token=` 后面的字符串即为 token。

2. **在服务器上开 TUI（全在 SSH 里操作）**  
   ```bash
   docker exec -it openclaw-gateway openclaw tui --url ws://127.0.0.1:18789 --token "你上一步拿到的token"
   ```  
   token 正确则会进入 TUI，可进行通道、模型等配置。

3. **若 TUI 提示需要设备配对**  
   - 不要关掉当前 TUI，另开一个 SSH 会话到同一台服务器。  
   - 新会话执行：`docker exec openclaw-gateway openclaw devices list`，记下待审批设备的 `requestId`。  
   - 执行：`docker exec openclaw-gateway openclaw devices approve <上一步看到的 requestId>`。  
   - 回到原 SSH 会话，TUI 即可正常使用。

---

### 3. 本机 build OpenClaw 镜像 OOM（2C4G 等小内存机器）

**现象**：在 2C4G 服务器上执行官方 `./docker-setup.sh` 或 `docker compose build` 时内存不足，构建失败。

**解决**：改用 **预构建镜像**，不再在本地 build。按顺序操作：

1. **先做持久化目录（配置不丢）**  
   ```bash
   mkdir -p /usr/share/nginx/server/openclaw/data
   mkdir -p /usr/share/nginx/server/openclaw/workspace
   ```

2. **用预构建镜像启动**（华为云示例，需同时暴露 18789 和 18791）  
   ```bash
   docker run -d \
     --name openclaw-gateway \
     --restart unless-stopped \
     -v /usr/share/nginx/server/openclaw/data:/root/.openclaw \
     -v /usr/share/nginx/server/openclaw/workspace:/root/workspace \
     -p 18789:18789 \
     -p 18791:18791 \
     swr.cn-north-4.myhuaweicloud.com/ddn-k8s/ghcr.io/openclaw/openclaw:latest
   ```  
   确认运行：`docker ps | grep openclaw`。

3. **配对 / 拿控制台链接**  
   ```bash
   docker exec openclaw-gateway openclaw dashboard --no-open
   ```  
   无桌面时用 TUI 配对，见上一条。

注意：若实际配置写在容器内其他路径（如 `/home/node/.openclaw/`），重启后仍在；若需持久化到宿主机，需挂载对应目录。

**Docker 产生的缓存与镜像（建议清理）**：构建失败或中断后会留下构建缓存、悬空镜像（无 tag 的中间层），占用空间。可在服务器上按需执行：

- 只清构建缓存（推荐先做）：`docker builder prune -f`
- 删掉没有 tag 的镜像：`docker image prune -f`
- 想一次多清一点（未使用的镜像、容器、网络）：`docker system prune -f`
- 加 `-a` 会连「没被容器用的镜像」都删，空间更大但下次拉镜像要重新下：`docker system prune -a -f`

---

### 4. QQ Bot 插件安装时 npm 依赖失败

**现象**：`openclaw plugins install @sliverp/qqbot@latest` 时依赖安装报错或超时。

**操作步骤**：

1. **删掉已有的 qqbot 插件目录**  
   ```bash
   docker exec openclaw-gateway rm -rf /home/node/.openclaw/extensions/qqbot
   ```  
   若报 Permission denied，改用 node 用户删：  
   ```bash
   docker exec -u node openclaw-gateway rm -rf /home/node/.openclaw/extensions/qqbot
   ```  
   若第一步把 data 挂载到了 `/root/.openclaw`，则插件可能在 `/root/.openclaw/extensions/qqbot`，可改为删该路径。

2. **再装一次（已用国内源）**  
   ```bash
   docker exec openclaw-gateway sh -c "npm config set registry https://registry.npmmirror.com && openclaw plugins install @sliverp/qqbot@latest"
   ```  
   会重新解压并执行 `npm install`，等其跑完。若再次出现 `npm install` 失败，把完整终端输出保留以便排查。

3. 安装完成后**重启 Gateway**：`docker restart openclaw-gateway`

---

### 5. QQ 沙箱下收不到消息或机器人「没反应」

**现象**：QQ 里给小龙虾发消息，OpenClaw 没有任何日志或会话。

**排查**：

- 确认发消息的 **QQ 号** 已在 QQ 开放平台 **沙箱/测试环境** 中添加到「测试用户」。
- 确认是在 **正确的小龙虾机器人** 的私聊或群聊里发消息（不是别的机器人）。
- 查看 Gateway 日志：`docker logs -f openclaw-gateway`，发送消息后应出现类似 `Processing message from <openid>`、`Sent input notify` 等；若无，多半是 QQ 侧未把消息推到网关（检查 token、通道状态、测试用户）。

**解决**：在 QQ 开放平台把当前 QQ 号加为测试用户，并在正确会话里重新发一条消息验证。

---

### 6. message send 报错 Unknown target

**现象**：执行 `openclaw message send --channel qqbot --target "qqbot: c2c: E3E164A8E23D16F691F59DDCED354F5B"` 时报错：`Unknown target "qqbot: c2c: E3E164A8E23D16F691F59DDCED354F5B" for QQ Bot. Hint: QQ Bot 目标格式: qqbot:c2c:openid (私聊) 或 qqbot:group:groupid (群聊)`。

**原因**：QQ Bot 插件要求的 target 格式中，**冒号之间不能有空格**。

**解决**：把 target 改为无空格格式，例如：
- 私聊：`qqbot:c2c:E3E164A8E23D16F691F59DDCED354F5B`
- 群聊：`qqbot:group:你的群openid`

修改脚本或命令中的 `QQ_TARGET` 后重新执行即可。

---
