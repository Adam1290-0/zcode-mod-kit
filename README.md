# ZCode Mod Kit / ZCode 补丁整合包

> 🔗 **广告**：[sharellm.net](https://sharellm.net/sign-up?aff=wb5b) — AI 模型共享平台，海量模型一键体验（注册邀请链接）

[English](#english) · [中文](#中文)

![Version](https://img.shields.io/badge/version-1.7.2-blue) ![License](https://img.shields.io/badge/license-MIT-green)

给 [ZCode](https://zcode.z.ai) 桌面端的**九模块补丁整合包**：一个赛博朋克菜单统一管理全部补丁模块，上下键选模块、左右键切换注入/不注入，一次解包、一次重打包全部搞定。ZCode 升级后双击 `reinstall.bat` 一键重打上次选择。

**本仓库是以下独立项目（均已停止单独更新）的整合后续**：

| 模块 | 继承自 | 独立仓库（历史） |
|---|---|---|
| route-override | ZCode Route Override v1.0.3 | [zcode-route-override](https://github.com/Adam1290-0/zcode-route-override) |
| pin | ZCode Pin v1.0.0 | [zcode-pin](https://github.com/Adam1290-0/zcode-pin) |
| skin-manager | ZCode Skin Manager v2.1.0（含状态条联动） | [zcode-skin-manager](https://github.com/Adam1290-0/zcode-skin-manager) |
| account-switcher | ZCode Account Switcher v1.0.2 | [zcode-account-switcher](https://github.com/Adam1290-0/zcode-account-switcher) |
| snapshot-kill | ZCode 安全补丁 v1.1.0 | —（并入整合包） |
| usage-bar | zcode-token-usage-statusbar | [xhwxt/zcode-token-usage-statusbar](https://github.com/xhwxt/zcode-token-usage-statusbar)（第三方，**MIT 允许二开**，集成维护并保留原许可） |
| edit-resend-model-fix | 对话逻辑补丁 | —（并入整合包） |
| usage-stats-fallback | 历史用量统计修复 | —（并入整合包） |
| zombie-cleanup | 僵尸进程清理 | —（并入整合包） |
| voice-input | 本地语音输入（双模式接管官方麦克风） | —（并入整合包） |

---

## 模块功能 / Modules

### 🎭 route-override — 请求头与网络路由

- 渠道级请求头预设：默认 / Claude Code / Codex CLI / OpenSquilla / 自定义，模型设置页 Base URL 下方两个下拉独立配置
- per-渠道 VPN 隧道：只有点名的渠道走代理（反向白名单），其余直连零浪费
- 白名单重建剥掉 ZCode 特征头，中转站无法指纹识别；热更新秒级生效
- 本地配置服务（安装时生成随机 token）、fail-open、Plan B 零侵入反代（`standalone-proxy.py`）

### 📌 pin — 上下文固定

- 三种钉住入口（面板输入 / 消息悬停 / 选区工具栏），每轮强制注入上下文最顶部
- 加强注入（双位置）、完整集声明、过时钩子（`[PIN_STALE:n]` 一次询问）
- 请求级会话身份（子 agent 跳过、侧聊隔离）、三种 API 格式全覆盖、注入状态可见
- 本地服务 challenge/HMAC 握手、fail-open + 自愈、多进程 `fs.watch` 同步

### 🎨 skin-manager — 皮肤管理

- 壁纸（图片/GIF/动态 WebP/视频 webm）、14 区透明度滑杆（悬停红框实时预览）、毛玻璃 + 壁纸模糊
- 动态特效（星空/飘雪/极光渐变）、处理中 GIF 加载图标替换（智能去底、比例自适应）
- 输入框氛围灯 Ambient Edge：流光/彗星模式、3 预设 + 2–6 色标自定义、8 状态反馈（聚焦/输入/发送/生成中/完成/失败脉冲）、夜间降亮
- 状态四态染色、外观定制（界面字号/滚动条/主题色/终端光标/全局圆角）、配置 JSON 导入导出

### 🔁 account-switcher — 多账号一键切换

- 登录过的账号保存为本地 Profile（加密凭据快照），切换 = 回写 + 自动重启，免重新登录/扫码
- 账号备注、渠道徽章（z.ai / BigModel 双体系自动识别）、头像菜单/设置侧栏/模型设置页三处入口
- aux 登录态快照：套餐/额度状态（config builtin token、providerFamily、套餐缓存）随账号完整切换
- `/api/diag` 远程诊断通道；数据全部本地化

### 🛡️ snapshot-kill — 快照上传拦截

- 在 `out/host/index.js` 的两个入口函数加默认拒绝闸门：阻断后台仓库快照的扫描/打包/上传全链路
- `ZCODE_SNAPSHOT_ALLOW=1` 环境变量恢复官方行为；构建中子系统被移除时自动 no-op

### 📊 usage-bar — Token 用量悬浮条

> 基于 [xhwxt/zcode-token-usage-statusbar](https://github.com/xhwxt/zcode-token-usage-statusbar)（MIT，Copyright (c) 2026 xhwx）二次开发——原项目许可明确允许修改与再分发；本包将其重打包为目录模式模块（安装器重写），overlay/loader/泵逻辑未改。版权与许可声明见 [LICENSE](LICENSE) 第三方组件段。

- 每个窗口常驻悬浮条：今日 token / 请求 / 工具调用 / 会话用量实时显示（常驻本地 python 泵驱动）
- 子代理面板、汇总聚合、历史查询；mtime 热更新免重启

### 🔄 edit-resend-model-fix — 编辑重发回放修正

- 修「编辑重发 / 重试后新选模型不接管」：zcode.cjs 的 `SJo`（startCanonicalIntent）回放时不再携带发送时刻冻结的旧 `modelSelection`/`mode`/`planEnabled`，会话回落到当前设置
- 锚点唯一校验 + `node --check` 双向语法校验，版本漂移自锁

### 📈 usage-stats-fallback — 历史用量回退

- 官方统计页（设置→使用统计）在 `model_usage` 表无记录的时间段回退查询 `message.data.tokens` 旧格式聚合，恢复 2026-09-01 前的历史用量数据
- 双锚点唯一校验（Xkr 函数体内各 1 次），版本漂移自锁

### 🧹 zombie-cleanup — 僵尸进程清理

- ZCode 退出钩子自动清理孤儿 MCP 子进程（白名单制：wigolo/filesystem/memory/github/sequential-thinking/acct 六类，只杀父进程已死的 node 进程）
- 锚点唯一校验 + `node --check` 语法校验，byte-exact uninject 还原

### 🎙️ voice-input — 本地语音输入

- **双模式接管** ZCode 3.18 官方的麦克风按钮：右键弹出菜单，在「官方云端 ASR」（放行，零干预）与「本地 SenseVoice」（音频不出本机）之间切换
- 本地模式功能：每 1.5 秒增量解码的实时草稿转写、三款录音皮肤（电平条 / 输入框声波 / 麦克风声纹环）、热键 toggle、输入设备选择、空闲自动退出、随 ZCode 自动启动
- 外观可自定义：主色/辅色取色器、线宽、辉光、不透明度、流动弧线；装了皮肤模块时可「跟随皮肤主题色」并实时联动，没装则用模块自带的青/紫配色（不会误用 ZCode 自己的主题变量）
- 依赖自举：首次点击才下载 npm tarball 与 SenseVoice 模型，两者都做 sha256 校验，npm 源与 HF 源均带镜像回退；sidecar 用 ZCode 自带 Electron 运行，目标机不需要预装 Node.js
- 生命周期绑定 ZCode：点麦克风才预热，ZCode 退出时 sidecar 跟随结束（stdin 管道断开兜底 + will-quit 主动终止双保险）

---

<a name="english"></a>
## English

### Install

**Prerequisites**: Windows 10/11, Python 3, Node.js (`npx`).

The installer locates ZCode automatically (env override `ZCODE_ROOT`, the
Windows registry, `%LOCALAPPDATA%\Programs`, Program Files, drive roots). If
it can't find your install, either set `ZCODE_ROOT` to your ZCode folder, or
copy the kit into the ZCode folder and run `install.bat` from there.

1. **Fully quit ZCode** (right-click the tray icon → Quit, not just closing the window)
2. Double-click `install.bat`
3. Menu appears: Up/Down to pick a module, Left/Right (or Space) to toggle **ON / OFF**, Enter to apply
   - `A` all on · `N` all off · `R` re-apply last selection · `Q` quit
4. Wait for the summary table — one extract + one repack covers all modules (~2-3 min each way)
5. Reopen ZCode

### Daily use (after each ZCode update)

Updates wipe `app.asar` and `zcode.cjs`. Just quit ZCode and double-click **`reinstall.bat`** — it re-applies your saved selection with zero interaction.

### Uninstall

`uninstall.bat` removes **all** modules. To remove only some, run `install.bat` and toggle them OFF (OFF = uninject for already-injected modules).

**Runtime directories are not removed, by design.** They live outside `app.asar`; they hold downloaded models and plaintext auth tokens, so auto-deleting them would be destructive. Delete by hand if you are done with a module:

| Directory | Contents | Size |
|---|---|---|
| `%USERPROFILE%\.zcode\plugins\voice-input\` | SenseVoice model + npm deps | ~249 MB |
| `%USERPROFILE%\.zcode\plugins\pin\` | wrapper + debug log (self-rotating, 1 MB cap) | ~0.5 MB |
| `%USERPROFILE%\.zcode\plugins\route-override\` | route rules + wrapper | ~0.6 MB |
| `%USERPROFILE%\.zcode\plugins\usage-bar\` | overlay / zusage.py | ~0.2 MB |
| `%USERPROFILE%\.zcode\plugins\zombie-cleanup\` | cleanup script | ~5 KB |
| `%USERPROFILE%\.zcode\account-profiles\` | **account snapshots + plaintext `auth-token`** | ~81 KB |

Note the last row: it is not under `plugins\`, and it stores unencrypted auth tokens. Delete it too if you have stopped using account-switching.

### How it works

1. Backs up `app.asar` → `app.asar.kitbak` (refreshed automatically when a ZCode update is detected)
2. Injects `zcode.cjs`-level modules first (route-override, then pin wraps outside it)
3. Extracts `app.asar` once, runs each selected module's directory-mode injector, repacks once (`--unpack "*.{node,dll,exe}"`)
4. Verifies every module and prints a summary

Runtime files (wrapper.js, auth-token, route-overrides.json, zusage pump) live under `%USERPROFILE%\.zcode\plugins\`, never inside the asar — the kit folder can be moved or deleted after patching. The pin/route local config servers retry their ports automatically if the owning process dies, so the UI never loses its backend.

### Compatibility

| 模块 | 已验证 ZCode 版本 |
|---|---|
| 全部 10 模块 | 3.12.2 / 3.12.3 / 3.14.1 / 3.14.3 / 3.14.4 / 3.15.3 / 3.16.2 / 3.16.3 / 3.17.2 / 3.18.0（3.11.2 及更早见各模块历史 README） |
| voice-input | 仅 3.18.0（takes over the mic button 3.18 introduced） |

> ⚠️ This is a **community third-party patch suite**. It modifies ZCode's `app.asar` and `zcode.cjs`, is **not affiliated with ZCode**, and every module can break on a ZCode update. Read [DISCLAIMER.md](DISCLAIMER.md) before use. ZCode is closed-source and updates frequently — if your version is not listed, do not patch; open an issue with your version number.

---

<a name="中文"></a>
## 中文

### 安装

**前置条件**：Windows 10/11、Python 3、Node.js（`npx`）。

安装器自动定位 ZCode（依次尝试：环境变量 `ZCODE_ROOT`、Windows 注册表、`%LOCALAPPDATA%\Programs`、Program Files、各盘根目录）。找不到时：设置 `ZCODE_ROOT` 指向你的 ZCode 文件夹，或把整合包拷进 ZCode 文件夹后运行 `install.bat`。

1. **完全退出 ZCode**（右键系统托盘图标 → 退出，不是关窗口）
2. 双击 `install.bat`
3. 出现菜单：上下键选模块，左右键（或空格）切换 **ON / OFF**，回车执行
   - `A` 全开 · `N` 全关 · `R` 重打上次选择 · `Q` 退出
4. 等待汇总表——全部模块只解包一次、重打包一次（各约 2-3 分钟）
5. 重新打开 ZCode

### 日常使用（ZCode 每次更新后）

更新会抹掉 `app.asar` 和 `zcode.cjs`。退出 ZCode 后双击 **`reinstall.bat`**——按你上次的选择无交互一键重打。

### 卸载

`uninstall.bat` 卸载**全部**模块。只想卸某几个：跑 `install.bat` 把对应模块切成 OFF（OFF = 对已注入模块执行卸载）。

**卸载后还需手动删除运行时目录。** 这些目录不在 `app.asar` 里，卸载器不碰它们（里面有账号凭据和已下载的模型，自动删反而危险）：

| 目录 | 内容 | 体积 |
|---|---|---|
| `%USERPROFILE%\.zcode\plugins\voice-input\` | SenseVoice 模型 + npm 依赖 | 约 249 MB |
| `%USERPROFILE%\.zcode\plugins\pin\` | wrapper + 调试日志（自动轮转，上限 1 MB） | 约 0.5 MB |
| `%USERPROFILE%\.zcode\plugins\route-override\` | 路由规则 + wrapper | 约 0.6 MB |
| `%USERPROFILE%\.zcode\plugins\usage-bar\` | overlay / zusage.py | 约 0.2 MB |
| `%USERPROFILE%\.zcode\plugins\zombie-cleanup\` | 清理脚本 ps1 | 约 5 KB |
| `%USERPROFILE%\.zcode\account-profiles\` | **账号快照 + `auth-token` 明文令牌** | 约 81 KB |

注意最后一行：`account-profiles\` 与其它模块不同，**不在** `plugins\` 目录下，里面有未加密的认证令牌，不再用账号切换时建议一并删除。

### 原理

1. 备份 `app.asar` → `app.asar.kitbak`（检测到 ZCode 更新时自动刷新备份）
2. 先注入 `zcode.cjs` 级模块（route-override 先、pin 包在其外层）
3. 解包 `app.asar` 一次 → 各选中模块在解包目录上注入 → 重打包一次（`--unpack "*.{node,dll,exe}"`）
4. 逐模块校验并输出汇总

运行时文件（wrapper.js、auth-token、route-overrides.json、zusage 泵）放在 `%USERPROFILE%\.zcode\plugins\` 下，不在 asar 里——打完补丁后整合包文件夹可以随意移动或删除。pin/route 的本地配置服务在持端口进程退出后会**自动重试接管端口**，UI 不会再失去后端。

### 兼容性

| 模块 | 已验证 ZCode 版本 |
|---|---|
| 全部 10 模块 | 3.12.2 / 3.12.3 / 3.14.1 / 3.14.3 / 3.14.4 / 3.15.3 / 3.16.2 / 3.16.3 / 3.17.2 / 3.18.0 |
| voice-input（新增） | 仅 3.18.0（接管官方 3.18 才有的麦克风按钮） |

> ⚠️ 本包是**社区第三方补丁**，修改 ZCode 的 `app.asar` 与 `zcode.cjs`，**与 ZCode 官方无关**，且每个模块都可能随 ZCode 更新失效。使用前请阅读 [DISCLAIMER.md](DISCLAIMER.md)。ZCode 是闭源应用且更新频繁——你的版本不在表内请勿打补丁，可提 Issue 告知版本号。

### 更新日志 / Changelog

### v1.7.2 — 修复卸载报「皮肤插件卸载失败」

- 🚨 **根因：`skin-manager/uninject.py` 不接受 `--kit-version` 参数**
  - modkit 用同一套参数调 `inject.py` / `verify.py` / `uninject.py`。skin-manager 需要 `--kit-version`（注入时写进 block、校验时比对），但 `uninject.py` 没声明这个参数，argparse 直接以 `unrecognized arguments: --kit-version` 退出
  - 结果：卸载流程里 verify 正确判定「陈旧、需卸载」，但真正执行卸载时脚本崩掉，界面显示 `[skin-manager] FAILED`，皮肤 block 留在 `app.asar` 里
  - 修法：`uninject.py` 接受该参数（卸载本身不需要版本号，block 靠 `<script id="zcode-skin-ui">` 定位），并在注释里写明为什么保留这个看似无用的参数
- 🧪 **新增参数契约测试**：modkit 传给每个模块的 argv，必须能被该模块的 3 个脚本全部接受。这类错误在任何单元测试里都不会暴露（脚本本身没错，是调用契约错位），现在 10 个模块 × 3 个脚本共 30 个组合全部校验
- 🧪 真实 asar 解包树验证：`verify` 返回 2 → `uninject` 成功 → `zcode-skin-ui` 残留 0
- 🧪 全套 **284 项测试全绿**（engine 22 + modules 173 + edge 52 + incident 37）

### v1.7.1 — 修复两个发布阻断问题

- 🚨 **修复打补丁后 ZCode 无法启动**（`failedPhase: preparing_session_storage` / `errorCode: transport_closed`）
  - 根因：`edit-resend-model-fix` v7 放宽 `retryTurn` schema 时用了 `modelSelection:Nl.optional()` 和 `mode:Cge.optional()`。这两个符号是从 bundle 别处 grep 来的，**不在该作用域内**——`Nl` 实际是无关段落里的值。ZCode 启动时会以子进程跑 `zcode.cjs app-server --stdio --prepare-storage` 准备会话存储，worker 因 `Nl is not defined` 直接崩溃，主进程收不到 `storagePrepared` 就报 `transport_closed`
  - 修法：改用**同作用域内 `editUserQuery` schema 已验证的别名** `Wc` / `H4`，并在 inject / uninject / verify 三处同步（否则注入用新别名、卸载找旧别名，永远还原不了）
  - `node --check` 查不出这类问题：语法合法，只是运行期标识符未定义。已补测试直接跑真实的 `--prepare-storage` 子进程，要求完成 `storagePath` → `storagePrepared` 握手
- 🚨 **修复卸载不彻底（皮肤模块残留）**
  - 根因：各模块 `verify.py` 把「未注入」和「已注入但内容陈旧」都返回 1。安装器的跳过门用「返回值非 0」判断「未注入」，于是在陈旧状态下**误以为无事可做，跳过了卸载**，`app.asar` 里留下活的 `<script id="zcode-skin-ui">`
  - 修法：verify 改为**三态**——`0` = 已注入且新鲜，`2` = 已注入但陈旧，`1` = 未注入。安装器据此正确区分「跳过」「重装」「卸载」。已同步 skin-manager / voice-input / usage-bar / zombie-cleanup / account-switcher / pin / route-override
  - 副作用修正：陈旧状态现在会正确触发**重装**（此前会被当成"已注入"直接跳过，导致模块资产更新后用户拿不到新版）
- 🧪 新增 `tests/test_incident_2026_11_12.py`（27 项）：别名作用域校验、真实启动子进程握手、陈旧态必须被判为"已注入"
- 🧪 全套 **274 项测试全绿**（engine 22 + modules 173 + edge 52 + incident 27）

### v1.7.0

- 🎨 **voice-input 外观自定义（v0.4.0）**：右键菜单新增「外观」区——主色/辅色两个取色器、线宽（0.5–6px）、辉光（0–30，可关）、不透明度（15%–100%）、流动弧线开关。改动实时生效并持久化
- 🔗 **与 skin-manager 联动**：检测到皮肤模块时，可一键「跟随皮肤主题色」，语音波形自动同步皮肤主色调；皮肤切换主题时波形实时跟着变（MutationObserver 监听 CSS 变量，无需刷新）
- 🛡️ **只装语音插件也不会出问题**：`--color-primary` 这类变量 ZCode 自己也定义，某些主题下是深色底，直接读会让波形隐形。现在主题色只在**检测到皮肤模块存在**时才读取，否则一律用语音模块自带的青/紫配色。没装皮肤模块时不显示「跟随皮肤」开关（避免给出无效选项），取色器仍完整可用
- 🧪 241 项测试全绿 + 真实 3.18.0 端到端（注入 → 注入后 UI 块 45KB 语法校验 → 卸载 → 字节级还原）

### v1.6.9

- ❄️ **冬季界面**：安装器开场加入飘雪动画（备用屏幕渲染，退出后终端原样恢复；非 TTY 自动降级为一行静态问候，不会往日志里灌转义码），banner 换成冷色渐变，11–2 月自动启用。`--no-snow` 可跳过动画
- 📋 **安装器显示完整模块清单**：10 个模块的名称、版本、一句话说明全部列出，版本号由 `modkit.py` 单一数据源提供，模块升版时 bat 无需改动
- 🐛 **修复 voice-input 本地模式首次点击失效**：`ensureService()` 把失败的 Promise 缓存住了，一次瞬时失败（管理器还没起来、端口还在漂移、依赖正在下载）就会让本地模式整个会话都点不动。现在每次失败都会重置状态，下次点击可重试
- 🐛 **修复 voice-input 渲染层陈旧盲区**：verify 只检查了运行时文件字节，没检查内联进 index.html 的 UI block，导致 `ui_voice.js` 更新后安装器会跳过重部署。现在把 token/端口归一化后与源资产逐字比对
- 🐛 **修复 usage-bar / zombie-cleanup 同类盲区**：两者 verify 都只检查「文件存在」或「锚点存在」，运行时文件更新后永远不会重部署。现在都做字节比对
- 🧹 移除仓库内的内部开发文档（`docs/superpowers/`），不再随发布分发
- 🧪 全套 **241 项测试全绿**（engine 22 + modules 167 + edge 52），新增 voice 渲染层陈旧拒收 2 项、ensureService 可重试 1 项
- 🧪 真实 3.18.0 端到端：10 模块注入 → 全部 verify 通过 → node --check 全过 → 全部卸载 → 4 个文件字节级还原
- 🧪 换用户目录模拟（`USERPROFILE` 指向另一路径）：注入路径正确跟随，无硬编码残留

### v1.6.8

- ✅ 适配 ZCode **3.18.0**（asar 384.8MB）：zombie-cleanup → **v1.2.1**（shutdown 第六代改名 Ios→mgs，且外层解注册符号从 `f()` 变更到 `d()`，锚点写作 `d(),n(mgs(_))`；legacy 形状匹配改为捕获并回放该符号，不再假定 `f()`）；usage-stats-fallback → **v1.1.1**（`let R=e.prepare(` 改名为 `let P=e.prepare(`，卸载从硬编码变量改为按字面 marker/tail 切割）；edit-resend-model-fix → **v7.0.0**（官方已自行修好编辑重发路径，与本模块 v2.2 设计同源，因此 v7 只补 retryTurn 三处：builder payload 门控放行、schema 放宽、重试回调带草稿所选）；pin / route-override / skin-manager / account-switcher / usage-bar / snapshot-kill 零锚点漂移
- ➕ **新增第 10 模块 voice-input v0.3.1（语音输入）**：接管 ZCode 3.18 官方的麦克风按钮，右键呼出菜单在「官方云端 ASR」与「本地 SenseVoice」之间切换。本地模式音频不出本机，并带实时草稿转写、三款录音皮肤、热键 toggle、输入设备选择、空闲退出、autoStart。依赖（npm tgz + 模型）首次使用时自动下载并做 sha256 校验，sidecar 跑在 ZCode 自带 Electron 上，目标机不需要预装 Node.js
- 🐛 **修复 voice-input 首次安装必然失败**：依赖校验拿 `sha256File()` 的结果去比对 npm registry 的 `dist.integrity`（那是 **sha512**），64 位对 128 位永远不等，两个镜像试完必然抛错。改为钉住每个 tarball 的 sha256，并补上 `tokens.txt` 的哈希
- 🐛 **修复 voice-input 管理器端口错位**：manager 实际绑定 47116–47135 中第一个空闲端口，而 UI 端口是注入时固定的；多开 ZCode 或端口被占时 UI 指向错误端口。UI 改为按身份探测（token 往返 + 配置结构校验），并拒绝把占用端口的无关进程认作 manager
- 🐛 **修 voice-input 的 SKIP 门盲区**：verify 原来只检查运行时文件「存在」，模块资产更新后安装器会跳过重部署。改为字节比对，不一致即判 FAIL
- 🛡️ `asar_is_clean` 补扫 voice-input 的两个 marker（`zcode-voice-ui` 在 index.html、`voice-main.cjs` 在 out/main/index.js）。漏扫会让「只装 voice-input」的 asar 被误判为干净，从而用已打补丁的 asar 覆盖 kitbak 基线
- 🧹 voice-input 清理：删除 27KB 的历史备份 `ui_voice.v2.bak.js` 与 `__pycache__`
- 🧪 真实 3.18.0 解包树端到端验证：10 模块全注入 → node --check（zcode.cjs / main / host / 全部 renderer chunk）全过 → 全部卸载 → **index.html / out/main/index.js / zcode.cjs 三个文件字节级完全还原**（md5 与原文件一致）
- 🧪 全套 **238 项测试全绿**（engine 22 + modules 164 + edge 52），新增 asar voice marker 1 项、voice 陈旧运行时拒收 2 项

### v1.6.7

- ✅ 适配 ZCode **3.17.2**（asar 374.7MB，较上版 +33MB）：edit-resend-model-fix → **v6.0.0**（builder 压缩名 bdi→r_i；注意 3.17.2 里 `bdi` 已被无关的 session-resource-close 辅助函数占用，锚点必须按字面 payload 文本匹配而非函数名。分发器 fi→Ci、草稿 ref Tr→Nr、retryTurn target 别名 KA→lP、schema 别名 Ehe→Cge）；zombie-cleanup → **v1.2.0**（shutdown 内层函数第五代改名 RYi→Ios，锚点表扩为 5 代）；pin / route-override / skin-manager / account-switcher / usage-bar / usage-stats-fallback 零锚点漂移
- 🧪 真实 3.17.2 解包树端到端验证：9 模块全注入 → node --check（zcode.cjs / main / renderer chunk `styles-Dv5E6Odo.js`）全过 → 全部卸载 → **zcode.cjs 与原始文件字节级完全一致**，asar 侧标记全清零
- 🧪 全套 **214 项测试全绿**（engine 20 + modules 142 + edge 52），新增 zombie 3.17.2 锚点与 legacy 迁移 9 项回归


### v1.6.6

- 🐛 **修复 zombie-cleanup 在他人机器上必然失效**：注入的 powershell 调用硬编码了作者本机的 `C:/Users/<name>/.zcode/scripts/...`，而该脚本从未随包发布——模块注入成功但功能静默死亡。现在脚本作为模块资产发布，由 `inject.py` 部署到 `~/.zcode/plugins/zombie-cleanup/`；已注入的旧路径会在重装时自动迁移（`verify.py` 同时检查脚本是否就位，缺失即判失败并触发重部署）
- 🧹 仓库清理：移除内部协作文档 `handoffs/`、取消跟踪本机状态文件 `config.json`、`UPGRADING.md` 重写为纯技术升级指南（去掉会话 ID / 本机路径 / 内部协作描述）；README 修正「六合一」错误表述与英文兼容表缺失的 3.16.x
- 🧪 全套 **206 项测试全绿**（engine 20 + modules 134 + edge 52），新增可移植路径、旧注入迁移、跨账户卸载 12 项回归


### v1.6.5

- 🐛 **修复「运行时 wrapper 永不更新」**（route-override v1.0.10 / pin v1.0.7）：安装器的外层跳过门只问 `verify.py`，而两个 verifier 只看 asar 与 zcode.cjs 的注入标记——`~/.zcode/plugins/<slug>/` 下的 wrapper 由 `inject.py` 部署，一旦跳过 `inject.py`，旧 wrapper 就永远留在机器上。
  - 这是 2026-09-28「仓库修了、机器没变」同类问题的第二个位置；这次它让 v1.6.4 的端口泄漏修复没能落到本机（wrapper 还停在 09-24）
  - 修法：两个 verifier 增加运行时 wrapper 与仓库资产的字节比对（pin 另含 pin-core.js），不一致即判 FAIL，安装器随之重新走 `inject.py` 部署
- 🧪 全套 **190 项测试全绿**（engine 20 + modules 118 + edge 52），新增 12 项「陈旧 wrapper 必须被拒 + 重装必须复原」回归


### ZCode 3.16.3 适配与修复（原 v1.6.3 / v1.6.4，已合并）

- ✅ 适配 ZCode **3.16.3**（asar 341.4MB）：edit-resend-model-fix → **v5.0.0**（分发器 li→fi、草稿 ref Er→Tr.current、retryTurn schema 别名 Che→Ehe）；zombie-cleanup → **v1.0.4**（shutdown 内层函数第五代改名 TYi→RYi，锚点表扩为 4 代）；skin-manager / account-switcher / route-override / pin / usage-stats-fallback 零锚点漂移
- 🐛 修复端口重试的监听器泄漏（route-override / pin / account-switcher）：`EADDRINUSE` 重试时每次给 `server.listen()` 传新回调，旧回调不解绑会持续累积，端口释放时一次性全部触发。改为单一常驻 `listening` 处理器；A/B 实测旧实现 40 次重试累积 42 个监听器，新实现恒为 2 个
- 🧪 真实 3.16.3 解包树端到端验证：9 模块全注入 → node --check（zcode.cjs / main / renderer chunk）全过 → 全部卸载 → **zcode.cjs 字节级还原 pristine**，asar 侧标记全清零

### v1.6.2

- ✅ 适配 ZCode **3.16.2**（asar 341.3MB）：edit-resend-model-fix → **v4.0.0**（官方把 LCt 拆成 bdi+zAt、retryTurn 双调收敛过 bdi，补丁点收敛到 bdi 一处；分发器 Fr→li、草稿 ref er→Er.current）；zombie-cleanup → **v1.0.3**（shutdown 内层函数名 z7i→TYi 第三锚点）；skin-manager → **v2.2.3**（官方删除 idle indicator 元素，颜色控制自动隐藏、配置键保留可复活）；account-switcher / route-override / pin / usage-stats-fallback 零锚点漂移
- 🛡️ asar_is_clean 补扫 out/renderer/assets chunk（edit-resend 的 renderer marker 落在内容哈希 chunk 而非 index.html），修掉「仅 edit-resend 注入时误判 clean、刷新 kitbak 破坏基线」的数据丢失类隐患
- 🧪 全套 **173 项测试全绿**（engine 20 + modules 101 + edge 52），新增 zombie 3.16.2 锚点/回滚 9 项与 asar chunk 扫描 2 项


### v1.6.1

- 🐛 修复 GitHub issue #1：ZCode 每次启动的 storage-prepare 迁移 worker 会连同加载 zcode.cjs 头部的 route/pin wrapper，在短驻 worker 里启动本地服务 + fs.watch + fetch patch，造成 EADDRINUSE 重试与 `MaxListenersExceededWarning` 刷屏。两条 require 行加守卫 `isMainThread && !--prepare-storage`，worker 直接跳过（route v1.0.8 / pin v1.0.5）
- 📌 install.bat 顶部 banner 显示补丁包版本号（动态读自 modkit.py `KIT_VERSION`），并把过时的 six-module 描述改为准确措辞
- 🏷️ 修正 v1.6.1 发布版本号未同步：`KIT_VERSION` 与 README badge 从 1.6.0 升到 1.6.1


### v1.6.0

- ✅ 适配 ZCode **3.15.3**（asar 340.5MB）：全部 9 模块跨会话检查完成——pin / route / skin / usage-bar / account-switcher 零锚点漂移；snapshot-kill 保持 NOT-NEEDED；edit-resend 锚点漂移已重写为 v3.0.0；usage-stats-fallback 与 zombie-cleanup 由整合窗口适配
- 🔄 edit-resend-model-fix → **v3.0.0**：官方半吸收后重写——LCt 回放 payload 优先、retryTurn schema 放宽、renderer nee/zi 读取实时草稿 ref `er.current`（v2 的 Qn() 闭包拿到过期值已弃用）
- 🧹 zombie-cleanup 支持 3.15.3 新 shutdown 锚点（eNi→z7i 双锚点）
- 📈 usage-stats-fallback 适配 3.15.3 变量重排（Xkr→h2r、E→C）
- 🧪 新增 6 项 zombie 3.15.3 回归，全套 **162 项全绿**



### v1.5.0

- 🆕 新增第 8 模块 **usage-stats-fallback**（历史用量回退，order=70）：官方统计页在 model_usage 无记录的时间段回退查询 message.data.tokens 旧格式，恢复 2026-09-01 前的历史用量
- 🆕 新增第 9 模块 **zombie-cleanup**（僵尸进程清理，order=75）：ZCode 退出钩子自动清理孤儿 MCP 子进程（白名单制，只杀父进程已死的 node 进程）
- ✅ 适配 ZCode **3.14.4**（9 模块全部锚点核验存活）



### v1.4.1

- ✅ 适配 ZCode **3.14.4**（四注入目标与全部模块锚点核验存活，9 模块全零改动，跨 7 会话窗口协作完成）
- 🐛 修复注入阶段弹球动画清行残留：改为 ANSI 清行序列，长行不再叠加刷屏
- 📊 usage-bar (zusage.py) 同步历史用量回退逻辑（message.data.tokens 旧格式聚合）

### v1.4.0

- 🆕 新增第 7 模块 **edit-resend-model-fix**（编辑重发回放修正，order=65）：修「编辑重发/重试后新选模型不接管」——zcode.cjs 的 `SJo`（startCanonicalIntent）回放时携带发送时刻冻结的旧 `modelSelection`/`mode`/`planEnabled`，下游 `??` 回退永不触发。补丁删除三字段让会话回落到当前设置。锚点唯一校验 + `node --check` + 字节级注入/还原
- 🔢 模块 order 规范化（edit-resend-model-fix 60 → 65，避免与 usage-bar 撞号）

### v1.3.0

- 🐛 **修复无休止 401 的真根因**（server.log 实锤：渲染层请求从不带 token 头）：注入器的全局 token 烘焙把 ui_accounts.js 判断条件里的占位符也替换成了 token 本身，`indexOf('<token>')` 恒 false → 头永远不被设置。v1.0.3 引入、潜伏至今——服务器端历代修复全部无效，因为请求根本不带凭证
- 🛡️ 判断条件改为格式检测（hex64 正则），不依赖占位符字符串；inject 烘焙改为精确 var 行替换 + 烘焙后残留检查（出现任何占位符拒绝部署）
- 🎨 skin-manager 同构 bug 同修（KIT_VERSION 条件里的占位符导致更新检查永不运行）
- 🧪 新增 bake-guard 回归测试，全套 **144 项全绿**
- 🔍 含 v1.2.3 的请求形状日志、401 双模式语义、端口占用重试与 UI 自愈重试

### v1.2.3

- 🔍 账号切换服务新增**请求形状日志**（`~/.zcode/account-profiles/server.log`，不含 token 值）：UI 报错时日志能精确显示渲染层请求是否带 token、Origin 是什么、被哪个环节拒绝——不再靠猜
- 🏷️ 401 区分两种模式：`unauthorized`（token 不匹配）与 `service-token-not-ready`（服务启动时 token 未加载，UI 显示"服务启动中"并 3 秒自动重试）
- 🔁 账号切换服务补齐端口占用自动重试（pin/route 已有；缺失时旧进程占口会导致新服务静默失效、请求全部打到旧进程）
- 💡 UI 对 `unauthorized` 给出可操作提示（完全退出 ZCode 后重开）

### v1.2.2

- 🐛 **修复补丁更新从未真正部署的根因**（v1.2.0/v1.2.1 的修复在已打补丁的机器上全部未生效）：account-switcher 注入器的幂等 SKIP 门只查"文件存在"，重装时解包旧 asar 后已部署的旧版主模块被原样保留重打包——主模块修复（401 自愈、CORS）和渲染块 UI 更新都到不了用户机器。现在主模块与渲染块都与当前资产做内容比对，不一致即重新部署；verify 同步校验渲染块 payload
- 🐛 route-override 修 CRLF 行尾破坏（读文件缺 `newline=''`）与 renderer-only 注入时 token 目录未创建的崩溃
- 🧪 新增 9 项回归测试（主模块/渲染块陈旧检测与恢复、verify 必须报陈旧、route CRLF 字节还原），全套 140 项
- 🤝 交叉审查：code-reviewer 确认修复正确性与其余 5 模块无同类洞；test-writer 发现渲染块陈旧活洞与 route 行尾违规（均已修）

### v1.2.1

- 🐛 **修复新版 Electron 下渲染层请求被 CORS 预检拦截**（用户实测：账号切换读不到已存凭证、保存报错、请求头设置空白）：account-switcher 与 route-override 的本地服务此前不发 CORS 头，新版 Chromium 收紧跨源/私有网络访问后 file:// 渲染层的 fetch（含自定义头的 OPTIONS 预检）被浏览器直接挡掉。现在正确回显 CORS 头（含 `Access-Control-Allow-Private-Network`），pin 补齐 Private-Network 头。token 鉴权仍然是唯一硬门禁，安全性不变
- 数据说明：受影响期间磁盘数据全程无损（profiles.json / route-overrides.json 均完好），仅渲染层读不到

### v1.2.0

- 🆕 **皮肤面板版本更新通知**：本机 mod-kit 旧于 GitHub 最新 Release 时，皮肤面板最上方出现提示行，点击直达 Releases 下载页；ZCode 启动时后台静默检查，每自然日最多一次，任何失败静默不干扰
- 🐛 **修复 401 unauthorized 故障类**（用户实测：切换账号报 unauthorized、已存凭证读不到）：三个本地服务的 token 此前只在启动时读一次 auth-token 文件，瞬时读失败（并发安装/杀软锁）后永久 401 直到重启。现在 401 前懒重读 token 文件自愈，数据无损
- 📄 设计与实现计划见 `docs/superpowers/`（spec + plan）

### v1.1.1

- 🐛 **修复安装定位硬编码 H:\Zcode 的可移植性问题**：非默认安装路径的机器（如 `C:\Program Files`、`%LOCALAPPDATA%\Programs`、其他盘）之前会找不到 ZCode 甚至误导性地在补丁包目录里找 asar。现在按 环境变量 `ZCODE_ROOT` → Windows 注册表卸载项 InstallLocation → 标准安装路径 → 各盘根 ➕补丁包所在目录 的顺序自动定位；找不到时给出明确修复指引而不是静默失败
- 🧪 新增安装定位回归测试（6 项），全套 120 项
- 📝 README 补充安装定位说明

### v1.1.0

- ✅ 适配 ZCode **3.14.3**（四注入目标与各模块锚点全部核验；snapshot-kill 因上游移除快照子系统自动降级 no-op）
- 🐛 修复 account-switcher / pin 的 token 烘焙坏块（`repr()` 二次套引号生成非法 JS，整块脚本静默失效、菜单不显示）；改为裸 token 替换，`verify.py` 新增 `node --check` 语法校验，旧坏块重装时自愈
- 🐛 修复 `asar_is_clean` 只查 2 个标记的误判（pin/route/snapshot/usage 单模块安装会被当"干净"并覆盖 kitbak 干净基线）——现校验全部 6 模块标记，异常一律 fail-closed
- 🐛 修复 route-override 重装丢 token（replace 路径补 `ZRO_TOKEN` prologue）与 verify 假阳性
- 🔒 脱敏：移除硬编码的第三方 Install-Id，改为运行时生成；token 比较改常量时间
- 🎨 install.bat 新增作者信息、彩色横幅与弹球开场动画；打包/解包等待动画升级为拖尾弹跳球
- 🧪 新增引擎级回归测试（12 项），三套测试共 114 项
- 📄 新增 [UPGRADING.md](UPGRADING.md)：ZCode 每次更新后的多窗口协作适配流程

### v1.0.1

- 🐛 修复 pin 本地服务消失（持端口进程退出后其他进程不再重试 → UI 报「服务不可用」）：pin 与 route-override 的配置服务均在端口被占时每 3 秒自动重试接管
- 🆕 新增第 6 模块 **usage-bar**（token 用量悬浮条，继承 zcode-token-usage-statusbar，目录模式注入 + 自洽运行时目录）
- 📝 README 模块功能按各独立项目完整梳理，并标注继承关系

### v1.0.0

- 🎉 首个版本：5 模块整合（route-override / pin / skin-manager / account-switcher / snapshot-kill）
- 🖥️ 交互菜单：上下选模块、左右切换注入、回车执行
- 💾 记忆上次选择，`reinstall.bat` 一键重打（ZCode 更新后的日常操作）
- ⚡ 一次解包 + 一次重打包覆盖全部模块
- ✅ 已验证适配 ZCode 3.12.2 / 3.12.3

## License

[MIT](LICENSE)
