# 交接文档 — route-override 模块（sess_39ba00ea）

> **v1.1 同步（2026-09-22 主整合窗口）**：
> 1. 整合器已加 **ZCode 版本识别**（读 asar package.json，未验证版本黄条警告）——发新版模块时把实测通过的版本号告知用户同步进清单。
> 2. 用户环境已是 ZCode **3.14.1** 且补丁已重打（六模块全在）——你们模块 product 与线上状态一致，无分叉。
> 3. 你们广告互斥用的 `data-zca-ad-model` 检测与 account-switcher 实际横幅（`zca-model-ad` class）的疑点已由对方会话确认：**互斥让位的让步方是你方**（你查对方的属性，对方不查你的），属性名以你方现有代码为准无需改；若对方未来改横幅属性，同步两侧。
> 4. 备份基线判定已改（marker 存在性，弃尺寸对比）——与你们无交集。

目标：未来 route-override 功能更新由本窗口完成 → 产物提交到整合包 `zcode-mod-kit/modules/route-override/`，由主整合窗口发布。**本窗口不再处理任何 GitHub 内容（push/Release/Issue 均由主整合窗口负责）。**

## 1. 主整合窗口修复了你们产物的以下内容（请同步知晓，勿回滚）

| # | 文件 | 修复 |
|---|---|---|
| 1 | `assets/wrapper.js` | **端口竞争修复**：原实现 `EADDRINUSE` 只记日志后 skip，持端口进程退出后配置服务空窗。现改为每 3 秒自动重试接管（`cfgRetryTimer`），成功后清定时器 |
| 2 | `inject.py` | **安全修复（P0）**：删除静态分发的 `assets/auth-token`。token 改为安装时随机生成，放运行时目录 `~/.zcode/plugins/route-override/auth-token`（首次生成、后续复用） |
| 3 | `inject.py` | wrapper.js 部署到 `~/.zcode/plugins/route-override/`，zcode.cjs require 指向该持久路径；**用户现有 `route-overrides.json` 自动从旧部署目录迁移**到运行时目录；旧 `/*zro*/` require 行原地替换（吞尾随换行），不再报错拒绝 |
| 4 | `inject.py / uninject.py / verify.py` | 渲染层路径修正：`out/renderer/index.html`（原产物缺 `out/` 前缀） |
| 5 | `module.json` | `order` 20 → **10**（zcode.cjs 先注入 route 的 `/*zro*/` 标记，pin 才能正确包在其外层） |
| 6 | `assets/ui_route_override.js` | 你们整合时加的 sharellm 广告横幅功能（`zro-model-ad`、`assertAdBanner`、与 account-switcher 横幅互斥）**保留**——这比旧仓库新，是模块的正式功能 |

## 2. 以后的标准结构与更新方式（v1.0.1 起冻结）

```
zcode-mod-kit/modules/route-override/
├── module.json   # slug/display_name/version/description/order/targets/markers
├── inject.py     # 目录模式注入：--dir <解包目录> [--zcode-cjs <路径>]
├── uninject.py   # 同上
├── verify.py     # 同上；exit 0 = 已注入
└── assets/
    ├── wrapper.js              # fetch patch + CONNECT + 配置服务
    └── ui_route_override.js    # 渲染层 UI（含 token 占位）
```

**更新功能时**：
- 功能代码改动只碰 `assets/` 里的 js，改完 `module.json` 的 `version` 升号
- 脚本契约不变（`--dir`、`--zcode-cjs`、`[route-override]` 日志前缀、幂等 `[SKIP]`、外科式、字节级恢复、`/*zro*/` 标记在文件头 500 字节内）
- 自测：跑 `python C:\Users\adamt\.zcode\workspace\default\zcode-mod-kit\tests\test_modules.py`（含旧行替换 + 配置迁移 + 组合顺序用例）+ 你们仓库原有 test/ 单测
- 完成后通知主整合窗口合体发布

**硬约束**：
- `order=10` 不要动；require 行锚点 `"use strict";`（500 字节窗口）与 `/*zro*/` 标记不变
- 端口 `27891`、运行时目录 `~/.zcode/plugins/route-override/` 不变；`route-overrides.json` 永远不随包分发
- 广告横幅若改样式/文案，保持"与 account-switcher 横幅互斥"的 yield 逻辑
- 脚本注释英文、bat 纯 ASCII、零第三方依赖

## 3. GitHub 归属

[zcode-route-override](https://github.com/Adam1290-0/zcode-route-override) 已停更（README 有迁移横幅）；所有发布由主整合窗口在 [zcode-mod-kit](https://github.com/Adam1290-0/zcode-mod-kit) 统一处理。你们窗口不要再 push 任何 GitHub 仓库。

## 4. 其他须知

- **真机验证**：`~/.zcode/plugins/route-override/wrapper.log` 出现 `port busy, retrying every 3s` 与 `(recovered)` 属新正常行为
- 老用户重打后首次注入会打印 `migrated route-overrides.json from ...`，属预期的迁移日志
- Plan B（standalone-proxy）暂未进整合包——若用户需要，在你们窗口做成独立交付物或告诉我加进模块
- ZCode 每次升级后用户只需 `reinstall.bat`；新版本锚点失效时由你们适配并只提交模块产物