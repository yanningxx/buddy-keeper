# Buddy 值守 / BuddyKeeper

WorkBuddy 每日自动值守：签到、猫猫旅行、积分余额、成长计划、活动提醒，一条播报推送到企业微信群 + 个人微信。

当前版本见 [VERSION](VERSION)（1.2.8）。

## 运行形态

服务器 cron 每天 09:00 执行一次 `src/daily_runner.py`，全程无需本地客户端参与。

| 环节 | 数据来源 | 是否需要本机 |
|---|---|---|
| 签到 / 成长计划 / 活动 | `www.workbuddy.cn` 成长与计费接口（长效 rt 令牌） | 否 |
| 猫猫旅行（领取 + 派遣） | 同上 | 否 |
| 积分余额 | 现取 deviceCode → client-login 换会话 → 计费接口 | 否 |
| 推送 | 企业微信群机器人 + 企业微信自建应用（微信插件全文） | 否 |

## 目录

```
buddy-keeper/
├── VERSION                 版本号
├── CHANGELOG.md            变更日志
├── src/
│   ├── daily_runner.py     唯一入口：签到 + 旅行 + 播报编排
│   ├── balance_direct.py   积分余额获取（自动续会话）
│   └── wecom_echo_server.py 企业微信回调验证 + /notify 通知端点
├── lib/
│   ├── buddy_station.py    签到/旅行/成长计划技能实现
│   ├── push_notify.py      多通道推送分发
│   ├── rt_auth.py          长效 rt 令牌管理
│   └── web_auth.py         网页登录态读取
├── config/
│   └── config.json.example 推送配置模板
├── scripts/
│   ├── deploy.py           一键部署到服务器（凭据不入库）
│   ├── setup_cron.sh       安装定时任务
│   ├── generate_archive_migration.py  历史计划任务归档 → SQL
│   └── archive_insert.sql  归档数据的建表与插入语句
└── docs/
    ├── ARCHITECTURE.md     架构与接口说明
    └── OPERATIONS.md       运维手册（故障处理）
```

## 安全约定（重要）

- **仓库内不含任何凭据**。服务器地址、账号、密码一律通过环境变量或本地文件提供：
  ```bash
  export BK_HOST=<IP> BK_USER=<user> BK_PASS=<password>
  python scripts/deploy.py
  ```
  或创建 `config/deploy.local.json`（已在 `.gitignore`，不会入库）：
  ```json
  {"host": "<IP>", "user": "<user>", "pass": "<password>"}
  ```
  两者都没有时 `deploy.py` 会直接报错退出。
- 运行期密钥文件 `config/config.json`、`notify_token.txt`、`wb_session_cookie.txt`、`wecom_echo_conf.json` 与 `logs/` 全部被 `.gitignore` 排除。

## 快速部署

```bash
python scripts/deploy.py            # 上传代码 + 建目录 + 校验
ssh ubuntu@<server> sudo bash /opt/buddy-keeper/scripts/setup_cron.sh
```

部署后需手工放置三类密钥文件（不进版本库）：`config.json`、`notify_token.txt`、`wecom_echo_conf.json`。


## 客户端看板（app/index.html）

在 WorkBuddy 里打开 `app/index.html` 即可查看：积分余额、签到天数、旅行状态、成长计划、未完成任务、最近运行日志。

- 首次打开会提示输入访问令牌（服务器 `config/notify_token.txt` 的内容），令牌只存在本机浏览器 localStorage。
- 「立即执行一次」会触发服务器跑完整流程（签到 + 旅行 + 播报推送），约 10 秒后可刷新查看。

看板依赖服务器两个端点：

| 端点 | 方法 | 说明 |
|---|---|---|
| `/status?token=` | GET | 返回最近运行状态与日志尾部 |
| `/run` | POST | 令牌鉴权后异步触发一次完整流程 |

## 文档

| 文档 | 内容 |
|---|---|
| [设计文档](docs/DESIGN.md) | 架构分层、模块划分、数据模型、关键流程、异常处理、扩展性 |
| [接口文档](docs/API.md) | 6 个接口的用途、参数、错误码与调用示例 |
| [使用说明](docs/USAGE.md) | 环境准备、安装配置、典型流程、常见问题 |
| [架构速览](docs/ARCHITECTURE.md) | 鉴权体系与外部接口契约速查 |
| [运维手册](docs/OPERATIONS.md) | 日常检查命令清单 |
| [域名与 HTTPS 上线手册](docs/DOMAIN-SETUP.md) | 可选：给看板绑定自定义域名 |
| [灵感社区投稿稿](docs/INSPIRATION-SUBMISSION.md) | 案例投稿材料 |
| [变更记录](CHANGELOG.md) | 版本历史 |
