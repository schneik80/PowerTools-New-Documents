# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

import adsk.core, adsk.fusion, adsk
import os
import re
import traceback
from datetime import datetime, timezone
from ...lib import fusionAddInUtils as futil
from .html_report import generate_history_report

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Document History"
CMD_ID = "PTND-history"
CMD_Description = "Show version history for the open document"

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

local_handlers = []

_AUTO_MILESTONE_PREFIXES = ("Milestone ", "Item Update")
_COPY_SAVE_RE    = re.compile(r"saved as latest from v(\d+)", re.IGNORECASE)
_COPY_SAVE_TS_RE = re.compile(r"saved as latest from (\d{4}-\d{2}-\d{2}T[\d.:]+Z GMT)", re.IGNORECASE)


def _parse_copy_ts(ts_str):
    try:
        dt = datetime.strptime(ts_str.strip(), "%Y-%m-%dT%H:%M:%S.%fZ GMT")
        return dt.replace(tzinfo=timezone.utc).timestamp()
    except Exception:
        return None


def start():
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )
    futil.add_handler(cmd_def.commandCreated, command_created)
    qat = ui.toolbars.itemById("QAT")
    qat.controls.addCommand(cmd_def, "save", True)


def stop():
    qat = ui.toolbars.itemById("QAT")
    command_control = qat.controls.itemById(CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)
    if command_control:
        command_control.deleteMe()
    if command_definition:
        command_definition.deleteMe()


def command_created(args: adsk.core.CommandCreatedEventArgs):
    futil.log(f"{CMD_NAME} Command Created Event")
    futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)


def command_execute(args: adsk.core.CommandEventArgs):
    try:
        doc = app.activeDocument
        if not doc.isSaved:
            ui.messageBox(
                "The active document must be saved before viewing history.",
                "Please Save", 0, 2,
            )
            return

        progress = ui.progressBar
        progress.showBusy("Document History — Loading versions...")
        adsk.doEvents()

        try:
            data = _collect_history(doc)
        finally:
            progress.hide()

        html_path = generate_history_report(data)
        app.executeTextCommand(f"QTWebBrowser.Display file:///{html_path}")

    except Exception:
        ui.messageBox("Failed:\n{}".format(traceback.format_exc()))


def _collect_history(doc):
    data_file = doc.dataFile
    versions = data_file.versions
    n = versions.count

    # Build milestone/revision map keyed by version number.
    # Revisions are milestones with short single-letter names (A, B, C...).
    # Auto-generated names like "Milestone V7" or "Item Update" are skipped.
    milestone_map = {}
    try:
        mss = data_file.milestones
        for i in range(mss.count):
            ms = mss.item(i)
            name = (ms.name or "").strip()
            if not name or any(name.startswith(p) for p in _AUTO_MILESTONE_PREFIXES):
                continue
            try:
                v_num = ms.version.versionNumber if ms.version else None
            except Exception:
                v_num = None
            if v_num is None:
                continue
            is_revision = len(name) == 1 and name.upper() in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            milestone_map[v_num] = {
                "name": name,
                "is_revision": is_revision,
                "letter": name.upper() if is_revision else None,
            }
    except Exception:
        pass

    raw = []
    for i in range(n):
        ver = versions.item(i)
        v_num = ver.versionNumber
        ms_info = milestone_map.get(v_num)

        author = ""
        try:
            if ver.lastUpdatedBy:
                author = ver.lastUpdatedBy.displayName
        except Exception:
            pass

        date_ts = None
        try:
            date_ts = ver.dateModified
        except Exception:
            pass

        description = ""
        try:
            description = (getattr(ver, "description", None) or "").strip()
        except Exception:
            pass

        raw.append({
            "number": v_num,
            "author": author,
            "date_ts": date_ts,
            "description": description,
            "is_milestone": bool(ms_info and not ms_info["is_revision"]),
            "milestone_name": ms_info["name"] if ms_info and not ms_info["is_revision"] else None,
            "is_revision": bool(ms_info and ms_info["is_revision"]),
            "revision_letter": ms_info["letter"] if ms_info else None,
        })

    version_list = sorted(raw, key=lambda v: v["number"], reverse=True)
    _compute_arc_states(version_list)

    path_parts = []
    try:
        folder = data_file.parentFolder
        while folder:
            path_parts.insert(0, folder.name)
            try:
                folder = folder.parentFolder
            except Exception:
                break
    except Exception:
        pass

    ms_count = sum(1 for v in version_list if v["is_milestone"])
    rev_count = sum(1 for v in version_list if v["is_revision"])

    is_modified = False
    try:
        is_modified = doc.isModified
    except Exception:
        pass

    return {
        "name": data_file.name,
        "path": " / ".join(path_parts),
        "total_versions": n,
        "milestone_count": ms_count,
        "revision_count": rev_count,
        "versions": version_list,
        "has_unsaved_tip": is_modified,
    }


def _compute_arc_states(version_list):
    for ver in version_list:
        ver["arc_state"] = None
        ver["is_dimmed"] = False
        ver["copy_source_version"] = None
        ver["copy_source_ts"] = None

    v_idx = {v["number"]: i for i, v in enumerate(version_list)}

    for ver in version_list:
        desc = ver.get("description") or ""

        m = _COPY_SAVE_RE.search(desc)
        if m:
            src_num = int(m.group(1))
        else:
            m_ts = _COPY_SAVE_TS_RE.search(desc)
            if not m_ts:
                continue
            target_ts = _parse_copy_ts(m_ts.group(1))
            if target_ts is None:
                continue
            # No version may exist at that exact timestamp (e.g. offline save).
            # Use the newest version whose date_ts is at or before the source time.
            bot = max(
                (v for v in version_list if v["date_ts"] and v["date_ts"] <= target_ts),
                key=lambda v: v["date_ts"],
                default=None,
            )
            if bot is None:
                continue
            src_num = bot["number"]
            ver["copy_source_ts"] = target_ts

        copy_idx = v_idx[ver["number"]]
        src_idx = v_idx.get(src_num)

        if src_idx is None or copy_idx >= src_idx:
            continue

        ver["arc_state"] = "top"
        ver["copy_source_version"] = src_num

        src_ver = version_list[src_idx]
        if src_ver["arc_state"] is None:
            src_ver["arc_state"] = "bot"

        for i in range(copy_idx + 1, src_idx):
            v = version_list[i]
            if v["arc_state"] is None:
                v["arc_state"] = "mid"
            if v["arc_state"] != "top":
                v["is_dimmed"] = True


def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers
    local_handlers = []
    futil.log(f"{CMD_NAME} Command Destroy Event")
