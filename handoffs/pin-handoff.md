# 交接文档 — pin 模块（sess_057a52bd）

目标：未来 pin 功能更新由本窗口完成 → 产物提交到整合包 `zcode-mod-kit/modules/pin/`，由主整合窗口发布。**本窗口不再处理任何 GitHub 内容（push/Release/Issue 均由主整合窗口负责）。**

## 1. 主整合窗口修复了你们产物的以下内容（请同步知晓，勿回滚）

| # | 文件 | 修复 |
|---|---|---|
| 1 | `assets/pin-wrapper.js` | **端口竞争修复（用户真机报错根因）**：原实现 `EADDRINUSE` 只记日志后 skip，持端口进程退出后 UI 报「pin 服务不可用 (failed to fetch)」。现改为每 3 秒自动重试 `server.listen` 接管端口，成功后清定时器（`retryTimer` 变量已加） |
| 2 | `inject.py` | wrapper 不再按 assets 绝对路径注入 require，改为**部署到 `~/.zcode/plugins/pin/`** 后指向该持久路径（整合包目录可移动/删除）；对已存在的旧 `/*zpin*/` require 行**原地替换**（含吞掉尾随换行），不再报错中止 |
| 3 | `uninject.py` | zcode.cjs 删除改为按 `/*zpin*/` 标记反查行首删除（不再按"当前 assets 路径拼接行"匹配——那样删不掉旧部署路径的行） |
| 4 | `inject.py / verify.py / uninject.py` | 渲染层路径修正：`out/renderer/index.html`（原产物缺 `out/` 前缀，真机注入会失败） |
| 5 | `module.json` | `order` 10 → **20**（route-override 先注入 zcode.cjs，pin 找 `/*zro*/` 插其后，保持 pin 为最外层 fetch patch） |

## 2. 以后的标准结构与更新方式（v1.0.1 起冻结）

```
zcode-mod-kit/modules/pin/
├── module.json   # slug/display_name/version/description/order/targets/markers
├── inject.py     # 目录模式注入：--dir <解包目录> [--zcode-cjs <路径>]
├── uninject.py   # 同上
├── verify.py     # 同上；exit 0 = 已注入
└── assets/
    ├── pin-core.js
    ├── pin-wrapper.js
    └── ui_pin.js
```

**更新功能时**：
- 功能代码改动只碰 `assets/` 里的 js，改完 `module.json` 的 `version` 升号
- 注入/卸载/校验脚本若需改锚点，保持 CLI 契约不变（`--dir`、`--zcode-cjs`，`[pin]` 日志前缀、幂等 `[SKIP]`、外科式、字节级恢复）
- 自测：打包方向跑 `python C:\Users\adamt\.zcode\workspace\default\zcode-mod-kit\tests\test_modules.py`（组合顺序/fallback/旧行替换用例都在）；纯逻辑改动跑你们仓库原有 62 项 node 测试
- 完成后把 `modules/pin/` 目录内容更新，通知主整合窗口合体发布

**硬约束**：
- `order=20` 不要动（zcode.cjs 注入顺序契约）；pin 锚点逻辑（`/*zro*/` → `use strict` fallback）保持不变
- 端口 `27892`、数据目录 `~/.zcode/plugins/pin/` 不变
- 脚本注释英文、bat 纯 ASCII、零第三方依赖

## 3. GitHub 归属

pin 的 GitHub（[zcode-pin](https://github.com/Adam1290-0/zcode-pin)）已停更，只保留历史；所有发布、tag、Release、Issue 由主整合窗口在 [zcode-mod-kit](https://github.com/Adam1290-0/zcode-mod-kit) 统一处理。你们窗口不要再 push 任何 GitHub 仓库。

## 4. 其他须知

- **真机验证**：`~/.zcode/plugins/pin/pin-wrapper.log` 出现 `port busy, retrying every 3s` 与 `(recovered)` 属新正常行为；UI 报「服务不可用」应在 3 秒内自愈
- 用户重打补丁后如 pin 仍报错，先查三点：zcode.cjs 头部 `/*zpin*/` require 行指向 `~/.zcode/plugins/pin/pin-wrapper.js`、该文件存在、`pin-wrapper.log` 最新时间戳
- ZCode 每次升级后用户只需 `reinstall.bat`；若新版本锚点失效，需你们适配（`zcode.cjs` 头部结构 / UI 锚点），适配验证通过后同样只提交模块产物