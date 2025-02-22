import adsk.core
import adsk.fusion
import adsk.cam
import adsk.drawing
import os
import json
import pathlib
import traceback
from ...lib import fusionAddInUtils as futil
from ... import config

CMD_NAME = "New Document"
CMD_ID = "PTND-new"
CMD_Description = "Create new Document"
IS_PROMOTED = False

# Global variables by referencing values from /config.py
WORKSPACE_ID = config.design_workspace
TAB_ID = config.tools_tab_id
TAB_NAME = config.my_tab_name

PANEL_ID = config.my_panel_id
PANEL_NAME = config.my_panel_name
PANEL_AFTER = config.my_panel_after


# Holds references to event handlers
local_handlers = []
app = adsk.core.Application.get()
ui = app.userInterface

# Resource location for command icons, here we assume a sub folder in this directory named "resources".
Theme = app.preferences.generalPreferences.userInterfaceTheme

if Theme == 2:
    HTML_PAGE = "index-d.html"
else:
    HTML_PAGE = "index-l.html"

# Resource location for command icons, here we assume a sub folder in this directory named "resources".
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

# Pallet
PALETTE_NAME = CMD_NAME
PALETTE_ID = f"{config.COMPANY_NAME}_{config.ADDIN_NAME}_palette_id"
PALETTE_URL = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "resources", HTML_PAGE
)
PALETTE_URL = PALETTE_URL.replace(
    "\\", "/"
)  # The path function builds a valid OS path. This fixes it to be a valid local URL.
PALETTE_DOCKING = (
    adsk.core.PaletteDockingStates.PaletteDockStateRight
)  # Set a default docking behavior for the palette


# Get the paths dictionary from the app
## ****** Document MAP ****** ##
PATHS_DICT = json.loads(app.executeTextCommand("paths.get"))
app_path = os.path.dirname(os.path.abspath(__file__))

# get the pictionary for new document types. Ensure HTML file has the same keys
newDocsDict = {
    "mm-Assembly": [
        "mm-Assembly",
        os.path.normpath(os.path.join(app_path, "resources/docs/mm/mm-Assembly.f3d")),
    ],
    "mm-Legacy": [
        "mm-Assembly",
        os.path.normpath(os.path.join(app_path, "resources/docs/mm/mm-Legacy.f3d")),
    ],
    "mm-Part": [
        "mm-Part",
        os.path.normpath(os.path.join(app_path, "resources/docs/mm/mm-Part.f3d")),
    ],
    "mm-Sheetmetal": [
        "mm-Sheetmetal",
        os.path.normpath(os.path.join(app_path, "resources/docs/mm/mm-Sheetmetal.f3d")),
    ],
    "mm-Plastic": [
        "mm-Plastic",
        os.path.normpath(os.path.join(app_path, "resources/docs/mm/mm-Plastic.f3d")),
    ],
    "mm-Direct": [
        "mm-Direct",
        os.path.normpath(os.path.join(app_path, "resources/docs/mm/mm-Direct.f3d")),
    ],
    "in-Assembly": [
        "in-Assembly",
        os.path.normpath(os.path.join(app_path, "resources/docs/in/in-Assembly.f3d")),
    ],
    "in-Legacy": [
        "in-Assembly",
        os.path.normpath(os.path.join(app_path, "resources/docs/in/in-Legacy.f3d")),
    ],
    "in-Part": [
        "in-Part",
        os.path.normpath(os.path.join(app_path, "resources/docs/in/in-Part.f3d")),
    ],
    "in-Sheetmetal": [
        "in-Sheetmetal",
        os.path.normpath(os.path.join(app_path, "resources/docs/in/in-Sheetmetal.f3d")),
    ],
    "in-Plastic": [
        "in-Plastic",
        os.path.normpath(os.path.join(app_path, "resources/docs/in/in-Plastic.f3d")),
    ],
    "in-Direct": [
        "in-Direct",
        os.path.normpath(os.path.join(app_path, "resources/docs/in/in-Direct.f3d")),
    ],
}


# Executed when add-in is run.
def start():
    """
    Executed when add-in is run. Creates the command definition and control.
    """
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )

    # Add command created handler. The function passed here will be executed when the command is executed.
    futil.add_handler(cmd_def.commandCreated, command_created)
    # Get target workspace for the command.
    qat = ui.toolbars.itemById("QAT")

    # Create the command control, i.e. a button in the UI.
    control = qat.controls.addCommand(cmd_def, "FileSubMenuCommand", False)

    futil.add_handler(app.documentOpened, get_type)
    futil.add_handler(app.documentActivated, get_type)
    futil.add_handler(app.documentCreated, get_type)
    # futil.add_handler(app., get_type)


# Executed when add-in is stopped.
def stop():
    """
    Executed when add-in is stopped. Deletes the command control, definition, and palette.
    """
    # Get the various UI elements for this command
    qat = ui.toolbars.itemById("QAT")
    command_control = qat.controls.itemById(CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)
    palette = ui.palettes.itemById(PALETTE_ID)

    # Delete the button command control
    if command_control:
        command_control.deleteMe()

    # Delete the command definition
    if command_definition:
        command_definition.deleteMe()

    # Delete the Palette
    if palette:
        palette.deleteMe()


# Event handler that is called when the user clicks the command button in the UI.
# To have a dialog, you create the desired command inputs here. If you don't need
# a dialog, don't create any inputs and the execute event will be immediately fired.
# You also need to connect to any command related events here.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    """
    Executed when command is created.
    """
    # General logging for debug.
    futil.log(f"{CMD_NAME}: Command created event.")

    # Create the event handlers you will need for this instance of the command
    futil.add_handler(
        args.command.execute, command_execute, local_handlers=local_handlers
    )
    futil.add_handler(
        args.command.destroy, command_destroy, local_handlers=local_handlers
    )


def get_type(args):
    design = adsk.fusion.Design.cast(app.activeProduct)

    attributes = design.findAttributes("litetype", "componenttype")

    if not attributes:
        try:

            design_workspace = ui.workspaces.itemById("FusionSolidEnvironment")

            alltbs = [
                "ASMTab",
                "SolidTab",
                "SurfaceTab",
                "SheetMetalTab",
                "ParaMeshOuterTab",
                "PlasticTab",
                "ManageTab",
                "PCBsTab",
            ]

            for i in alltbs:
                tabs = design_workspace.toolbarTabs.itemById(i)
                if tabs:
                    tabs.isVisible = True

        except:
            futil.log(f"{CMD_NAME}: failed to get attribute")

    for attribute in attributes:
        futil.log(f"{CMD_NAME}: {attribute.name} = {attribute.value}")

        if attribute.value == "assembly":
            try:
                design_workspace = ui.workspaces.itemById("FusionSolidEnvironment")

                alltbs = [
                    "ASMTab",
                    "SolidTab",
                    "SurfaceTab",
                    "SheetMetalTab",
                    "ParaMeshOuterTab",
                    "PlasticTab",
                    "ManageTab",
                    "PCBsTab",
                ]

                for i in alltbs:
                    tabs = design_workspace.toolbarTabs.itemById(i)
                    if tabs:
                        tabs.isVisible = True

                asmtb = [
                    "SolidTab",
                    "SurfaceTab",
                    "SheetMetalTab",
                    "ParaMeshOuterTab",
                    "PlasticTab",
                    "ManageTab",
                    "PCBsTab",
                ]

                for i in asmtb:
                    tabs = design_workspace.toolbarTabs.itemById(i)
                    if tabs:
                        tabs.isVisible = False
            except:
                futil.log(f"{CMD_NAME}: failed to get attribute")

        if attribute.value == "part":
            try:
                design_workspace = ui.workspaces.itemById("FusionSolidEnvironment")

                alltbs = [
                    "ASMTab",
                    "SolidTab",
                    "SurfaceTab",
                    "SheetMetalTab",
                    "ParaMeshOuterTab",
                    "PlasticTab",
                    "ManageTab",
                    "PCBsTab",
                ]

                for i in alltbs:
                    tabs = design_workspace.toolbarTabs.itemById(i)
                    if tabs:
                        tabs.isVisible = True

                prttb = [
                    "ASMTab",
                    "SheetMetalTab",
                    "ParaMeshOuterTab",
                    "PlasticTab",
                    "ManageTab",
                    "PCBsTab",
                ]

                for i in prttb:
                    tabs = design_workspace.toolbarTabs.itemById(i)
                    if tabs:
                        tabs.isVisible = False
            except:
                futil.log(f"{CMD_NAME}: failed to get attribute")

        if attribute.value == "sheetmetal":
            try:

                design_workspace = ui.workspaces.itemById("FusionSolidEnvironment")

                alltbs = [
                    "ASMTab",
                    "SolidTab",
                    "SurfaceTab",
                    "SheetMetalTab",
                    "ParaMeshOuterTab",
                    "PlasticTab",
                    "ManageTab",
                    "PCBsTab",
                ]

                for i in alltbs:
                    tabs = design_workspace.toolbarTabs.itemById(i)
                    if tabs:
                        tabs.isVisible = True

                smttb = [
                    "ASMTab",
                    "SolidTab",
                    "SurfaceTab",
                    "ParaMeshOuterTab",
                    "PlasticTab",
                    "ManageTab",
                    "PCBsTab",
                ]

                for i in smttb:
                    tabs = design_workspace.toolbarTabs.itemById(i)
                    if tabs:
                        tabs.isVisible = False
            except:
                futil.log(f"{CMD_NAME}: failed to get attribute")

        if attribute.value == "plastic":
            try:

                design_workspace = ui.workspaces.itemById("FusionSolidEnvironment")

                alltbs = [
                    "ASMTab",
                    "SolidTab",
                    "SurfaceTab",
                    "SheetMetalTab",
                    "ParaMeshOuterTab",
                    "PlasticTab",
                    "ManageTab",
                    "PCBsTab",
                ]

                for i in alltbs:
                    tabs = design_workspace.toolbarTabs.itemById(i)
                    if tabs:
                        tabs.isVisible = True

                smttb = [
                    "ASMTab",
                    "SolidTab",
                    "SurfaceTab",
                    "SheetMetalTab",
                    "ParaMeshOuterTab",
                    "ManageTab",
                    "PCBsTab",
                ]

                for i in smttb:
                    tabs = design_workspace.toolbarTabs.itemById(i)
                    if tabs:
                        tabs.isVisible = False
            except:
                futil.log(f"{CMD_NAME}: failed to get attribute")

        if attribute.value == "direct" or attribute.value == "legacy":
            try:

                design_workspace = ui.workspaces.itemById("FusionSolidEnvironment")

                alltbs = [
                    "ASMTab",
                    "SolidTab",
                    "SurfaceTab",
                    "SheetMetalTab",
                    "ParaMeshOuterTab",
                    "PlasticTab",
                    "ManageTab",
                    "PCBsTab",
                ]

                for i in alltbs:
                    tabs = design_workspace.toolbarTabs.itemById(i)
                    if tabs:
                        tabs.isVisible = True

            except:
                futil.log(f"{CMD_NAME}: failed to get attribute")

    futil.log(f"{CMD_NAME}: ===== {app.activeDocument.name}Doc opened. =====")


# Because no command inputs are being added in the command created event, the execute
# event is immediately fired.
def command_execute(args: adsk.core.CommandEventArgs):
    """
    Executes the command. This function is called when the command is executed.

    Args:
        args (adsk.core.CommandEventArgs): The arguments for the command event.
    """
    global palette
    # General logging for debug.
    if ui is None:
        futil.log(f"{CMD_NAME}: User interface is not available.")
        return

    palettes = ui.palettes
    palette = palettes.itemById(PALETTE_ID)

    palette = palettes.itemById(PALETTE_ID)
    if palette is None:
        palette = palettes.add(
            id=PALETTE_ID,
            name=PALETTE_NAME,
            htmlFileURL=PALETTE_URL,
            isVisible=False,
            showCloseButton=True,
            isResizable=True,
            width=450,
            height=600,
            useNewWebBrowser=True,
        )
        futil.add_handler(palette.closed, palette_closed)
        futil.add_handler(palette.navigatingURL, palette_navigating)
        futil.add_handler(palette.incomingFromHTML, palette_incoming)
        futil.log(
            f"{CMD_NAME}: Created a new palette: ID = {palette.id}, Name = {palette.name}"
        )
    else:
        palette.isVisible = True

    if palette.dockingState == adsk.core.PaletteDockingStates.PaletteDockStateFloating:
        palette.dockingState = PALETTE_DOCKING
        palette.isVisible = True


# Use this to handle a user closing your palette.
def palette_closed(args: adsk.core.UserInterfaceGeneralEventArgs):
    """
    Handles the event when the user closes the palette.

    Args:
        args (adsk.core.UserInterfaceGeneralEventArgs): The arguments for the event.
    """
    # General logging for debug.
    futil.log(f"{CMD_NAME}: Palette was closed.")


# Use this to handle a user navigating to a new page in your palette.
def palette_navigating(args: adsk.core.NavigationEventArgs):
    """
    Handles the event when the user navigates to a new page in the palette.

    Args:
        args (adsk.core.NavigationEventArgs): The arguments for the event.
    """
    # General logging for debug.
    futil.log(f"{CMD_NAME}: Palette navigating event.")

    # Get the URL the user is navigating to:
    url = args.navigationURL

    log_msg = f"User is attempting to navigate to {url}\n"
    futil.log(log_msg, adsk.core.LogLevels.InfoLogLevel)

    # Check if url is an external site and open in user's default browser.
    if url.startswith("http"):
        args.launchExternally = True


# Use this to handle events sent from javascript in your palette.
def palette_incoming(html_args: adsk.core.HTMLEventArgs):
    """
    Handles events sent from JavaScript in the palette.

    Args:
        html_args (adsk.core.HTMLEventArgs): Passed from HTML json to Fusion events.
    """
    global palette

    importManager = app.importManager
    message_data: dict = json.loads(html_args.data)
    message_action = html_args.action

    # General logging for debug.
    futil.log(f"{CMD_NAME}: Palette incoming event.")
    log_msg = f"Event received from {html_args.firingEvent.sender.name}\n"
    log_msg += f"Action: {message_action}\n"
    log_msg += f"Data: {message_data}"
    futil.log(log_msg, adsk.core.LogLevels.InfoLogLevel)

    palette.isVisible = False

    ui.progressBar.showBusy("Creating new document...")

    link = message_data["link"]
    if link == "ecad-LBR":
        cmdDefs = ui.commandDefinitions
        fuscommand = cmdDefs.itemById("NewElectronLbrDocumentCommand")
        fuscommand.execute()
        return
    if link == "ecad-Project":
        cmdDefs = ui.commandDefinitions
        fuscommand = cmdDefs.itemById("NewElectronDesignDocumentCommand")
        fuscommand.execute()
        return
    if link in newDocsDict:
        filePath = newDocsDict[link][1]
        importOptions = importManager.createFusionArchiveImportOptions(filePath)
        importOptions.isViewFit = False
        importManager.importToNewDocument(importOptions)
        return
    futil.log(f"Link '{link}' not found in Document map")
    ui.progressBar.hide()


# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    """
    Handles the event when the command terminates.

    Args:
        args (adsk.core.CommandEventArgs): The arguments for the event.
    """
    # General logging for debug.
    futil.log(f"{CMD_NAME}: Command destroy event.")

    global local_handlers
    local_handlers = []
