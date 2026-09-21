#!/usr/bin/env python3
"""ZCode Mod Kit - all-in-one patcher for ZCode addon modules.

Cyberpunk-style interactive menu: up/down to pick a module, left/right to
toggle INJECT / SKIP, ENTER to apply. Remembers the last selection in
config.json so `reinstall.bat` can re-apply everything after a ZCode update
with zero interaction.

ASCII-only output (cmd codepage safe). Python stdlib only.
"""
import json
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
BG_CYAN = "\x1b[46m\x1b[30m"
BG_GREEN = "\x1b[42m\x1b[30m"
BG_RED = "\x1b[41m\x1b[30m"

# module slug -> menu label (ASCII only)
LABELS = {
    "route-override": "ROUTE  headers + vpn tunnel per provider",
    "pin": "PIN    sticky context re-injection",
    "skin-manager": "SKIN   wallpaper / opacity / ambient edge",
    "account-switcher": "ACCT   one-click multi-account switch",
    "snapshot-kill": "SNAP   repo-snapshot upload kill-switch",
}
ORDER_HINT = {
    "route-override": "cjs chain first, pin wraps outside it",
    "pin": "injects after route-override marker (fallback: use strict)",
    "skin-manager": "renderer-only, order-independent",
    "account-switcher": "main + renderer, order-independent",
    "snapshot-kill": "static gate in out/host/index.js",
}

BANNER = r"""
 ____ ____ ___  ____  _____    __  __ ___  ____    _  ___ ___ _____
|__  |  _ \_  ||_  ||  _  |  |  \/  | __||  _ \  | |/ / |_ _|_   _|
  / /| |_| / /__| |__| |_| |  | |\/| |  _|| | | | | ' /   | |  | |
 /_/ |____/___/|____/|____/   |_|  |_|___||_| |_| |_|\_\ |___| |_|
"""


def c(code, text):
    return code + text + RESET


def vt_on():
    """Enable ANSI escape processing on legacy cmd consoles."""
    try:
        os.system("")
    except Exception:
        pass


def clear():
    sys.stdout.write("\x1b[2J\x1b[H")
    sys.stdout.flush()


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


def find_zcode_root():
    for candidate in (Path("H:/Zcode"), Path("H:/zcode")):
        if (candidate / "resources" / "app.asar").exists():
            return candidate
    return None


def zcode_running():
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq ZCode.exe"],
            capture_output=True, text=True, timeout=20,
        )
        return "ZCode.exe" in out.stdout
    except Exception:
        return False


# ---------------------------------------------------------------------------
# asar tooling
# ---------------------------------------------------------------------------

_spinner_frames = "|/-\\"
_spinner_stop = threading.Event()


def _spin(label):
    start = time.time()
    i = 0
    while not _spinner_stop.is_set():
        elapsed = int(time.time() - start)
        sys.stdout.write("\r    " + c(CYAN, "[" + _spinner_frames[i % 4] + "]") +
                         " " + label + " " + c(DIM, f"{elapsed}s"))
        sys.stdout.flush()
        i += 1
        time.sleep(0.15)
    sys.stdout.write("\r" + " " * 60 + "\r")
    sys.stdout.flush()


def run_asar(args, cwd, label):
    """Run npx @electron/asar with a spinner; returns (rc, output)."""
    _spinner_stop.clear()
    t = threading.Thread(target=_spin, args=(label,), daemon=True)
    t.start()
    proc = subprocess.Popen(
        "npx --yes @electron/asar " + args,
        shell=True, cwd=str(cwd),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    out, _ = proc.communicate()
    _spinner_stop.set()
    t.join(timeout=1)
    return proc.returncode, out


def run_py(script, args, label):
    """Run a module python script with a spinner; returns (rc, output)."""
    _spinner_stop.clear()
    t = threading.Thread(target=_spin, args=(label,), daemon=True)
    t.start()
    proc = subprocess.Popen(
        [sys.executable, str(script)] + args,
        cwd=str(script.parent),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    out, _ = proc.communicate()
    _spinner_stop.set()
    t.join(timeout=1)
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
    return args


def apply_modules(mods, selection, paths, interactive):
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
    last_size = cfg.get("last_patched_size")

    # ---- backup (refresh only when ZCode updated = clean asar) ------------
    if not paths.asar_bak.exists():
        print(c(CYAN, "[BACKUP] creating app.asar.kitbak"))
        shutil.copy2(paths.asar, paths.asar_bak)
    elif last_size is not None and paths.asar.stat().st_size != last_size:
        print(c(CYAN, "[BACKUP] asar size changed (ZCode update) - refreshing kitbak"))
        shutil.copy2(paths.asar, paths.asar_bak)
    if not paths.unpacked_bak.exists() and paths.unpacked.exists():
        shutil.copytree(paths.unpacked, paths.unpacked_bak)
    cjs_needed = any("zcode-cjs" in m.get("targets", []) and selection.get(m["slug"], True)
                     for m in mods)
    if cjs_needed and paths.cjs.exists() and not paths.cjs_bak.exists():
        shutil.copy2(paths.cjs, paths.cjs_bak)

    # ---- extract once -------------------------------------------------------
    if paths.work.exists():
        shutil.rmtree(paths.work)
    print(c(CYAN, "[EXTRACT] unpacking app.asar (2-3 min)..."))
    rc, out = run_asar(f'extract "{paths.asar}" "{paths.work}"', paths.asar.parent,
                       "unpacking asar")
    if rc != 0:
        print(c(RED, "[ERROR] extract failed:") + "\n" + out[-2000:])
        return 1

    # ---- run modules --------------------------------------------------------
    results = []
    for mod in mods:
        slug = mod["slug"]
        want = selection.get(slug, True)
        args = module_cmd(mod, paths.work, paths.cjs, "verify.py")
        vrc, _ = run_py(mod["_dir"] / "verify.py", args, f"checking {slug}")
        already = (vrc == 0)
        if want and already:
            print(c(YELLOW, f"[{slug:16s}]") + " already injected, skip")
            results.append((slug, "SKIP"))
            continue
        if not want and not already:
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
    print(c(CYAN, "[PACK] repacking app.asar (2-3 min)..."))
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
    cfg["selections"] = selection
    cfg["last_patched_size"] = paths.asar.stat().st_size
    save_config(cfg)

    # ---- summary -------------------------------------------------------------
    print()
    print(c(BG_GREEN, "  ALL SYSTEMS OPERATIONAL  "))
    for slug, state in results:
        icon = {"INJECT": c(GREEN, "[+]"), "REMOVE": c(RED, "[-]"),
                "SKIP": c(YELLOW, "[=]"), "OFF": c(DIM, "[.]"),
                "N/A": c(DIM, "[~]"),
                "FAIL": c(RED, "[!]")}[state]
        print(f"    {icon}  {c(CYAN, slug):24s} {state}")
    print()
    print(c(DIM, "  ZCode was updated? Just re-run reinstall.bat -"))
    print(c(DIM, "  it re-applies this exact selection in one shot."))
    return 0


def uninstall_all(mods, paths):
    if zcode_running():
        print(c(RED, "[ERROR] ZCode is running. Fully quit it first."))
        return 1
    selection = {m["slug"]: False for m in mods}
    return apply_modules(mods, selection, paths, interactive=False)


# ---------------------------------------------------------------------------
# cyberpunk TUI
# ---------------------------------------------------------------------------

def render(mods, selection, idx, config_sel):
    clear()
    print(c(CYAN, BANNER))
    print(c(MAGENTA, "  zcode-mod-kit  ::  modular patcher console"))
    print(c(YELLOW, "  =" * 36))
    print()
    print(c(DIM, "  UP/DOWN pick module    LEFT/RIGHT toggle    ENTER apply"))
    print(c(DIM, "  A all-on    N all-off    R reinstall-last    Q quit"))
    print()
    for i, mod in enumerate(mods):
        slug = mod["slug"]
        on = selection.get(slug, True)
        cur = " " + c(DIM, "last-run: on ") if config_sel.get(slug, True) else \
              " " + c(DIM, "last-run: off")
        status = c(BG_GREEN, "  ON  ") if on else c(BG_RED, " OFF  ")
        row = f"  {status}  {LABELS.get(slug, slug):44s}{cur}"
        if i == idx:
            row = "\x1b[7m" + row + RESET
        print(row)
    print()
    sel = mods[idx]["slug"]
    print("  " + c(CYAN, "> ") + c(BOLD, ORDER_HINT.get(sel, "")))
    print()


def menu(mods):
    selection = {m["slug"]: True for m in mods}
    cfg = load_config()
    config_sel = cfg.get("selections", {})
    if config_sel:
        selection = {m["slug"]: config_sel.get(m["slug"], True) for m in mods}
    idx = 0
    hide_cursor()
    try:
        while True:
            render(mods, selection, idx, config_sel)
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
            elif key == "allon":
                for m in mods:
                    selection[m["slug"]] = True
            elif key == "alloff":
                for m in mods:
                    selection[m["slug"]] = False
            elif key == "enter":
                return selection
            elif key == "reinstall":
                return config_sel or selection
    finally:
        show_cursor()


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
    if ch == "\x1b":
        return "esc"
    return None


def main():
    vt_on()
    mods = load_modules()
    paths = KitPaths(find_zcode_root() or ROOT)

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

    clear()
    try:
        selection = menu(mods)
    except KeyboardInterrupt:
        selection = None
    if selection is None:
        clear()
        print(c(DIM, "BYE. \\o/"))
        return
    clear()
    sys.exit(apply_modules(mods, selection, paths, interactive=True))


if __name__ == "__main__":
    main()
