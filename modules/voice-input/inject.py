#!/usr/bin/env python3
"""voice-input module — directory-mode injector for the ZCode Mod Kit (v0.2).

Targets: asar only, two injection points:
  1. out/main/index.js  — one dynamic-import line pointing at the deployed
     voice-main.cjs (usage-bar loader pattern). Marker: "zvoice-main".
  2. out/renderer/index.html — marked <script> block before </body> with
     __ZVOICE_TOKEN__ / __ZVOICE_PORT__ / __ZVOICE_MPORT__ baked in.

Runtime home: ~/.zcode/plugins/voice-input/ holds server.js, voice-main.cjs,
auth-token, config.json, deps/ (unpacked npm tarballs), models/ (SenseVoice).
Nothing depends on this module directory staying in place after patching.

Usage:
  python inject.py --dir <extracted-asar-root> [--install-root <root>]

Standard library only. All output lines are prefixed with [voice-input].
"""
import sys, secrets, argparse, shutil, json
from pathlib import Path

SLUG = "voice-input"
UI_MARKER = '<script id="zcode-voice-ui">'
MAIN_MARKER = b'voice-main.cjs")'
TOKEN_PLACEHOLDER = "__ZVOICE_TOKEN__"
PORT_PLACEHOLDER = "__ZVOICE_PORT__"
MPORT_PLACEHOLDER = "__ZVOICE_MPORT__"
DEFAULT_PORT = 47115          # sidecar
DEFAULT_MPORT = 47116         # manager
RUNTIME_DIR = Path.home() / ".zcode" / "plugins" / "voice-input"


def log(msg):
    print(f"[{SLUG}] " + msg)


def fail(msg) -> int:
    print(f"[{SLUG}] [ERROR] {msg}")
    return 1


# ---------------------------------------------------------------- runtime
def deploy_runtime(assets_dir: Path) -> Path:
    """Copy server.js + voice-main.cjs into the persistent runtime dir."""
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("server.js", "voice-main.cjs"):
        shutil.copy2(assets_dir / name, RUNTIME_DIR / name)
    return RUNTIME_DIR


def load_or_mint_token(runtime_dir: Path) -> str:
    """Single source of truth: the file the sidecar/manager both read."""
    token_file = runtime_dir / "auth-token"
    if token_file.exists():
        t = token_file.read_text(encoding="utf-8").strip()
        if t:
            return t
    t = secrets.token_hex(24)
    token_file.write_text(t, encoding="utf-8")
    log(f"generated auth token -> {token_file}")
    return t


def load_or_mint_manager_port(runtime_dir: Path) -> int:
    """Reuse the port the running manager bound last time; else default."""
    port_file = runtime_dir / "manager.port"
    if port_file.exists():
        try:
            return int(port_file.read_text(encoding="utf-8").strip())
        except ValueError:
            pass
    return DEFAULT_MPORT


# ---------------------------------------------------------------- renderer
def inject_renderer(out_dir: Path, ui_js: Path, token: str, port: int, mport: int) -> bool:
    html_path = out_dir / "out" / "renderer" / "index.html"
    if not html_path.exists():
        raise RuntimeError(f"renderer/index.html not found under {out_dir}")

    html = html_path.read_text(encoding="utf-8", newline="")
    js = ui_js.read_text(encoding="utf-8", newline="")
    for ph in (TOKEN_PLACEHOLDER, PORT_PLACEHOLDER, MPORT_PLACEHOLDER):
        if ph not in js:
            raise RuntimeError(f"{ui_js.name} is missing the {ph} placeholder")
    # token placeholder is a bare identifier; replacement includes the quotes.
    js = js.replace(TOKEN_PLACEHOLDER, json.dumps(token))
    js = js.replace(PORT_PLACEHOLDER, str(port))
    js = js.replace(MPORT_PLACEHOLDER, str(mport))

    if UI_MARKER in html:
        start = html.find(UI_MARKER)
        end = html.find("</script>", start)
        if end < 0:
            raise RuntimeError("renderer marker found but no closing </script>")
        tag = UI_MARKER + "\n" + js + "\n</script>"
        html = html[:start] + tag + html[end + len("</script>"):]
        log("[SKIP] renderer already injected — replaced in place (idempotent)")
        html_path.write_text(html, encoding="utf-8", newline="")
        return True

    if "</body>" not in html:
        raise RuntimeError("</body> not found in renderer/index.html")
    tag = UI_MARKER + "\n" + js + "\n</script>"
    html = html.replace("</body>", tag + "\n</body>", 1)
    html_path.write_text(html, encoding="utf-8", newline="")
    log("renderer script injected before </body>")
    return True


def uninject_renderer(out_dir: Path) -> bool:
    html_path = out_dir / "out" / "renderer" / "index.html"
    if not html_path.exists():
        log(f"renderer/index.html not found under {out_dir}")
        return False
    html = html_path.read_text(encoding="utf-8", newline="")
    idx = html.find(UI_MARKER)
    if idx < 0:
        log("renderer: no marker block, nothing to remove")
        return False
    end = html.find("</script>", idx)
    if end < 0:
        raise RuntimeError("renderer marker found but no closing </script>")
    tail = end + len("</script>")
    if html[tail: tail + 1] == "\n":
        tail += 1
    html = html[:idx] + html[tail:]
    html_path.write_text(html, encoding="utf-8", newline="")
    log("removed renderer script block")
    return True


# ---------------------------------------------------------------- main proc
def import_line_for(runtime_dir: Path) -> str:
    """Dynamic-import line appended to out/main/index.js (usage-bar form)."""
    url = (runtime_dir / "voice-main.cjs").resolve().as_uri()
    return f'\n;import("{url}").then(() => null, (e) => console.error("[zvoice] load failed", e));'


def inject_main(out_dir: Path, runtime_dir: Path) -> bool:
    entry = out_dir / "out" / "main" / "index.js"
    if not entry.exists():
        raise RuntimeError(f"out/main/index.js not found under {out_dir}")
    data = entry.read_bytes()
    line = import_line_for(runtime_dir).encode("utf-8")
    if MAIN_MARKER in data:
        # Recover the existing line's full span: it is '\n;import("<uri>")...'
        # ending at the ');' following the marker, plus one optional ';'.
        mstart = data.find(MAIN_MARKER)
        start = data.rfind(b"\n;import(", 0, mstart)
        if start < 0 or mstart - start > 400:
            raise RuntimeError(
                "a voice-main import line with unexpected form exists; "
                "refusing to stack a second one (run uninject.py first)")
        # find the closing ');' after the marker, then one optional ';'
        seg_end = data.find(b");", mstart)
        if seg_end < 0:
            raise RuntimeError("voice-main import line has no closing );")
        end = seg_end + 2
        if data[end:end + 1] == b";":
            end += 1
        old = data[start:end]
        if old == line:
            log("[SKIP] out/main/index.js already injected (same runtime path)")
            return False
        data = data[:start] + data[end:]
        log("replaced previous voice-main import line (runtime path changed)")
    data = data + line
    entry.write_bytes(data)
    log("injected dynamic import line into out/main/index.js")
    return True


def uninject_main(out_dir: Path) -> bool:
    entry = out_dir / "out" / "main" / "index.js"
    if not entry.exists():
        log(f"out/main/index.js not found under {out_dir}")
        return False
    data = entry.read_bytes()
    idx = data.find(MAIN_MARKER)
    if idx < 0:
        log("out/main/index.js: no marker, nothing to remove")
        return False
    # The line is '\n;import("<uri>")...;' — recover its start and end.
    start = data.rfind(b"\n;import(", 0, idx)
    if start < 0 or idx - start > 400:
        raise RuntimeError("marker found but import line start not locatable")
    semi = data.find(b");", start)
    end = semi + len(b");")
    if data[end:end + 1] == b";":
        end += 1
    data = data[:start] + data[end:]
    entry.write_bytes(data)
    log("removed dynamic import line from out/main/index.js")
    return True


# ---------------------------------------------------------------- verify
def verify(out_dir: Path) -> int:
    import re
    # Return codes: 0 = injected + fresh, 2 = injected + STALE, 1 = not injected.
    # The installer needs the middle state: on uninstall a stale block must still
    # be removed, on install it must be re-deployed. Reporting it as 1 made the
    # uninstall skip this module (2026-11-12 leftover skin block incident).
    ok = True
    stale = False
    # renderer
    html_path = out_dir / "out" / "renderer" / "index.html"
    if not html_path.exists():
        log(f"renderer/index.html not found under {out_dir}")
        ok = False
    else:
        html = html_path.read_text(encoding="utf-8", newline="")
        count = html.count(UI_MARKER)
        if count != 1:
            log(f"renderer: marker count={count} (want exactly 1)")
            ok = False
        else:
            start = html.find(UI_MARKER)
            end = html.find("</script>", start)
            block = html[start:end]
            tok_m = re.search(r'var TOKEN ?= ?"([0-9a-f]{32,48})"', block)
            if not tok_m:
                log('renderer: baked token missing (var TOKEN = "<hex>")')
                ok = False
            for ph in (TOKEN_PLACEHOLDER, PORT_PLACEHOLDER, MPORT_PLACEHOLDER):
                if ph in block:
                    log(f"renderer: unresolved placeholder: {ph}")
                    ok = False
            for feat in ("v4-composer-input", "v4-composer-voice-input",
                         "ClipboardEvent", "getUserMedia", "127.0.0.1",
                         "mode: 'official'"):
                if feat not in block:
                    log(f"renderer: feature marker missing: {feat}")
                    ok = False
            # STALE check. Feature spot-checks above pass on ANY past version
            # of this block, so an updated ui_voice.js would never re-deploy
            # (the skip gate trusts this verifier). Normalise the one-time
            # values back to placeholders and diff against the source asset.
            if tok_m and ok:
                norm = block
                norm = norm.replace(tok_m.group(0),
                                    'var TOKEN = ' + TOKEN_PLACEHOLDER)
                norm = re.sub(r'(var SPORT ?= ?)\d+', r'\g<1>' + PORT_PLACEHOLDER, norm)
                norm = re.sub(r'(var MPORT ?= ?)\d+', r'\g<1>' + MPORT_PLACEHOLDER, norm)
                src = (Path(__file__).resolve().parent / "assets"
                       / "ui_voice.js").read_text(encoding="utf-8", newline="")
                src_body = src.rstrip("\n")
                # `block` stops at "</script>", so the expected value must too.
                want = UI_MARKER + "\n" + src_body + "\n"
                if norm.rstrip("\n") != want.rstrip("\n"):
                    log("renderer: UI block is STALE (differs from assets/ui_voice.js)")
                    stale = True
            if ok:
                log("renderer: UI block OK (token/ports + official-btn takeover + paste)")

    # main process
    entry = out_dir / "out" / "main" / "index.js"
    if not entry.exists():
        log(f"out/main/index.js not found under {out_dir}")
        ok = False
    else:
        data = entry.read_bytes()
        cnt = data.count(MAIN_MARKER)
        if cnt != 1:
            log(f"out/main/index.js: marker count={cnt} (want exactly 1)")
            ok = False
        else:
            idx = data.find(MAIN_MARKER)
            start = data.rfind(b"\n;import(", 0, idx)
            if start < 0 or idx - start > 400:
                log("out/main/index.js: import line form unexpected")
                ok = False
            else:
                line = data[start:].split(b");", 1)[0] + b");"
                uri = line.decode("utf-8", "replace")
                if "voice-main.cjs" not in uri:
                    log("out/main/index.js: import does not point at voice-main.cjs")
                    ok = False
                else:
                    log("out/main/index.js: dynamic import OK")

    # runtime files: existence is NOT enough. The mod-kit outer skip gate
    # trusts this verifier, so a stale deployed copy would be skipped forever
    # (the v1.6.5 route/pin blind spot, same class). Compare bytes.
    assets = Path(__file__).resolve().parent / "assets"
    for name in ("server.js", "voice-main.cjs"):
        p = RUNTIME_DIR / name
        if not p.exists():
            log(f"runtime file missing: {p}")
            ok = False
        elif p.read_bytes() != (assets / name).read_bytes():
            log(f"runtime file is STALE (differs from assets): {p}")
            stale = True
    if (RUNTIME_DIR / "auth-token").exists():
        log(f"runtime OK: {RUNTIME_DIR}")
    else:
        log(f"auth-token missing: {RUNTIME_DIR}")
        ok = False
    if not ok:
        return 1
    return 2 if stale else 0


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="extracted asar root")
    ap.add_argument("--install-root", default=None, help="ZCode install root (unused, protocol)")
    args = ap.parse_args()

    out_dir = Path(args.dir)
    here = Path(__file__).resolve().parent
    assets = here / "assets"

    runtime_dir = deploy_runtime(assets)
    log(f"deployed sidecar + manager -> {runtime_dir}")
    token = load_or_mint_token(runtime_dir)
    port = DEFAULT_PORT
    mport = load_or_mint_manager_port(runtime_dir)
    inject_renderer(out_dir, assets / "ui_voice.js", token, port, mport)
    inject_main(out_dir, runtime_dir)
    log(f"ui ports: sidecar={port}, manager={mport}")
    return verify(out_dir)


if __name__ == "__main__":
    sys.exit(main())
