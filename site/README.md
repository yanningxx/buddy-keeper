# 看板应用复刻 · 交付说明

复刻对象：`https://buddy-keeper.app.workbuddy.host/?sharecode=37JOHWXES6`

## 一、线上地址

| 用途 | 地址 |
| --- | --- |
| 主链接（独立子域名，推荐） | `https://kanban-board-xuyanning-d2g5ejg513e3c8e1d.webapps.tcloudbase.com/?code=4ZX99GZL` |
| 备用链接（共享域名子目录） | `https://xuyanning-d2g5ejg513e3c8e1d-1414642200.tcloudbaseapp.com/board/?code=4ZX99GZL` |

`?code=4ZX99GZL` 是**演示看板**的分享码。演示看板故意不设 owner，所以任何人打开都只能看 —— 用来演示「分享出去能看、但改不了」。直接删掉 `?code=` 打开，会落到本机上次用的看板，或给你新建一块属于你自己的。

本地文件：`site/index.html`（单文件，82,304 B，sha256 `950f32f4…9bab6183`）。两个线上地址的内容与该文件逐字节一致。

**这份代码在仓库里的位置**：`buddy-keeper` 仓库的 `site/` 目录 —— `site/index.html` 是发布页本体，`site/tests/` 是可复跑的验证脚本，`site/shots/` 是截图，本文件是 `site/README.md`。`site/` 是唯一真源，其他地方出现的同名页面都是它的副本。

## 二、原站测绘结论（复刻依据）

动手前先把原页面拆到底，结论决定了「哪些能复刻、哪些必须新建」：

| 维度 | 实测 |
| --- | --- |
| 体积 | 单文件 22,675 B / 400 行，零外部依赖（无框架、无 CDN、无字体、无图片） |
| 数据来源 | `fetch` / `XMLHttpRequest` / `localStorage` / `sessionStorage` 出现次数均为 **0**——纯只读展示页，内容全部硬编码 |
| 主题 | 13 个 CSS 变量：`--bg #f6f7f9`、`--card #fff`、`--line #e5e7eb`、`--text #1a1d24`、`--muted #6b7280`、`--accent #2f6feb`、`--ok #0f9d58`、`--warn #c77700`、`--err #d13438` 等 |
| 布局 | 容器 `.wrap` max-width 900px，`padding:40px 20px 64px`；系统字体栈；正文 14px / 行高 1.65 |
| 断点 | 仅 1 个 `@media(max-width:640px)`：四栏指标 → 2 栏，双栏对比 → 单栏，h1 28px → 23px |
| 结构 | `header`（h1 + 副标 + 4 徽章）→ `nav`（4 按钮）→ 4 个 `section.panel`（`.on` 显隐 + 0.22s fade）→ `footer` |
| 交互总量 | 6 个：标签切换、预设切换、开始回放、重置、5 个外链、1 个空转定时器 |

**四个面板**：值守看板（hero 结论 + 4 格指标 + 6 行键值 + 播报气泡 + 深色日志）、判据实验室（4 预设 + 红绿双栏 + 3 条理由）、模拟值守回放（6 步时间轴，每步 700ms）、发布说明（4 卡 + 6 行文档表）。

**原站没有的能力**（也就是你在需求里列的第 2、3 项）：卡片 CRUD、拖拽、列容器、持久化、搜索筛选、成员、标签、应用内分享逻辑。`?sharecode=` 是 WorkBuddy 托管平台的访问码，不是页面自己实现的分享。

所以「复刻 + 补齐功能」是两件事：原站能 1:1 还原的是**视觉与四个只读面板**；卡片能力必须新造。这也是我先向你确认「复刻原页 + 加看板标签」和「接 CloudBase」两个决策的原因。

## 三、完成度逐条对照

### 1）视觉样式还原

- 13 个 CSS 变量原样继承，逐项比对无一改值（`tests/diff_orig.py` 会自动核）。
- `.wrap` / `.grid` / `.dual` / `.hero` / `.badge` / `.verdict` / `.timeline` / `@keyframes fade` / `@media(max-width:640px)` 全部保留原定义。
- 四个原面板的 HTML 内容逐字复制：比对脚本确认 `board` 55 行、`lab` 23 行、`replay` 24 行文本**完全一致**，`notes` 41 行原内容一行未删（只在末尾追加了第 5 张卡）。
- 页脚、页面标题与原站一致；徽章在原 4 个基础上追加 1 个（「任务看板 · CloudBase 云数据库」）。
- 响应式实测（CDP 量测 `documentElement.scrollWidth - innerWidth`）：

| 视口 | 横向溢出 | 看板列可见 | 导航 |
| --- | --- | --- | --- |
| 1440 | 0 | 4 列全见（每列 275px） | 5 个标签平铺 |
| 1024 | 0 | 3 列全见 + 第 4 列露头 | 5 个标签平铺 |
| 768 | 0 | 2 列全见 + 第 3 列露头 | 5 个标签平铺 |
| 390 | 0 | 1 列（82vw） | 导航自身横向滚动 |

### 2）核心功能复刻（看板 / 列表 / 卡片）

- 看板：新建（含二次确认）、改标题（失焦即存）、分享码。
- 列表：新增、双击列名重命名、`⋯` 菜单删除（连带删该列卡片）。
- 卡片：新建 / 编辑 / 删除（二次确认）、标题 / 描述 / 截止日 / 标签 / 成员。
- 拖拽：HTML5 `draggable`，`clientY` 对半判定插入位，`dragend` 后批量 PATCH `column_id` + `position`；拖拽结束 250ms 内的尾随 click 被忽略，不会误开编辑弹窗。

### 3）能力还原（持久化 / 分享 / 筛选 / 成员标签）

- 持久化：CloudBase PostgreSQL，两张表 `bk_boards` / `bk_cards`，走 PostgREST 风格 HTTP 接口（`/v1/rdb/rest/<table>`），每次请求带当前身份的 access_token。
- 分享：`?code=<8 位分享码>`，`navigator.clipboard` 复制，失败回退 `execCommand`。带 `?code=` 打开会**自动切到「任务看板」标签**并加载对应看板。
- 搜索筛选：标题 + 描述模糊匹配、成员下拉、标签下拉，三条件组合；不匹配的卡片 `display:none` 而非移除。
- 成员与标签：可新增（带颜色），卡片上以头像圆点与配色 pill 呈现。
- 多端同步：20 秒轮询，`document.hidden` / 拖拽中 / 弹窗打开 / 本地写入后 4 秒内 四种情况跳过，JSON 比对变了才重渲。

### 4）交互反馈与边界

- 加载态：列骨架屏 + `@keyframes sh` 微光；启动阶段状态栏依次显示「正在登录…」→「正在连接云端…」→「已同步」。
- 空态分三种：列内无卡片、筛选无结果、看板无列表。
- 错误态：连不上库时整块换成错误卡，带具体错误原因和「重试」按钮，状态栏同步显示「连接失败」。
- 操作确认：删卡片、删列表、新建看板、重置身份均二次确认；删除文案明确写「无法恢复」。
- 轻提示：`toast` 两色（ok / err），2.6 秒自动消失。
- 键盘：Esc 关闭所有弹窗；点击遮罩关闭；`prompt` 输入框回车确认；身份条可 Tab 聚焦 + 回车打开。
- 输入校验：卡片标题为空时不提交并聚焦回输入框；保存期间按钮禁用并显示「保存中…」。

## 四、登录与 RLS 改造（本轮新增）

上一版的限制是「任何拿到链接的人都能改看板」。本轮把它收紧成**只有创建者能改，别人只能看**。分三层：数据库策略、前端身份、前端权限态。

### 1）判据从哪来：实测出来的三个事实

改造前先探明平台到底给了什么，而不是照着 Supabase 的习惯写：

| 探测 | 结果 | 结论 |
| --- | --- | --- |
| `GET /auth/v1/*` | 全部 404 | 路径前缀写错，认证服务挂在 **`/auth/v1/*`**，不是 `/v1/auth/*` |
| `POST /auth/v1/signin/anonymously` + 头 `x-device-id` | 200，返回 `access_token` / `refresh_token` / `expires_in:7200` | 匿名登录可用 |
| 同一 device-id 连续登 3 次 | `sub` 三次完全相同 | 匿名身份按 device-id 稳定映射，可以作为「用户 id」 |
| 不带 `x-device-id` | 400「请在请求头添加设备id」 | device-id 是必填的身份种子 |
| `POST /auth/v1/signup` 纯用户名密码 | **501 UNIMPLEMENTED**「you can not signup just by username and password」 | 自助注册走不通 |
| `POST /auth/v1/signup` 带邮箱 | 400「verification_token or verification_code required」 | 必须过邮箱/手机验证码，而两者在本环境都未开通 |
| 管理端是否有建用户入口 | 只有登录方式/provider/key 配置，**没有建用户** | 无法凭空造账号 |
| `rpc/kb_whoami()` 拿 `auth.uid()` | publishable key → 字面量 `'anon'`；匿名用户 token → 22 字符真实 uid | **这是唯一可用的隔离判据** |
| `auth.jwt()` 在库里的可见 claim | 只剩 `aud/exp/iat/is_anonymous/iss/role/sub/user_metadata` | `user_id`、`meta.platform` 等被剥离，不能靠它们区分 |

于是有了一个必须处理的坑：**publishable key 自己的 `sub` 就是字符串 `"anon"`**。如果不排除这种情况，所有未登录访客会共享同一个 `auth.uid()`，`owner_uid = auth.uid()` 会把所有人当成同一个 owner。所以策略里的身份判据不能直接写 `auth.uid()`。

### 2）数据库层：owner 列 + 6 条策略

迁移 `cloudbase/migrations/20261030140000_board_owner_rls.sql`（已应用，version `20261030140000`）：

```sql
ALTER TABLE public.bk_boards ADD COLUMN IF NOT EXISTS owner_uid text;

-- 把「publishable key 的伪身份」归一化为 NULL
CREATE OR REPLACE FUNCTION public.kb_uid() RETURNS text
  LANGUAGE sql STABLE SET search_path = ''
AS $$
  SELECT CASE
    WHEN auth.uid() IS NULL  THEN NULL
    WHEN auth.uid() = 'anon' THEN NULL
    ELSE auth.uid()
  END;
$$;
```

策略语义：

| 表 | 动作 | 规则 |
| --- | --- | --- |
| `bk_boards` | SELECT | `true` —— 读保持公开（分享码看板的核心用法） |
| `bk_boards` | INSERT | `owner_uid IS NOT NULL AND owner_uid = kb_uid()` |
| `bk_boards` | UPDATE | `USING` 与 `WITH CHECK` 都是同一条件 → 既改不了别人的，也不能把 owner 转让给别人 |
| `bk_boards` | DELETE | `owner_uid = kb_uid()` |
| `bk_cards` | SELECT | `true` |
| `bk_cards` | INSERT / UPDATE / DELETE | `EXISTS (SELECT 1 FROM bk_boards b WHERE b.id = board_id AND b.owner_uid = kb_uid())` —— 卡片权限跟着所属看板的 owner 走，不在卡片上冗余存 owner，避免两份数据漂移 |

**关键细节**：旧的 `bk_boards_all` / `bk_cards_all` 是 `FOR ALL ... USING (true)`。Postgres 的多条宽松策略之间是 **OR**，只要旧策略还在，新策略就形同虚设。所以迁移第一步先 `DROP POLICY`，再建新的。

演示看板 `4ZX99GZL` 的 `owner_uid` 保持为 `NULL`，结果是**任何人（包括登录用户）都只读**，正好当「只读示例」。

### 3）前端层：匿名登录 + token 注入 + 权限态

- `AUTH` 模块：`deviceId()` 首次随机生成 13 位并写入 `localStorage.kb_device_id`；`signin()` 打 `/auth/v1/signin/anonymously`；`refresh()` 用 `refresh_token` 换新 token；`ensure()` 做 120 秒提前刷新并合并并发请求（`inflight`）。
- `api()`：每个请求先 `AUTH.ensure()` 取 token 注入 `Authorization`。遇到 401 时先看响应体 —— 如果是 `DATABASE_42501`（RLS 拒绝）就直接报「没有权限」，**不刷新 token**；只有真的是凭证问题才清 token 重试一次。
- 两种越权表现的翻译：
  - INSERT → `401 DATABASE_42501`，能直接看出被拒。
  - UPDATE / DELETE → **200 / 204，但影响 0 行**，状态码完全看不出问题。所以 `saveBoard()` 在 `return=representation` 下拿到空数组就主动抛错，前端不靠状态码判成败。
- 权限态：`canEdit()` 比较 `board.owner_uid === 自己 uid`。为 false 时给 `#kanban` 加 `.kb-ro`：隐藏「+ 添加列表 / + 成员 / + 标签 / 添加卡片 / ⋯」，标题框 `readOnly`，卡片去掉 `draggable`，弹窗变「查看卡片（只读）」且没有保存/删除按钮，所有写函数开头都有 `canEdit` 守卫。
- 身份 UI：工具栏一个身份条（`● 身份 xxxxxx`，点开弹窗），弹窗里可以复制**身份码**（= device-id）、粘贴别人的身份码切换登录、重置身份。换电脑时把身份码粘过去就能接管自己建过的看板 —— 这条不是文案承诺，`tests/adopt_test.js` 用两台「设备」做了一遍：B 从只读、粘码、`canEdit` 翻真、到库里标题真的被改掉，32 项全过。
- 「重置身份」刻意**不删地址栏的 `?code=`**：重置后仍停在刚才那块看板上，只是变只读。原来那版会把 `?code=` 摘掉、跳到一块新看板，结果确认框里说的「之前用它建的看板将变成只读」当场不成立 —— 提示语和实际行为对不上，改行为比改提示语更省事。想另起一块，点工具栏的「新建看板」。
- 兜底：登录彻底失败时退回 publishable key，只能读，状态栏会显示「未登录 · 只读」。

## 五、与原站的差异

**只有增加，没有删改。**

| 项 | 原站 | 复刻版 |
| --- | --- | --- |
| 标签数 | 4 | 5（新增「任务看板」，插在「模拟一次值守」与「发布说明」之间） |
| 徽章 | 4 个 | 5 个（追加「任务看板 · CloudBase 云数据库」） |
| 发布说明面板 | 4 张卡 | 5 张卡（追加第 5 张，说明看板标签的数据来源与安全模型） |
| 看板容器宽度 | 900px | 仅在「任务看板」标签下放宽到 1180px，其余标签仍 900px |
| 数据 | 全硬编码 | 四个原面板仍硬编码（保持快照语义）；看板标签走云数据库 |

## 六、已知限制

1. **平台访问门禁**：`*.tcloudbaseapp.com` 与 `*.webapps.tcloudbase.com` 都是腾讯云测试域名，浏览器首次访问会先出「页面访问提示」，等 3 秒点「确定访问」才进页面。这是平台行为，页面代码无法绕过；要彻底去掉需绑定已备案的自定义域名。顺带说明控制台里那条 `Document 404`：那是门禁页本身就是用 **404 + 提示 HTML** 返回的（`tests/probe_404.js` 抓到的请求只有两条，一条是这个门禁文档、一条是 `favicon.ico`），点「确定访问」之后真实页面是 200，与页面代码无关。
2. **这是「设备身份」不是「账号密码」**：本环境的 `/auth/v1/signup` 必须带邮箱或手机验证码（纯用户名密码返回 501），邮箱与手机登录方式都未开通，管理端也没有建用户的入口，所以自助注册走不通。当前用的是平台匿名登录：真 JWT、稳定 uid、能撑起「只有自己能改」，但**身份码（device-id）本身就是凭据**，泄露它等于让别人变成你；清掉浏览器存储就失去对自己看板的写权限（除非导出了身份码）。要升级成真账号，需要在控制台开通邮箱或手机登录并接上验证码通道，然后前端换 `signInWithPassword` / 验证码登录，RLS 一行都不用改。
3. **读是公开的**：任何人拿到 `?code=` 都能读完整看板内容（含所有卡片描述）。这是分享语义决定的，不是漏洞；要连读也收紧，就得放弃「链接即分享」，改成显式邀请。
4. **未登录访客共用 `auth.uid() = 'anon'`**：publishable key 的 `sub` 是字面量 `anon`，所以策略里必须 `owner_uid IS NOT NULL` 才能挡住「匿名冒充 owner」。这一点已经写进 `kb_uid()`，但换平台/换 key 类型时要重新确认。
5. **publishable key 明文在前端**：这是 CloudBase 该 key 的设计定位（等同 Supabase anon key），权限边界完全由 RLS 决定，不能当密钥用。
6. **无版本冲突控制**：两人同时改同一张卡时后写覆盖先写，没有 `updated_at` 乐观锁。轮询间隔 20 秒，期间看不到别人改动。
7. **拖拽只在桌面端**：移动端 HTML5 拖放不触发，跨列移动目前只能通过编辑弹窗改列。触屏拖拽需另做 pointer 事件实现。
8. **看板列宽有下限**：单列 min-width 252px，超过 4 列时横向滚动；移动端列宽 82vw，一次看一列。
9. **四个原面板仍是静态快照**：数据日期 2026-10-29 09:00，不会随看板变化。这是为了保持与参赛作品一致的展示语义。

## 七、验证记录（可复现）

全部脚本在 `site/tests/`，从 `site/` 目录下运行。脚本里所有相对路径都按「`tests/` 的上一级就是页面所在目录」算，所以只能在这个位置跑，挪走会找不到 `index.html`。

| 脚本 | 覆盖 | 结果 |
| --- | --- | --- |
| `python tests/validate.py` | 内联脚本语法（node --check）、CSS 花括号配平、HTML 标签配平、key 与环境一致性、标签/面板一一对应 | 全部通过 |
| `python tests/probe_auth.py` | 认证端点探测：匿名登录、user/me、token 刷新、用户名密码错误码、signup 限制 | 端点与限制全部摸清 |
| `python tests/probe_identity.py` | device-id 稳定性（同一 id 三次登录 sub 相同）、换 id 换人、缺头报错、refresh_token 单次有效 | 全部符合预期 |
| `python tests/probe_whoami.py` | `auth.uid()` / `auth.role()` 在 publishable key、匿名 token、无凭证 三种情况下的取值 | key→`anon`，用户→22 位 uid，无凭证→401 |
| `python tests/probe_auth_cors.py` | 认证与数据端点的 CORS 预检，`x-device-id` 是否在 allow-headers | 环境自有域名 + localhost 放行；第三方域名 403 |
| `python tests/rls_test.py` | **RLS 行为验收 35 项**：未登录只能读、伪造 owner 被拒、A 能改自己的、A 不能把 owner 转给 B、B 能读 A 的但改/删/插都被拦、演示看板人人只读、越权写以「数据有没有变」为准 | 35/35 |
| `python tests/e2e.py` | 接口层 22 项 CRUD：建板（带 owner_uid）、按分享码读、批量灌卡、按列过滤、改卡跨列、批量改 position、删卡、按列删卡、改列定义、清理 | 22/22 |
| `NODE_PATH=/tmp/node_modules node tests/dom_test.js` | jsdom 里真实执行页面脚本 70 项：懒加载、匿名登录、owner 判定、建板灌种子、卡片增删改、搜索筛选、列表增删、身份弹窗、Esc、刷新、**第二个身份只读态 17 项**、绕过前端直接越权写被 RLS 拒、坏接口地址错误态、清理 | 70/70，运行期异常 0 |
| `NODE_PATH=/tmp/node_modules node tests/drag_test.js` | 拖拽落库 11 项：`column_id` / `position` 是否写回、position 是否连续、能否反复移动、**只读身份拖动后库里不变** | 11/11 |
| `node tests/adopt_test.js` | **身份码接管 32 项**：A 建板 → B（另一台机器，预置另一个 device-id）打开分享码只读 → 在 B 上粘 A 的身份码登录 → uid 与 A 一致、`canEdit` 翻真、库里的标题真的被改掉 → 再点「重置身份」回到只读且**没跳到别的看板** | 32/32 |
| `python tests/health.py` | 只读体检：看板/卡片总数、每块板的 owner、孤儿卡片、演示看板是否被误改 | 1 块演示看板 + 8 张卡 + 0 孤儿 |
| `python tests/diff_orig.py` | 与原站逐面板文本比对 | board/lab/replay 完全一致；notes 仅追加 |
| `node tests/cdp_auth.js <url>` | 真 Chrome + CDP 34 项：过平台门禁、匿名登录、token 注入、owner 判定、**token 过期后刷新且身份不变**、浏览器里建卡真的入库、切换身份变只读、越权写入被拒、390px 无横向溢出、无 JS 异常与 CORS 失败 | 本地 / 两个线上域名均 34/34 |
| `node tests/cdp_online.js <url> <tag>` | 线上地址端到端：过门禁 → 量测渲染 → 抓 JS 异常 | 通过，异常 0，横向溢出 0 |

截图在 `board-app/shots/`：`orig-board.png`（原站）、`mine-board.png`（复刻首屏）、`v1440/v1024/v768/v390.png`（四档宽度）、`auth-1440.png`（可编辑态）、`auth-readonly-1440.png`（只读态）、`auth-390.png`（移动端）、`final-webapps.png`（线上最终版）。

依赖说明：`jsdom` 不在项目内，装在 `/tmp/node_modules`，跑 jsdom 测试时需要 `NODE_PATH` 指向它。

`site/.key.txt` 是发布密钥（一行，就是页面 `CFG.key` 那串，1,170 字符），**不入库**（见 `.gitignore`）。新克隆的仓库要跑脚本，先在 `site/` 目录下把它补回来：

```
python tests/showkey.py > .key.txt
```

这条命令已实测（输出与本地 `.key.txt` 逐字符一致）。这串 key 本来就是公开的——它写在页面里，任何人打开源码都能看到——单独落成文件只是让脚本不用每次解析 HTML。

### 部署记录

两条通道并行发布，发布后必须核对哈希 —— 不核哈希就无从判断线上到底是哪一版。

| 时间 | 通道 | 版本 / 路径 | 线上取回体积 | 与本地是否逐字节一致 |
| --- | --- | --- | --- | --- |
| 10:34 | `manageApps` → 独立子域名 | `kanban-board-006`（BuildId 2609897527） | 82,304 B | 一致 |
| 10:34 | `manageHosting` → 共享域名 | `board/index.html` | 82,304 B | 一致 |

当前本地基准：`82,304 B`，sha256 `950f32f4a592bfe73b54bf9f2341f97dbc8db94a87c689af88685de89bab6183`。核对方式是 `curl` 取回线上文件后 `sha256sum` 比对，不靠 `Content-Length` 或上传返回值推断。

版本演进（每次都很小，但都不能不回填，否则线上会长期停在旧文案上）：

| 版本 | 体积 / sha256 前缀 | 与上一版的差异 |
| --- | --- | --- |
| 10:18 | 82,029 B / `daf8822e…` | 登录 + RLS 改造主体 |
| 10:24 | 82,256 B / `bfecf381…` | `notes` 第 5 张卡三句文案。旧文案还写着「任何人拿到链接都能改动这个看板」，与 RLS 改造后的实际行为相反，必须重发 |
| 10:34 | 82,304 B / `950f32f4…` | 「重置身份」改为保留地址栏 `?code=`，重置后停在原看板并显示只读，而不是跳到一块新看板 |
