# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

import adsk.core
import os
import os.path
import json
from .lib import fusionAddInUtils as futil

DEBUG = True
ADDIN_NAME = os.path.basename(os.path.dirname(__file__))
COMPANY_NAME = "IMA LLC"


design_workspace = "FusionSolidEnvironment"
tools_tab_id = "ToolsTab"
my_tab_name = "Power Tools"

my_panel_id = f"PT_{my_tab_name}"
my_panel_name = "Power Tools"
my_panel_after = ""

# ---------------------------------------------------------------------------
# Shared cache / settings paths
# ---------------------------------------------------------------------------

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
SETTINGS_FILE = os.path.join(CACHE_DIR, "settings.json")


def load_settings() -> dict:
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_settings(settings: dict) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)


# ---------------------------------------------------------------------------
# Shared PowerTools Settings dropdown in the QAT file menu
# ---------------------------------------------------------------------------

PT_SETTINGS_DROPDOWN_ID = "PT-settings-dropdown"
PT_SETTINGS_DROPDOWN_NAME = "PowerTools Settings"


def get_or_create_pt_settings_dropdown():
    """Return the PowerTools Settings dropdown in the QAT file menu, creating it if absent."""
    app = adsk.core.Application.get()
    ui = app.userInterface
    qat = ui.toolbars.itemById("QAT")
    if not qat:
        return None
    file_dropdown = qat.controls.itemById("FileSubMenuCommand")
    if not file_dropdown:
        return None

    dropdown = file_dropdown.controls.itemById(PT_SETTINGS_DROPDOWN_ID)
    if not dropdown:
        dropdown = file_dropdown.controls.addDropDown(
            PT_SETTINGS_DROPDOWN_NAME, "", PT_SETTINGS_DROPDOWN_ID
        )
    return dropdown


def remove_from_pt_settings_dropdown(control_id: str) -> None:
    """Remove *control_id* from the PowerTools Settings dropdown.

    Deletes the dropdown itself when no children remain, so the last
    command to unregister cleans up automatically.
    """
    app = adsk.core.Application.get()
    ui = app.userInterface
    qat = ui.toolbars.itemById("QAT")
    if not qat:
        return
    file_dropdown = qat.controls.itemById("FileSubMenuCommand")
    if not file_dropdown:
        return

    dropdown = file_dropdown.controls.itemById(PT_SETTINGS_DROPDOWN_ID)
    if not dropdown:
        return

    ctrl = dropdown.controls.itemById(control_id)
    if ctrl:
        ctrl.deleteMe()

    if dropdown.controls.count == 0:
        dropdown.deleteMe()
