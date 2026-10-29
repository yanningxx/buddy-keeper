# WorkBuddy 每日签到全勤值守

值守 WorkBuddy 每日签到与全勤（Buddy加油站签到、今日礼包、猫猫旅行派遣、积分余额、成长计划）。每天 09:00 在服务器无人值守执行，不依赖本机与客户端，结果推送到企业微信，看板可随时查状态并一键补跑。

> 内部代号与仓库名仍为 `buddy-keeper`：部署路径 `/opt/buddy-keeper`、cron 与部署脚本都依赖它，故不改。对外产品名统一为「WorkBuddy 每日签到全勤值守」。

当前版本见 [VERSION](VERSION)（1.3.0）。参加 WorkBuddy「1024 造物挑战」程序员节应用创作大赛。

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
├── VERSION                    版本号（唯一真源）
├── CHANGELOG.md               变更日志
├── README.md                  本文件：定位、结构、部署与文档索引
├── src/
│   ├── daily_runner.py        唯一入口：签到 + 旅行 + 播报编排
│   ├── balance_direct.py      积分余额获取（自动续会话）
│   └── wecom_echo_server.py   企业微信回调 + /status /run /notify 端点
├── lib/
│   ├── buddy_station.py       签到 / 旅行 / 成长计划实现与可领判据
│   ├── push_notify.py         多通道推送分发
│   ├── rt_auth.py             长效 rt 令牌管理
│   └── web_auth.py            网页登录态读取
├── config/
│   └── config.json.example    推送配置模板（真实配置不入库）
├── scripts/
│   ├── deploy.py              一键部署到服务器（凭据走环境变量或本地文件）
│   ├── setup_cron.sh          安装每天 09:00 的定时任务
│   ├── bind_domain.py         可选：绑定自定义域名 + HTTPS，失败自动回滚
│   ├── generate_archive_migration.py  历史计划任务归档 → SQL
│   ├── archive_insert.sql     归档数据的建表与插入语句
│   ├── package_skill.py       技能打包 + 开放平台合规自检（八项必填 / kebab-case / 顶层目录一致性）
│   └── make_skill_icon.py     生成 512×512 技能头像（纯标准库，零依赖）
├── app/
│   └── index.html             值守看板（积分 / 签到 / 旅行 / 成长计划 / 日志）
├── site/
│   └── index.html             对外发布页：可交互看板 + 判据实验室 + 值守回放 + 发布说明
├── skill/
│   ├── SKILL.md               技能定义（自用执行版）：含签到 / 旅行执行动作
│   └── market/
│       ├── SKILL.md           技能市场版（只读范围，用于开放平台过审）
│       └── references/
│           ├── data-fields.md        状态字段口径表（含四个易误判项）
│           └── troubleshooting.md    「播报没来」判定树
├── assets/
│   └── skill-icon-512.png     技能市场头像（512×512 PNG，22 KB）
├── docs/
│   ├── DESIGN.md              设计文档：架构分层、模块、数据模型、流程、异常、扩展
│   ├── API.md                 接口文档：6 个接口的参数、错误码与示例
│   ├── USAGE.md               使用说明：环境、安装配置、典型流程、常见问题
│   ├── ARCHITECTURE.md        架构速览：鉴权体系与外部契约
│   ├── OPERATIONS.md          运维手册：日常检查命令
│   ├── DOMAIN-SETUP.md        可选：域名与 HTTPS 上线手册
│   ├── SKILLHUB-LISTING.md    技能商店上架文案
│   ├── OPEN-PLATFORM-RELEASE.md  开放平台（全网技能池）上架手册：认证、上传、逐屏填写、避坑
│   ├── ESSAY-1024.md          1024 造物挑战参赛征文
│   ├── SHARE-XHS.md           小红书发布稿（含配图与自查）
│   └── INSPIRATION-SUBMISSION.md  灵感社区投稿材料
└── 绑定域名.cmd                Windows 双击入口，调用 scripts/bind_domain.py
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
| [技能商店上架文案](docs/SKILLHUB-LISTING.md) | 名称拆解、商店说明、竞品对比、触发词 |
| [开放平台上架手册](docs/OPEN-PLATFORM-RELEASE.md) | 全网技能池：认证、上传、逐屏填写字段、七条避坑、审核答辩口径 |
| [1024 参赛征文](docs/ESSAY-1024.md) | 功能亮点、适用场景与实际价值 |
| [小红书发布稿](docs/SHARE-XHS.md) | 标题、正文、配图顺序与发布自查 |
| [变更记录](CHANGELOG.md) | 版本历史 |

## 线上地址

| 用途 | 地址 |
|---|---|
| 发布说明页 | <https://buddy-keeper.app.workbuddy.host/?sharecode=37JOHWXES6> |
| 仓库 | <https://github.com/yanningxx/buddy-keeper> |
