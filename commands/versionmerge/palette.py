# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

"""Fusion HTML Palette lifecycle for the Version Merge command."""

import json
import traceback

import adsk.core
import adsk.fusion

from ...lib import fusionAddInUtils as futil
from . import apply_merge

PALETTE_ID = "PTND-versionmerge-palette"
PALETTE_NAME = "Version Merge"

# Held so Fusion doesn't garbage-collect the handler shims.
_palette_handlers: list = []

# Snapshot of the design's structural state at palette-open time. Used to
# detect that the user modified the active document between viewing the
# merge report and clicking Apply — we prompt them to confirm before
# applying against potentially-stale data.
_baseline_signature: tuple = ()


def set_baseline_signature(sig: tuple) -> None:
    global _baseline_signature
    _baseline_signature = sig


def _fusion_theme() -> str:
    """Return 'dark' or 'light' matching Fusion's currently applied UI theme.

    Uses ``activeUserInterfaceTheme`` so the "follow device OS theme" setting
    is resolved to the actual rendered theme before comparison.  Returns
    'dark' on any failure since Fusion's default is dark and our CSS root
    tokens are dark.
    """
    try:
        app_ = adsk.core.Application.get()
        theme = app_.preferences.generalPreferences.activeUserInterfaceTheme
        dark_set = {
            adsk.core.UserInterfaceThemes.DarkBlueUserInterfaceTheme,
            adsk.core.UserInterfaceThemes.DarkGrayUserInterfaceTheme,
        }
        return "dark" if theme in dark_set else "light"
    except Exception:
        return "dark"


def _send_theme() -> None:
    palette = _get_palette()
    if palette is None:
        return
    try:
        palette.sendInfoToHTML("setTheme", _fusion_theme())
    except Exception as exc:
        futil.log(f"versionmerge: sendInfoToHTML(setTheme) failed: {exc}")


def compute_design_signature(design: adsk.fusion.Design, document) -> tuple:
    """Lightweight fingerprint of the design's structural state.

    Captures timeline count, the ordered list of timeline item names, and
    the document's isModified flag.  Any of those changing is enough to
    warn the user that the merge report no longer matches reality.
    """
    try:
        timeline = design.timeline
        names = []
        for i in range(timeline.count):
            try:
                names.append(timeline.item(i).name)
            except Exception:
                names.append("")
        is_modified = bool(getattr(document, "isModified", False))
        return (timeline.count, tuple(names), is_modified)
    except Exception:
        return ()


def _get_palette():
    return adsk.core.Application.get().userInterface.palettes.itemById(PALETTE_ID)


def show_palette(html_url: str) -> None:
    """Open or reload the merge palette pointing at *html_url*."""
    app = adsk.core.Application.get()
    ui = app.userInterface

    palette = ui.palettes.itemById(PALETTE_ID)
    is_new = palette is None

    if is_new:
        palette = ui.palettes.add(
            PALETTE_ID,
            PALETTE_NAME,
            html_url,
            True,   # isVisible
            True,   # showCloseButton
            True,   # isResizable
            900,    # width
            700,    # height
        )
        try:
            palette.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateRight
        except Exception as exc:
            futil.log(f"versionmerge: setting dockingState failed: {exc}")
        futil.add_handler(
            palette.incomingFromHTML, _on_html_event,
            local_handlers=_palette_handlers,
        )
    else:
        palette.htmlFileURL = html_url
        try:
            palette.reload()
        except AttributeError:
            pass

    palette.isVisible = True
    # Push current Fusion theme to the page on every show. The page also
    # independently pulls it on load + visibilitychange via 'getTheme'.
    _send_theme()


def dispose() -> None:
    """Tear down the palette during add-in stop."""
    global _palette_handlers
    palette = _get_palette()
    if palette is not None:
        try:
            palette.deleteMe()
        except Exception as exc:
            futil.log(f"versionmerge: palette.deleteMe() failed: {exc}")
    _palette_handlers = []


def _send_to_html(action: str, payload: dict) -> None:
    palette = _get_palette()
    if palette is None:
        return
    try:
        palette.sendInfoToHTML(action, json.dumps(payload))
    except Exception as exc:
        futil.log(f"versionmerge: sendInfoToHTML failed: {exc}")


def _on_html_event(args: adsk.core.HTMLEventArgs) -> None:
    action = args.action
    raw = args.data or ""

    # The theme handshake doesn't carry JSON — short-circuit before parsing.
    if action == "getTheme":
        _send_theme()
        return

    try:
        data = json.loads(raw) if raw else {}
    except Exception as exc:
        futil.log(f"versionmerge: malformed JSON from html ({action}): {exc}")
        return

    if action == "applyMerges":
        _handle_apply_merges(data)
    else:
        futil.log(f"versionmerge: unknown html action: {action!r}")


def _handle_apply_merges(data: dict) -> None:
    selections = data.get("selections") or []
    if not selections:
        return

    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    if design is None:
        _send_to_html("applyResult", {
            "results": [
                {"rowId": s.get("rowId", ""), "ok": False,
                 "message": "No active Fusion design"}
                for s in selections
            ],
        })
        return

    # Stale-state check. If the timeline structure or the modified flag
    # has shifted since the report was generated, the user may be applying
    # against a different document than what they're seeing in the table.
    if _baseline_signature:
        current_sig = compute_design_signature(design, app.activeDocument)
        if current_sig and current_sig != _baseline_signature:
            ui = app.userInterface
            result = ui.messageBox(
                "The active document has been modified since this merge report "
                "was prepared.\n\n"
                "Per-row results may not match the displayed state. Apply anyway?",
                "Document State Changed",
                adsk.core.MessageBoxButtonTypes.OKCancelButtonType,
                adsk.core.MessageBoxIconTypes.WarningIconType,
            )
            if result != adsk.core.DialogResults.DialogOK:
                futil.log("versionmerge: user cancelled apply due to stale state")
                _send_to_html("applyResult", {
                    "results": [
                        {"rowId": s.get("rowId", ""), "ok": False,
                         "message": "Cancelled — document modified after report was generated"}
                        for s in selections
                    ],
                })
                return

    try:
        results = apply_merge.apply_selections(design, selections)
    except Exception as exc:
        futil.log(
            f"versionmerge: apply_selections raised: {exc}\n{traceback.format_exc()}"
        )
        _send_to_html("applyResult", {
            "results": [
                {"rowId": s.get("rowId", ""), "ok": False,
                 "message": f"Apply failed: {exc}"}
                for s in selections
            ],
        })
        return

    _send_to_html("applyResult", {"results": [r.to_dict() for r in results]})
