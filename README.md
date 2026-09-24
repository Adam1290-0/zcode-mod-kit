# ZCode Mod Kit / ZCode 补丁整合包

> 🔗 **广告**：[sharellm.net](https://sharellm.net/sign-up?aff=wb5b) — AI 模型共享平台，海量模型一键体验（注册邀请链接）

[English](#english) · [中文](#中文)

![Version](https://img.shields.io/badge/version-1.1.0-blue) ![License](https://img.shields.io/badge/license-MIT-green)

给 [ZCode](https://zcode.z.ai) 桌面端的**六合一补丁整合包**：一个赛博朋克菜单统一管理全部补丁模块，上下键选模块、左右键切换注入/不注入，一次解包、一次重打包全部搞定。ZCode 升级后双击 `reinstall.bat` 一键重打上次选择。

**本仓库是以下独立项目（均已停止单独更新）的整合后续**：

| 模块 | 继承自 | 独立仓库（历史） |
|---|---|---|
| route-override | ZCode Route Override v1.0.3 | [zcode-route-override](https://github.com/Adam1290-0/zcode-route-override) |
| pin | ZCode Pin v1.0.0 | [zcode-pin](https://github.com/Adam1290-0/zcode-pin) |
| skin-manager | ZCode Skin Manager v2.1.0（含状态条联动） | [zcode-skin-manager](https://github.com/Adam1290-0/zcode-skin-manager) |
| account-switcher | ZCode Account Switcher v1.0.2 | [zcode-account-switcher](https://github.com/Adam1290-0/zcode-account-switcher) |
| snapshot-kill | ZCode 安全补丁 v1.1.0 | —（并入整合包） |
| usage-bar | zcode-token-usage-statusbar | [xhwxt/zcode-token-usage-statusbar](https://github.com/xhwxt/zcode-token-usage-statusbar)（第三方，**MIT 允许二开**，集成维护并保留原许可） |

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

### How it works

1. Backs up `app.asar` → `app.asar.kitbak` (refreshed automatically when a ZCode update is detected)
2. Injects `zcode.cjs`-level modules first (route-override, then pin wraps outside it)
3. Extracts `app.asar` once, runs each selected module's directory-mode injector, repacks once (`--unpack "*.{node,dll,exe}"`)
4. Verifies every module and prints a summary

Runtime files (wrapper.js, auth-token, route-overrides.json, zusage pump) live under `%USERPROFILE%\.zcode\plugins\`, never inside the asar — the kit folder can be moved or deleted after patching. The pin/route local config servers retry their ports automatically if the owning process dies, so the UI never loses its backend.

### Compatibility

| 模块 | 已验证 ZCode 版本 |
|---|---|
| 全部 6 模块 | 3.12.2 / 3.12.3 / 3.14.1 / 3.14.3（3.11.2 及更早见各模块历史 README） |

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

### 原理

1. 备份 `app.asar` → `app.asar.kitbak`（检测到 ZCode 更新时自动刷新备份）
2. 先注入 `zcode.cjs` 级模块（route-override 先、pin 包在其外层）
3. 解包 `app.asar` 一次 → 各选中模块在解包目录上注入 → 重打包一次（`--unpack "*.{node,dll,exe}"`）
4. 逐模块校验并输出汇总

运行时文件（wrapper.js、auth-token、route-overrides.json、zusage 泵）放在 `%USERPROFILE%\.zcode\plugins\` 下，不在 asar 里——打完补丁后整合包文件夹可以随意移动或删除。pin/route 的本地配置服务在持端口进程退出后会**自动重试接管端口**，UI 不会再失去后端。

### 兼容性

| 模块 | 已验证 ZCode 版本 |
|---|---|
| 全部 6 模块 | 3.12.2 / 3.12.3 / 3.14.1 / 3.14.3 |

> ⚠️ 本包是**社区第三方补丁**，修改 ZCode 的 `app.asar` 与 `zcode.cjs`，**与 ZCode 官方无关**，且每个模块都可能随 ZCode 更新失效。使用前请阅读 [DISCLAIMER.md](DISCLAIMER.md)。ZCode 是闭源应用且更新频繁——你的版本不在表内请勿打补丁，可提 Issue 告知版本号。

### 更新日志 / Changelog

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
