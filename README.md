# ZCode Mod Kit / ZCode 补丁整合包

> 🔗 **广告**：[sharellm.net](https://sharellm.net/sign-up?aff=wb5b) — AI 模型共享平台，海量模型一键体验（注册邀请链接）

[English](#english) · [中文](#中文)

![Version](https://img.shields.io/badge/version-1.0.0-blue) ![License](https://img.shields.io/badge/license-MIT-green)

给 [ZCode](https://zcode.z.ai) 桌面端的**五合一补丁整合包**：一个菜单统一管理 5 个补丁模块，上下键选模块、左右键切换注入/不注入，一次解包、一次重打包全部搞定。ZCode 升级后双击 `reinstall.bat` 一键重打上次选择。

Give the [ZCode](https://zcode.z.ai) desktop app an **all-in-one patch console**: one cyberpunk menu manages 5 patch modules — pick with Up/Down, toggle inject/skip with Left/Right, one extract + one repack for everything. After a ZCode update, double-click `reinstall.bat` to re-apply your last selection.

---

## 模块 / Modules

| # | 模块 | 作用 | 版本 | 独立仓库（历史） |
|---|---|---|---|---|
| 1 | route-override | 渠道级请求头伪装 + per-渠道 VPN 隧道 | 1.0.3 | [zcode-route-override](https://github.com/Adam1290-0/zcode-route-override) |
| 2 | pin | 关键约束每轮自动注入上下文顶部 | 1.0.0 | [zcode-pin](https://github.com/Adam1290-0/zcode-pin) |
| 3 | skin-manager | 壁纸/透明度/氛围灯/加载图标 | 2.0.12 | [zcode-skin-manager](https://github.com/Adam1290-0/zcode-skin-manager) |
| 4 | account-switcher | 多账号一键切换 | 1.0.2 | [zcode-account-switcher](https://github.com/Adam1290-0/zcode-account-switcher) |
| 5 | snapshot-kill | 阻断后台仓库快照扫描/上传（隐私） | 1.1.0 | — |

---

<a name="english"></a>
## English

### Install

**Prerequisites**: Windows 10/11, Python 3, Node.js (`npx`).

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

Runtime files (wrapper.js, auth-token, route-overrides.json) live under `%USERPROFILE%\.zcode\plugins\`, never inside the asar — the kit folder can be moved or deleted after patching.

### Compatibility

| 模块 | 已验证 ZCode 版本 |
|---|---|
| 全部 5 模块 | 3.12.2 / 3.12.3（3.11.2 及更早见各模块历史 README） |

> ⚠️ This is a **community third-party patch suite**. It modifies ZCode's `app.asar` and `zcode.cjs`, is **not affiliated with ZCode**, and every module can break on a ZCode update. Read [DISCLAIMER.md](DISCLAIMER.md) before use. ZCode is closed-source and updates frequently — if your version is not listed, do not patch; open an issue with your version number.

---

<a name="中文"></a>
## 中文

### 安装

**前置条件**：Windows 10/11、Python 3、Node.js（`npx`）。

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

运行时文件（wrapper.js、auth-token、route-overrides.json）放在 `%USERPROFILE%\.zcode\plugins\` 下，不在 asar 里——打完补丁后整合包文件夹可以随意移动或删除。

### 兼容性

| 模块 | 已验证 ZCode 版本 |
|---|---|
| 全部 5 模块 | 3.12.2 / 3.12.3 |

> ⚠️ 本包是**社区第三方补丁**，修改 ZCode 的 `app.asar` 与 `zcode.cjs`，**与 ZCode 官方无关**，且每个模块都可能随 ZCode 更新失效。使用前请阅读 [DISCLAIMER.md](DISCLAIMER.md)。ZCode 是闭源应用且更新频繁——你的版本不在表内请勿打补丁，可提 Issue 告知版本号。

### 更新日志 / Changelog

### v1.0.0

- 🎉 首个版本：5 模块整合（route-override / pin / skin-manager / account-switcher / snapshot-kill）
- 🖥️ 赛博朋克风格交互菜单：上下选模块、左右切换注入、回车执行
- 💾 记忆上次选择，`reinstall.bat` 一键重打（ZCode 更新后的日常操作）
- ⚡ 一次解包 + 一次重打包覆盖全部模块
- ✅ 已验证适配 ZCode 3.12.2 / 3.12.3

## License

[MIT](LICENSE)
