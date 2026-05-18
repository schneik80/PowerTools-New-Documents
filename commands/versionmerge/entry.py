# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

"""Version Merge command — pick a prior version and selectively merge
parameter changes back into the active document.

Reuses the diff computation pipeline from versiondiff, but renders the
results into an interactive Fusion HTML Palette so the user can choose
which changes to apply.
"""

import base64
import os
import secrets
import tempfile
import traceback
from datetime import datetime

import adsk.core
import adsk.fusion

from ...lib import fusionAddInUtils as futil
from ... import config
from ..versiondiff.design_properties import extract_design_properties
from ..versiondiff.param_fingerprint import (
    extract_feature_params, attach_params_to_features,
)
from ..versiondiff.timeline_diff import (
    walk_timeline, get_version_info, compute_diff,
)
from ..versiondiff.timeline_model import DiffResult
from . import palette as merge_palette
from .history import build_histories
from .html_merge_report import generate_merge_html

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Version Merge"
CMD_ID = "PTND-versionmerge"
CMD_Description = (
    "Pick a prior version and selectively merge changes back into the active document"
)
IS_PROMOTED = True

WORKSPACE_ID = config.design_workspace
TAB_ID = config.tools_tab_id
TAB_NAME = config.my_tab_name
PANEL_ID = config.my_panel_id
PANEL_NAME = config.my_panel_name
PANEL_AFTER = config.my_panel_after

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

local_handlers: list = []
_version_map: dict = {}


def _safe_user(data_file_or_version) -> str:
    """Defensively read ``.lastUpdatedBy.displayName`` from a DataFile.

    Fusion's DataFile properties can transiently throw InternalValidationError
    when hub metadata isn't fully loaded; return an empty string on failure
    so the dialog still opens.
    """
    try:
        user = data_file_or_version.lastUpdatedBy
        return user.displayName if user else ""
    except Exception as exc:
        futil.log(f"{CMD_NAME}: lastUpdatedBy unavailable: {exc}")
        return ""


def _safe_date(data_file_or_version, fmt: str) -> str:
    try:
        d = data_file_or_version.dateModified
        if d:
            return datetime.fromtimestamp(d).strftime(fmt)
    except Exception as exc:
        futil.log(f"{CMD_NAME}: dateModified unavailable: {exc}")
    return ""


def _safe_str(getter, default: str = "") -> str:
    try:
        v = getter()
        return v if v is not None else default
    except Exception:
        return default


def _capture_viewport_thumbnail() -> str:
    """Reset the active viewport to home view and save it as a transparent PNG.

    Returns the base64-encoded bytes, or "" on failure (in which case the
    caller falls back to whatever ``data_file.thumbnail`` produced).
    """
    try:
        viewport = app.activeViewport
        if viewport is None:
            return ""

        # Re-orient to the design's home view so every captured frame has
        # the same framing. False = no smooth transition (instant jump).
        try:
            viewport.goHome(False)
        except TypeError:
            # Older API signature with no boolean parameter.
            viewport.goHome()
        try:
            viewport.fit()
        except Exception:
            pass
        viewport.refresh()
        adsk.doEvents()

        png_path = os.path.join(
            tempfile.gettempdir(),
            f"vmerge_thumb_{secrets.token_urlsafe(6)}.png",
        )

        try:
            options = adsk.core.SaveImageFileOptions.create(png_path)
            options.width = 400
            options.height = 300
            options.isAntiAliased = True
            options.isBackgroundTransparent = True
            ok = viewport.saveAsImageFileWithOptions(options)
        except (AttributeError, RuntimeError) as exc:
            # Fall back to the older API if SaveImageFileOptions isn't
            # available — no transparency in that case.
            futil.log(
                f"{CMD_NAME}: saveAsImageFileWithOptions unavailable "
                f"({exc}); falling back to opaque capture."
            )
            ok = viewport.saveAsImageFile(png_path, 400, 300)

        if not ok or not os.path.exists(png_path):
            return ""

        with open(png_path, "rb") as fh:
            data = fh.read()
        try:
            os.remove(png_path)
        except Exception:
            pass
        return base64.b64encode(data).decode("ascii")
    except Exception as exc:
        futil.log(f"{CMD_NAME}: viewport thumbnail capture failed: {exc}")
        return ""


def start() -> None:
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )
    futil.add_handler(cmd_def.commandCreated, command_created)

    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    if not workspace:
        futil.log(f"Warning: Workspace {WORKSPACE_ID} not found")
        return

    toolbar_tab = workspace.toolbarTabs.itemById(TAB_ID)
    if toolbar_tab is None:
        toolbar_tab = workspace.toolbarTabs.add(TAB_ID, TAB_NAME)

    panel = toolbar_tab.toolbarPanels.itemById(PANEL_ID)
    if panel is None:
        panel = toolbar_tab.toolbarPanels.add(PANEL_ID, PANEL_NAME, PANEL_AFTER, False)

    control = panel.controls.addCommand(cmd_def)
    control.isPromoted = IS_PROMOTED

    futil.log(f"{CMD_NAME} command started successfully")


def stop() -> None:
    try:
        merge_palette.dispose()

        workspace = ui.workspaces.itemById(WORKSPACE_ID)
        if not workspace:
            return

        panel = workspace.toolbarPanels.itemById(PANEL_ID)
        toolbar_tab = workspace.toolbarTabs.itemById(TAB_ID)
        command_control = panel.controls.itemById(CMD_ID) if panel else None
        command_definition = ui.commandDefinitions.itemById(CMD_ID)

        if command_control:
            command_control.deleteMe()
        if command_definition:
            command_definition.deleteMe()
        if panel and panel.controls.count == 0:
            panel.deleteMe()
        if toolbar_tab and toolbar_tab.toolbarPanels.count == 0:
            toolbar_tab.deleteMe()

        futil.log(f"{CMD_NAME} command stopped successfully")

    except Exception as e:
        futil.log(f"Error stopping {CMD_NAME}: {e}")


def command_created(args: adsk.core.CommandCreatedEventArgs) -> None:
    global _version_map
    _version_map = {}

    futil.log(f"{CMD_NAME} Command Created Event")

    try:
        if not app.activeDocument.isSaved:
            ui.messageBox(
                "The active document must be saved before you can merge versions.",
                "Document Not Saved", 0, 2,
            )
            args.command.doExecute(True)
            return

        product = app.activeProduct
        design = adsk.fusion.Design.cast(product)
        if not design:
            ui.messageBox(
                "Version Merge requires an active Fusion 3D design.",
                "No Design Found", 0, 2,
            )
            args.command.doExecute(True)
            return

        if design.designType == adsk.fusion.DesignTypes.DirectDesignType:
            ui.messageBox(
                "Version Merge requires a parametric (timeline) design.",
                "Direct Design Not Supported", 0, 2,
            )
            args.command.doExecute(True)
            return

        data_file = app.activeDocument.dataFile
        versions = data_file.versions
        if versions.count < 2:
            ui.messageBox(
                "This document has only one version.\n"
                "Save at least one more version before merging.",
                "Insufficient Versions", 0, 2,
            )
            args.command.doExecute(True)
            return

        progress = ui.progressBar
        progress.showBusy(f"{CMD_NAME} — Loading version history...")
        adsk.doEvents()

        try:
            cmd = args.command
            inputs = cmd.commandInputs

            # Current version info
            info_group = inputs.addGroupCommandInput("current_version_info", "Current Version")
            info_group.isEnabledCheckBoxDisplayed = False
            info_group.isExpanded = True
            group_inputs = info_group.children

            version_num = data_file.versionNumber
            date_str = _safe_date(data_file, "%Y-%m-%d %H:%M:%S")
            updated_by = _safe_user(data_file)
            description = _safe_str(lambda: data_file.description, "") or "(no description)"
            latest_version_number = _safe_str(
                lambda: str(data_file.latestVersionNumber), str(version_num)
            )

            group_inputs.addTextBoxCommandInput(
                "info_version", "Version",
                f"<b>Version {version_num}</b> of {latest_version_number}",
                1, True,
            )
            group_inputs.addTextBoxCommandInput("info_date", "Date Saved", date_str, 1, True)
            group_inputs.addTextBoxCommandInput("info_user", "Saved By", updated_by, 1, True)
            group_inputs.addTextBoxCommandInput("info_desc", "Description", description, 1, True)

            # Comparison version dropdown — only versions older than current make sense
            # as "merge from" sources for phase 1.
            dropdown = inputs.addDropDownCommandInput(
                "compare_version",
                "Merge Changes From Version",
                adsk.core.DropDownStyles.TextListDropDownStyle,
            )

            current_version_num = data_file.versionNumber
            version_list = []
            for i in range(versions.count):
                ver = versions.item(i)
                # Phase 1: only older versions are valid merge sources.
                # The aligned-row layout always puts the comparison on
                # the "older" side; selecting a newer version would
                # invert the revert semantics.
                if ver.versionNumber >= current_version_num:
                    continue
                version_list.append(ver)

            if not version_list:
                ui.messageBox(
                    "There are no older versions to merge from.",
                    "No Older Versions", 0, 2,
                )
                args.command.doExecute(True)
                return

            version_list.sort(key=lambda v: v.versionNumber, reverse=True)

            is_first = True
            for ver in version_list:
                ver_date = _safe_date(ver, "%Y-%m-%d %H:%M")
                ver_user = _safe_user(ver)
                label = f"V{ver.versionNumber} - {ver_date} - {ver_user}"
                dropdown.listItems.add(label, is_first)
                _version_map[label] = ver
                is_first = False

        finally:
            progress.hide()

        futil.add_handler(cmd.execute, command_execute, local_handlers=local_handlers)
        futil.add_handler(cmd.destroy, command_destroy, local_handlers=local_handlers)

    except Exception as e:
        futil.log(f"Error in command_created: {e}\n{traceback.format_exc()}")
        ui.messageBox(f"Failed to initialize {CMD_NAME}:\n{e}")


def command_execute(args: adsk.core.CommandEventArgs) -> None:
    open_doc = None

    try:
        cmd_inputs = args.command.commandInputs
        dropdown = cmd_inputs.itemById("compare_version")
        selected_label = dropdown.selectedItem.name
        compare_data_file = _version_map.get(selected_label)
        if not compare_data_file:
            ui.messageBox("Could not resolve the selected version.", CMD_NAME, 0, 3)
            return

        product = app.activeProduct
        design = adsk.fusion.Design.cast(product)

        baseline_features = walk_timeline(design.timeline)
        attach_params_to_features(baseline_features, extract_feature_params(design))
        baseline_info = get_version_info(app.activeDocument.dataFile)
        baseline_properties = extract_design_properties(design)
        baseline_v = baseline_info.version_number
        compare_v = compare_data_file.versionNumber

        # Capture the baseline's viewport now (before we switch docs) for the
        # scrubber strip and the "Newer (Current)" card.
        fresh_baseline_thumb = _capture_viewport_thumbnail()
        if fresh_baseline_thumb:
            baseline_info.thumbnail_b64 = fresh_baseline_thumb

        futil.log(
            f"{CMD_NAME} baseline: V{baseline_v}, "
            f"{len(baseline_features)} timeline features"
        )

        # Build the list of versions to walk: everything from compare up to
        # (but not including) baseline. baseline is already walked above.
        data_file = app.activeDocument.dataFile
        versions_to_walk = []
        for i in range(data_file.versions.count):
            ver = data_file.versions.item(i)
            if compare_v <= ver.versionNumber < baseline_v:
                versions_to_walk.append(ver)
        versions_to_walk.sort(key=lambda v: v.versionNumber)

        # Safety cap — walking many versions opens N documents sequentially.
        # Confirm before doing anything expensive.
        WALK_WARNING_THRESHOLD = 15
        if len(versions_to_walk) > WALK_WARNING_THRESHOLD:
            result = ui.messageBox(
                f"Picking V{compare_v} requires walking {len(versions_to_walk)} versions "
                f"of this document.\n\n"
                f"Each version is opened, scanned for changes, and closed — this can take "
                f"several seconds per version. Estimated time: ~"
                f"{len(versions_to_walk) * 4} seconds.\n\n"
                f"Continue?",
                f"{CMD_NAME} — Many Versions",
                adsk.core.MessageBoxButtonTypes.OKCancelButtonType,
                adsk.core.MessageBoxIconTypes.WarningIconType,
            )
            if result != adsk.core.DialogResults.DialogOK:
                futil.log(f"{CMD_NAME}: user cancelled walk of {len(versions_to_walk)} versions")
                return

        per_version_features = {baseline_v: baseline_features}
        intermediate_infos = []
        compare_info = None
        compare_properties = None

        progress = ui.progressBar
        progress.showBusy(f"{CMD_NAME} — walking {len(versions_to_walk)} version(s)...")
        adsk.doEvents()

        for idx, ver_df in enumerate(versions_to_walk):
            label = (
                "comparison" if ver_df.versionNumber == compare_v
                else f"intermediate {idx}/{len(versions_to_walk) - 1}"
            )
            progress.message = f"{CMD_NAME} — opening V{ver_df.versionNumber} ({label})..."
            adsk.doEvents()

            opened = app.documents.open(ver_df, True)
            if not opened:
                progress.hide()
                ui.messageBox(
                    f"Failed to open V{ver_df.versionNumber}.", CMD_NAME, 0, 3,
                )
                return

            open_doc = opened
            try:
                v_product = opened.products.itemByProductType("DesignProductType")
                v_design = adsk.fusion.Design.cast(v_product)
                if not v_design:
                    raise RuntimeError(
                        f"V{ver_df.versionNumber} does not contain a valid design"
                    )

                v_features = walk_timeline(v_design.timeline)
                attach_params_to_features(v_features, extract_feature_params(v_design))
                per_version_features[ver_df.versionNumber] = v_features

                v_info = get_version_info(ver_df)

                # Capture a fresh viewport thumb for every walked version so
                # the scrubber strip has a frame to show.
                fresh_thumb = _capture_viewport_thumbnail()
                if fresh_thumb:
                    v_info.thumbnail_b64 = fresh_thumb

                if ver_df.versionNumber == compare_v:
                    compare_info = v_info
                    compare_properties = extract_design_properties(v_design)
                else:
                    intermediate_infos.append(v_info)
            finally:
                try:
                    opened.close(False)
                except Exception:
                    pass
                open_doc = None

        progress.hide()

        if compare_info is None:
            ui.messageBox(
                f"Could not find V{compare_v} in this document's version list.",
                CMD_NAME, 0, 3,
            )
            return

        compare_features = per_version_features[compare_v]
        diff_entries, aligned_rows, summary = compute_diff(baseline_features, compare_features)

        feature_histories = build_histories(per_version_features, compare_v, baseline_v)

        older_is_comparison = compare_info.version_number < baseline_info.version_number

        diff_result = DiffResult(
            baseline=baseline_info,
            comparison=compare_info,
            features=diff_entries,
            aligned_rows=aligned_rows,
            summary=summary,
            older_is_comparison=older_is_comparison,
            baseline_properties=baseline_properties,
            comparison_properties=compare_properties,
            feature_histories=feature_histories,
            intermediate_versions=intermediate_infos,
        )

        html_path = generate_merge_html(diff_result)
        futil.log(f"Version Merge HTML saved to: {html_path}")

        # Capture a structural fingerprint of the design as the user sees
        # it now; the apply handler will warn if it has drifted by the
        # time the user clicks Apply.
        merge_palette.set_baseline_signature(
            merge_palette.compute_design_signature(design, app.activeDocument)
        )

        merge_palette.show_palette(f"file:///{html_path}")

        total_events = sum(len(h.events) for h in feature_histories.values())
        futil.log(
            f"{CMD_NAME} ready: walked {len(versions_to_walk)} version(s), "
            f"{len(feature_histories)} feature histories, {total_events} edit events"
        )

    except Exception as e:
        futil.log(f"{CMD_NAME} failed: {e}\n{traceback.format_exc()}")
        ui.messageBox(f"{CMD_NAME} failed:\n{e}", CMD_NAME, 0, 3)

    finally:
        if open_doc:
            try:
                open_doc.close(False)
            except Exception:
                pass


def command_destroy(args: adsk.core.CommandEventArgs) -> None:
    global local_handlers, _version_map
    local_handlers = []
    _version_map = {}
    futil.log(f"{CMD_NAME} Command Destroy Event")
