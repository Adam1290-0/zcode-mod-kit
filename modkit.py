#!/usr/bin/env python3
"""ZCode Mod Kit - all-in-one patcher for ZCode addon modules.

Cyberpunk-style interactive menu: up/down to pick a module, left/right to
toggle INJECT / SKIP, ENTER to apply. Remembers the last selection in
config.json so `reinstall.bat` can re-apply everything after a ZCode update
with zero interaction.

ASCII-only output (cmd codepage safe). Python stdlib only.
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    import msvcrt  # Windows only - arrow key input
except ImportError:
    msvcrt = None

ROOT = Path(__file__).resolve().parent
MODULES_DIR = ROOT / "modules"
CONFIG = ROOT / "config.json"

# ---- cyberpunk palette -----------------------------------------------------
RESET = "\x1b[0m"
CYAN = "\x1b[96m"
MAGENTA = "\x1b[95m"
YELLOW = "\x1b[93m"
GREEN = "\x1b[92m"
RED = "\x1b[91m"
BLUE = "\x1b[94m"
DIM = "\x1b[2m"
BOLD = "\x1b[1m"
WHITE = "\x1b[97m"
BG_CYAN = "\x1b[46m\x1b[30m"
BG_GREEN = "\x1b[42m\x1b[30m"
BG_RED = "\x1b[41m\x1b[30m"
# neon 256-color set for gradients
N_PINK = "\x1b[38;5;213m"
N_PURPLE = "\x1b[38;5;135m"
N_CYAN = "\x1b[38;5;51m"
N_BLUE = "\x1b[38;5;39m"
N_YELLOW = "\x1b[38;5;220m"
N_ORANGE = "\x1b[38;5;208m"

AD_URL = "https://sharellm.net/sign-up?aff=wb5b"
# mod-kit's own version: single machine-readable source (README badge/changelog
# bump in lockstep). Baked into the skin ui at inject time for the update banner.
KIT_VERSION = "2.0.0"

# ---------------------------------------------------------------------------
# language: Chinese systems get Chinese by default, everything else English.
# The menu switches live with L and the choice is remembered in config.json.
# ---------------------------------------------------------------------------
LANGS = ("zh", "en")
_lang = "en"


def _system_lang():
    """zh when Windows' UI language is Chinese, else en.

    Order matters. Git Bash on a Chinese Windows sets LANG=C.UTF-8, which is a
    shell default and says nothing about the user's language - treating it as
    authoritative made every Chinese machine come out English. So C/POSIX are
    discarded, a real zh/xx locale is honoured, and Windows' own UI language is
    the final word.
    """
    import locale
    probe = " ".join(filter(None, (
        os.environ.get("LC_ALL"), os.environ.get("LANG"),
        os.environ.get("LANGUAGE")))).strip()
    low = probe.lower()
    # Only the C/POSIX pseudo-locales are meaningless (Git Bash defaults to
    # C.UTF-8). A real "en_US" or "zh_CN" is the user's own choice and wins.
    if low and not low.startswith(("c.utf-8", "c", "posix")):
        return "zh" if low.startswith("zh") else "en"
    if os.name == "nt":
        try:
            # 0x0804 = zh-CN, 0x0404 = zh-TW; the low byte is the primary id
            import ctypes
            lid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            if (lid & 0xFF) == 0x04:
                return "zh"
            return "en"
        except Exception:
            pass
    try:
        loc = locale.getlocale()[0] or ""
    except Exception:
        loc = ""
    low = str(loc).lower()
    if any(k in low for k in ("chinese", "zh_cn", "zh-cn", "zh_tw", "zh-tw")):
        return "zh"
    return "en"


def set_lang(lang):
    global _lang
    _lang = lang if lang in LANGS else "en"


def lang():
    return _lang


# Every user-facing string. Format placeholders are kept identical across
# languages so call sites can stay single-expression.
T = {
    "menu.hint1": {
        "en": "  UP/DOWN pick    LEFT/RIGHT or SPACE toggle    ENTER review & apply",
        "zh": "  上下键选择    左右键或空格切换    ENTER 确认后执行",
    },
    "menu.hint2": {
        "en": "  A all-on    N all-off    R load last    O sponsor    "
              "L 中文/English    Q/ESC quit",
        "zh": "  A 全开    N 全关    R 载入上次    O 赞助    "
              "L 中文/English    Q/ESC 退出",
    },
    "menu.dirty": {
        "en": "  * selections differ from the last run - press R to go back to it",
        "zh": "  * 当前勾选与上次运行不同 - 按 R 可恢复上次的选择",
    },
    "menu.title": {
        "en": "  zcode-mod-kit  ::  modular patcher console",
        "zh": "  zcode-mod-kit  ::  模块化补丁控制台",
    },
    "menu.no_saved": {
        "en": "\n  no saved selection yet - run install.bat once first.\n",
        "zh": "\n  还没有保存过的选择 - 请先跑一次 install.bat。\n",
    },
    "menu.back": {
        "en": "  press ENTER to go back to the menu ",
        "zh": "  按 ENTER 返回菜单 ",
    },
    "review.title": {"en": "  REVIEW", "zh": "  确认清单"},
    "review.install": {"en": "  ZCode install : ", "zh": "  ZCode 安装位置 : "},
    "review.notfound": {"en": "NOT FOUND", "zh": "未找到"},
    "review.counts": {"en": "  Modules ON    : ", "zh": "  启用模块 : "},
    "review.off": {"en": "    OFF: ", "zh": "    关闭: "},
    "review.alloff": {
        "en": "  Nothing is ON - this will REMOVE every module currently installed.",
        "zh": "  一个模块都没开 - 这会移除当前已安装的全部模块。",
    },
    "review.rewrite": {
        "en": "  This rewrites app.asar and zcode.cjs. ZCode must be closed.",
        "zh": "  这会重写 app.asar 与 zcode.cjs，ZCode 必须先完全退出。",
    },
    "review.ask": {"en": "  apply this plan? [y/N] ", "zh": "  确认执行？[y/N] "},
    "summary.ok": {"en": "  ALL SYSTEMS OPERATIONAL  ", "zh": "  全部完成  "},
    "summary.fail": {"en": "  COMPLETED WITH FAILURES  ", "zh": "  存在失败项  "},
    "summary.failed_list": {
        "en": "  These modules did not complete: ",
        "zh": "  这些模块没有完成: ",
    },
    "summary.failed_help": {
        "en": "  Re-run install.bat and open an issue with the log above.",
        "zh": "  请重跑 install.bat，并带上上面的日志提 issue。",
    },
    "summary.backup_ok": {
        "en": "  Your previous asar backup is intact: app.asar.kitbak.",
        "zh": "  上一次的 asar 备份完好: app.asar.kitbak。",
    },
    "summary.reinstall": {
        "en": "  ZCode was updated? Just re-run reinstall.bat -",
        "zh": "  ZCode 刚更新过？直接重跑 reinstall.bat -",
    },
    "summary.reinstall2": {
        "en": "  it re-applies this exact selection in one shot.",
        "zh": "  它会按这套选择一次性重打。",
    },
    "summary.start": {
        "en": "  Start ZCode now: the modules load at boot.",
        "zh": "  现在可以启动 ZCode 了，模块随启动加载。",
    },
    "summary.removed": {
        "en": "  Every selected module was removed; app.asar and",
        "zh": "  所选模块已全部移除，app.asar 与",
    },
    "summary.removed2": {
        "en": "  zcode.cjs are back to the official bytes.",
        "zh": "  zcode.cjs 已恢复为官方原始字节。",
    },
    "summary.removed3": {
        "en": "  Want them back? Run install.bat and pick modules again.",
        "zh": "  想重新装回来？跑 install.bat 重新勾选即可。",
    },
    "err.zcode_running": {
        "en": "  ZCode is running.",
        "zh": "  ZCode 正在运行。",
    },
    "err.zcode_running2": {
        "en": "  Fully quit it first: right-click the tray icon -> Quit",
        "zh": "  请先完全退出：右键托盘图标 -> 退出",
    },
    "err.zcode_running3": {
        "en": "  (closing the window is not enough - the process stays).",
        "zh": "  （只关窗口不够 - 进程还在）。",
    },
    "err.after_quit": {
        "en": "  press ENTER after quitting, or Ctrl+C to abort ",
        "zh": "  退出后按 ENTER 继续，或 Ctrl+C 中止 ",
    },
    "err.still_running": {
        "en": "  still running - aborting. Nothing was changed.",
        "zh": "  仍在运行 - 已中止，未做任何修改。",
    },
    "byebye": {"en": "BYE. \\o/", "zh": "再见。\\o/"},
    "splash.done": {
        "en": "   painting done - the menu opens next.",
        "zh": "   版式完成 - 接下来进入菜单。",
    },
    "splash.winter": {"en": "winter edition", "zh": "冬季版"},
    "splash.reassure": {
        "en": "   every module is optional and reversible; nothing is "
              "written outside",
        "zh": "   每个模块都可选、可逆；除 ZCode 安装目录与",
    },
    "splash.reassure2": {
        "en": "   your ZCode install and ~/.zcode/plugins.",
        "zh": "   ~/.zcode/plugins 之外不写任何东西。",
    },
    "splash.modules": {"en": "   MODULES", "zh": "   模块"},
    "splash.loaded": {
        "en": "  %d loaded  ·  every one optional and reversible",
        "zh": "  已载入 %d 个  ·  全部可选可逆",
    },
    "splash.skip": {"en": "  press any key to skip", "zh": "  按任意键跳过"},
    "splash.word": {"en": "winter edition", "zh": "冬季版"},
    # per-module note shown under the menu
    "hint.route-override": {
        "en": "cjs chain first, pin wraps outside it",
        "zh": "先装 cjs 链，pin 包在它外层",
    },
    "hint.pin": {
        "en": "injects after the route-override marker (fallback: use strict)",
        "zh": "接在 route-override 的标记之后（找不到则退回 use strict）",
    },
    "hint.skin-manager": {
        "en": "renderer-only, order-independent",
        "zh": "只改渲染层，与顺序无关",
    },
    "hint.account-switcher": {
        "en": "main + renderer, order-independent",
        "zh": "主进程 + 渲染层，与顺序无关",
    },
    "hint.snapshot-kill": {
        "en": "static gate in out/host/index.js",
        "zh": "在 out/host/index.js 里加静态闸门",
    },
    "hint.usage-bar": {
        "en": "one import line at the tail of out/main/index.js",
        "zh": "在 out/main/index.js 尾部加一行 import",
    },
    "hint.edit-resend-model-fix": {
        "en": "makes retry replay the model/mode you have selected now",
        "zh": "让重试走你当前选中的模型与模式",
    },
    "hint.usage-stats-fallback": {
        "en": "backfills pre-09 usage from the message table",
        "zh": "从 message 表回填 9 月之前的用量",
    },
    "hint.zombie-cleanup": {
        "en": "shutdown hook runs a powershell sweep for orphaned MCP",
        "zh": "退出钩子跑 powershell 清理孤儿 MCP 进程",
    },
    "hint.voice-input": {
        "en": "renderer button + main dynamic import (ZCode 3.18+)",
        "zh": "渲染层按钮 + 主进程动态 import（ZCode 3.18+）",
    },
}


def t(key, *fmt):
    """Look up a translated string, falling back to English then the key."""
    entry = T.get(key)
    if not entry:
        return key
    s = entry.get(_lang) or entry.get("en") or key
    return s % fmt if fmt else s
AD_INTRO = [
    ("SHARELLM.NET", N_PINK + BOLD),
    ("  AI model sharing platform - massive models, one subscription", N_CYAN),
    ("  Claude / GPT / Gemini / DeepSeek and more, ready to use", N_CYAN),
    ("  Sign up via the invite link below and start in minutes", DIM),
]

# module slug -> menu label (ASCII only)
LABELS = {
    "route-override": "ROUTE  headers + vpn tunnel per provider",
    "pin": "PIN    sticky context re-injection",
    "skin-manager": "SKIN   wallpaper / opacity / ambient edge",
    "account-switcher": "ACCT   one-click multi-account switch",
    "snapshot-kill": "SNAP   repo-snapshot upload kill-switch",
    "usage-bar": "USAGE  token usage statusbar (zusage)",
    "edit-resend-model-fix": "EDITFIX edit-resend replays CURRENT model/mode",
    "usage-stats-fallback": "HISTFIX usage page backfills pre-09 message tokens",
    "zombie-cleanup": "ZOMBIE  kill orphaned MCP procs on exit",
    "voice-input": "VOICE  local speech-to-text on the official mic button",
}
ORDER_HINT = {
    "route-override": "cjs chain first, pin wraps outside it",
    "pin": "injects after route-override marker (fallback: use strict)",
    "skin-manager": "renderer-only, order-independent",
    "account-switcher": "main + renderer, order-independent",
    "snapshot-kill": "static gate in out/host/index.js",
    "usage-bar": "one import line at the tail of out/main/index.js",
    "edit-resend-model-fix": "drops 3 stale fields in zcode.cjs SJo re-run",
    "usage-stats-fallback": "Xkr 2 insertions in zcode.cjs usage query",
    "zombie-cleanup": "shutdown handler fires powershell cleanup script",
    "voice-input": "renderer button + main dynamic import (ZCode 3.18+)",
}

BANNER_LINES = [
    r" ____ ____ ___  ____  _____    __  __ ___  ____    _  ___ ___ _____ ",
    r"|__  |  _ \_  ||_  ||  _  |  |  \/  | __||  _ \  | |/ / |_ _|_   _|",
    r"  / /| |_| / /__| |__| |_| |  | |\/| |  _|| | | | | ' /   | |  | |  ",
    r" /_/ |____/___/|____/|____/   |_|  |_|___||_| |_| |_|\_\ |___| |_|  ",
]
# neon gradient across the banner: pink -> purple -> cyan -> blue
GRADIENT = [N_PINK, N_PURPLE, N_CYAN, N_BLUE]
WINTER_GRADIENT = ["\x1b[38;5;111m", "\x1b[38;5;117m",
                   "\x1b[38;5;153m", "\x1b[38;5;195m"]

# NO_COLOR (no-color.org): respected by setting every palette entry to "" so
# no code path has to test for it. The ON/OFF words, the [+] / [ ] markers and
# the reverse-video selected row all still carry the information without colour.
NO_COLOR = bool(os.environ.get("NO_COLOR"))


def c(code, text):
    return text if NO_COLOR else code + text + RESET


def safe_print(*args, **kw):
    """print() that cannot die on a console whose codepage lacks a glyph.

    install.bat sets chcp 65001, but a user running `python modkit.py` from a
    plain cmd inherits cp936. Emitting the Chinese UI there raises
    UnicodeEncodeError mid-menu and kills the installer. Re-encode with
    'replace' so the worst case is a question mark, not a crash.
    """
    text = " ".join(str(a) for a in args)
    try:
        print(text, **kw)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        try:
            print(text.encode(enc, "replace").decode(enc, "replace"), **kw)
        except Exception:
            pass


def _disp_width(s):
    """Terminal cell width: CJK / fullwidth glyphs occupy two columns."""
    import unicodedata
    w = 0
    for ch in s:
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


def pad_display(s, width):
    """Left-justify by DISPLAY width so a Chinese label does not shift the
    version column right (str.ljust counts characters, not cells)."""
    return s + " " * max(0, width - _disp_width(s))


def order_hint(slug):
    """The per-module note under the menu, translated."""
    key = "hint." + slug
    if key in T:
        return t(key)
    return ORDER_HINT.get(slug, "")


def gradient_banner():
    """Each banner line in its own neon shade."""
    pal = WINTER_GRADIENT if _winter_palette() else GRADIENT
    return "\n" + "\n".join(c(pal[i], ln) for i, ln in enumerate(BANNER_LINES))


def clickable(url, text):
    """OSC 8 hyperlink; terminals that don't support it just show the text."""
    return "\x1b]8;;" + url + "\x1b\\" + c(N_YELLOW + BOLD, text) + "\x1b]8;;\x1b\\"


def print_ad_block(clickable_link=False):
    """sharellm ad block; footer form carries an OSC 8 clickable link."""
    print(c(N_PURPLE, "  +" + "-" * 66 + "+"))
    for text, color in AD_INTRO:
        print("  " + c(DIM, "|") + " " + c(color, text.ljust(62)) + " " + c(DIM, "|"))
    if clickable_link:
        print("  " + c(DIM, "|") + " " +
              clickable(AD_URL, AD_URL).ljust(62 + len(AD_URL)) + " " + c(DIM, "|"))
        print("  " + c(DIM, "|") + " " +
              c(MAGENTA, "press O to open it in your browser right now".ljust(62)) + " " + c(DIM, "|"))
    else:
        print("  " + c(DIM, "|") + " " +
              c(DIM, ("invite: " + AD_URL)[:62].ljust(62)) + " " + c(DIM, "|"))
    print(c(N_PURPLE, "  +" + "-" * 66 + "+"))


def try_open_ad():
    """Open the ad link in the default browser (wait screens suggest it)."""
    try:
        import os
        os.startfile(AD_URL)
        print(c(GREEN, "  opening " + AD_URL))
        return True
    except Exception:
        print(c(RED, "  could not open browser; link: " + AD_URL))
        return False


def vt_on():
    """Enable ANSI escape processing on legacy cmd consoles."""
    try:
        import os
        os.system("")
    except Exception:
        pass


def clear():
    sys.stdout.write("\x1b[2J\x1b[H")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# winter intro: layered snowfall + a light sweep across the wordmark
# ---------------------------------------------------------------------------
# Three depth planes. Far flakes are dim, small and drift slowly; near flakes
# are bright, large and fall fast. That parallax is what separates "snow" from
# "random dots": without it every flake moves at the same rate and the eye
# reads it as noise.
SNOW_PLANES = (
    # (weight, chars,        dim colour,        bright colour,  speed band)
    (0.50, ("\u00b7", "."), "\x1b[38;5;60m", "\x1b[38;5;153m", (0.30, 0.55)),
    (0.32, ("*", "+"),      "\x1b[38;5;110m", "\x1b[38;5;159m", (0.55, 0.95)),
    (0.18, ("*", "o", "O"), "\x1b[38;5;153m", "\x1b[38;5;231m", (0.95, 1.55)),
)
SNOW_SPARKLE = "\x1b[38;5;231m"

BANNER_GRAD = ("\x1b[38;5;117m", "\x1b[38;5;153m",
               "\x1b[38;5;159m", "\x1b[38;5;195m",
               "\x1b[38;5;231m")

WINTER_WORDS = ("winter edition", "snow on the wire",
                "cold boot", "frost / 冬")


def _winter_palette():
    """Cold neon for the winter months, the usual palette otherwise."""
    import datetime
    return datetime.date.today().month in (11, 12, 1, 2)


def _make_flakes(rows, cols, count):
    """Spawn flakes with a depth plane each; y starts above the top edge so the
    first frame already has snow in flight instead of an empty sky."""
    import random
    flakes = []
    for _ in range(count):
        r = random.random()
        acc = 0.0
        plane = SNOW_PLANES[-1]
        for p in SNOW_PLANES:
            acc += p[0]
            if r <= acc:
                plane = p
                break
        _, chars, dim, bright, (vlo, vhi) = plane
        flakes.append({
            "x": random.uniform(0, cols - 1),
            "y": random.uniform(-rows, rows - 1),
            "v": random.uniform(vlo, vhi),
            # horizontal sway is a phase-shifted sine, not a random walk:
            # a walk makes flakes jitter like static, a sine reads as wind
            "sway_amp": random.uniform(0.0, 1.6),
            "sway_ph": random.uniform(0, 6.283),
            "sway_sp": random.uniform(0.03, 0.11),
            "ch": random.choice(chars),
            "col": bright if random.random() < 0.30 else dim,
            "tw": random.random() < 0.25,      # twinkles while falling
            "ph": random.uniform(0, 6.283),
        })
    return flakes


def _render_frame(grid, rows, cols, t):
    """Compose one frame: snow, then the wordmark on a cleared plateau."""
    out = ["\x1b[H"]
    for y in range(rows):
        out.append("  " + "".join(grid[y]) + RESET + "\n")
    return "".join(out)


def snowfall(seconds=3.0, rows=15, cols=76, fps=24, reveal=True):
    """Layered snow that settles, then the wordmark rises through it.

    Runs on the alternate screen and always restores the terminal. When stdout
    is not a TTY it prints one static line instead of thousands of escape
    codes, so `install.bat > log.txt` stays readable.
    """
    import math
    import random

    if not sys.stdout.isatty():
        print(c(N_CYAN, "  *  .  *   winter edition  *  .  *"))
        return

    flakes = _make_flakes(rows, cols, max(40, int(cols * 0.85)))
    banner_top = max(1, rows // 2 - 3)
    banner_w = max(len(ln) for ln in BANNER_LINES)
    banner_left = max(2, (cols - banner_w) // 2)

    sys.stdout.write("\x1b[?1049h")     # alternate screen
    sys.stdout.write("\x1b[?25l")       # hide cursor
    skip_hint = t("splash.skip")   # translate before `t` is
                                    # rebound to the frame clock
    try:
        frames = int(seconds * fps)
        for f in range(frames):
            # A 3 second intro is pleasant once and annoying on the tenth
            # reinstall. Poll the keyboard without consuming input when there
            # is no console (msvcrt is None under a redirected stdout).
            if msvcrt is not None:
                try:
                    if msvcrt.kbhit():
                        msvcrt.getwch()
                        break
                except Exception:
                    pass
            elapsed = f / fps
            grid = [[" "] * cols for _ in range(rows)]
            for s in flakes:
                s["y"] += s["v"]
                if s["y"] >= rows + 1:
                    s["y"] = -1.0 - random.random() * 3
                    s["x"] = random.uniform(0, cols - 1)
                x = int(s["x"] + math.sin(elapsed * s["sway_sp"] * 6.283 + s["sway_ph"])
                        * s["sway_amp"])
                y = int(s["y"])
                if not (0 <= y < rows and 0 <= x < cols):
                    continue
                ch = s["ch"]
                col = s["col"]
                if s["tw"] and math.sin(elapsed * 5.0 + s["ph"]) > 0.72:
                    ch, col = "+", SNOW_SPARKLE
                grid[y][x] = col + ch + RESET

            # wordmark: rises line by line over the last 45% of the intro,
            # each line lit by a moving highlight band (a static gradient on a
            # still image looks like a screenshot; the sweep makes it "boot")
            if reveal and f > frames * 0.38:
                prog = (f - frames * 0.38) / max(1, frames * 0.62)
                shown = int(math.ceil(prog * len(BANNER_LINES)))
                sweep = (elapsed * 26.0) % (banner_w + 24) - 12
                for i, ln in enumerate(BANNER_LINES[:shown]):
                    y = banner_top + i
                    if not (0 <= y < rows):
                        continue
                    for j in range(cols):
                        grid[y][j] = " "
                    for j, ch in enumerate(ln):
                        if ch == " ":
                            continue
                        x = banner_left + j
                        if not (0 <= x < cols):
                            continue
                        d = abs(j - sweep)
                        shade = BANNER_GRAD[0]
                        if d < 3:
                            shade = BANNER_GRAD[4]
                        elif d < 9:
                            shade = BANNER_GRAD[3]
                        elif d < 16:
                            shade = BANNER_GRAD[2]
                        grid[y][x] = shade + ch + RESET

            out = [_render_frame(grid, rows, cols, elapsed)]
            if reveal and f > frames * 0.72:
                word = random.choice(WINTER_WORDS)
                pad = max(0, (cols - len(word) - 4) // 2)
                out.append("  " + " " * pad +
                           c("\x1b[38;5;195m" + BOLD, "~ " + word + " ~") + "\n")
            if f < frames * 0.5:
                out.append(c(DIM, skip_hint) + "\n")
            sys.stdout.write("".join(out))
            sys.stdout.flush()
            time.sleep(1.0 / fps)
    except (KeyboardInterrupt, OSError):
        pass
    finally:
        sys.stdout.write("\x1b[?25h")
        sys.stdout.write("\x1b[?1049l")   # back to the normal screen
        sys.stdout.flush()


def module_roster(mods):
    """One line per module: version + what it does. Screen-reader friendly."""
    lines = []
    width = max(len(m.get("version", "")) for m in mods) if mods else 0
    # Name column width must follow the longest label (EDITFIX/HISTFIX are 7),
    # otherwise the version runs into the name: "EDITFIXv7.0.3".
    name_w = max(len(LABELS.get(m["slug"], m["slug"]).partition(" ")[0])
                 for m in mods) if mods else 7
    for m in mods:
        slug = m["slug"]
        ver = m.get("version", "")
        label = LABELS.get(slug, slug)
        name, _, desc = label.partition(" ")
        lines.append("   " + c(N_CYAN + BOLD, name.ljust(name_w + 2)) +
                     c(DIM, ("v%s" % ver).ljust(width + 2)) +
                     c(WHITE, desc.strip()))
    return "\n".join(lines)


def _rule(width=74, ch="\u2500"):
    return c("\x1b[38;5;60m", "   " + ch * width)


def splash_plate(mods, kit_version=""):
    """The single screen the user sees before the menu.

    One composition instead of the old "animation, clear, loose text": banner,
    a version rule, the module grid and a hint line, all inside one frame so it
    still reads as a designed plate after the snow has gone.
    """
    winter = _winter_palette()
    out = [""]
    if winter:
        out.append(c("\x1b[38;5;54m", "   ~  ") +
                   c("\x1b[38;5;117m", t("splash.winter")) +
                   c("\x1b[38;5;54m", "  ~"))
        out.append("")
    out.append(gradient_banner())
    out.append("")
    left = "  zcode mod kit"
    right = ("v%s" % kit_version) if kit_version else ""
    out.append(c(DIM, "   " + left.ljust(58) + right))
    out.append(_rule())
    out.append("")
    out.append(c(MAGENTA + BOLD, t("splash.modules")) +
               c(DIM, t("splash.loaded", len(mods))))
    out.append("")
    out.append(module_roster(mods))
    out.append("")
    out.append(c(DIM, t("splash.reassure")))
    out.append(c(DIM, t("splash.reassure2")))
    out.append(_rule())
    return "\n".join(out)


def winter_banner(mods):
    """Banner block printed once before the interactive menu."""
    return splash_plate(mods, KIT_VERSION) + "\n"


def hide_cursor():
    sys.stdout.write("\x1b[?25l")
    sys.stdout.flush()


def show_cursor():
    sys.stdout.write("\x1b[?25h")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# modules / config
# ---------------------------------------------------------------------------

def load_modules():
    mods = []
    for d in sorted(MODULES_DIR.iterdir()):
        mj = d / "module.json"
        if d.is_dir() and mj.exists():
            try:
                m = json.loads(mj.read_text(encoding="utf-8"))
            except Exception:
                continue
            m["_dir"] = d
            mods.append(m)
    mods.sort(key=lambda m: m.get("order", 50))
    return mods


def load_config():
    if CONFIG.exists():
        try:
            return json.loads(CONFIG.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_config(cfg):
    CONFIG.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _registry_install_locations():
    """InstallLocation of uninstall entries whose DisplayName mentions ZCode.
    NSIS/Squirrel installers register here, so this finds standard installs
    on any drive — the kit must never assume a fixed path."""
    found = []
    try:
        import winreg
    except ImportError:
        return found
    for hive, key_path in (
        (winreg.HKEY_CURRENT_USER,
         r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ):
        try:
            with winreg.OpenKey(hive, key_path) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        with winreg.OpenKey(key, winreg.EnumKey(key, i)) as sub:
                            disp = str(winreg.QueryValueEx(sub, "DisplayName")[0])
                            if "zcode" not in disp.lower():
                                continue
                            loc = winreg.QueryValueEx(sub, "InstallLocation")[0]
                            if loc:
                                found.append(Path(str(loc).rstrip("/\\")))
                    except OSError:
                        continue
        except OSError:
            continue
    return found


def _is_zcode_root(p):
    """A folder counts as the ZCode root only when the real target exists."""
    try:
        return (p / "resources" / "app.asar").is_file()
    except OSError:
        return False


def find_zcode_root():
    """Locate the ZCode install: env override, registry, then common paths.

    NEVER assume one fixed drive — the kit must work on machines where ZCode
    lives in %LOCALAPPDATA%\\Programs, Program Files or any drive root."""
    candidates = []
    env = os.environ.get("ZCODE_ROOT")
    if env:
        candidates.append(Path(env))
    candidates += _registry_install_locations()
    home = Path.home()
    candidates += [
        home / "AppData" / "Local" / "Programs" / "ZCode",
        home / "AppData" / "Local" / "Programs" / "zcode",
        home / "AppData" / "Local" / "ZCode",
        home / "AppData" / "Roaming" / "ZCode",
        Path("C:/Program Files/ZCode"),
        Path("C:/Program Files (x86)/ZCode"),
        ROOT,  # kit copied INTO the ZCode folder (documented fallback)
    ]
    for d in "CDEFGH":
        candidates.append(Path(d + ":/Zcode"))
        candidates.append(Path(d + ":/zcode"))
    for p in candidates:
        if _is_zcode_root(p):
            return p
    return None


# ZCode versions the shipped modules were verified against (kept in sync with
# each module's own compatibility table; bumped when modules are re-validated)
# 3.14.4 (2026-09-29): four injection targets unchanged; all 7 modules verified
# with zero anchor drift across the 7 module windows.
# 3.16.2 (2026-10-19): four targets present; all 6 modules inject/verify/node-check
# pass; uninject byte-identical restore confirmed.
# 3.16.3 (2026-10-23): same four targets; full roundtrip re-validated, no drift.
# 3.17.2 (2026-11-02): same four targets; full roundtrip re-validated, no drift.
# 3.18.0 (2026-11-10): same four targets; full roundtrip re-validated, no drift.
# 3.18.2 (2026-11-16): zombie anchor d()/c0s, edit-resend DR + Mi/ii() aliases.
# 3.19.1 (2026-11-23): zod binding m->d, edit-resend $R/qc/fj + Di/ei(), gate var p.
VERIFIED_VERSIONS = {"3.12.2", "3.12.3", "3.14.1", "3.14.3", "3.14.4", "3.15.3", "3.16.2", "3.16.3", "3.17.2", "3.18.0", "3.18.2", "3.19.1"}


def read_asar_version(asar_path):
    """Read the app version out of package.json inside the asar header.
    Header layout: uint32 leading(4) + uint32 json_len(4) + JSON payload."""
    try:
        import struct
        with open(asar_path, "rb") as f:
            f.seek(4)
            jl = struct.unpack("<I", f.read(4))[0]
            if not (0 < jl < 20_000_000):
                return None
            hdr = f.read(jl).decode("utf-8", "replace")
        i = hdr.find('{"files"')
        if i < 0:
            i = hdr.find("{")
        pkg = json.loads(hdr[i:].rstrip("\0"))
        files = pkg.get("files", {})
        pj = files.get("package.json")
        if not pj or "offset" not in pj:
            return None
        base = 8 + jl
        base += (4 - (base % 4)) % 4
        with open(asar_path, "rb") as f:
            f.seek(base + int(pj["offset"]))
            content = f.read(min(int(pj["size"]), 65536)).decode("utf-8", "replace")
        return json.loads(content).get("version")
    except Exception:
        return None


def version_compat_check(asar_path, cfg):
    """Warn when the running ZCode version was never verified with these
    modules. Returns the version string (or '?')."""
    ver = read_asar_version(asar_path)
    if not ver:
        print(c(YELLOW, "[VERSION] could not read the ZCode version from the asar"))
        return "?"
    last_seen = cfg.get("last_zcode_version")
    if last_seen and last_seen != ver:
        print(c(CYAN, f"[VERSION] ZCode was updated ({last_seen} -> {ver}) - "
                      f"patches were wiped; reinstalling everything"))
    if ver in VERIFIED_VERSIONS:
        print(c(GREEN, f"[VERSION] ZCode {ver} - verified compatible"))
    else:
        print(c(YELLOW, f"[VERSION] ZCode {ver} - NOT in the verified list "
                        f"({', '.join(sorted(VERIFIED_VERSIONS))})"))
        print(c(YELLOW, "          modules are patched best-effort and may misbehave; "
                        "if anything breaks, please open an issue"))
    return ver


# Content markers each module leaves in the PACKED asar. Used to decide whether
# the current asar is a clean pre-patch baseline before refreshing kitbak. A
# partial patch (any single module) must count as NOT clean, or refreshing the
# backup would overwrite the clean baseline with a patched asar.
ASAR_RENDERER_MARKERS = ("zcode-skin-ui", "zcode-account-switcher",
                         "zcode-route-override-ui", "zcode-pin-ui",
                         "zcode-voice-ui")
ASAR_HOST_MARKER = "zcode-snapshot-kill-switch"   # snapshot-kill -> out/host/index.js
# usage-bar and voice-input both append a dynamic-import line to the same file.
ASAR_MAIN_MARKERS = ("[zusage]", "voice-main.cjs")
ASAR_CHUNK_MARKERS = ("zcode-editresend-ui",)     # edit-resend   -> out/renderer/assets/*.js chunk

# Every marker a module writes into zcode.cjs. Used to decide whether the loose
# cjs is a clean pre-patch baseline before refreshing zcode.cjs.kitbak. One
# marker is not enough: five modules write this file and any one of them makes
# it a patched baseline.
CJS_MARKERS = ("/*zro*/", "/*zpin*/", "zusage-fb-day",
               "zcode-zombie-cleanup", "zcode-editresend-model-fix")


def asar_is_clean(asar_path):
    """True only when the asar carries NONE of the six modules' injections.

    CANNOT use the head bytes: the first hundreds of KB are the asar INDEX
    (filenames+offsets), which never contains content markers - a head check is
    always 'clean' and would refresh kitbak on every run (observed 2026-09-22:
    the post-uninstall pack then overwrote the clean baseline). Parse the header
    and read the actual patched files.

    Every module marker is checked, across all three patched files. The old
    check looked at skin+account only, so a pin-only (or route- / snapshot- /
    usage-only) install read as 'clean' and refreshing kitbak overwrote the
    baseline with a patched asar - the same data-loss class, narrower trigger.

    Unreadable -> False (treat as patched; never destroy the backup)."""
    try:
        import struct
        with open(asar_path, "rb") as f:
            f.seek(4)
            jl = struct.unpack("<I", f.read(4))[0]
            if not (0 < jl < 20_000_000):
                return False
            hdr = f.read(jl).decode("utf-8", "replace")
        pkg = json.loads(hdr[hdr.find("{"):].rstrip("\0"))
        base = 8 + jl
        base += (4 - (base % 4)) % 4
        files = pkg.get("files", {})

        def read_entry(*parts):
            node = files
            for p in parts[:-1]:
                node = node.get(p, {}).get("files", {})
            entry = node.get(parts[-1])
            if not entry or "offset" not in entry:
                return None
            with open(asar_path, "rb") as f:
                f.seek(base + int(entry["offset"]))
                return f.read(int(entry["size"])).decode("utf-8", "replace")

        html = read_entry("out", "renderer", "index.html")
        if html is None:
            return False  # can't verify -> treat as patched, never destroy backup
        if any(m in html for m in ASAR_RENDERER_MARKERS):
            return False
        host = read_entry("out", "host", "index.js")
        if host and ASAR_HOST_MARKER in host:
            return False
        main = read_entry("out", "main", "index.js")
        if main and any(m in main for m in ASAR_MAIN_MARKERS):
            return False
        # edit-resend injects its renderer markers into a content-hashed
        # out/renderer/assets/*.js chunk (never index.html), so the index.html
        # scan above cannot see them. Walk every assets chunk so a
        # chunk-only patch still reads as NOT clean - the same kitbak
        # data-loss class as the index/host/main markers. Fail-closed: any
        # chunk carrying a marker means patched, regardless of chunk size.
        assets = (files.get("out", {}).get("files", {})
                  .get("renderer", {}).get("files", {})
                  .get("assets", {}).get("files", {}))
        for name, entry in assets.items():
            if not str(name).endswith(".js"):
                continue
            chunk = read_entry("out", "renderer", "assets", name)
            if chunk and any(m in chunk for m in ASAR_CHUNK_MARKERS):
                return False
        return True
    except Exception:
        return False  # unreadable = treat as patched, never destroy the backup


def zcode_running():
    try:
        # tasklist prints localized (GBK) headers on Chinese Windows; a bare
        # text=True decodes as utf-8 and the reader thread crashes on non-ASCII
        # bytes -> empty stdout -> "not running" every time. errors="replace"
        # keeps the ASCII process name ("ZCode.exe") intact either way.
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq ZCode.exe"],
            capture_output=True, text=True, timeout=20,
            encoding="utf-8", errors="replace",
        )
        return "ZCode.exe" in out.stdout
    except Exception:
        return False


# ---------------------------------------------------------------------------
# asar tooling
# ---------------------------------------------------------------------------

_spinner_frames = "|/-\\"
_spinner_stop = threading.Event()
# bouncing-ball track: one bounce = half a sine period across a 15-char lane
_BALL_TRACK_W = 15


def _ball_positions():
    """23 precomputed lane positions for one full bounce cycle."""
    import math
    return [int(round(math.sin(math.pi * k / 22) * (_BALL_TRACK_W - 1)))
            for k in range(23)]


SPINNER_TIPS = [
    "2-3 minutes is normal - app.asar is ~385 MB",
    "runtime files live in ~/.zcode/plugins - the kit folder is movable",
    "OFF on an injected module uninjects it surgically",
    "each ZCode update wipes patches - reinstall.bat brings them all back",
]


def _spin(label):
    """Neon bouncing ball with a fading trail + elapsed time + rotating tips."""
    start = time.time()
    track = _ball_positions()
    n = len(track)
    i = 0
    trail = []
    while not _spinner_stop.is_set():
        elapsed = int(time.time() - start)
        pos = track[i % n]
        trail.append(pos)
        if len(trail) > 4:
            trail.pop(0)
        lane = [" "] * _BALL_TRACK_W
        for p in trail[:-1]:
            lane[p] = "\u00b7"  # fading trail dots behind the ball
        ball_color = GRADIENT[(i // 5) % len(GRADIENT)]
        tip = SPINNER_TIPS[(elapsed // 8) % len(SPINNER_TIPS)]
        line = ("\r    [" + c(N_PURPLE + DIM, "".join(lane[:pos])) +
                c(ball_color + BOLD, "\u25cf") +
                c(N_PURPLE + DIM, "".join(lane[pos + 1:]) + "]") +
                " " + c(BOLD, label) + " " + c(DIM, f"{elapsed:3d}s") +
                "   " + c(DIM, tip) + "  " + "\x1b[K")
        sys.stdout.write(line)
        sys.stdout.flush()
        i += 1
        time.sleep(0.06)
    sys.stdout.write("\r\x1b[K")
    sys.stdout.flush()


def run_asar(args, cwd, label):
    """Run npx @electron/asar with a spinner; returns (rc, output)."""
    _spinner_stop.clear()
    spin = threading.Thread(target=_spin, args=(label,), daemon=True)
    spin.start()
    proc = subprocess.Popen(
        "npx --yes @electron/asar " + args,
        shell=True, cwd=str(cwd),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    out, _ = proc.communicate()
    _spinner_stop.set()
    spin.join(timeout=1)
    return proc.returncode, out


def run_py(script, args, label):
    """Run a module python script with a spinner; returns (rc, output)."""
    _spinner_stop.clear()
    spin = threading.Thread(target=_spin, args=(label,), daemon=True)
    spin.start()
    proc = subprocess.Popen(
        [sys.executable, str(script)] + args,
        cwd=str(script.parent),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    out, _ = proc.communicate()
    _spinner_stop.set()
    spin.join(timeout=1)
    return proc.returncode, out


# ---------------------------------------------------------------------------
# patch engine
# ---------------------------------------------------------------------------

class KitPaths:
    def __init__(self, root):
        res = root / "resources"
        self.asar = res / "app.asar"
        self.cjs = res / "glm" / "zcode.cjs"
        self.unpacked = res / "app.asar.unpacked"
        self.asar_bak = res / "app.asar.kitbak"
        self.unpacked_bak = res / "app.asar.kitbak.unpacked"
        self.cjs_bak = res / "glm" / "zcode.cjs.kitbak"
        self.work = res / ".modkit-work"


def module_cmd(mod, work_dir, cjs_path, script_name):
    args = []
    if work_dir:
        args += ["--dir", str(work_dir)]
    if cjs_path and "zcode-cjs" in mod.get("targets", []):
        args += ["--zcode-cjs", str(cjs_path)]
    if mod.get("slug") == "skin-manager":
        args += ["--kit-version", KIT_VERSION]
    return args


def apply_modules(mods, selection, paths, interactive):
    """selection: slug -> bool (True = inject, False = skip/remove)."""
    # Single-instance lock: two overlapping install runs each generate their
    # own auth token, then one packs token-A into the asar while the other
    # leaves token-B on disk — the service then rejects the renderer forever
    # (observed 2026-09-22). O_CREAT|O_EXCL is atomic on Windows.
    lock_path = paths.asar.parent / ".modkit-lock"
    lock_fd = None
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        lock_fd_holder(lock_fd, lock_path)
    except FileExistsError:
        print(c(RED, "[ERROR] another mod-kit run is already in progress (found "
                    f"{lock_path}). If you are sure nothing is running, delete that file."))
        return 1
    try:
        return _apply_locked(mods, selection, paths, interactive)
    finally:
        cleanup_lock(lock_path)


_LOCK_STATE = {}

def lock_fd_holder(fd, path):
    """Keep the lock file descriptor open for the process lifetime."""
    _LOCK_STATE["fd"] = fd
    _LOCK_STATE["path"] = path


def cleanup_lock(path):
    try:
        fd = _LOCK_STATE.pop("fd", None)
        if fd is not None:
            os.close(fd)
        os.unlink(path)
    except OSError:
        pass


def _apply_locked(mods, selection, paths, interactive):
    """selection: slug -> bool (True = inject, False = skip/remove)."""
    if not mods:
        print(c(RED, "[ERROR] no modules found under modules/"))
        return 1
    if zcode_running():
        print(c(RED, "[ERROR] ZCode is running. Fully quit it (tray -> Quit) and retry."))
        return 1
    if not paths.asar.exists():
        print(c(RED, f"[ERROR] app.asar not found: {paths.asar}"))
        return 1

    cfg = load_config()
    apply_modules._zcode_version = version_compat_check(paths.asar, cfg)

    # ---- backup: kitbak is the CLEAN pre-patch baseline. Refresh it only when
    # the current asar carries NO kit markers (= an official ZCode update wiped
    # the patches). asar_is_clean() parses the header and checks every module's
    # marker; a partial patch counts as NOT clean, so refreshing can never
    # overwrite the baseline with a patched asar (the 2026-09-22 data-loss bug).
    if not paths.asar_bak.exists():
        print(c(CYAN, "[BACKUP] creating app.asar.kitbak"))
        shutil.copy2(paths.asar, paths.asar_bak)
    elif asar_is_clean(paths.asar):
        print(c(CYAN, "[BACKUP] current asar has no kit injections (ZCode update) - refreshing kitbak"))
        shutil.copy2(paths.asar, paths.asar_bak)
        # The cjs baseline needs the SAME all-modules check as the asar, not a
        # single marker. Checking only /*zro*/ meant "pin-only" or
        # "zombie-only" runs copied a PATCHED cjs into zcode.cjs.kitbak - the
        # 2026-09-22 data-loss bug, still live on the cjs side. A ZCode update
        # replaces both files together, so the first post-update run was fine;
        # the second consecutive run with asar modules OFF was not.
        if paths.cjs_bak.exists() and paths.cjs.exists():
            # Scan the WHOLE file, not a head window. Measured on a fully
            # patched 3.19.1 cjs: zcode-zombie-cleanup sits at ~510 KB,
            # zusage-fb-day at ~1.66 MB, zcode-editresend at ~15.07 MB. A
            # 4000-byte head read saw none of them, so the guard reported
            # "clean" no matter what was patched and copied a patched cjs over
            # the baseline - the data-loss class it was written to prevent.
            with open(paths.cjs, "rb") as _f:
                body = _f.read()
            if not any(m.encode("utf-8") in body for m in CJS_MARKERS):
                shutil.copy2(paths.cjs, paths.cjs_bak)
    if not paths.unpacked_bak.exists() and paths.unpacked.exists():
        shutil.copytree(paths.unpacked, paths.unpacked_bak)
    cjs_needed = any("zcode-cjs" in m.get("targets", []) and selection.get(m["slug"], True)
                     for m in mods)
    if cjs_needed and paths.cjs.exists() and not paths.cjs_bak.exists():
        shutil.copy2(paths.cjs, paths.cjs_bak)

    # ---- extract once -------------------------------------------------------
    # npx is a hard prerequisite (README lists it) but nothing checked for it,
    # so a machine without Node sailed through the menu and died with a raw
    # "npx is not recognized" deep inside the extract output. Fail early with
    # the same actionable wording the Python guard uses.
    if not shutil.which("npx"):
        print(c(RED, "[ERROR] npx not found - Node.js is required."))
        print(c(YELLOW, "  Install from https://nodejs.org/ (LTS), tick"))
        print(c(YELLOW, "  'Add to PATH' during setup, then re-open this window."))
        return 1
    if paths.work.exists():
        shutil.rmtree(paths.work)
    print(c(CYAN, "[EXTRACT]") + " " + c(BOLD, "unpacking app.asar - this takes 2-3 minutes"))
    print_ad_block()
    rc, out = run_asar(f'extract "{paths.asar}" "{paths.work}"', paths.asar.parent,
                       "unpacking asar")
    if rc != 0:
        # Do not leave a half-extracted tree behind: the next run would rmtree
        # it anyway, but a partial tree on disk looks like a corrupt install
        # to anyone inspecting it.
        shutil.rmtree(paths.work, ignore_errors=True)
        print(c(RED, "[ERROR] extract failed:") + "\n" + out[-2000:])
        print(c(YELLOW, "  Common causes: not enough disk space, ZCode running,"))
        print(c(YELLOW, "  no admin rights on Program Files, or npx cannot reach"))
        print(c(YELLOW, "  the npm registry to fetch @electron/asar."))
        return 1

    # ---- run modules --------------------------------------------------------
    # Verifier exit codes carry three states, not two:
    #   0 = injected and the payload matches the module's assets
    #   2 = injected but STALE (marker present, content differs from assets)
    #   1 = not injected at all
    # Collapsing 2 into 1 is what made `uninstall.bat` silently skip skin-manager
    # (2026-11-12): the block was present but stale, verify returned 1, the gate
    # read that as "not injected", and the uninject never ran - leaving a live
    # <script id="zcode-skin-ui"> in the shipped asar after "remove all".
    results = []
    for mod in mods:
        slug = mod["slug"]
        want = selection.get(slug, True)
        args = module_cmd(mod, paths.work, paths.cjs, "verify.py")
        vrc, _ = run_py(mod["_dir"] / "verify.py", args, f"checking {slug}")
        present = (vrc == 0 or vrc == 2)      # injected, fresh or stale
        stale = (vrc == 2)
        if want and vrc == 0:
            print(c(YELLOW, f"[{slug:16s}]") + " already injected, skip")
            results.append((slug, "SKIP"))
            continue
        if want and stale:
            print(c(YELLOW, f"[{slug:16s}]") + " injected but stale, re-deploying")
        if not want and not present:
            print(c(DIM, f"[{slug:16s}]") + " not injected, nothing to do")
            results.append((slug, "OFF"))
            continue
        script = "inject.py" if want else "uninject.py"
        args = module_cmd(mod, paths.work, paths.cjs, script)
        rc, out = run_py(mod["_dir"] / script, args,
                         ("injecting" if want else "removing") + f" {slug}")
        if rc != 0:
            print(c(RED, f"[{slug:16s}] FAILED") + "\n" + out[-1500:])
            results.append((slug, "FAIL"))
            continue
        if "[NOT-NEEDED]" in out:
            print(c(YELLOW, f"[{slug:16s}]") + " not needed (subsystem absent in this build)")
            results.append((slug, "N/A"))
            continue
        print(c(GREEN if want else RED,
                f"[{slug:16s}] {'injected' if want else 'removed'} ok"))
        results.append((slug, "INJECT" if want else "REMOVE"))

    # ---- repack once ---------------------------------------------------------
    print()
    print(c(CYAN, "[PACK]") + " " + c(BOLD, "repacking app.asar - this takes 2-3 minutes"))
    print_ad_block()
    if paths.unpacked.exists():
        shutil.rmtree(paths.unpacked)
    rc, out = run_asar(
        f'pack "{paths.work}" "{paths.asar}" --unpack "*.{{node,dll,exe}}"',
        paths.asar.parent, "repacking asar")
    if rc != 0:
        print(c(RED, "[ERROR] pack failed - restoring backup"))
        shutil.copy2(paths.asar_bak, paths.asar)
        if paths.unpacked.exists():
            shutil.rmtree(paths.unpacked)
        if paths.unpacked_bak.exists():
            shutil.copytree(paths.unpacked_bak, paths.unpacked)
        print(c(RED, out[-2000:]))
        return 1

    shutil.rmtree(paths.work, ignore_errors=True)

    # ---- remember selection ------------------------------------------------
    # NOTE: kitbak is refreshed ONLY in the backup section at the start (via
    # asar_is_clean()'s header parse). No refresh here: after a pack the asar
    # always lacks... nothing - but a post-pack check would ever only fire on
    # a failed inject pass and could overwrite the pre-patch baseline with the
    # post-run state (observed 2026-09-22: the post-uninstall refresh destroyed
    # the baseline). Baseline maintenance happens at the START of a run only.
    cfg["selections"] = selection
    cfg["last_zcode_version"] = getattr(apply_modules, "_zcode_version", None) or \
        read_asar_version(paths.asar)
    save_config(cfg)

    # ---- summary -------------------------------------------------------------
    any_fail = any(s == "FAIL" for _, s in results)
    print()
    # A green "ALL SYSTEMS OPERATIONAL" over a failed module is worse than no
    # banner at all: the user closes the window believing the install worked,
    # and the exit code stayed 0 so a script could not tell either.
    if any_fail:
        print(c(BG_RED, t("summary.fail")))
    else:
        print(c(BG_GREEN, t("summary.ok")))
    for slug, state in results:
        icon = {"INJECT": c(GREEN, "[+]"), "REMOVE": c(RED, "[-]"),
                "SKIP": c(YELLOW, "[=]"), "OFF": c(DIM, "[.]"),
                "N/A": c(DIM, "[~]"),
                "FAIL": c(RED, "[!]")}[state]
        print(f"    {icon}  {c(CYAN, slug):24s} {state}")
    print()
    if any_fail:
        failed = [s for s, st in results if st == "FAIL"]
        print(c(RED, t("summary.failed_list") + ", ".join(failed)))
        print(c(YELLOW, t("summary.failed_help")))
        print(c(DIM, t("summary.backup_ok")))
    # The footer has to match what just happened: telling someone who removed
    # every module to "re-run reinstall.bat" reads like the uninstall failed.
    injected = any(s == "INJECT" for _, s in results)
    removed = any(s == "REMOVE" for _, s in results)
    if injected:
        print(c(DIM, t("summary.reinstall")))
        print(c(DIM, t("summary.reinstall2")))
        print(c(DIM, t("summary.start")))
    elif removed:
        print(c(DIM, t("summary.removed")))
        print(c(DIM, t("summary.removed2")))
        print(c(DIM, t("summary.removed3")))
    print()
    print_ad_block(clickable_link=True)
    return 1 if any_fail else 0


def uninstall_all(mods, paths):
    if zcode_running():
        print(c(RED, "[ERROR] ZCode is running. Fully quit it first."))
        return 1
    selection = {m["slug"]: False for m in mods}
    return apply_modules(mods, selection, paths, interactive=False)


# ---------------------------------------------------------------------------
# cyberpunk TUI
# ---------------------------------------------------------------------------

def display_name(mod):
    """Menu label: the module's own Chinese display_name in Chinese mode, the
    ASCII label in English mode.

    A stream with no `encoding` attribute (StringIO, a pipe wrapper) is not
    evidence that the console cannot render CJK - assume UTF-8 and let
    safe_print degrade on the write if it really cannot.
    """
    ascii_label = LABELS.get(mod["slug"], mod["slug"]).partition(" ")[0]
    name = (mod.get("display_name") or "").strip()
    if not name or _lang == "en":
        return ascii_label
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        name.encode(enc)
    except (UnicodeEncodeError, LookupError):
        return ascii_label
    return name


def render(mods, selection, idx, config_sel, dirty=False):
    clear()
    safe_print(gradient_banner())
    safe_print(c(MAGENTA, t("menu.title")) +
          (c(N_CYAN, "   *  .  *  " + t("splash.winter")) if _winter_palette() else ""))
    safe_print(c(N_CYAN, "  " + "=" * 36))
    safe_print()
    safe_print(c(DIM, t("menu.hint1")))
    safe_print(c(DIM, t("menu.hint2")))
    if dirty:
        safe_print(c(YELLOW, t("menu.dirty")))
    safe_print()
    for i, mod in enumerate(mods):
        slug = mod["slug"]
        on = selection.get(slug, True)
        cur = " " + c(DIM, "last-run: on ") if config_sel.get(slug, True) else \
              " " + c(DIM, "last-run: off")
        status = c(BG_GREEN, "  ON  ") if on else c(BG_RED, " OFF  ")
        name = display_name(mod)
        ver = mod.get("version", "")
        ver_txt = c(DIM, f"v{ver}") if ver else ""
        # CJK glyphs occupy two terminal cells, so str.ljust() pads a Chinese
        # name too little and the version column goes ragged. Pad by display
        # width instead.
        row = f"  {status}  {pad_display(name, 32)}{ver_txt:10s}{cur}"
        if i == idx:
            row = "\x1b[7m" + row + RESET
        safe_print(row)
    safe_print()
    sel = mods[idx]["slug"]
    safe_print("  " + c(CYAN, "> ") + c(BOLD, order_hint(sel)))
    safe_print()
    print_ad_block(clickable_link=True)


def menu(mods):
    selection = {m["slug"]: True for m in mods}
    cfg = load_config()
    config_sel = cfg.get("selections", {})
    if config_sel:
        selection = {m["slug"]: config_sel.get(m["slug"], True) for m in mods}
    # A selection that differs from the last run is the normal case on a first
    # install; only warn once the user has actually changed something, so the
    # hint does not cry wolf on every redraw.
    dirty = False
    idx = 0
    hide_cursor()
    try:
        while True:
            render(mods, selection, idx, config_sel, dirty)
            key = get_key()
            if key == "quit" or key == "esc":
                return None
            elif key == "up":
                idx = (idx - 1) % len(mods)
            elif key == "down":
                idx = (idx + 1) % len(mods)
            elif key == "toggle" or key == "left" or key == "right":
                slug = mods[idx]["slug"]
                selection[slug] = not selection[slug]
                dirty = True
            elif key == "allon":
                for m in mods:
                    selection[m["slug"]] = True
                dirty = True
            elif key == "alloff":
                for m in mods:
                    selection[m["slug"]] = False
                dirty = True
            elif key == "enter":
                # Never start a 2-3 minute rewrite of a 300 MB app on a single
                # keystroke. Show exactly what will happen and require an
                # explicit y. This is the last chance to notice "all 10 ON".
                show_cursor()
                if confirm_plan(mods, selection):
                    return selection
                hide_cursor()
            elif key == "reinstall":
                # "load last selection", not "apply it": the user sees the
                # restored ticks and still confirms with ENTER. Silently
                # applying an old config on one keystroke was a footgun.
                if not config_sel:
                    show_cursor()
                    print(c(YELLOW, t("menu.no_saved")))
                    input(t("menu.back"))
                    hide_cursor()
                    continue
                selection = {m["slug"]: config_sel.get(m["slug"], True)
                             for m in mods}
                dirty = True
            elif key == "openad":
                show_cursor()
                try_open_ad()
                input("  press ENTER to go back to the menu ")
                hide_cursor()
            elif key == "lang":
                # One-key switch, remembered for next time. Redraw only -
                # never touches a selection or a file.
                set_lang("en" if lang() == "zh" else "zh")
                cfg = load_config()
                cfg["lang"] = lang()
                save_config(cfg)
    finally:
        show_cursor()


def confirm_plan(mods, selection):
    """Print the exact plan and ask for y. Returns True to proceed."""
    clear()
    on = [m for m in mods if selection.get(m["slug"], True)]
    off = [m for m in mods if not selection.get(m["slug"], True)]
    safe_print()
    safe_print(c(MAGENTA + BOLD, t("review.title")))
    safe_print(c(DIM, "  " + "-" * 66))
    safe_print(t("review.install") + c(WHITE, str(find_zcode_root() or t("review.notfound"))))
    safe_print(t("review.counts") + c(GREEN, str(len(on))) +
          t("review.off") + c(DIM, str(len(off))))
    safe_print()
    for m in mods:
        flag = selection.get(m["slug"], True)
        mark = c(GREEN, " [+] ") if flag else c(DIM, " [ ] ")
        ver = c(DIM, "v" + m.get("version", ""))
        safe_print("  " + mark + c(WHITE if flag else DIM, display_name(m)) +
              "  " + ver)
    safe_print()
    if not on:
        safe_print(c(YELLOW, t("review.alloff")))
        safe_print()
    safe_print(c(DIM, t("review.rewrite")))
    try:
        ans = input(c(BOLD, t("review.ask")) + "").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return ans in ("y", "yes")


def get_key():
    if msvcrt is None:
        return input().strip().lower() or "enter"
    ch = msvcrt.getwch()
    if ch in ("\x00", "\xe0"):
        ch2 = msvcrt.getwch()
        return {"H": "up", "P": "down", "K": "left", "M": "right"}.get(ch2)
    if ch in ("\r", "\n"):
        return "enter"
    if ch == " ":
        return "toggle"
    low = ch.lower()
    if low == "q":
        return "quit"
    if low == "r":
        return "reinstall"
    if low == "a":
        return "allon"
    if low == "n":
        return "alloff"
    if low == "o":
        return "openad"
    if low == "l":
        return "lang"
    if ch == "\x1b":
        return "esc"
    return None


def main():
    vt_on()
    # UI language: an explicit choice from a previous run wins, otherwise the
    # system locale decides (Chinese Windows -> Chinese, everything else ->
    # English). The menu switches it live with L.
    _cfg0 = load_config()
    set_lang(_cfg0.get("lang") or _system_lang())
    # The bat only checks that *some* python exists; a 3.8 install would then
    # die on a 3.10 f-string/typing difference far from this line. Check once,
    # up front, with the same actionable wording.
    if sys.version_info < (3, 10):
        print(c(RED, "[ERROR] Python 3.10+ required, found %d.%d."
                % sys.version_info[:2]))
        print(c(YELLOW, "  Install from https://www.python.org/downloads/ and"))
        print(c(YELLOW, "  tick 'Add python.exe to PATH' during setup."))
        return 1
    mods = load_modules()

    # --splash: winter intro + roster, then hand control back to install.bat.
    # Kept ahead of the ZCode lookup so the animation still plays (and the
    # module list is still readable) on a machine where ZCode is installed
    # somewhere unusual - the error message then explains how to point at it.
    args = sys.argv[1:]
    if "--splash" in args:
        clear()
        if _winter_palette() and "--no-snow" not in args:
            snowfall()
        clear()
        print(splash_plate(mods, KIT_VERSION))
        print(c(DIM, t("splash.done")))
        time.sleep(0.8)
        return

    root = find_zcode_root()
    if root is None:
        print(c(RED, "[ERROR] ZCode installation not found."))
        print(c(YELLOW, "  Searched: %LOCALAPPDATA% programs, the Windows registry,"))
        print(c(YELLOW, "  Program Files and every drive root."))
        print(c(YELLOW, "  Fix 1: set ZCODE_ROOT to your ZCode folder, e.g."))
        print(c(DIM, '    set ZCODE_ROOT=C:\\Users\\you\\AppData\\Local\\Programs\\ZCode'))
        print(c(DIM, "    install.bat"))
        print(c(YELLOW, "  Fix 2: copy this kit INTO the ZCode folder and run install.bat there."))
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
        return
    paths = KitPaths(root)

    args = sys.argv[1:]
    if "--uninstall-all" in args:
        rc = uninstall_all(mods, paths)
        sys.exit(rc)

    cfg = load_config()
    if "--reinstall" in args:
        sel = cfg.get("selections")
        if not sel:
            print(c(RED, "[ERROR] no saved selection - run install.bat once first"))
            sys.exit(1)
        print(c(CYAN, "[REINSTALL] re-applying saved selection"))
        sys.exit(apply_modules(mods, sel, paths, interactive=False))

    # The splash already played the animation when install.bat launched us
    # as `--splash`; don't replay it in the run that follows.
    if _winter_palette() and "--no-snow" not in args and "--from-splash" not in args:
        clear()
        snowfall()

    # Check the process BEFORE the menu, not after. Discovering "ZCode is
    # running" only after ticking ten modules throws the whole selection away
    # and makes the user redo it in a fresh window.
    if zcode_running():
        clear()
        print()
        print(c(RED, t("err.zcode_running")))
        print(c(YELLOW, t("err.zcode_running2")))
        print(c(YELLOW, t("err.zcode_running3")))
        print()
        try:
            input(c(DIM, t("err.after_quit")))
        except (EOFError, KeyboardInterrupt):
            return
        if zcode_running():
            print(c(RED, t("err.still_running")))
            return

    clear()
    try:
        selection = menu(mods)
    except KeyboardInterrupt:
        selection = None
    if selection is None:
        clear()
        print(c(DIM, t("byebye")))
        return
    clear()
    sys.exit(apply_modules(mods, selection, paths, interactive=True))


if __name__ == "__main__":
    main()
