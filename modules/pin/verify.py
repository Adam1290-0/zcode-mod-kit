#!/usr/bin/env python3
"""pin module — injection verifier for the ZCode Mod Kit.

Exit 0 = fully injected; non-zero = missing pieces (names printed to stdout).
Checks:
- zcode.cjs contains the /*zpin*/ require line (only when --zcode-cjs given)
- renderer/index.html contains the zcode-pin-ui block AND the token placeholder
  was replaced (no '__ZPIN_TOKEN__' residue)

Usage:
  python verify.py --dir <extracted-asar-root> [--zcode-cjs <path>]

Standard library only. All output lines are prefixed with [pin].
"""
import sys, argparse, os, re
from pathlib import Path

DATA_DIR = Path(os.path.expanduser("~/.zcode/plugins/pin"))
WRAPPER_MARKER = b"/*zpin*/"
UI_MARKER = '<script id="zcode-pin-ui">'
TOKEN_PLACEHOLDER = "'__ZPIN_TOKEN__'"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="extracted asar root")
    ap.add_argument("--zcode-cjs", default=None, help="path to resources/glm/zcode.cjs")
    args = ap.parse_args()

    missing = []

    if args.zcode_cjs:
        zcjs = Path(args.zcode_cjs)
        if not zcjs.exists():
            missing.append("zcode-cjs-missing")
        elif WRAPPER_MARKER not in zcjs.read_bytes():
            missing.append("zcode-cjs-marker")

    html_path = Path(args.dir) / "out" / "renderer" / "index.html"
    stale_payload = False
    if not html_path.exists():
        missing.append("index-html-missing")
    else:
        html = html_path.read_text(encoding="utf-8", newline="")
        if UI_MARKER not in html:
            missing.append("ui-block")
        if TOKEN_PLACEHOLDER in html:
            missing.append("token-unreplaced")
        # Payload freshness: the block must equal assets/ui_pin.js, modulo the
        # inlined token. Without this, an updated ui_pin.js would never reach a
        # machine that already has the marker - this verifier is the only thing
        # the kit's SKIP gate consults (same class as skin-manager's STALE bug).
        asset_ui = Path(__file__).resolve().parent / "assets" / "ui_pin.js"
        if UI_MARKER in html and asset_ui.is_file():
            start = html.find(UI_MARKER)
            end = html.find("</script>", start)
            if end > start:
                # inject.py substitutes the quoted placeholder in place
                # ('__ZPIN_TOKEN__' -> '<hex>'), so normalise the hex back to
                # the placeholder and compare against the raw asset. There is
                # no prologue line to strip here.
                got = html[start:end].replace(UI_MARKER, "", 1)
                got = re.sub(r"['\"][0-9a-fA-F]{32,64}['\"]",
                             TOKEN_PLACEHOLDER, got, count=1)
                try:
                    want = asset_ui.read_text(encoding="utf-8",
                                              newline="").strip()
                except Exception:
                    want = None
                if want is not None and got.strip().rstrip("</script>").strip() != want:
                    stale_payload = True

    # Runtime wrapper freshness. The kit's SKIP gate trusts this verifier, and
    # the wrapper is only deployed by inject.py - so without this check a
    # re-install keeps an outdated ~/.zcode/plugins/pin wrapper indefinitely
    # (the 2026-09-28 "repo fixed, machine never updated" failure class).
    asset = Path(__file__).resolve().parent / "assets" / "pin-wrapper.js"
    deployed = DATA_DIR / "pin-wrapper.js"
    if not deployed.exists():
        missing.append("runtime-wrapper-missing")
    elif deployed.read_bytes() != asset.read_bytes():
        missing.append("runtime-wrapper-stale")
    core_asset = Path(__file__).resolve().parent / "assets" / "pin-core.js"
    core_deployed = DATA_DIR / "pin-core.js"
    if core_asset.exists():
        if not core_deployed.exists():
            missing.append("runtime-core-missing")
        elif core_deployed.read_bytes() != core_asset.read_bytes():
            missing.append("runtime-core-stale")

    if missing or stale_payload:
        # ANY "-stale" entry (or a stale UI payload) means the injection is
        # present but outdated: exit 2 so the installer re-deploys on install
        # and still removes it on uninstall. Only genuinely absent pieces are
        # exit 1. The old `all(...)` form collapsed a mixed
        # "wrapper-stale + core-missing" into exit 1, which made uninstall
        # treat a live module as absent and skip removing it.
        any_stale = stale_payload or any(m.endswith("-stale") for m in missing)
        parts = list(missing) + (["ui-payload-stale"] if stale_payload else [])
        print("[pin] verify " + ("STALE" if any_stale else "FAIL") + ": "
              + ", ".join(parts))
        return 2 if any_stale else 1
    print("[pin] verify OK: fully injected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
