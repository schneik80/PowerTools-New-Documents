# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

"""Interactive merge report rendered inside a Fusion HTML Palette.

For every aligned diff row that has a multi-version edit history, expands
to show one child row per per-version edit. Users tick the edits they
want to undo; the page computes the target expression per parameter by
walking the edit list (skipping ticked edits) and sends a single
``params`` selection per parameter to Python.

Edit kinds rendered as children:
    param_changed   — actionable (tick to undo this specific version's edit)
    added           — actionable on ``newer`` rows (tick to remove the feature)
    deleted         — informational only (re-adding isn't supported)
    sketch_modified — informational only (geometry isn't revertible)
"""

import json
import os
import secrets
import tempfile
from pathlib import Path

from ... import config
from ..versiondiff.feature_icons import icon_img_tag
from ..versiondiff.html_report import HTML_CSS
from ..versiondiff.timeline_diff import _feature_key
from ..versiondiff.timeline_model import DiffResult


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


THEME_CSS = """<style>
    /* ------------------------------------------------------------------
     * Theme tokens
     *
     * Fusion is dark by default, so the :root values are the dark theme
     * and html[data-theme="light"] overrides them. The JS sets that
     * attribute on the documentElement when it receives a 'setTheme'
     * action from Python (push on show, pull on load + visibilitychange).
     * ------------------------------------------------------------------ */
    :root {
        --bg-page:         #1e2838;
        --bg-surface:      #2a3442;
        --bg-surface-2:    #242e39;
        --bg-divider:      #1f2832;
        --bg-input:        #1e2838;

        --header-bg:       #1a1a2e;
        --header-text:     #ffffff;
        --header-subtle:   #b2bec3;

        --text:            #e0e6ec;
        --text-strong:     #ffffff;
        --text-muted:      #8a9bb0;
        --text-faint:      #5c6f84;

        --border:          #3d4f66;
        --border-soft:     #2a3442;

        --accent:          #0696d7;
        --accent-soft:     rgba(9, 132, 227, 0.18);
        --older-soft:      rgba(108, 92, 231, 0.18);

        --status-newer-bg:    #1e3a2e;  --status-newer-text:    #74c69d;
        --status-deleted-bg:  #3a1e1e;  --status-deleted-text:  #e88a8a;
        --status-version-bg:  #3a3220;  --status-version-text:  #e0c878;
        --status-sketch-bg:   #3a2e1e;  --status-sketch-text:   #e8b87a;
        --status-params-bg:   #1e2a3a;  --status-params-text:   #74b3d4;
        --status-health-bg:   #3a2920;  --status-health-text:   #ed9c5a;
        --status-unchanged-bg:#2c333d;  --status-unchanged-text:#95a5a6;

        --row-newer:       #243a2e;
        --row-deleted:     #3a2424;
        --row-version:     #3a3324;
        --row-sketch:      #3a2e24;
        --row-params:      #243044;
        --row-health:      #3a2c24;
    }
    html[data-theme="light"] {
        --bg-page:         #f5f6fa;
        --bg-surface:      #ffffff;
        --bg-surface-2:    #f8f9fa;
        --bg-divider:      #fafafa;
        --bg-input:        #ffffff;

        --header-bg:       #1a1a2e;
        --header-text:     #ffffff;
        --header-subtle:   #b2bec3;

        --text:            #2d3436;
        --text-strong:     #1a1a1a;
        --text-muted:      #636e72;
        --text-faint:      #95a5a6;

        --border:          #e6eaef;
        --border-soft:     #f0f0f0;

        --accent:          #0984e3;
        --accent-soft:     #eef6ff;
        --older-soft:      #f3f0ff;

        --status-newer-bg:    #d4edda;  --status-newer-text:    #155724;
        --status-deleted-bg:  #f8d7da;  --status-deleted-text:  #721c24;
        --status-version-bg:  #fff3cd;  --status-version-text:  #856404;
        --status-sketch-bg:   #fde8d0;  --status-sketch-text:   #8a4b08;
        --status-params-bg:   #d6eaf8;  --status-params-text:   #1a5276;
        --status-health-bg:   #ffe0b2;  --status-health-text:   #e65100;
        --status-unchanged-bg:#e2e3e5;  --status-unchanged-text:#383d41;

        --row-newer:       #ecfaee;
        --row-deleted:     #fdedee;
        --row-version:     #fffde7;
        --row-sketch:      #fef5eb;
        --row-params:      #ebf5fb;
        --row-health:      #fff3e0;
    }

    /* ------------------------------------------------------------------
     * Overrides on the shared HTML_CSS so the merge palette honours the
     * theme tokens. !important is needed because HTML_CSS sets explicit
     * colours that we want to defeat.
     * ------------------------------------------------------------------ */
    body {
        background: var(--bg-page) !important;
        color: var(--text) !important;
    }
    .report-header {
        background: var(--header-bg) !important;
        color: var(--header-text) !important;
    }
    .report-header .subtitle { color: var(--header-subtle) !important; }

    .version-card { background: var(--bg-surface) !important; }
    .version-card .detail { color: var(--text-muted) !important; }
    .version-card .detail b { color: var(--text) !important; }
    .card-thumb {
        background: var(--bg-surface-2) !important;
        border-color: var(--border) !important;
    }

    .diff-table-wrap { background: var(--bg-surface) !important; }
    .diff-table-wrap h2 {
        color: var(--text) !important;
        border-color: var(--border) !important;
    }
    .table-summary { color: var(--text-muted) !important; }

    table.diff-table th {
        background: var(--bg-surface-2) !important;
        color: var(--text-muted) !important;
        border-color: var(--border) !important;
    }
    table.diff-table td {
        border-color: var(--border-soft) !important;
        color: var(--text) !important;
    }
    table.diff-table tr { background: var(--bg-surface); }

    th.col-older { background: var(--older-soft) !important; }
    th.col-newer { background: var(--accent-soft) !important; }
    td.col-divider, th.col-divider {
        background: var(--bg-divider) !important;
        border-left-color: var(--border) !important;
        border-right-color: var(--border) !important;
    }
    td.empty-cell { background: var(--bg-surface-2) !important; }

    /* Row status tints */
    tr.row-newer td.col-divider { background: var(--row-newer) !important; }
    tr.row-deleted td.col-divider { background: var(--row-deleted) !important; }
    tr.row-version_changed td.col-divider { background: var(--row-version) !important; }
    tr.row-sketch_modified td.col-divider { background: var(--row-sketch) !important; }
    tr.row-params_changed td.col-divider { background: var(--row-params) !important; }
    tr.row-health_changed td.col-divider { background: var(--row-health) !important; }

    tr.row-newer td.newer-name,
    tr.row-newer td.newer-type,
    tr.row-newer td.newer-idx { background: var(--row-newer) !important; }
    tr.row-deleted td.older-name,
    tr.row-deleted td.older-type,
    tr.row-deleted td.older-idx { background: var(--row-deleted) !important; }
    tr.row-version_changed td.newer-idx,
    tr.row-version_changed td.newer-name,
    tr.row-version_changed td.newer-type { background: var(--row-version) !important; }
    tr.row-sketch_modified td.newer-name,
    tr.row-sketch_modified td.newer-type,
    tr.row-sketch_modified td.newer-idx { background: var(--row-sketch) !important; }
    tr.row-params_changed td.newer-name,
    tr.row-params_changed td.newer-type,
    tr.row-params_changed td.newer-idx { background: var(--row-params) !important; }
    tr.row-health_changed td.newer-name,
    tr.row-health_changed td.newer-type,
    tr.row-health_changed td.newer-idx { background: var(--row-health) !important; }

    /* Status badges */
    .status-newer       { background: var(--status-newer-bg)     !important; color: var(--status-newer-text)     !important; }
    .status-deleted     { background: var(--status-deleted-bg)   !important; color: var(--status-deleted-text)   !important; }
    .status-unchanged   { background: var(--status-unchanged-bg) !important; color: var(--status-unchanged-text) !important; }
    .status-version_changed { background: var(--status-version-bg) !important; color: var(--status-version-text) !important; }
    .status-sketch_modified { background: var(--status-sketch-bg)  !important; color: var(--status-sketch-text)  !important; }
    .status-params_changed  { background: var(--status-params-bg)  !important; color: var(--status-params-text)  !important; }
    .status-health_changed  { background: var(--status-health-bg)  !important; color: var(--status-health-text)  !important; }

    /* Detail spans embedded in cells */
    .params-detail  { color: var(--status-params-text)  !important; }
    .sketch-detail  { color: var(--status-sketch-text)  !important; }
    .health-detail  { color: var(--status-health-text)  !important; }
    .version-detail { color: var(--status-version-text) !important; }
</style>
"""


MERGE_CSS = """<style>
    /* Merge column */
    th.col-merge, td.col-merge {
        width: 110px;
        text-align: center;
        background: var(--bg-divider);
        border-left: 2px solid var(--border);
    }
    th.col-merge {
        color: var(--status-params-text);
        background: var(--accent-soft);
    }
    td.col-merge label.merge-label {
        display: inline-block;
        padding: 4px 6px;
        cursor: pointer;
        user-select: none;
        vertical-align: middle;
    }
    td.col-merge label.merge-label:hover { background: var(--accent-soft); }
    td.col-merge input.merge-cb,
    td.col-merge input.merge-cb-parent,
    td.col-merge input.merge-cb-edit {
        -webkit-appearance: checkbox !important;
        appearance: checkbox !important;
        width: 18px !important;
        height: 18px !important;
        margin: 0 !important;
        padding: 0 !important;
        cursor: pointer;
        accent-color: #0984e3;
        display: inline-block;
        vertical-align: middle;
    }
    td.col-merge .merge-na {
        font-size: 10px;
        color: var(--text-faint);
        font-style: italic;
    }
    td.col-merge .merge-direction-delete {
        display: block;
        margin-top: 2px;
        font-size: 10px;
        color: var(--status-deleted-text);
        font-weight: 600;
    }

    /* Expand caret on parent rows */
    .caret {
        display: inline-block;
        width: 14px;
        cursor: pointer;
        user-select: none;
        color: var(--text-muted);
        margin-right: 2px;
        font-size: 11px;
        vertical-align: middle;
    }
    .caret:hover { color: var(--accent); }

    /* Version chip strip on parent rows */
    .version-chips {
        display: block;
        margin-top: 3px;
        font-size: 10px;
        color: var(--text-muted);
    }
    .version-chips .chip {
        display: inline-block;
        padding: 1px 7px;
        margin-right: 3px;
        border-radius: 8px;
        background: var(--bg-page);
        color: var(--text);
        font-weight: 600;
    }

    /* Child (per-edit) rows */
    tr.row-edit { background: var(--bg-surface-2) !important; }
    tr.row-edit td { padding-top: 5px; padding-bottom: 5px; font-size: 12px; }
    tr.row-edit td.col-divider { background: var(--bg-divider) !important; border-color: var(--border) !important; padding: 5px 6px; }
    tr.row-edit td.col-merge { background: var(--bg-divider) !important; border-color: var(--border) !important; }
    tr.row-edit td.child-content {
        padding-left: 36px;
        color: var(--text);
        white-space: nowrap;
    }
    tr.row-edit .child-indent { color: var(--text-faint); margin-right: 8px; }
    tr.row-edit .child-name { font-weight: 600; }
    tr.row-edit .child-detail { color: var(--text-muted); margin-left: 8px; }
    tr.row-edit .child-detail code {
        background: var(--bg-page);
        padding: 1px 6px;
        border-radius: 3px;
        font-family: ui-monospace, Menlo, monospace;
        font-size: 11px;
        color: var(--text);
    }
    tr.row-edit.row-edit-disabled .child-name,
    tr.row-edit.row-edit-disabled .child-detail {
        color: var(--text-faint);
        font-style: italic;
    }

    /* Version badge in the child divider cell */
    .edit-version-badge {
        display: inline-block;
        padding: 1px 8px;
        border-radius: 8px;
        background: #2d3436;
        color: #fff;
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.3px;
    }
    .edit-version-badge.added { background: #155724; }
    .edit-version-badge.deleted { background: #721c24; }
    .edit-version-badge.sketch { background: #8a4b08; }
    .edit-version-badge.xref { background: #856404; }

    /* Apply feedback (works for parent and child) */
    tr.row-applied td.col-merge { background: var(--status-newer-bg) !important; }
    tr.row-applied td.col-merge::after {
        content: "applied";
        display: block;
        font-size: 10px;
        color: var(--status-newer-text);
        font-weight: 600;
        margin-top: 2px;
    }
    tr.row-apply-error td.col-merge { background: var(--status-deleted-bg) !important; }
    tr.row-apply-error td.col-merge::after {
        content: "error";
        display: block;
        font-size: 10px;
        color: var(--status-deleted-text);
        font-weight: 600;
        margin-top: 2px;
    }
    tr.row-apply-error td.col-merge .err-tip {
        display: block;
        font-size: 10px;
        color: var(--status-deleted-text);
        margin-top: 2px;
        white-space: normal;
        line-height: 1.2;
    }

    /* Sticky merge action bar */
    .merge-bar {
        position: sticky;
        bottom: 0;
        background: var(--header-bg);
        color: var(--header-text);
        padding: 12px 18px;
        margin: 18px -24px -24px -24px;
        display: flex;
        align-items: center;
        gap: 12px;
        box-shadow: 0 -2px 8px rgba(0,0,0,0.25);
    }
    .merge-bar .summary { font-size: 13px; flex: 1; }
    .merge-bar .summary b { color: var(--accent); }
    .merge-bar button {
        font-size: 13px;
        font-weight: 600;
        padding: 8px 16px;
        border-radius: 4px;
        border: 1px solid var(--border);
        background: var(--bg-surface);
        color: var(--text);
        cursor: pointer;
    }
    .merge-bar button:hover { background: var(--bg-surface-2); }
    .merge-bar button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
    .merge-bar button.primary:hover { background: var(--accent); filter: brightness(1.1); }
    .merge-bar button:disabled { opacity: 0.4; cursor: not-allowed; }

    /* Scrubber strip — interactive thumbnail across walked versions */
    .scrubber-wrap {
        background: var(--bg-surface);
        border-radius: 8px;
        padding: 16px 16px 12px;
        margin-bottom: 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        text-align: center;
    }
    .scrubber-wrap h3 {
        font-size: 13px;
        font-weight: 700;
        color: var(--text-muted);
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 8px;
    }
    .scrubber-display {
        position: relative;
        width: 500px;
        max-width: 100%;
        height: 280px;
        margin: 0 auto;
        background: var(--bg-surface-2);
        border: 1px solid var(--border);
        border-radius: 4px;
        overflow: hidden;
        cursor: ew-resize;
    }
    .scrubber-thumb {
        position: absolute;
        top: 0; left: 0;
        width: 100%;
        height: 100%;
        object-fit: contain;
        background: var(--bg-surface-2);
    }
    .scrubber-indicator {
        position: relative;
        width: 500px;
        max-width: 100%;
        margin: 10px auto 4px;
        height: 14px;
    }
    .scrubber-bar {
        position: absolute;
        top: 6px;
        left: 0;
        width: 100%;
        height: 2px;
        background: var(--border);
        border-radius: 1px;
    }
    .scrubber-tick {
        position: absolute;
        top: 3px;
        width: 1px;
        height: 8px;
        background: var(--text-faint);
    }
    .scrubber-marker {
        position: absolute;
        top: 2px;
        width: 10px;
        height: 10px;
        background: var(--accent);
        border-radius: 50%;
        margin-left: -5px;
        box-shadow: 0 0 0 2px var(--accent-soft);
        pointer-events: none;
    }
    .scrubber-label {
        font-size: 13px;
        color: var(--text);
        font-weight: 600;
        margin-top: 6px;
    }
    .scrubber-label .v-tag {
        display: inline-block;
        padding: 2px 8px;
        margin-right: 6px;
        border-radius: 10px;
        background: var(--header-bg);
        color: var(--header-text);
        font-size: 11px;
        letter-spacing: 0.5px;
    }
    .scrubber-hint {
        font-size: 11px;
        color: var(--text-faint);
        margin-top: 2px;
    }

    /* Filter controls above the diff table */
    .filter-controls {
        background: var(--bg-surface);
        color: var(--text);
        border-radius: 6px;
        padding: 10px 14px;
        margin-bottom: 8px;
        display: flex;
        align-items: center;
        gap: 12px;
        font-size: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    .filter-controls button {
        font-size: 12px;
        padding: 4px 10px;
        border-radius: 4px;
        border: 1px solid var(--border);
        background: var(--bg-surface-2);
        color: var(--text);
        cursor: pointer;
        font-weight: 600;
    }
    .filter-controls button:hover { background: var(--bg-page); }
    .filter-controls .filter-hint { color: var(--text-faint); }

    /* Default-hide rows tagged as unchanged with no actionable history. */
    body.hide-unchanged tr[data-status="unchanged"][data-has-actions="false"] {
        display: none !important;
    }
    body.hide-unchanged tr.row-edit[data-status="child"][data-parent-unchanged="true"] {
        display: none !important;
    }

    /* Inline help panel */
    .help-button {
        position: absolute;
        top: 14px;
        right: 22px;
        background: rgba(255,255,255,0.12);
        color: #fff;
        border: 1px solid rgba(255,255,255,0.35);
        border-radius: 50%;
        width: 28px;
        height: 28px;
        font-size: 14px;
        font-weight: 700;
        cursor: pointer;
        padding: 0;
        line-height: 26px;
        text-align: center;
    }
    .help-button:hover { background: rgba(255,255,255,0.22); }
    .help-panel {
        background: var(--bg-surface);
        border-radius: 8px;
        padding: 18px 22px;
        margin-bottom: 18px;
        font-size: 13px;
        color: var(--text);
        line-height: 1.55;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    .help-panel h3 {
        margin-bottom: 8px;
        font-size: 14px;
        color: var(--text-strong);
    }
    .help-panel p { margin-bottom: 8px; }
    .help-panel ul { margin: 6px 0 8px 22px; }
    .help-panel code {
        background: var(--bg-page);
        color: var(--text);
        padding: 1px 6px;
        border-radius: 3px;
        font-family: ui-monospace, Menlo, monospace;
        font-size: 11px;
    }
    .help-panel .close-help {
        margin-top: 8px;
        padding: 4px 12px;
        border-radius: 4px;
        border: 1px solid var(--border);
        background: var(--bg-surface-2);
        color: var(--text);
        cursor: pointer;
        font-size: 12px;
        font-weight: 600;
    }
</style>
"""


def _build_version_card(info, label: str, css_class: str) -> str:
    desc = _escape_html(info.description) if info.description else "<i>No description</i>"
    thumb_html = ""
    if getattr(info, "thumbnail_b64", ""):
        thumb_html = (
            f'<img class="card-thumb" '
            f'src="data:image/png;base64,{info.thumbnail_b64}" '
            f'alt="Version {info.version_number} thumbnail" />'
        )
    return f"""<div class="version-card {css_class}">
    <div class="card-label">{label}</div>
    <div class="card-body">
        {thumb_html}
        <div class="card-details">
            <div class="version-number">Version {info.version_number}</div>
            <div class="detail"><b>Date Saved:</b> {_escape_html(info.date_modified)}</div>
            <div class="detail"><b>Saved By:</b> {_escape_html(info.last_updated_by)}</div>
            <div class="detail"><b>Description:</b> {desc}</div>
        </div>
    </div>
</div>"""


_STATUS_LABELS = {
    "newer": "NEW",
    "deleted": "DEL",
    "unchanged": "SAME",
    "version_changed": "VER Δ",
    "sketch_modified": "SK Δ",
    "params_changed": "PRM Δ",
    "health_changed": "HTH Δ",
}


def _row_feature_key(ar):
    """Return the matching feature_key for an aligned row (older or newer side)."""
    feat = ar.newer or ar.older
    if feat is None:
        return None
    return _feature_key(feat)


def _build_data_for_js(diff_result: DiffResult) -> dict:
    """Build the JS-side data that drives cherry-pick computation.

    Returns a dict shaped like::

        {
            "edits": {edit_id: {kind, rowId, feature_id, param_name?, version,
                                older_expr?, newer_expr?}},
            "param_histories": {"<row_id>|<param_name>": {
                feature_id, param_name,
                compare_expr, baseline_expr,
                edits: [{edit_id, version, value_expr}],
            }},
            "feature_info": {row_id: {is_new_in_span, feature: {name, type, index}}},
        }
    """
    histories = diff_result.feature_histories or {}
    edits_out = {}
    param_histories_out = {}
    feature_info_out = {}

    for i, ar in enumerate(diff_result.aligned_rows):
        row_id = f"row-{i}"
        feat_key = _row_feature_key(ar)
        if feat_key is None:
            continue
        hist = histories.get(feat_key)
        if hist is None:
            continue

        # Per-edit data for every event we surface to the page.
        for ev in hist.events:
            # Skip add/delete events that aren't this row's "newer" or
            # "deleted" status — they're already collapsed by snapshot diff.
            qualified_edit_id = f"{row_id}.{ev.edit_id}"
            edit_record = {
                "rowId": qualified_edit_id,
                "feature_id": row_id,
                "kind": ev.kind,
                "version": ev.version_number,
                "param_name": ev.param_name,
                "older_expr": ev.older_value_expr,
                "newer_expr": ev.newer_value_expr,
                "detail": ev.detail,
            }
            edits_out[qualified_edit_id] = edit_record

        # Per-parameter chronological history.
        for pname in hist.param_names_edited():
            key = f"{row_id}|{pname}"
            compare_entry = (hist.compare_params or {}).get(pname)
            baseline_entry = (hist.baseline_params or {}).get(pname)
            compare_expr = compare_entry[1] if compare_entry else ""
            baseline_expr = baseline_entry[1] if baseline_entry else ""
            edits_list = []
            for ev in hist.param_edits(pname):
                edits_list.append({
                    "edit_id": f"{row_id}.{ev.edit_id}",
                    "version": ev.version_number,
                    "value_expr": ev.newer_value_expr,
                })
            param_histories_out[key] = {
                "feature_id": row_id,
                "param_name": pname,
                "compare_expr": compare_expr,
                "baseline_expr": baseline_expr,
                "edits": edits_list,
            }

        # Feature-info for delete actions.
        if ar.status == "newer" and ar.newer is not None:
            added_event = next(
                (ev for ev in hist.events if ev.kind == "added"),
                None,
            )
            added_edit_id = f"{row_id}.{added_event.edit_id}" if added_event else None
            feature_info_out[row_id] = {
                "feature": {
                    "name": ar.newer.name,
                    "feature_type": ar.newer.feature_type,
                    "index": ar.newer.index,
                },
                "added_edit_id": added_edit_id,
            }

    # Per-XREF chronological history: only present for rows whose
    # feature is an XREF that changed version at least once.
    xref_histories_out = {}
    for i, ar in enumerate(diff_result.aligned_rows):
        row_id = f"row-{i}"
        feat_key = _row_feature_key(ar)
        if feat_key is None:
            continue
        hist = histories.get(feat_key)
        if hist is None:
            continue
        xref_events = [e for e in hist.events if e.kind == "xref_version_changed"]
        if not xref_events:
            continue
        if not (ar.newer and ar.newer.feature_type == "XREF"):
            # Only act on XREFs that exist in baseline; otherwise the
            # occurrence isn't there to replace.
            continue
        compare_xref = ar.older.component_version if ar.older else ""
        baseline_xref = ar.newer.component_version
        edits_list = [
            {
                "edit_id": f"{row_id}.{e.edit_id}",
                "version": e.version_number,
                "target_xref": e.newer_value_expr,
            }
            for e in sorted(xref_events, key=lambda e: e.version_number)
        ]
        xref_histories_out[row_id] = {
            "feature_id": row_id,
            "occurrence_name": ar.newer.name,
            "compare_xref": compare_xref,
            "baseline_xref": baseline_xref,
            "edits": edits_list,
        }

    return {
        "edits": edits_out,
        "param_histories": param_histories_out,
        "xref_histories": xref_histories_out,
        "feature_info": feature_info_out,
    }


def _render_param_edit_child(parent_id: str, ev, qualified_id: str, parent_unchanged: str = "false") -> str:
    return f"""<tr id="{qualified_id}" class="row-edit" data-parent="{parent_id}" data-status="child" data-parent-unchanged="{parent_unchanged}" style="display: none;">
    <td class="empty-cell"></td>
    <td class="empty-cell"></td>
    <td class="empty-cell"></td>
    <td class="col-divider"><span class="edit-version-badge">V{ev.version_number}</span></td>
    <td class="empty-cell"></td>
    <td class="child-content">
        <span class="child-indent">└</span>
        <span class="child-name">{_escape_html(ev.param_name)}</span>
        <span class="child-detail"><code>{_escape_html(ev.older_value_expr)}</code> &rarr; <code>{_escape_html(ev.newer_value_expr)}</code></span>
    </td>
    <td class="empty-cell"></td>
    <td class="col-merge">
        <label class="merge-label" title="Tick to undo this specific edit">
            <input type="checkbox" class="merge-cb-edit" data-edit-id="{qualified_id}" data-parent-id="{parent_id}">
        </label>
    </td>
</tr>"""


def _render_added_edit_child(parent_id: str, ev, qualified_id: str, parent_unchanged: str = "false") -> str:
    return f"""<tr id="{qualified_id}" class="row-edit" data-parent="{parent_id}" data-status="child" data-parent-unchanged="{parent_unchanged}" style="display: none;">
    <td class="empty-cell"></td>
    <td class="empty-cell"></td>
    <td class="empty-cell"></td>
    <td class="col-divider"><span class="edit-version-badge added">V{ev.version_number}</span></td>
    <td class="empty-cell"></td>
    <td class="child-content">
        <span class="child-indent">└</span>
        <span class="child-name">feature added</span>
        <span class="child-detail">first appeared in V{ev.version_number}</span>
    </td>
    <td class="empty-cell"></td>
    <td class="col-merge">
        <label class="merge-label" title="Tick to remove this feature from the active document">
            <input type="checkbox" class="merge-cb-edit" data-edit-id="{qualified_id}" data-parent-id="{parent_id}">
            <span class="merge-direction-delete">remove</span>
        </label>
    </td>
</tr>"""


def _render_deleted_edit_child(parent_id: str, ev, qualified_id: str, parent_unchanged: str = "false") -> str:
    return f"""<tr id="{qualified_id}" class="row-edit row-edit-disabled" data-parent="{parent_id}" data-status="child" data-parent-unchanged="{parent_unchanged}" style="display: none;">
    <td class="empty-cell"></td>
    <td class="empty-cell"></td>
    <td class="empty-cell"></td>
    <td class="col-divider"><span class="edit-version-badge deleted">V{ev.version_number}</span></td>
    <td class="empty-cell"></td>
    <td class="child-content">
        <span class="child-indent">└</span>
        <span class="child-name">feature deleted</span>
        <span class="child-detail">removed in V{ev.version_number} — re-adding not yet supported</span>
    </td>
    <td class="empty-cell"></td>
    <td class="col-merge">
        <span class="merge-na" title="Re-adding deleted features is not yet supported">can&rsquo;t re-add</span>
    </td>
</tr>"""


def _render_xref_edit_child(parent_id: str, ev, qualified_id: str, parent_unchanged: str = "false") -> str:
    return f"""<tr id="{qualified_id}" class="row-edit" data-parent="{parent_id}" data-status="child" data-parent-unchanged="{parent_unchanged}" style="display: none;">
    <td class="empty-cell"></td>
    <td class="empty-cell"></td>
    <td class="empty-cell"></td>
    <td class="col-divider"><span class="edit-version-badge xref">V{ev.version_number}</span></td>
    <td class="empty-cell"></td>
    <td class="child-content">
        <span class="child-indent">└</span>
        <span class="child-name">XREF version</span>
        <span class="child-detail"><code>{_escape_html(ev.older_value_expr)}</code> &rarr; <code>{_escape_html(ev.newer_value_expr)}</code></span>
    </td>
    <td class="empty-cell"></td>
    <td class="col-merge">
        <label class="merge-label" title="Tick to undo this XREF version change">
            <input type="checkbox" class="merge-cb-edit" data-edit-id="{qualified_id}" data-parent-id="{parent_id}">
        </label>
    </td>
</tr>"""


def _render_sketch_edit_child(parent_id: str, ev, qualified_id: str, parent_unchanged: str = "false") -> str:
    return f"""<tr id="{qualified_id}" class="row-edit row-edit-disabled" data-parent="{parent_id}" data-status="child" data-parent-unchanged="{parent_unchanged}" style="display: none;">
    <td class="empty-cell"></td>
    <td class="empty-cell"></td>
    <td class="empty-cell"></td>
    <td class="col-divider"><span class="edit-version-badge sketch">V{ev.version_number}</span></td>
    <td class="empty-cell"></td>
    <td class="child-content">
        <span class="child-indent">└</span>
        <span class="child-name">sketch geometry</span>
        <span class="child-detail">{_escape_html(ev.detail or 'modified')} — not yet supported</span>
    </td>
    <td class="empty-cell"></td>
    <td class="col-merge">
        <span class="merge-na" title="Sketch geometry merge not yet supported">&mdash;</span>
    </td>
</tr>"""


def _build_two_column_table(diff_result: DiffResult) -> tuple:
    """Render the diff table with per-edit child rows.

    Returns ``(table_html, mergeable_count)``.
    """
    older_is_comparison = diff_result.older_is_comparison
    if older_is_comparison:
        older_info = diff_result.comparison
        newer_info = diff_result.baseline
    else:
        older_info = diff_result.baseline
        newer_info = diff_result.comparison

    older_label = f"V{older_info.version_number} (Older)"
    newer_label = f"V{newer_info.version_number} (Newer)"

    histories = diff_result.feature_histories or {}
    rows_html = []
    mergeable_count = 0

    for i, ar in enumerate(diff_result.aligned_rows):
        row_id = f"row-{i}"
        feat_key = _row_feature_key(ar)
        hist = histories.get(feat_key) if feat_key else None

        row_class = f"row-{ar.status}"
        status_class = f"status-{ar.status}"
        status_label = _STATUS_LABELS.get(ar.status, ar.status.upper())

        # Older side cells
        if ar.older:
            older_idx = str(ar.older.index)
            older_icon = icon_img_tag(ar.older.feature_type)
            older_name_inner = older_icon + _escape_html(ar.older.name)
            older_type = _escape_html(ar.older.feature_type)
            if ar.older.feature_type == "XREF" and ar.older.component_version:
                older_name_inner += (
                    f'<span class="version-detail">'
                    f'{_escape_html(ar.older.component_version)}</span>'
                )
            older_cls = ""
        else:
            older_idx = ""
            older_name_inner = ""
            older_type = ""
            older_cls = " empty-cell"

        # Newer side cells
        if ar.newer:
            newer_idx = str(ar.newer.index)
            newer_icon = icon_img_tag(ar.newer.feature_type)
            newer_name_inner = newer_icon + _escape_html(ar.newer.name)
            newer_type = _escape_html(ar.newer.feature_type)
            if ar.newer.feature_type == "XREF" and ar.newer.component_version:
                newer_name_inner += (
                    f'<span class="version-detail">'
                    f'{_escape_html(ar.newer.component_version)}</span>'
                )
            if ar.status == "sketch_modified" and ar.sketch_detail:
                newer_name_inner += (
                    f'<span class="sketch-detail">'
                    f'{_escape_html(ar.sketch_detail)}</span>'
                )
            if ar.status == "params_changed" and ar.params_detail:
                newer_name_inner += (
                    f'<span class="params-detail">'
                    f'{_escape_html(ar.params_detail)}</span>'
                )
            if ar.status == "health_changed" and ar.health_detail:
                newer_name_inner += (
                    f'<span class="health-detail">'
                    f'{_escape_html(ar.health_detail)}</span>'
                )
            newer_cls = ""
        else:
            newer_idx = ""
            newer_name_inner = ""
            newer_type = ""
            newer_cls = " empty-cell"

        # Version chip strip — only if there are multiple edited versions
        # or the only edit was at an intermediate version (not at the
        # baseline boundary). Showing the strip even for single events
        # gives consistent at-a-glance provenance.
        chip_strip = ""
        edited_versions = hist.edited_versions() if hist else []
        if edited_versions:
            chips = " ".join(
                f'<span class="chip">V{v}</span>' for v in edited_versions
            )
            chip_strip = f'<span class="version-chips">{chips}</span>'

        # The text under newer-name gets the chip strip appended.
        if newer_name_inner and chip_strip:
            newer_name_inner = newer_name_inner + chip_strip
        elif chip_strip and not newer_name_inner and older_name_inner:
            # Show chips under older-name when newer is empty (deleted row)
            older_name_inner = older_name_inner + chip_strip

        divider_extra = ""
        if ar.status == "version_changed" and ar.detail:
            divider_extra = (
                f'<br><span class="version-detail">{_escape_html(ar.detail)}</span>'
            )

        # Determine if this row has any actionable (checkable) edits.
        actionable_events = []
        unactionable_events = []
        if hist:
            for ev in hist.events:
                if ev.kind == "param_changed":
                    actionable_events.append(ev)
                elif ev.kind == "xref_version_changed" and ar.newer and ar.newer.feature_type == "XREF":
                    actionable_events.append(ev)
                elif ev.kind == "added" and ar.status == "newer":
                    actionable_events.append(ev)
                else:
                    unactionable_events.append(ev)

        has_any_children = bool(hist and hist.events)

        # Merge cell on parent
        if actionable_events:
            merge_cell = (
                f'<span class="caret" onclick="toggleExpand(\'{row_id}\')">&#x25B6;</span>'
                f'<label class="merge-label" title="Tick to select all undoable edits below">'
                f'<input type="checkbox" class="merge-cb-parent" data-parent-id="{row_id}">'
                f'</label>'
            )
            mergeable_count += len(actionable_events)
        elif has_any_children:
            # Children exist but none are actionable (e.g. sketch geometry only).
            merge_cell = (
                f'<span class="caret" onclick="toggleExpand(\'{row_id}\')">&#x25B6;</span>'
                f'<span class="merge-na">no actionable edits</span>'
            )
        elif ar.status == "deleted":
            merge_cell = (
                '<span class="merge-na" '
                'title="Re-adding deleted features is not yet supported">'
                'can&rsquo;t re-add</span>'
            )
        elif ar.status == "health_changed":
            merge_cell = (
                '<span class="merge-na" '
                'title="Health state changes are usually side effects '
                'of param or XREF edits — they typically resolve when '
                'those underlying changes are merged.">info only</span>'
            )
        else:
            merge_cell = '<span class="merge-na">&mdash;</span>'

        has_actions = "true" if actionable_events else "false"
        rows_html.append(
            f'<tr id="{row_id}" class="{row_class}" data-status="{ar.status}" data-has-actions="{has_actions}">'
            f'<td class="older-idx{older_cls}">{older_idx}</td>'
            f'<td class="older-name{older_cls}">{older_name_inner}</td>'
            f'<td class="older-type{older_cls}">{older_type}</td>'
            f'<td class="col-divider"><span class="status-badge {status_class}">{status_label}</span>{divider_extra}</td>'
            f'<td class="newer-idx{newer_cls}">{newer_idx}</td>'
            f'<td class="newer-name{newer_cls}">{newer_name_inner}</td>'
            f'<td class="newer-type{newer_cls}">{newer_type}</td>'
            f'<td class="col-merge">{merge_cell}</td>'
            f"</tr>"
        )

        # Children — render every event for the feature, in chronological order.
        # Tag children with the parent's unchanged-ness so the hide-unchanged
        # filter collapses them together with the parent.
        parent_unchanged_attr = (
            'true' if (ar.status == "unchanged" and not actionable_events) else 'false'
        )
        if hist and hist.events:
            for ev in sorted(hist.events, key=lambda e: (e.version_number, e.kind, e.param_name)):
                qid = f"{row_id}.{ev.edit_id}"
                if ev.kind == "param_changed":
                    rows_html.append(_render_param_edit_child(row_id, ev, qid, parent_unchanged_attr))
                elif ev.kind == "xref_version_changed":
                    if ar.newer and ar.newer.feature_type == "XREF":
                        rows_html.append(_render_xref_edit_child(row_id, ev, qid, parent_unchanged_attr))
                elif ev.kind == "added":
                    if ar.status == "newer":
                        rows_html.append(_render_added_edit_child(row_id, ev, qid, parent_unchanged_attr))
                elif ev.kind == "deleted":
                    if ar.status == "deleted":
                        rows_html.append(_render_deleted_edit_child(row_id, ev, qid, parent_unchanged_attr))
                elif ev.kind == "sketch_modified":
                    rows_html.append(_render_sketch_edit_child(row_id, ev, qid, parent_unchanged_attr))

    table_rows = "\n        ".join(rows_html)
    table_summary = (
        f"{mergeable_count} actionable edit"
        f"{'s' if mergeable_count != 1 else ''}"
    )

    table_html = f"""<div class="diff-table-wrap">
    <h2>Timeline Comparison <span class="table-summary">&mdash; {_escape_html(table_summary)}</span></h2>
    <table class="diff-table">
        <thead>
            <tr>
                <th class="older-idx col-older">#</th>
                <th class="older-name col-older">{_escape_html(older_label)}</th>
                <th class="older-type col-older">Type</th>
                <th class="col-divider col-status">Status</th>
                <th class="newer-idx col-newer">#</th>
                <th class="newer-name col-newer">{_escape_html(newer_label)}</th>
                <th class="newer-type col-newer">Type</th>
                <th class="col-merge">Merge</th>
            </tr>
        </thead>
        <tbody>
        {table_rows}
        </tbody>
    </table>
</div>"""
    return table_html, mergeable_count


def _build_merge_bar(mergeable_count: int) -> str:
    return f"""<div class="merge-bar">
    <div class="summary">
        <span id="selection-summary"><b>0</b> of {mergeable_count} edits ticked</span>
    </div>
    <button onclick="selectAll(true)">Tick all undoable</button>
    <button onclick="selectAll(false)">Clear</button>
    <button id="apply-btn" class="primary" onclick="applyMerges()" disabled>Apply 0 edits</button>
</div>"""


def _build_scrubber(diff_result: DiffResult) -> str:
    """Scrubber strip: every walked version's viewport thumbnail, scrubbed
    by horizontal cursor position.  Left edge = oldest (comparison version),
    right edge = newest (baseline / current).
    """
    chrono = [diff_result.comparison] + list(diff_result.intermediate_versions or []) + [diff_result.baseline]
    chrono = [v for v in chrono if v is not None and getattr(v, "thumbnail_b64", "")]
    if len(chrono) < 2:
        return ""

    thumbs_html = []
    js_versions = []
    for i, info in enumerate(chrono):
        thumbs_html.append(
            f'<img class="scrubber-thumb" data-version="{info.version_number}" '
            f'src="data:image/png;base64,{info.thumbnail_b64}" '
            f'style="display: {"block" if i == len(chrono) - 1 else "none"};" />'
        )
        date_part = _escape_html(info.date_modified or "")
        user_part = _escape_html(info.last_updated_by or "")
        meta_bits = [b for b in (date_part, user_part) if b]
        meta = " · ".join(meta_bits)
        js_versions.append({
            "version": info.version_number,
            "label": f'<span class="v-tag">V{info.version_number}</span>{meta}',
        })

    n = len(chrono)
    ticks_html = []
    for i in range(n):
        pos = 0 if n == 1 else (i / (n - 1)) * 100
        ticks_html.append(f'<div class="scrubber-tick" style="left: {pos}%"></div>')

    versions_json = json.dumps(js_versions)
    last_label = js_versions[-1]["label"]

    return f"""<div class="scrubber-wrap">
    <h3>Version scrubber &mdash; {n} versions walked</h3>
    <div class="scrubber-display" id="scrubber-display">
        {chr(10).join(thumbs_html)}
    </div>
    <div class="scrubber-indicator">
        <div class="scrubber-bar"></div>
        {''.join(ticks_html)}
        <div class="scrubber-marker" id="scrubber-marker" style="left: 100%"></div>
    </div>
    <div class="scrubber-label" id="scrubber-label">{last_label}</div>
    <div class="scrubber-hint">Move the cursor across the thumbnail &mdash; left edge is V{chrono[0].version_number} (oldest), right edge is V{chrono[-1].version_number} (current).</div>
</div>
<script>
const SCRUB_VERSIONS = __SCRUB_VERSIONS__;
(function() {{
    const display = document.getElementById('scrubber-display');
    const marker  = document.getElementById('scrubber-marker');
    const labelEl = document.getElementById('scrubber-label');
    if (!display) return;
    const thumbs = display.querySelectorAll('.scrubber-thumb');
    function update(idx) {{
        idx = Math.max(0, Math.min(SCRUB_VERSIONS.length - 1, idx));
        thumbs.forEach((t, i) => {{ t.style.display = (i === idx) ? 'block' : 'none'; }});
        const ratio = SCRUB_VERSIONS.length > 1 ? idx / (SCRUB_VERSIONS.length - 1) : 1;
        marker.style.left = (ratio * 100) + '%';
        labelEl.innerHTML = SCRUB_VERSIONS[idx].label;
    }}
    display.addEventListener('mousemove', function(e) {{
        const rect = display.getBoundingClientRect();
        const x = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
        // Map x to an index, including both endpoints reliably.
        const ratio = rect.width > 0 ? x / rect.width : 0;
        const idx = Math.min(SCRUB_VERSIONS.length - 1, Math.floor(ratio * SCRUB_VERSIONS.length));
        update(idx);
    }});
}})();
</script>""".replace("__SCRUB_VERSIONS__", versions_json)


def _intermediate_version_summary(diff_result: DiffResult) -> str:
    """A small banner showing which intermediate versions were walked."""
    inter = diff_result.intermediate_versions or []
    if not inter:
        return ""
    items = []
    for info in inter:
        items.append(
            f'<span class="chip">V{info.version_number} '
            f'<span style="color:#95a5a6">· {_escape_html(info.last_updated_by or "")}'
            f'</span></span>'
        )
    chips = " ".join(items)
    return f"""<div style="background:#fff;padding:10px 14px;border-radius:6px;margin-bottom:14px;font-size:12px;color:#636e72;">
    <b>Walked intermediate versions:</b> {chips}
</div>"""


def generate_merge_html(diff_result: DiffResult) -> str:
    """Render the interactive merge report to a temp HTML file."""
    doc_name = _escape_html(diff_result.baseline.name)

    if diff_result.older_is_comparison:
        left_card = _build_version_card(diff_result.comparison, "Older (Comparison)", "older")
        right_card = _build_version_card(diff_result.baseline, "Newer (Current)", "newer")
    else:
        left_card = _build_version_card(diff_result.baseline, "Older (Current)", "older")
        right_card = _build_version_card(diff_result.comparison, "Newer (Comparison)", "newer")

    feature_table, mergeable_count = _build_two_column_table(diff_result)
    merge_bar = _build_merge_bar(mergeable_count)
    scrubber = _build_scrubber(diff_result)
    debug_strip = (
        '<div id="debug-strip">(debug strip — newest events first)</div>'
        if getattr(config, "DEBUG", False) else ""
    )
    filter_controls = """<div class="filter-controls">
    <button id="unchanged-toggle" onclick="toggleUnchanged()">Show unchanged rows</button>
    <span class="filter-hint">unchanged rows are hidden by default</span>
</div>"""
    help_panel = """<div class="help-panel" id="help-panel" style="display: none;">
    <h3>How Version Merge works</h3>
    <p>Each ticked edit is one you want to <b>undo</b>. When you click Apply:</p>
    <ul>
        <li><b>Parameter changes</b> — the walk computes what value the parameter would have if you'd skipped each ticked version's edit, and sets it directly.</li>
        <li><b>XREF version changes</b> — same logic across version history. The target version replaces the current external reference.</li>
        <li><b>Feature additions</b> — ticking the "added" row removes the feature from the active document. (Confirmation prompt shown before applying.)</li>
    </ul>
    <p>Edits that override each other can cancel out — e.g. <code>V4: d1 → 12 mm</code> followed by <code>V6: d1 → 15 mm</code>. Ticking only V4 has no effect, because V6 still sets d1 to 15.</p>
    <p>Some changes can't be merged yet and are shown disabled:</p>
    <ul>
        <li>Sketch geometry edits — we can't round-trip arbitrary sketch entities.</li>
        <li>Re-adding a feature that was deleted in an intermediate version.</li>
        <li>Health-state changes — usually resolve on their own when underlying changes merge.</li>
    </ul>
    <button class="close-help" onclick="toggleHelp()">Close</button>
</div>"""

    js_data = _build_data_for_js(diff_result)
    data_json = json.dumps(js_data)

    merge_js = """<script>
const MERGE_DATA = __DATA__;

// Maps the rowId of an aggregated apply action (built client-side) to the
// list of edit-row IDs that contributed, so result feedback can fan out.
let CONTRIB_MAP = {};

function debug(msg) {
    const el = document.getElementById('debug-strip');
    if (!el) return;
    const ts = new Date().toISOString().slice(11, 23);
    el.textContent = '[' + ts + '] ' + msg + '   |   ' + el.textContent;
    if (el.textContent.length > 500) el.textContent = el.textContent.slice(0, 500);
}

function cssEsc(s) {
    return (window.CSS && CSS.escape) ? CSS.escape(s) : s.replace(/[^a-zA-Z0-9_.\\-]/g, '\\\\$&');
}

function countCheckedEdits() {
    return document.querySelectorAll('.merge-cb-edit:checked').length;
}

function updateSummary() {
    const checked = countCheckedEdits();
    // Total actionable = enabled edit checkboxes (sketch_modified / deleted are not)
    const total = document.querySelectorAll('input.merge-cb-edit:not(:disabled)').length;
    document.getElementById('selection-summary').innerHTML =
        '<b>' + checked + '</b> of ' + total + ' edits ticked';
    const btn = document.getElementById('apply-btn');
    btn.textContent = 'Apply ' + checked + ' edit' + (checked === 1 ? '' : 's');
    btn.disabled = checked === 0;
}

function refreshParentState(parentId) {
    const sel = 'input.merge-cb-edit[data-parent-id="' + cssEsc(parentId) + '"]';
    const children = Array.from(document.querySelectorAll(sel)).filter(cb => !cb.disabled);
    const parent = document.querySelector(
        'input.merge-cb-parent[data-parent-id="' + cssEsc(parentId) + '"]'
    );
    if (!parent) return;
    if (children.length === 0) {
        parent.checked = false;
        parent.indeterminate = false;
        return;
    }
    const checkedCount = children.filter(cb => cb.checked).length;
    if (checkedCount === 0) {
        parent.checked = false;
        parent.indeterminate = false;
    } else if (checkedCount === children.length) {
        parent.checked = true;
        parent.indeterminate = false;
    } else {
        parent.checked = false;
        parent.indeterminate = true;
    }
}

function toggleExpand(parentId) {
    const parentRow = document.getElementById(parentId);
    if (!parentRow) return;
    const caret = parentRow.querySelector('.caret');
    if (!caret) return;
    const expanded = !caret.classList.contains('expanded');
    caret.classList.toggle('expanded', expanded);
    caret.innerHTML = expanded ? '&#x25BC;' : '&#x25B6;';
    document.querySelectorAll('tr[data-parent="' + cssEsc(parentId) + '"]').forEach(r => {
        r.style.display = expanded ? '' : 'none';
    });
}

function selectAll(state) {
    document.querySelectorAll('input.merge-cb-edit').forEach(cb => {
        if (!cb.disabled) cb.checked = state;
    });
    document.querySelectorAll('input.merge-cb-parent').forEach(p => {
        refreshParentState(p.getAttribute('data-parent-id'));
    });
    updateSummary();
}

document.addEventListener('change', function(e) {
    const t = e.target;
    if (!t || !t.classList) return;
    if (t.classList.contains('merge-cb-parent')) {
        const pid = t.getAttribute('data-parent-id');
        const state = t.checked;
        document.querySelectorAll(
            'input.merge-cb-edit[data-parent-id="' + cssEsc(pid) + '"]'
        ).forEach(cb => { if (!cb.disabled) cb.checked = state; });
        refreshParentState(pid);
        updateSummary();
        debug('parent toggle ' + pid + ' -> ' + state);
    } else if (t.classList.contains('merge-cb-edit')) {
        refreshParentState(t.getAttribute('data-parent-id'));
        updateSummary();
        debug('edit toggle ' + t.getAttribute('data-edit-id'));
    }
});

// Walk a parameter's edit history applying-or-skipping each version,
// starting from the compare-version value. Returns the final expression
// that the parameter should hold once the user's chosen edits are undone.
function computeTargetExpr(historyKey, skippedVersions) {
    const h = MERGE_DATA.param_histories[historyKey];
    if (!h) return null;
    let cur = h.compare_expr;
    for (const e of h.edits) {
        if (!skippedVersions.has(e.version)) {
            cur = e.value_expr;
        }
    }
    return cur;
}

function applyMerges() {
    const checked = Array.from(document.querySelectorAll('.merge-cb-edit:checked'));
    if (checked.length === 0) return;

    // Bucket edits.
    const featuresToDelete = new Set();    // feature_id
    const featureContrib = {};             // feature_id -> [edit row ids]
    const paramSkipSets = {};              // "feature_id|param_name" -> Set of versions
    const paramContrib = {};               // same key -> [edit row ids]
    const xrefSkipSets = {};               // feature_id -> Set of versions
    const xrefContrib = {};                // feature_id -> [edit row ids]

    for (const cb of checked) {
        const editId = cb.getAttribute('data-edit-id');
        const data = MERGE_DATA.edits[editId];
        if (!data) continue;
        if (data.kind === 'added') {
            featuresToDelete.add(data.feature_id);
            (featureContrib[data.feature_id] = featureContrib[data.feature_id] || []).push(editId);
        } else if (data.kind === 'param_changed') {
            const key = data.feature_id + '|' + data.param_name;
            if (!paramSkipSets[key]) paramSkipSets[key] = new Set();
            paramSkipSets[key].add(data.version);
            (paramContrib[key] = paramContrib[key] || []).push(editId);
        } else if (data.kind === 'xref_version_changed') {
            const fid = data.feature_id;
            if (!xrefSkipSets[fid]) xrefSkipSets[fid] = new Set();
            xrefSkipSets[fid].add(data.version);
            (xrefContrib[fid] = xrefContrib[fid] || []).push(editId);
        }
    }

    const selections = [];
    CONTRIB_MAP = {};

    // Build delete selections.
    for (const fid of featuresToDelete) {
        const finfo = MERGE_DATA.feature_info[fid];
        if (!finfo) continue;
        const aggId = fid + '|delete';
        selections.push({
            rowId: aggId,
            kind: 'delete_feature',
            feature: finfo.feature,
        });
        CONTRIB_MAP[aggId] = featureContrib[fid] || [];
    }

    // Build param-revert selections by cherry-pick walk.
    for (const key of Object.keys(paramSkipSets)) {
        const [featureId, paramName] = key.split('|');
        if (featuresToDelete.has(featureId)) {
            const aggDelId = featureId + '|delete';
            if (CONTRIB_MAP[aggDelId]) {
                CONTRIB_MAP[aggDelId] = CONTRIB_MAP[aggDelId].concat(paramContrib[key] || []);
            }
            continue;
        }
        const target = computeTargetExpr(key, paramSkipSets[key]);
        if (target === null || target === undefined) continue;
        const baseline = MERGE_DATA.param_histories[key].baseline_expr;
        if (target === baseline) continue;
        const aggId = key + '|target';
        selections.push({
            rowId: aggId,
            kind: 'params',
            params: [{name: paramName, expression: target}],
        });
        CONTRIB_MAP[aggId] = paramContrib[key] || [];
    }

    // Build XREF-revert selections by cherry-pick walk.
    for (const fid of Object.keys(xrefSkipSets)) {
        const hist = MERGE_DATA.xref_histories[fid];
        if (!hist) continue;
        const skip = xrefSkipSets[fid];
        let cur = hist.compare_xref;
        for (const e of hist.edits) {
            if (!skip.has(e.version)) cur = e.target_xref;
        }
        if (!cur || cur === hist.baseline_xref) continue;
        const targetNum = parseInt(String(cur).replace(/^v/i, ''), 10);
        if (!Number.isFinite(targetNum)) continue;
        const aggId = fid + '|xref';
        selections.push({
            rowId: aggId,
            kind: 'xref_version',
            occurrence_name: hist.occurrence_name,
            target_version: targetNum,
        });
        CONTRIB_MAP[aggId] = xrefContrib[fid] || [];
    }

    if (selections.length === 0) {
        debug('no net changes after cherry-pick walk');
        alert('Ticked edits cancel out (later edits override them). Nothing to apply.');
        return;
    }

    // Destructive-action confirmation. Only feature removals are non-reversible
    // from inside this command — XREF reverts and param reverts can be undone
    // by re-running merge.
    const deleteCount = featuresToDelete.size;
    if (deleteCount > 0) {
        const msg = deleteCount === 1
            ? "About to remove 1 feature from the active document. "
              + "Re-adding deleted features is not yet supported and this may break dependent features. Continue?"
            : "About to remove " + deleteCount + " features from the active document. "
              + "Re-adding deleted features is not yet supported and this may break dependent features. Continue?";
        if (!confirm(msg)) {
            debug('user cancelled destructive apply (' + deleteCount + ' deletion(s))');
            CONTRIB_MAP = {};
            return;
        }
    }

    document.getElementById('apply-btn').disabled = true;
    document.getElementById('apply-btn').textContent = 'Applying...';
    if (typeof adsk === 'undefined' || !adsk.fusionSendData) {
        alert('Host bridge not available.');
        return;
    }
    adsk.fusionSendData('applyMerges', JSON.stringify({selections: selections}));
    debug('apply ' + selections.length + ' aggregated action(s)');
}

window.fusionJavaScriptHandler = {
    handle: function(action, data) {
        try {
            // Theme handshake — Python sends the raw theme string, not JSON.
            if (action === 'setTheme') {
                document.documentElement.setAttribute('data-theme', data || 'dark');
                debug('setTheme -> ' + data);
                return 'OK';
            }
            const payload = JSON.parse(data || '{}');
            if (action === 'applyResult') {
                handleApplyResult(payload.results || []);
            }
        } catch (e) {
            debug('handler error: ' + e.message);
        }
        return 'OK';
    }
};

// Pull the current Fusion theme on load and whenever the palette becomes
// visible again — covers the case where the user changed Fusion's theme
// while we weren't looking.
function requestTheme() {
    try {
        if (typeof adsk !== 'undefined' && adsk.fusionSendData) {
            adsk.fusionSendData('getTheme', '');
        }
    } catch (e) { debug('requestTheme failed: ' + e.message); }
}
requestTheme();
document.addEventListener('visibilitychange', function() {
    if (!document.hidden) requestTheme();
});

function handleApplyResult(results) {
    const parentsToRefresh = new Set();
    for (const r of results) {
        const contributingEditIds = CONTRIB_MAP[r.rowId] || [];
        for (const editId of contributingEditIds) {
            const cb = document.querySelector(
                'input.merge-cb-edit[data-edit-id="' + cssEsc(editId) + '"]'
            );
            if (!cb) continue;
            const tr = cb.closest('tr');
            if (!tr) continue;
            tr.classList.remove('row-applied', 'row-apply-error');
            tr.classList.add(r.ok ? 'row-applied' : 'row-apply-error');
            cb.checked = false;
            if (r.ok) cb.disabled = true;
            if (!r.ok && r.message) {
                const cell = tr.querySelector('td.col-merge');
                const existing = cell.querySelector('.err-tip');
                if (existing) existing.remove();
                const tip = document.createElement('span');
                tip.className = 'err-tip';
                tip.textContent = r.message;
                cell.appendChild(tip);
            }
            parentsToRefresh.add(cb.getAttribute('data-parent-id'));
        }
    }
    parentsToRefresh.forEach(pid => refreshParentState(pid));
    updateSummary();
    const btn = document.getElementById('apply-btn');
    btn.textContent = 'Apply 0 edits';
    btn.disabled = true;
    debug('applyResult: ' + results.length + ' aggregated row(s)');
}

updateSummary();
</script>""".replace("__DATA__", data_json)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{doc_name} - Version Merge</title>
    {HTML_CSS}
    {THEME_CSS}
    {MERGE_CSS}
    <style>
        #debug-strip {{
            position: sticky; top: 0; z-index: 100;
            background: #2d3436; color: #74b9ff;
            font-family: ui-monospace, Menlo, monospace;
            font-size: 11px; padding: 4px 10px;
            white-space: nowrap; overflow-x: auto;
            margin: -24px -24px 12px -24px;
        }}
    </style>
</head>
<body class="hide-unchanged">
    {debug_strip}

    <div class="report-header" style="position: relative;">
        <h1>{doc_name} - Version Merge</h1>
        <div class="subtitle">Cherry-pick edits to undo, walking from V{diff_result.comparison.version_number} forward to V{diff_result.baseline.version_number}</div>
        <button class="help-button" onclick="toggleHelp()" title="How does this work?">?</button>
    </div>

    {help_panel}

    {scrubber}

    <div class="version-cards">
        {left_card}
        {right_card}
    </div>

    {filter_controls}

    {feature_table}

    {merge_bar}

    <script>
    function toggleHelp() {{
        const panel = document.getElementById('help-panel');
        if (!panel) return;
        panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
    }}
    function toggleUnchanged() {{
        const hidden = document.body.classList.toggle('hide-unchanged');
        const btn = document.getElementById('unchanged-toggle');
        if (btn) {{
            btn.textContent = hidden ? 'Show unchanged rows' : 'Hide unchanged rows';
        }}
    }}
    // body starts with class "hide-unchanged" so the initial click toggles to show
    </script>

    {merge_js}
</body>
</html>"""

    temp_path = tempfile.gettempdir()
    token = secrets.token_urlsafe(8)
    html_filepath = os.path.join(temp_path, f"version_merge_{token}.html")
    with open(html_filepath, "w", encoding="utf-8") as f:
        f.write(html)
    return Path(html_filepath).as_posix()
