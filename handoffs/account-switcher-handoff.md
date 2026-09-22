# 交接文档 — account-switcher 模块（sess_186ebe95）

> **v1.1 同步（2026-09-22 主整合窗口）**：本模块已加入 **token 鉴权机制**（安全审查 P1 修复），更新要点——
> 1. `assets/ui_accounts.js`：`var TOKEN = '__ZCA_TOKEN__'` 占位符 + `api()` 每请求带 `x-zca-token` 头
> 2. `assets/zcode-account-switcher-main.mjs`：读 `~/.zcode/account-profiles/auth-token`（patch 时生成）+ `timingSafeEqual` 校验 + **全端点 401 闸门（含 /api/diag）**；CORS `*` 与 Allow-Private-Network 头已全部删除（攻击场景：恶意网页可读账号身份/强制切换/删光 profile 快照）
> 3. `inject.py`：生成/复用 auth-token + 烘焙占位符；幂等门判据是块内含 `x-zca-token` 字符串（marker 存在性无法区分旧版无 token 块）；旧块整体替换重烘焙
> 4. `verify.py`：块内 `__ZCA_TOKEN__` 残留 = FAIL
> 5. **以后更新 ui_accounts.js 时不要删 TOKEN 逻辑**；版本升号基数从 1.0.2 起算下一次为 1.0.3
> 6. 你们此前提出的接口疑点已核实：route-override 的广告互斥让位检测确实基于 `data-zca-ad-model`，但当前你方 assets 的横幅用的是 `zca-model-ad` class——互斥让位的让步方是 route-override（它查 `data-zca-ad-model`），所以横幅属性不需要改；如有冲突实测再议。

目标：未来账号切换功能更新由本窗口完成 → 产物提交到整合包 `zcode-mod-kit/modules/account-switcher/`，由主整合窗口发布。**本窗口不再处理任何 GitHub 内容（push/Release/Issue 均由主整合窗口负责）。**

## 1. 主整合窗口修复了你们产物的以下内容（请同步知晓，勿回滚）

| # | 文件 | 修复 |
|---|---|---|
| 1 | `inject.py` | `MAIN_IMPORT` 硬编码 `\n` 改为**按 `out/main/index.js` 实际换行风格**（`\r\n` 文件用 `\r\n`），保证 uninject 字节级还原 |
| 2 | `uninject.py` | `remove_block` 删除了"回退到行首"逻辑——原实现在单行 HTML 里会把整个文件头部切掉（mock 测试实锤）。现在按注入点精确切除（`marker` 至 `</script>` + 尾随换行） |
| 3 | `verify.py` | import 行判定同步改为兼容两种换行（`startswith(MAIN_IMPORT_CORE)`） |
| 4 | `module.json` | order=40 已就位，未改动 |

## 2. 以后的标准结构与更新方式（v1.0.1 起冻结）

```
zcode-mod-kit/modules/account-switcher/
├── module.json   # slug/display_name/version/description/order/targets/markers
├── inject.py     # 目录模式注入：--dir <解包目录>（--zcode-cjs/--install-root 仅接受不使用）
├── uninject.py
├── verify.py     # exit 0 = 已注入（主进程模块 byte-for-byte + import 行 + 渲染层块）
└── assets/
    ├── zcode-account-switcher-main.mjs
    └── ui_accounts.js
```

**更新功能时**：
- 功能改动碰 `assets/` 两个文件，改完 `module.json` 的 `version` 升号
- 约定不变：`import("./zcode-account-switcher-main.mjs").catch(()=>{});` 前缀、`<script id="zcode-account-switcher">` 标记、端口 `27890`、`~/.zcode/account-profiles/` 数据目录
- 自测：跑 `python C:\Users\adamt\.zcode\workspace\default\zcode-mod-kit\tests\test_modules.py`（LF + CRLF 双用例都在）
- 完成后通知主整合窗口合体发布

**硬约束**：
- 注释英文、bat 纯 ASCII、零第三方依赖；注入幂等（markers 全在 → `[SKIP]`）
- 渲染层广告横幅与 route-override 的横幅有互斥约定（`data-zca-ad-model` 存在时对方让步）——修改广告逻辑前先看对方 assets 里的注释

## 3. GitHub 归属

[zcode-account-switcher](https://github.com/Adam1290-0/zcode-account-switcher) 已停更（README 有迁移横幅）且 open issue 已闭环；所有发布由主整合窗口在 [zcode-mod-kit](https://github.com/Adam1290-0/zcode-mod-kit) 统一处理。你们窗口不要再 push 任何 GitHub 仓库。

## 4. 其他须知

- **真机验证**：主进程服务 `127.0.0.1:27890` 需监听；`/api/diag` 的 adPresent/btnPresent/descFound 三真值可用作冒烟
- ZCode 每次升级后用户只需 `reinstall.bat`；菜单文案/凭据结构锚点失效时由你们适配并只提交模块产物
- 卸载语义：整合器里 OFF = 对已注入模块执行卸载，用户 Profile 数据永远不删