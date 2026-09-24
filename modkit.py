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
}
ORDER_HINT = {
    "route-override": "cjs chain first, pin wraps outside it",
    "pin": "injects after route-override marker (fallback: use strict)",
    "skin-manager": "renderer-only, order-independent",
    "account-switcher": "main + renderer, order-independent",
    "snapshot-kill": "static gate in out/host/index.js",
    "usage-bar": "one import line at the tail of out/main/index.js",
}

BANNER_LINES = [
    r" ____ ____ ___  ____  _____    __  __ ___  ____    _  ___ ___ _____ ",
    r"|__  |  _ \_  ||_  ||  _  |  |  \/  | __||  _ \  | |/ / |_ _|_   _|",
    r"  / /| |_| / /__| |__| |_| |  | |\/| |  _|| | | | | ' /   | |  | |  ",
    r" /_/ |____/___/|____/|____/   |_|  |_|___||_| |_| |_|\_\ |___| |_|  ",
]
# neon gradient across the banner: pink -> purple -> cyan -> blue
GRADIENT = [N_PINK, N_PURPLE, N_CYAN, N_BLUE]


def c(code, text):
    return code + text + RESET


def gradient_banner():
    """Each banner line in its own neon shade."""
    return "\n" + "\n".join(c(GRADIENT[i], ln) for i, ln in enumerate(BANNER_LINES))


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
# 3.14.3 (2026-09-23): four injection targets unchanged; snapshot-kill degrades
# gracefully (RepoSnapshotSidecarService subsystem removed upstream).
VERIFIED_VERSIONS = {"3.12.2", "3.12.3", "3.14.1", "3.14.3"}


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
                         "zcode-route-override-ui", "zcode-pin-ui")
ASAR_HOST_MARKER = "zcode-snapshot-kill-switch"   # snapshot-kill -> out/host/index.js
ASAR_MAIN_MARKER = "[zusage]"                     # usage-bar     -> out/main/index.js


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
        if main and ASAR_MAIN_MARKER in main:
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
    "tip: press R anytime to re-apply your last selection in one shot",
    "tip: runtime files live in ~/.zcode/plugins - the kit folder is movable",
    "tip: OFF on an injected module uninjects it surgically",
    "tip: each ZCode update wipes patches - reinstall.bat brings them all back",
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
                "   " + c(DIM, tip) + "  ")
        sys.stdout.write(line)
        sys.stdout.flush()
        i += 1
        time.sleep(0.06)
    sys.stdout.write("\r" + " " * 110 + "\r")
    sys.stdout.flush()


def wait_screen(first_line):
    """Full idle screen shown while a 2-3 min asar step runs:
    animated ball + sharellm ad block with a clickable link."""
    _spinner_stop.clear()
    t = threading.Thread(target=_spin, args=(first_line,), daemon=True)
    t.start()
    return t


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
        if paths.cjs_bak.exists() and paths.cjs.exists():
            with open(paths.cjs, "rb") as _f:
                if b"/*zro*/" not in _f.read(600):
                    shutil.copy2(paths.cjs, paths.cjs_bak)
    if not paths.unpacked_bak.exists() and paths.unpacked.exists():
        shutil.copytree(paths.unpacked, paths.unpacked_bak)
    cjs_needed = any("zcode-cjs" in m.get("targets", []) and selection.get(m["slug"], True)
                     for m in mods)
    if cjs_needed and paths.cjs.exists() and not paths.cjs_bak.exists():
        shutil.copy2(paths.cjs, paths.cjs_bak)

    # ---- extract once -------------------------------------------------------
    if paths.work.exists():
        shutil.rmtree(paths.work)
    print(c(CYAN, "[EXTRACT]") + " " + c(BOLD, "unpacking app.asar - this takes 2-3 minutes"))
    print_ad_block()
    wt = wait_screen("unpacking asar")
    rc, out = run_asar(f'extract "{paths.asar}" "{paths.work}"', paths.asar.parent,
                       "unpacking asar")
    _spinner_stop.set()
    wt.join(timeout=1)
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
    print()
    print(c(CYAN, "[PACK]") + " " + c(BOLD, "repacking app.asar - this takes 2-3 minutes"))
    print_ad_block()
    wt = wait_screen("repacking asar")
    if paths.unpacked.exists():
        shutil.rmtree(paths.unpacked)
    rc, out = run_asar(
        f'pack "{paths.work}" "{paths.asar}" --unpack "*.{{node,dll,exe}}"',
        paths.asar.parent, "repacking asar")
    _spinner_stop.set()
    wt.join(timeout=1)
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
    print()
    print_ad_block(clickable_link=True)
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
    print(gradient_banner())
    print(c(MAGENTA, "  zcode-mod-kit  ::  modular patcher console"))
    print(c(N_CYAN, "  " + "=" * 36))
    print()
    print(c(DIM, "  UP/DOWN pick module    LEFT/RIGHT toggle    ENTER apply"))
    print(c(DIM, "  A all-on    N all-off    R reinstall-last    O sponsor    Q quit"))
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
    print_ad_block(clickable_link=True)


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
            elif key == "openad":
                try_open_ad()
                time.sleep(1.5)
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
    if low == "o":
        return "openad"
    if ch == "\x1b":
        return "esc"
    return None


def main():
    vt_on()
    mods = load_modules()
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
