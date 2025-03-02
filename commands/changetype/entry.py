import adsk.core
import os
from ...lib import fusionAddInUtils as futil
from ... import config

app = adsk.core.Application.get()
ui = app.userInterface
myTypesDict = []

myTypesDict = [
    {"type": "None", "isactive": "true"},
    {"type": "Assembly", "isactive": "false"},
    {"type": "Concept", "isactive": "false"},
    {"type": "Part", "isactive": "false"},
    {"type": "Sheetmetal", "isactive": "false"},
    {"type": "Plastic", "isactive": "false"},
    {"type": "Direct", "isactive": "false"},
]


# TODO *** Specify the command identity information. ***
CMD_ID = f"{config.COMPANY_NAME}_{config.ADDIN_NAME}_cmdDialog"
CMD_NAME = "Document Type"
CMD_Description = "A Fusion 360 Add-in Command with a dialog"

# Specify that the command will be promoted to the panel.
IS_PROMOTED = True

# TODO *** Define the location where the command button will be created. ***
# This is done by specifying the workspace, the tab, and the panel, and the
# command it will be inserted beside. Not providing the command to position it
# will insert it at the end.
WORKSPACE_ID = "FusionSolidEnvironment"
PANEL_ID = "SolidScriptsAddinsPanel"
COMMAND_BESIDE_ID = "ScriptsManagerCommand"

# Resource location for command icons, here we assume a sub folder in this directory named "resources".
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []


# Executed when add-in is run.
def start():
    # Create a command Definition.
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )

    # Define an event handler for the command created event. It will be called when the button is clicked.
    futil.add_handler(cmd_def.commandCreated, command_created)

    # ******** Add a button into the UI so the user can run the command. ********
    # Get the target workspace the button will be created in.
    workspace = ui.workspaces.itemById(WORKSPACE_ID)

    # Get the panel the button will be created in.
    panel = workspace.toolbarPanels.itemById(PANEL_ID)

    # Create the button command control in the UI after the specified existing command.
    control = panel.controls.addCommand(cmd_def, COMMAND_BESIDE_ID, False)

    # Specify if the command is promoted to the main toolbar.
    control.isPromoted = IS_PROMOTED


# Executed when add-in is stopped.
def stop():
    # Get the various UI elements for this command
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    command_control = panel.controls.itemById(CMD_ID)
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
    # General logging for debug.
    futil.log(f"{CMD_NAME} Command Created Event")

    design = adsk.fusion.Design.cast(app.activeProduct)

    # https://help.autodesk.com/view/fusion360/ENU/?contextId=CommandInputs
    inputs = args.command.commandInputs

    # TODO Define the dialog for your command by adding different inputs to the command.

    # Create a simple text box input.

    attributes = design.findAttributes("litetype", "componenttype")
    try:
        for attribute in attributes:
            if attribute.value == "assembly":
                myTypesDict[1]["isactive"] = "true"
            if attribute.value == "concept":
                myTypesDict[2]["isactive"] = "true"
            if attribute.value == "part":
                myTypesDict[3]["isactive"] = "true"
            if attribute.value == "sheetmetal":
                myTypesDict[4]["isactive"] = "true"
            if attribute.value == "plastic":
                myTypesDict[5]["isactive"] = "true"
            if attribute.value == "direct":
                myTypesDict[6]["isactive"] = "true"
    except:
        myTypesDict[0]["isactive"] = "true"

    drop_down_style = adsk.core.DropDownStyles.LabeledIconDropDownStyle
    drop_down_input = inputs.addDropDownCommandInput("Type", "Type:", drop_down_style)
    drop_down_items = drop_down_input.listItems

    for item in myTypesDict:
        drop_down_items.add(item["type"], item["isactive"] == "true")

    # TODO Connect to the events that are needed by this command.
    futil.add_handler(
        args.command.execute, command_execute, local_handlers=local_handlers
    )
    futil.add_handler(
        args.command.inputChanged, command_input_changed, local_handlers=local_handlers
    )
    futil.add_handler(
        args.command.executePreview, command_preview, local_handlers=local_handlers
    )
    futil.add_handler(
        args.command.validateInputs,
        command_validate_input,
        local_handlers=local_handlers,
    )
    futil.add_handler(
        args.command.destroy, command_destroy, local_handlers=local_handlers
    )


# This event handler is called when the user clicks the OK button in the command dialog or
# is immediately called after the created event not command inputs were created for the dialog.
def command_execute(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f"{CMD_NAME} Command Execute Event")

    # TODO ******************************** Your code here ********************************
    design = adsk.fusion.Design.cast(app.activeProduct)
    attributes = design.attributes.itemByName("litetype", "componenttype")

    types = "None"
    try:
        types = attributes.value
    except:
        pass
    inputs = args.command.commandInputs

    if inputs.itemById("Type").selectedItem.name == types:
        exit()
    else:
        if inputs.itemById("Type").selectedItem.name == "Assembly":
            design.createAttribute("litetype", "componenttype", "assembly")
        if inputs.itemById("Type").selectedItem.name == "Concept":
            design.createAttribute("litetype", "componenttype", "concept")
        if inputs.itemById("Type").selectedItem.name == "Part":
            design.createAttribute("litetype", "componenttype", "part")
        if inputs.itemById("Type").selectedItem.name == "Sheetmetal":
            design.createAttribute("litetype", "componenttype", "sheetmetal")
        if inputs.itemById("Type").selectedItem.name == "Plastic":
            design.createAttribute("litetype", "componenttype", "plastic")
        if inputs.itemById("Type").selectedItem.name == "Direct":
            design.createAttribute("litetype", "componenttype", "direct")
        if inputs.itemById("Type").selectedItem.name == "None":
            design.deleteAttributes("litetype", "componenttype")


# This event handler is called when the command needs to compute a new preview in the graphics window.
def command_preview(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f"{CMD_NAME} Command Preview Event")
    inputs = args.command.commandInputs


# This event handler is called when the user changes anything in the command dialog
# allowing you to modify values of other inputs based on that change.
def command_input_changed(args: adsk.core.InputChangedEventArgs):
    changed_input = args.input
    inputs = args.inputs

    # General logging for debug.
    futil.log(
        f"{CMD_NAME} Input Changed Event fired from a change to {changed_input.id}"
    )


# This event handler is called when the user interacts with any of the inputs in the dialog
# which allows you to verify that all of the inputs are valid and enables the OK button.
def command_validate_input(args: adsk.core.ValidateInputsEventArgs):
    # General logging for debug.
    futil.log(f"{CMD_NAME} Validate Input Event")

    inputs = args.inputs

    # Verify the validity of the input values. This controls if the OK button is enabled or not.
    valueInput = inputs.itemById("value_input")
    if valueInput.value >= 0:
        args.areInputsValid = True
    else:
        args.areInputsValid = False


# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f"{CMD_NAME} Command Destroy Event")

    global local_handlers
    local_handlers = []
