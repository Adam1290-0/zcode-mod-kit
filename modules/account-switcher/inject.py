#!/usr/bin/env python3
"""account-switcher directory-mode injector (ZCode Mod Kit interface v1.0).

Injects into an EXTRACTED asar tree; never extracts or repacks on its own.

Steps:
  1. copy assets/zcode-account-switcher-main.mjs -> out/main/
  2. prepend a dynamic import line to out/main/index.js
  3. insert the renderer UI script block before </body> in out/renderer/index.html

Idempotent: if every marker is already present, prints [SKIP] and exits 0.
Surgical: only touches this module's files and injection blocks.
Line endings of the two edited files are preserved exactly (newline='').
"""
import argparse
import re
import secrets
import sys
from pathlib import Path

SLUG = "account-switcher"
MAIN_IMPORT_CORE = 'import("./zcode-account-switcher-main.mjs").catch(()=>{});'
MAIN_MARKER = 'zcode-account-switcher-main.mjs'
RENDERER_MARKER = '<script id="zcode-account-switcher">'
RENDERER_ID = 'id="zcode-account-switcher"'
TOKEN_PLACEHOLDER = "__ZCA_TOKEN__"


def log(msg: str) -> None:
    print(f"[{SLUG}] {msg}")


def read_raw(p: Path) -> str:
    # newline='' = no line-ending translation; keep bytes exactly as they are.
    with open(p, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write_raw(p: Path, s: str) -> None:
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(s)


def detect_nl(body_idx: int, html: str) -> str:
    """Newline style of the line that carries </body>, mirrored into the block."""
    if body_idx >= 2 and html[body_idx - 2 : body_idx] == "\r\n":
        return "\r\n"
    if body_idx >= 1 and html[body_idx - 1] == "\n":
        return "\n"
    return "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="extracted asar root")
    ap.add_argument("--install-root", default=None, help="(unused, accepted per contract)")
    ap.add_argument("--zcode-cjs", default=None, help="(unused, accepted per contract)")
    args = ap.parse_args()

    root = Path(args.dir)
    assets = Path(__file__).resolve().parent / "assets"
    main_entry = root / "out" / "main" / "index.js"
    module_dst = root / "out" / "main" / "zcode-account-switcher-main.mjs"
    html_path = root / "out" / "renderer" / "index.html"

    for p in (main_entry, html_path):
        if not p.exists():
            log(f"[ERROR] required file missing: {p}")
            return 1
    for a in ("zcode-account-switcher-main.mjs", "ui_accounts.js"):
        if not (assets / a).exists():
            log(f"[ERROR] asset missing: {assets / a}")
            return 1

    # Idempotent gate: all markers present AND the renderer block is a
    # token-aware build -> skip. The discriminator is the strict baked-token
    # line, not mere marker presence: an older pre-token block has neither
    # the placeholder nor the header, and a syntactically broken bake
    # (e.g. doubled quotes around the token, 2026-09-23 incident) also
    # parses in no browser and kills the whole block — every such case must
    # FALL THROUGH to the redeploy path below so the block is replaced.
    entry_src = read_raw(main_entry)
    html = read_raw(html_path)
    ri = html.find(RENDERER_ID)
    bend = html.find("</script>", ri) if ri >= 0 else -1
    tail = html[ri:bend] if ri >= 0 and bend >= 0 else ""
    token_aware = (
        ri >= 0
        and bend >= 0
        and "x-zca-token" in tail
        and "__ZCA_TOKEN__" not in tail
        and re.search(r"var TOKEN = '[0-9a-f]{64}'", tail) is not None
    )

    # auth token: reuse or generate BEFORE the gate — the payload-freshness
    # comparison below needs it baked into the expected block.
    token_file = Path.home() / ".zcode" / "account-profiles" / "auth-token"
    token_file.parent.mkdir(parents=True, exist_ok=True)
    if token_file.exists() and token_file.read_text(encoding="utf-8").strip():
        token = token_file.read_text(encoding="utf-8").strip()
    else:
        token = secrets.token_hex(32)
        token_file.write_text(token, encoding="utf-8")
        log(f"auth token generated -> {token_file}")

    # Renderer payload freshness: the deployed block must equal the CURRENT
    # asset with the token baked. Token-shape checks alone let stale UI code
    # survive re-installs forever — the renderer half of the 2026-09-28
    # staleness incident. Computed HERE so the skip gate can require it.
    renderer_fresh = False
    if token_aware:
        start = html.find(RENDERER_MARKER)
        deployed = html[start + len(RENDERER_MARKER):bend] if start >= 0 else ""
        js_asset = read_raw(assets / "ui_accounts.js")
        if TOKEN_PLACEHOLDER not in js_asset:
            log(f"[ERROR] ui_assets.js missing token placeholder {TOKEN_PLACEHOLDER}")
            return 1
        renderer_fresh = deployed.strip() == js_asset.replace(TOKEN_PLACEHOLDER, token).strip()

    module_current = module_dst.exists() and \
        read_raw(module_dst) == read_raw(assets / "zcode-account-switcher-main.mjs")
    if MAIN_MARKER in entry_src and token_aware and renderer_fresh and module_current:
        log("[SKIP] already injected")
        return 0
    # NOTE: the content checks above are load-bearing. Gating the main module
    # on module_dst.exists() alone made every re-install skip the recopy, so
    # main-module fixes shipped in new assets (v1.2.0 401 self-heal, v1.2.1
    # CORS) never reached already-patched installs (observed 2026-09-28: the
    # asar carried the old main.mjs while KIT_VERSION said 1.2.1). The
    # renderer block had the same hole on the other axis: a token-shaped but
    # stale payload passed every check forever.

    # redeploy path (fresh install or pre-token upgrade): regenerate everything

    # 1. copy main-process module
    module_src = read_raw(assets / "zcode-account-switcher-main.mjs")
    write_raw(module_dst, module_src)
    log(f"copied main module -> out/main/{module_dst.name}")

    # 1b. token already resolved above (the gate's freshness check needs it).

    # 2. prepend dynamic import (tolerates other modules' prepended lines)
    if MAIN_MARKER not in entry_src:
        # Match the file's own newline style so uninject can restore bytes.
        nl = "\r\n" if "\r\n" in entry_src[:4000] else "\n"
        write_raw(main_entry, MAIN_IMPORT_CORE + nl + entry_src)
        log("main entry patched (import prepended)")
    else:
        log("main entry already patched")

    # 3. renderer script block: fresh-insert, stale-replace or leave intact
    if RENDERER_ID in html and token_aware:
        if renderer_fresh:
            log("renderer script already present")
        else:
            start = html.find(RENDERER_MARKER)
            end = html.find("</script>", start)
            if end < 0:
                log("[ERROR] existing renderer block has no closing </script>")
                return 1
            nl = detect_nl(html.find("</body>"), html)
            js = read_raw(assets / "ui_accounts.js").replace(TOKEN_PLACEHOLDER, token)
            block = nl.join([RENDERER_MARKER, js, "</script>"]) + nl
            end += len("</script>")
            if html[end:end + 2] == "\r\n":
                end += 2
            elif html[end:end + 1] == "\n":
                end += 1
            html = html[:start] + block + html[end:]
            write_raw(html_path, html)
            log("renderer block refreshed (payload updated)")
    else:
        body_idx = html.find("</body>")
        if body_idx < 0:
            log("[ERROR] </body> not found in out/renderer/index.html")
            return 1
        nl = detect_nl(body_idx, html)
        js = read_raw(assets / "ui_accounts.js")
        if TOKEN_PLACEHOLDER not in js:
            log(f"[ERROR] ui_accounts.js missing token placeholder {TOKEN_PLACEHOLDER}")
            return 1
        # Bake the token WITHOUT repr(): the placeholder already sits inside
        # single quotes in ui_accounts.js, and repr() would emit a second
        # quote pair (''tok''), a JS syntax error that silently killed the
        # whole block (2026-09-23 incident).
        js = js.replace(TOKEN_PLACEHOLDER, token)
        block = nl.join([RENDERER_MARKER, js, "</script>"]) + nl
        if RENDERER_ID in html:
            # pre-token block present: replace it wholly so the token lands
            start = html.find(RENDERER_MARKER)
            end = html.find("</script>", start)
            if end < 0:
                log("[ERROR] existing renderer block has no closing </script>")
                return 1
            end += len("</script>")
            if html[end:end + 2] == "\r\n":
                end += 2
            elif html[end:end + 1] == "\n":
                end += 1
            html = html[:start] + block + html[end:]
            log("renderer block replaced (token baked in)")
        else:
            html = html[:body_idx] + block + html[body_idx:]
            log("renderer script injected before </body> (token baked in)")
        write_raw(html_path, html)

    log("inject complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())