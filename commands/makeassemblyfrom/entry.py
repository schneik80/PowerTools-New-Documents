import adsk.core, adsk.fusion
import os, traceback
import pathlib
from ...lib import fusionAddInUtils as futil
from ... import config

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Make Assembly from Part"
CMD_ID = "PTND-assemblyfrom"
CMD_Description = "Create a new assembly referencing the active document. Active document must be a 3D design. The assembly will open as an usaved document in a new tab with a default name and cane be renamed a time of first save."

# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []


# Executed when add-in is run.
def start():
    # ******************************** Create Command Definition ********************************
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description
    )

    # Define an event handler for the command created event. It will be called when the button is clicked.
    futil.add_handler(cmd_def.commandCreated, command_created)

    # **************** Add a button into the UI so the user can run the command. ****************
    # Get the target workspace the button will be created in.

    qat = ui.toolbars.itemById("QAT")

    # Get the drop-down that contains the file related commands.
    fileDropDown = qat.controls.itemById("FileSubMenuCommand")

    # Add a new button after the Export control.
    control = fileDropDown.controls.addCommand(
        cmd_def, "PLM360SaveAsLatestOnQATCommand", False
    )


# Executed when add-in is stopped.
def stop():
    # Get the various UI elements for this command
    qat = ui.toolbars.itemById("QAT")
    fileDropDown = qat.controls.itemById("FileSubMenuCommand")
    command_control = fileDropDown.controls.itemById(CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)

    # Delete the button command control
    if command_control:
        command_control.deleteMe()

    # Delete the command definition
    if command_definition:
        command_definition.deleteMe()


# Function that is called when a user clicks the corresponding button in the UI.
# This defines the contents of the command dialog and connects to the command related events.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    futil.log(f"{CMD_NAME} Command Created Event")

    # Connect to the events that are needed by this command.
    futil.add_handler(
        args.command.execute, command_execute, local_handlers=local_handlers
    )
    futil.add_handler(
        args.command.destroy, command_destroy, local_handlers=local_handlers
    )


def command_execute(args: adsk.core.CommandCreatedEventArgs):
    # this handles the document close and reopen
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        product = app.activeProduct
        design = adsk.fusion.Design.cast(product)
        docActive = app.activeDocument
        docActiveUnits = design.unitsManager.defaultLengthUnits

        app_path = pathlib.Path(os.path.dirname(os.path.abspath(__file__)))
        importManager = app.importManager

        # Check a Design document is active.
        if not design:
            ui.messageBox("No active Fusion design", "No Design")
            return

        # Check that the active document has been saved.
        if futil.isSaved() == False:
            return

        if docActiveUnits == "mm" or "cm" or "m":
            parentdoc = os.path.normpath(
                os.path.join(app_path.parent, "new/resources/docs/mm/mm-Part.f3d")
            )
        if docActiveUnits == "in" or "ft" or "yd":
            parentdoc = os.path.normpath(
                os.path.join(app_path.parent, "new/resources/docs/in/in-Part.f3d")
            )
        importOptions = importManager.createFusionArchiveImportOptions(parentdoc)
        importOptions.isViewFit = True
        newDoc = importManager.importToNewDocument(importOptions)

        transform = adsk.core.Matrix3D.create()
        seedDoc = adsk.fusion.Design.cast(
            newDoc.products.itemByProductType("DesignProductType")
        )
        seedDoc.rootComponent.occurrences.addByInsert(
            docActive.dataFile, transform, True
        )
        app.activeViewport.goHome()

    except:
        if ui:
            ui.messageBox("Failed:\n{}".format(traceback.format_exc()))


# This function will be called when the user completes the command.
def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers
    local_handlers = []
    futil.log(f"{CMD_NAME} Command Destroy Event")
