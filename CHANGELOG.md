# 变更日志

版本号遵循语义化：主版本.次版本.修订号。

## 1.2.9 — 2026-10-28

### 新增

- `docs/DESIGN.md`：设计文档。含定位与边界（做什么 / 明确不做什么）、五层架构图、模块划分表（职责 / 依赖 / 不负责）、数据模型（运行状态、日志、凭据、外部接口契约）、三条关键流程、异常处理策略表、扩展性路径与五条已知限制。
- `docs/API.md`：接口文档。逐个说明 6 个接口的用途、请求方式、请求与返回参数、错误码与 curl 示例；单列一节标注 `/status` 与 `/run` 免鉴权的风险与三种缓解方式。
- `docs/USAGE.md`：使用说明。环境准备、安装与配置四步、五条典型使用流程、10 条常见问题（含「播报误报」「日志降级文件」「80 端口被占」等实踩坑）。
- `docs/DOMAIN-SETUP.md`：域名与 HTTPS 上线手册，覆盖「确认后缀可备案 → 购买 → 实名 → ICP 备案 → DNS → 服务器配置 → 验收」全流程。
- `scripts/bind_domain.py` 与 `绑定域名.cmd`：一次性把自定义域名接上并启用 HTTPS，任一步失败自动回滚。

### 变更

- `src/wecom_echo_server.py`：监听地址与端口改为可被环境变量 `BK_ECHO_HOST` / `BK_ECHO_PORT` 覆盖，**默认值仍为 `0.0.0.0:80`**，不设环境变量时行为与改动前完全一致。
  原因：2026-10-28 实测目标服务器无 nginx、无 certbot，80 端口由 `wecom-echo.service` 的 python3 进程独占。要让 Nginx 接管 80/443，必须先把它迁到 `127.0.0.1:8080`；而 `scripts/deploy.py` 每次部署都会重新上传该文件，直接改服务器上的端口会在下次部署时被覆盖回 80，Nginx 就抢不到端口。

### 文档

- `ARCHITECTURE.md` 保留为速览，与三份新文档互相引用，形成「速览 → 设计 → 接口 → 使用」的层次。
- 版本号在 `VERSION`、三份新文档页首、`site/index.html`、`skill/SKILL.md` 保持一致。

## 1.2.8 — 2026-10-28

### 修复（「⚠️ 有积分可领」假阳性）

- **根因**：`claim.claim_button_text` 是服务端下发的**静态 UI 文案**，与「是否真能领」无关。2026-10-28 实测：`today_checked_in=true`（今日已签）时该字段依然返回「立即领取」。旧逻辑 `if "领" in cbt` 于是每次都判成「有积分可领」，属假阳性。
- **客户端侧证据（`resources/app.asar` 原文，两处独立命中）**：
  - `uiState = today_checked_in ? "claimed" : "available"`；`shouldShow = (uiState === "available")`——已签到时客户端**根本不显示**该按钮。
  - `handleClaim` 开头即 `if (status?.today_checked_in) { skip: today already checked in }`。
  - 领取动作 `claimDailyCheckin()` → `POST /v2/billing/meter/daily-checkin`，与本地 `CHECKIN_PATH` 为**同一接口**。
- **后端侧证据**：`/v2/activity/growth/tasks` 实测 19 个任务，18 个 `accept_status="claimed"`，1 个 `accepted` 但 `progress=0/1`（关注公众号，需人工操作微信）——真实可领任务数为 **0**。
- **改动**：
  - `lib/buddy_station.py`：新增 `claimable_credit(data, parsed_growth)`，仅按数据事实计算可领积分（签到：`active && !today_checked_in`；任务：`progress 达成 && accept_status != claimed && has_reward && reward_credit > 0`）。`build_report` 的 `claim` 结构新增 `claimable_credit` / `claimable_checkin_credit` / `claimable_tasks` / `claimable_task_count`；`parse_growth` 的任务结构补 `task_code` / `has_reward`。
  - `lib/buddy_station.py`：`render_human` 的「领取状态：xxx」改为**仅在可领时**输出「可领积分：+N（原因）」；`render_html` 的领取卡片同理，不可领时整块不渲染。
  - `src/daily_runner.py`：`fmt_activity` 不再匹配「领」字，改为按 `claimable_credit` 输出「⚠️ 可领 +N（今日签到未领 +N / M 项任务奖励 +M）」，不可领时该提示**完全不出现**。

### 未实现（诚实说明）

- **任务奖励的自动领取未实现**：在客户端安装包内仅检索到 3 条成长相关路径（`buddy/info`、`travel/claim`、`travel/depart`），客户端全部日志中成长活动请求只有 `tasks` / `profile` / `buddy/info` / `energy` 四类 GET——**找不到任何任务奖励领取接口**，且当前可领任务数为 0，无可抓样本。故不猜测路径、不写死调用。
- 目前能自动领取的「活动积分」只有每日签到（`POST /v2/billing/meter/daily-checkin`），该动作早已在 `checkin` 步骤自动完成。

## 1.2.7 — 2026-10-28

### 清理（移除旧扁平部署遗留）

- **彻底移除 `/opt/workbuddy-automation` 依赖**：该目录为早期扁平部署遗留，经全量排查确认无任何 cron / systemd / 进程引用，仅剩两处代码内的**死 fallback 路径**。本次一并清理：
  - `src/balance_direct.py`：模块搜索路径去掉旧 `skills/totorosir-workbuddy-score/scripts` fallback，仅用项目内 `lib/`。
  - `src/wecom_echo_server.py`：同上；`MAIN_CONFIG` 的 `/opt/workbuddy-automation/config.json` fallback 改为 `HERE/config.json`。
  - `scripts/deploy.py`：删除 `link_legacy()`（原本每次部署都会重建 `/opt/workbuddy-automation` 软链目录，属反向制造残留），以及主流程中的调用。
- 删除前已实测确认 `/opt/buddy-keeper/lib` 下 4 个依赖模块（buddy_station / push_notify / rt_auth / web_auth）与 `config/config.json` 全部存在，fallback 确为死代码。

## 1.2.6 — 2026-10-28

### 增强

- **`scripts/setup_cron.sh` 支持一次性调度**：新增 `BK_DOM` / `BK_MON` 环境变量（默认 `*`，即保持每天执行的原行为）。
  用于临时把任务改到指定日期某时刻执行一次（如 `BK_HOUR=12 BK_DOM=28 BK_MON=10`），验证完可用默认值一条命令切回每天 09:00。
  脚本输出的「下次触发」提示也会相应区分「每天」与「一次性」两种语义。

## 1.2.5 — 2026-10-28

### 修复（a/b 两处遗留弱点）

- **(b) `daily_runner.py` 自愈笔误**：第 563 行原 `os.open(_p, ...).close()` 在 `os.open` 返回文件描述符（int）时调用 `.close()` 会抛 `AttributeError`，且不在 `except OSError` 捕获范围——全新环境首次运行（日志文件都不存在）时会导致启动崩溃。改为 `fd = os.open(...); os.close(fd)`。
- **(a) cron.log 跨身份写权限死结彻底闭合**：仅 `chmod 0666` 兜底无法应对「cron.log 被改回 `root:root 644`」场景（ubuntu 非 owner，`chmod` 失效，shell 重定向在启动 python 前即失败）。cron 行改为**降级重定向**：若 `cron.log` 不可写，自动改用 ubuntu 自有日志文件 `cron.$(id -u).log`，保证 `daily_runner` 始终能启动；`run.log`（ubuntu 拥有）始终作为核心记录源不受影响。

## 1.2.4 — 2026-10-28

### 修复（关键，会导致每日自动化完全不执行）

- **cron.log 跨身份写权限**：cron 任务以 `ubuntu` 身份运行，但日志文件 `logs/cron.log`
  因先前 root 身份的 `/run` 触发被创建为 `root:root 644`，`ubuntu` 无写权限，
  导致 shell 的 `>> cron.log` 重定向在启动 python 之前即失败，
  `daily_runner.py` 根本未启动——表现为每日 09:00 的签到 / 旅行 / 微信推送全部未执行。
- 三层防御修复：
  - `src/daily_runner.py`：将 `logs/cron.log` 纳入 `0666` 自愈合列表（与 `run.log`/`run.lock` 一致）。
  - `scripts/setup_cron.sh`：部署时以 root 固化 `cron.log` 为 `ubuntu:ubuntu 0666`；
    cron 行启动 python 前先 `touch` + `chmod 0666` 预确保可写（自愈兜底）。
  - `src/wecom_echo_server.py`：`/run` 处理器写 `cron.log` 前先 `chmod 0666` 保底。

## 1.2.3 — 2026-10-27

### 新增（健壮性）

- **单飞锁（single-flight）**：防止看板「立即执行一次」被连点与 09:00 cron 重叠时并发运行。
  - `src/daily_runner.py`：启动即对非阻塞 `fcntl.flock` 排他锁（`logs/run.lock`）加锁，
    已被其他实例（cron 或上一轮 `/run`）持有时记录一行并直接退出，不重复执行；
    锁随进程退出自动释放，无残留锁风险。锁文件权限放宽到 `0666`，使 root（经 `/run`）
    与 ubuntu（cron）跨身份可共用。
  - `src/wecom_echo_server.py`：`/run` 处理器加建议性检查，若已有实例在跑则返回
    「本次触发已合并（单飞锁）」并跳过派生，避免无谓进程；真正排他仍由 daily_runner 内部锁保证。

### 说明

- 单飞锁为去重语义：并发触发只跑一个，后到者合并跳过（不排队）。若想强制重跑，需先等当前实例结束。

### 附带修复（同次部署发现）

- **跨身份日志/锁文件可写性**：`run.log` 与 `run.lock` 由 root（经 `/run` 派生）首次创建时属主为 root、权限 0644，
  导致 ubuntu 的 09:00 cron 任务无法追加日志（看板日志面板在 cron 跑后空白）。现 `daily_runner`
  启动时将二者统一放宽到 `0666`（自愈合），并已引导修正现有文件属主为 ubuntu，使 root 与 ubuntu 均可写。

## 1.2.2 — 2026-10-27

### 修复（关键根因）

- **看板「立即执行一次」报错「通道 A/B/C 均不可用」的真正根因修复**：
  `wecom-echo` 系统服务以 **root** 运行，看板 `/run` 派生的 `daily_runner`
  子进程继承 root 身份；旧 `rt_auth.py` 用 `os.path.expanduser("~")` 解析凭据目录，
  在 root 下得到 `/root/.workbuddy/checkin-rt.json`（不存在），导致长效令牌读取失败、
  通道 C 失效、三通道全挂。cron（ubuntu）与手动 `sudo -u ubuntu` 因 HOME 正确而正常。
- **修复方式（三重加固，已实测）**：
  - `lib/rt_auth.py`：凭据目录改为候选列表解析（`WORKBUDDY_HOME` 环境变量 →
    `/home/ubuntu` → `expanduser("~")`，取首个已存在的 `.workbuddy` 目录，否则回退
    `/home/ubuntu`）；`save_rt` 权限改为 `0644`，root 写入后 ubuntu(cron) 仍可读取。
  - `src/daily_runner.py`：子进程调用注入 `env=dict(os.environ, HOME="/home/ubuntu")`。
  - `src/wecom_echo_server.py`：`/run` 派生子进程注入 `env["HOME"]="/home/ubuntu"`。
- **验证**：复现 root+HOME=/root 条件下 `checkin --check-only` 返回合法已签 JSON（不再报
  「均不可用」）；真实 `POST /run` 端到端成功（checkin+travel 成功、双通道推送送达）。

### 说明

- 早前曾误判为「一过性上游抖动 + 并发刷新竞争」，本次已据实更正：该判断不成立，
  根因是运行身份导致的 HOME 路径错位，与上游稳定性无关。

## 1.2.1 — 2026-10-27

### 变更

- **看板免令牌访问**：`wecom_echo_server.py` 的 `GET /status` 与 `POST /run` 移除令牌校验，
  打开 `http://<服务器IP>/` 即可直接查看值守状态、点「立即执行一次」触发流程，不再提示输入 notify_token。
- 前端 `app/index.html` 去掉令牌输入弹窗，改为无参调用 `/status` 与 `/run`。
- **保留受保护**：外部集成端点 `POST /notify`（Windows 端推送用，不在看板 UI 内）仍要求 notify_token。

## 1.2.0 — 2026-10-27

### 新增

- **看板同源托管（发布）**：`wecom_echo_server.py` 现于 `GET /` 与 `/app` 同源托管 `app/index.html`，
  看板 API 改用 `location.origin` 调用，避免跨域/混合内容拦截。打开 `http://<服务器IP>/`
  即可在任何浏览器（含手机）查看值守状态并手动触发一次流程。
- **运行日志落盘**：`daily_runner.py` 的 `log()` 同时写入 `logs/run.log`，`/status` 优先读取
  `run.log`（回退 `cron.log`），看板日志面板在任意触发方式下均有内容。

### 部署

- `app/index.html` 加入 `deploy.py` 上传清单；服务器已建 `app/` 目录并部署。
- 已重启 `wecom-echo` 服务，确认 `/` 返回看板 HTML、`/status` 令牌鉴权正常。

## 1.1.0 — 2026-10-27

### 新增

- **项目化结构**：代码拆分为 `src/`（入口）、`lib/`（依赖模块）、`config/`（密钥）、`scripts/`（部署）、`docs/`（文档）。
- **一键部署**：`scripts/deploy.py` 完成建目录、上传、兼容层、权限、语法校验、余额链路自检。
- **客户端看板**：`app/index.html` 展示余额、签到、旅行状态、成长计划、未完成任务与运行日志，并支持手动触发一次流程。
- **只读/触发端点**：`GET /status`（令牌鉴权，返回最近运行状态与日志尾部）、`POST /run`（令牌鉴权，异步触发一次完整流程）。

### 变更

- `daily_runner.py` 路径解析改为自动兼容新旧两种部署结构，不再硬编码目录。
- 状态文件补充结构化摘要（余额、套餐、成长等级与 Buddy、未完成任务数），供看板读取。
- `wecom-echo` 服务改指向 `/opt/buddy-keeper/src/wecom_echo_server.py`。

### 迁移

- 定时任务由 `/etc/cron.d/workbuddy-automation` 迁移至 `/etc/cron.d/buddy-keeper`，旧任务已删除避免双跑。

## 1.0.0 — 2026-10-27

首个正式版本，功能与既有生产环境一致。

### 功能

- 每日 09:00 自动签到（幂等，已签不重复领取）
- 猫猫旅行：自动领取到达奖励 + 自动派遣（每日次数上限内）
- 积分余额：通过 deviceCode → client-login 现取会话读取真实钱包余额
- 成长计划：等级、Buddy、本周活跃天数、未完成任务数
- 积分活动：进行中活动与可领取提醒
- 免费模型快览（静态快照）
- 双通道推送：企业微信群机器人 + 企业微信自建应用（个人微信全文）
- 失败可观测：任一环节失败均推送原因与重试次数，不静默

### 技术决策记录

- **余额必须走会话链路**：计费接口按 UA 绑定会话，标准浏览器 UA 返回 401；必须带客户端 UA。
- **会话每次现取**：deviceCode 申请需同时带 `Authorization` 与 `X-Refresh-Token`，缺一返回 code 10034；因此无需长期缓存 cookie。
- **响应式加粗**：企业微信群机器人走 markdown；自建应用在内容含 `**` 时切换 markdown 消息类型。
- **定时任务用 ubuntu 身份**：root 读不到 `/home/ubuntu/.workbuddy` 下的长效令牌。
