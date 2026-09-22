# 交接文档 — skin-manager 模块（sess_1842e23a）

> **v1.1 同步（2026-09-22 主整合窗口）**：
> 1. **`inject.py` 已改**：不再"marker 在即 SKIP"——现比较注入块 payload 与当前 assets/ui_skin.js，不同 = 判定旧版本整块替换（`replaced older ui_skin.js block`），相同 = `[SKIP] (payload identical)`。**以后功能更新直接改 assets + 升 version + 通知整合窗口即可，重打自动生效，无需先卸载**。
> 2. **灯效问题已结**：用户补丁已重打（3.14.1，六模块全在），menu 开关问题根因是面板只在 init 构建一次（异步挂载的状态条晚于皮肤脚本）——已修为点开面板时重建（v2.1.1，asr 里的 ui_skin.js 已是新版）。**如灯效仍有异常，等你拿用户截图再排查**。
> 3. 版本号请以整合包 module.json 为准（当前 2.1.1）；你方 git 的 `72e7c90` v2.1.0 与整合包的关系：整合包包含它且多一个面板重建修复。
> 4. ZCode 版本识别已加进整合器（读 asar package.json，版本不在已验证清单会警告）——你们无感知，无需动作。

目标：未来皮肤功能更新由本窗口完成 → 产物提交到整合包 `zcode-mod-kit/modules/skin-manager/`，由主整合窗口发布。**本窗口不再处理任何 GitHub 内容（push/Release/Issue 均由主整合窗口负责）。**

## 1. 主整合窗口对你们产物的核对结论

- `assets/ui_skin.js` 与旧仓库 v2.0.12 **字节一致**——无需修复，保持即可
- `module.json` 已按规范就位（order=30，targets=asar，markers=zcode-skin-ui）
- 一致性核对发现整合包缺了你们维护的 **zcode-token-usage-statusbar**：已由主整合窗口做成第 6 个模块 `usage-bar` 并入（见下述"其他须知"），**你们不需要再管它**
- 真机反馈「输入框灯效有点奇怪」待你们排查。初步判断不是代码版本问题（资产与旧仓库一致），怀疑方向：ZCode 3.12.3 下 composer DOM 变化、与 statusbar overlay 同页面共存、或用户 localStorage 旧配置迁移。**请向用户要具体现象（截图最好）或对照 3.12.3 真机 DOM 复核 Ambient Edge 定位**；锚点适配如需改 `ui_skin.js`，按下面规范改 assets 后提交

## 2. 以后的标准结构与更新方式（v1.0.1 起冻结）

```
zcode-mod-kit/modules/skin-manager/
├── module.json   # slug/display_name/version/description/order/targets/markers
├── inject.py     # 目录模式注入：--dir <解包目录>（--zcode-cjs/--install-root 仅接受不使用）
├── uninject.py
├── verify.py     # exit 0 = 已注入且 payload 与 assets 字节一致
└── assets/
    └── ui_skin.js
```

**更新功能时**：
- 功能改动只碰 `assets/ui_skin.js`，改完 `module.json` 的 `version` 升号（皮肤功能丰富，建议沿用大版本节奏 v2.x 系列）
- verify.py 要求注入块与 assets **字节一致**——只要改 assets，旧注入块即被判 stale，重打时会整体替换，逻辑正确不用改
- 约定：`<script id="zcode-skin-ui">` 标记不变；`ui_skin.js` 内严禁出现 `</script>` 字面量（inject 有断言）
- 自测：跑 `python C:\Users\adamt\.zcode\workspace\default\zcode-mod-kit\tests\test_modules.py`
- 完成后通知主整合窗口合体发布

**硬约束**：
- 只增删本模块的 script 块；`app.asar.unpacked` 原生模块备份由整合器统一负责，模块内不处理
- 注释英文、bat 纯 ASCII、零第三方依赖

## 3. GitHub 归属

[zcode-skin-manager](https://github.com/Adam1290-0/zcode-skin-manager) 已停更（README 有迁移横幅，v2.0.12 为最后一版独立发布）；所有发布由主整合窗口在 [zcode-mod-kit](https://github.com/Adam1290-0/zcode-mod-kit) 统一处理。你们窗口不要再 push 任何 GitHub 仓库。

## 4. 其他须知

- statusbar（zusage）已独立为整合包第 6 模块 `usage-bar`（目录模式重写：`out/main/index.js` 尾部注入一行 dynamic import，运行时目录 `~/.zcode/plugins/usage-bar/` 自洽克隆）。你们窗口原有的 zcode-token-usage-statusbar 相关维护职责移交，无需再更新
- ZCode 每次升级后用户只需 `reinstall.bat`；CSS 变量/锚点失效时由你们适配 `ui_skin.js` 并提交
- 灯效问题的修复同样走"改 assets → 版本升号 → 提交模块产物"的流程