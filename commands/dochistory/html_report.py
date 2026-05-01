# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

import html as _html
import os
import secrets
import tempfile
from datetime import datetime
from pathlib import Path

# Row height in px — must stay in sync with .commit-row height in HTML_CSS
ROW_H = 48

# SVG graph geometry constants
_SVG_W   = 88
_LX_MAIN = 18    # x of main rail
_LX_ANN  = 46   # x of milestone / revision annotation node
_LX_ARC  = 72   # x of copy-save arc rail
_BG      = "#ffffff"   # node halo stroke — must match graph-col background
_C = {
    "rail": "#21262d",
    "node": "#58a6ff",
    "ms":   "#d29922",
    "rev":  "#a371f7",
    "arc":  "#f78166",
    "dim":  "#8b949e",
}


HTML_CSS = """<style>
    * { margin: 0; padding: 0; box-sizing: border-box; }

    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
                     Helvetica, Arial, sans-serif;
        background: #f6f8fa;
        color: #24292f;
        line-height: 1.5;
        padding: 24px;
    }

    /* ── Header ─────────────────────────────────────────── */
    .report-header {
        background: #1a1a2e;
        color: #fff;
        padding: 20px 28px;
        border-radius: 8px;
        margin-bottom: 20px;
    }
    .report-header h1 { font-size: 20px; font-weight: 600; margin-bottom: 4px; }
    .report-header .subtitle { font-size: 13px; color: #b2bec3; margin-bottom: 10px; }
    .header-stats { display: flex; gap: 20px; }
    .hstat { font-size: 12px; color: #b2bec3; }
    .hstat b { color: #fff; }

    /* ── History panel: dark graph + white content ───────── */
    .history-panel {
        display: flex;
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 1px 4px rgba(0,0,0,0.15), 0 0 0 1px rgba(0,0,0,0.08);
    }

    .graph-col {
        flex-shrink: 0;
        background: transparent;
        line-height: 0;   /* collapse whitespace around inline SVG */
    }

    .content-col {
        flex: 1;
        min-width: 0;
        background: #ffffff;
    }

    /* ── Commit rows ─────────────────────────────────────── */
    .commit-row {
        height: 48px;
        padding: 0 12px;
        border-top: 1px solid #f0f3f4;
        display: flex;
        flex-direction: column;
        justify-content: center;
        gap: 2px;
        overflow: hidden;
    }
    .commit-row:first-child { border-top: none; }
    .commit-row.dimmed { opacity: 0.5; }
    .tip-row { border-top: 1px dashed #d0d7de; }
    .tip-chip { background: #ddf4ff !important; color: #0969da !important; }

    .row-line1 {
        display: flex;
        align-items: center;
        gap: 7px;
        white-space: nowrap;
        overflow: hidden;
    }
    .row-line2 {
        display: flex;
        align-items: center;
        gap: 5px;
        overflow: hidden;
    }

    .ver-chip {
        font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
        font-size: 11px;
        font-weight: 700;
        color: #24292f;
        background: #f0f3f4;
        padding: 2px 6px;
        border-radius: 4px;
        flex-shrink: 0;
    }
    .commit-ts {
        font-size: 12px;
        color: #8b949e;
        flex-shrink: 0;
        cursor: default;
    }
    .sep { color: #d0d7de; font-size: 12px; flex-shrink: 0; }
    .commit-author {
        font-size: 12px;
        color: #57606a;
        font-weight: 500;
        flex-shrink: 0;
    }
    .commit-desc {
        font-size: 12px;
        color: #6e7781;
        font-style: italic;
        overflow: hidden;
        text-overflow: ellipsis;
        flex: 1;
    }

    /* ── Tags ────────────────────────────────────────────── */
    .tag {
        font-size: 11px;
        font-weight: 600;
        padding: 1px 8px;
        border-radius: 100px;
        white-space: nowrap;
        flex-shrink: 0;
    }
    .tag-ms {
        color: #9a6700;
        background: rgba(210,153,34,0.12);
        border: 1px solid rgba(210,153,34,0.4);
    }
    .tag-rev {
        color: #6e40c9;
        background: rgba(163,113,247,0.12);
        border: 1px solid rgba(163,113,247,0.4);
    }
    .tag-arc {
        color: #b33a2b;
        background: rgba(247,129,102,0.12);
        border: 1px solid rgba(247,129,102,0.4);
    }

    /* ── Footer ──────────────────────────────────────────── */
    .report-footer {
        margin-top: 20px;
        text-align: center;
        font-size: 11px;
        color: #8b949e;
    }
</style>"""


# ── SVG generation (Python-side, no JavaScript) ───────────────────────────────

def _ln(x1, y1, x2, y2, color, w=2):
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"'
            f' stroke="{color}" stroke-width="{w}"/>')


def _ci(cx, cy, r, fill):
    return (f'<circle cx="{cx}" cy="{cy}" r="{r}"'
            f' fill="{fill}" stroke="{_BG}" stroke-width="2"/>')


def _bz(d, color, w=2):
    return f'<path d="{d}" stroke="{color}" stroke-width="{w}" fill="none"/>'


def _co(cx, cy, r, color):
    return (f'<circle cx="{cx}" cy="{cy}" r="{r}"'
            f' fill="none" stroke="{color}" stroke-width="2"/>')


def _di(cx, cy, r, fill):
    pts = f"{cx},{cy-r} {cx+r},{cy} {cx},{cy+r} {cx-r},{cy}"
    return f'<polygon points="{pts}" fill="{fill}" stroke="{_BG}" stroke-width="2"/>'


def _tx(x, y, text, sz=9):
    return (f'<text x="{x}" y="{y}" text-anchor="middle"'
            f' dominant-baseline="central" fill="#fff"'
            f' font-size="{sz}" font-weight="bold"'
            f' font-family="system-ui,-apple-system">{text}</text>')


def _build_svg(versions):
    n     = len(versions)
    svg_h = n * ROW_H
    mx    = _LX_MAIN
    bx    = _LX_ANN
    ax    = _LX_ARC
    half  = ROW_H // 2
    ts    = half // 2   # bezier tangent scale = ROW_H / 4

    v_idx = {v["number"]: i for i, v in enumerate(versions)}
    parts = []

    # ── Pass 1: main rail ────────────────────────────────────────────────────
    for i in range(1, n):
        y0 = (i - 1) * ROW_H + half
        y1 = i * ROW_H + half
        parts.append(_ln(mx, y0, mx, y1, _C["rail"]))

    # ── Pass 2: arc bezier paths ──────────────────────────────────────────────
    for i, ver in enumerate(versions):
        if ver.get("arc_state") != "top":
            continue
        src_idx = v_idx.get(ver.get("copy_source_version"))
        if src_idx is None:
            continue

        cyt  = i * ROW_H + half
        cyb  = src_idx * ROW_H + half
        midt = cyt + half    # arc lane entry
        midb = cyb - half    # arc lane exit

        # Top S-curve: main rail → arc lane
        parts.append(_bz(
            f"M {mx} {cyt} C {mx} {cyt+ts} {ax} {midt-ts} {ax} {midt}",
            _C["arc"]
        ))
        # Straight middle section
        if midb > midt:
            parts.append(_ln(ax, midt, ax, midb, _C["arc"]))
        # Bottom S-curve: arc lane → main rail
        parts.append(_bz(
            f"M {ax} {midb} C {ax} {midb+ts} {mx} {cyb-ts} {mx} {cyb}",
            _C["arc"]
        ))
        # Lane entry/exit dots
        parts.append(_ci(ax, midt, 4, _C["arc"]))
        if midb > midt:
            parts.append(_ci(ax, midb, 4, _C["arc"]))

    # ── Pass 3: branch connector lines (drawn under nodes) ───────────────────
    for i, ver in enumerate(versions):
        if ver.get("is_dimmed"):
            continue
        if not (ver.get("is_milestone") or ver.get("is_revision")):
            continue
        cy    = i * ROW_H + half
        color = _C["rev"] if ver.get("is_revision") else _C["ms"]
        parts.append(_ln(mx, cy, bx, cy, color))

    # ── Pass 4: all nodes (drawn last — on top of everything) ────────────────
    for i, ver in enumerate(versions):
        cy = i * ROW_H + half

        if ver.get("is_tip"):
            parts.append(_co(mx, cy, 5, _C["node"]))
            continue

        if ver.get("is_dimmed"):
            node_color = _C["dim"]
        elif ver.get("arc_state") in ("top", "bot"):
            node_color = _C["arc"]
        elif ver.get("is_milestone"):
            node_color = _C["ms"]
        elif ver.get("is_revision"):
            node_color = _C["rev"]
        else:
            node_color = _C["node"]

        r = 6 if (ver.get("is_milestone") or ver.get("is_revision")) else 5
        parts.append(_ci(mx, cy, r, node_color))

        # Annotation node for milestones / revisions
        if not ver.get("is_dimmed") and (ver.get("is_milestone") or ver.get("is_revision")):
            color = _C["rev"] if ver.get("is_revision") else _C["ms"]
            if ver.get("is_revision"):
                parts.append(_ci(bx, cy, 9, color))
                parts.append(_tx(bx, cy, ver.get("revision_letter") or "?"))
            else:
                parts.append(_di(bx, cy, 8, color))

    inner = "\n".join(parts)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg"'
        f' width="{_SVG_W}" height="{svg_h}">'
        f'{inner}'
        f'</svg>'
    )


# ── Commit row HTML ───────────────────────────────────────────────────────────

def _relative_time(ts):
    if not ts:
        return "unknown"
    try:
        diff = datetime.now().timestamp() - ts
        if diff < 60:
            return "just now"
        if diff < 3600:
            m = int(diff / 60)
            return f"{m}m ago"
        if diff < 86400:
            h = int(diff / 3600)
            return f"{h}h ago"
        if diff < 7 * 86400:
            d = int(diff / 86400)
            return f"{d}d ago"
        dt = datetime.fromtimestamp(ts)
        if dt.year == datetime.now().year:
            return dt.strftime("%b %-d")
        return dt.strftime("%b %-d, %Y")
    except Exception:
        return ""


def _abs_time(ts):
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(ts).strftime("%b %-d, %Y %H:%M")
    except Exception:
        return ""


def _build_rows(versions):
    rows = []
    for ver in versions:
        if ver.get("is_tip"):
            rows.append(
                '<div class="commit-row tip-row">'
                '<div class="row-line1">'
                '<span class="ver-chip tip-chip">Now</span>'
                '<span class="commit-desc">Unsaved changes</span>'
                '</div>'
                '</div>'
            )
            continue

        is_ms    = ver["is_milestone"]
        is_rev   = ver["is_revision"]
        ms_name  = ver.get("milestone_name") or ""
        rev_lett = ver.get("revision_letter") or ""
        arc_st   = ver.get("arc_state")
        is_dim   = ver.get("is_dimmed", False)
        copy_src = ver.get("copy_source_version")
        desc     = ver.get("description") or ""

        row_cls  = "commit-row dimmed" if is_dim else "commit-row"
        ts_rel   = _relative_time(ver["date_ts"])
        ts_abs   = _abs_time(ver["date_ts"])
        author   = _html.escape(ver.get("author") or "")

        author_html = (
            f'<span class="sep">&middot;</span>'
            f'<span class="commit-author">{author}</span>'
        ) if author else ""

        is_auto_copy = arc_st == "top" and copy_src is not None
        desc_html = (
            f'<span class="sep">&middot;</span>'
            f'<span class="commit-desc">{_html.escape(desc)}</span>'
        ) if desc and not is_auto_copy else ""

        tags = []
        if is_ms and ms_name:
            tags.append(f'<span class="tag tag-ms">&#9670;&thinsp;{_html.escape(ms_name)}</span>')
        if is_rev and rev_lett:
            tags.append(f'<span class="tag tag-rev">Rev&thinsp;{rev_lett}</span>')
        if is_auto_copy:
            src_ts = ver.get("copy_source_ts")
            if src_ts:
                src_label = _abs_time(src_ts)
                tags.append(f'<span class="tag tag-arc">&#x21A9;&thinsp;from {_html.escape(src_label)}</span>')
            else:
                tags.append(f'<span class="tag tag-arc">&#x21A9;&thinsp;from v{copy_src}</span>')

        line2 = (
            f'<div class="row-line2">{"".join(tags)}</div>'
        ) if tags else ""

        rows.append(
            f'<div class="{row_cls}">'
            f'<div class="row-line1">'
            f'<span class="ver-chip">v{ver["number"]}</span>'
            f'<span class="commit-ts" title="{ts_abs}">{ts_rel}</span>'
            f'{author_html}'
            f'{desc_html}'
            f'</div>'
            f'{line2}'
            f'</div>'
        )
    return "\n".join(rows)


# ── Public entry point ────────────────────────────────────────────────────────

def generate_history_report(data):
    doc_name  = data["name"]
    path      = data.get("path") or ""
    total     = data["total_versions"]
    ms_count  = data.get("milestone_count", 0)
    rev_count = data.get("revision_count", 0)
    versions  = data["versions"]

    if data.get("has_unsaved_tip"):
        versions = [{
            "number": None, "author": "", "date_ts": None, "description": "",
            "is_milestone": False, "is_revision": False,
            "milestone_name": None, "revision_letter": None,
            "arc_state": None, "is_dimmed": False, "copy_source_version": None,
            "is_tip": True,
        }] + versions

    subtitle_path = f"&ensp;&middot;&ensp;{path}" if path else ""
    ms_stat = (
        f'<span class="hstat"><b>{ms_count}</b> '
        f'milestone{"s" if ms_count != 1 else ""}</span>'
    ) if ms_count else ""
    rev_stat = (
        f'<span class="hstat"><b>{rev_count}</b> '
        f'revision{"s" if rev_count != 1 else ""}</span>'
    ) if rev_count else ""

    svg_html  = _build_svg(versions)
    rows_html = _build_rows(versions)

    html_out = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{_html.escape(doc_name)} &mdash; Document History</title>
    {HTML_CSS}
</head>
<body>
    <div class="report-header">
        <h1>{_html.escape(doc_name)}</h1>
        <div class="subtitle">Document History{subtitle_path}</div>
        <div class="header-stats">
            <span class="hstat"><b>{total}</b> version{"s" if total != 1 else ""}</span>
            {ms_stat}
            {rev_stat}
        </div>
    </div>

    <div class="history-panel">
        <div class="graph-col">{svg_html}</div>
        <div class="content-col">
{rows_html}
        </div>
    </div>

    <div class="report-footer">
        Power Tools Document History &middot; IMA LLC
    </div>
</body>
</html>"""

    temp_path     = tempfile.gettempdir()
    report_name   = secrets.token_urlsafe(8)
    html_filepath = os.path.join(temp_path, f"doc_history_{report_name}.html")

    with open(html_filepath, "w", encoding="utf-8") as f:
        f.write(html_out)

    return Path(html_filepath).as_posix()
