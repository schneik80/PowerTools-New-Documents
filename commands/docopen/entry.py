import adsk.core, adsk.fusion
from ...lib import fusionAddInUtils as futil

app = adsk.core.Application.get()

CMD_NAME = "Show In Location on Open"
SHOW_IN_LOCATION_CMD_ID = "ShowInLocationCmd"

# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []


# Executed when add-in is run.
def start():
    futil.add_handler(
        app.documentOpened,
        application_documentOpened,
        local_handlers=local_handlers,
    )
    futil.add_handler(
        app.documentActivated,
        application_documentActivated,
        local_handlers=local_handlers,
    )
    futil.log(f"{CMD_NAME}: documentOpened and documentActivated handlers registered.")


# Executed when add-in is stopped.
def stop():
    global local_handlers
    local_handlers = []
    futil.log(f"{CMD_NAME}: documentOpened and documentActivated handlers removed.")


def _show_in_location(event_name: str):
    """Select the root component and run ShowInLocationCmd. Logs silently on failure."""
    try:
        ui = app.userInterface
        product = app.activeProduct
        design = adsk.fusion.Design.cast(product)
        if not design:
            futil.log(f"{CMD_NAME} [{event_name}]: no active Fusion design, skipping.")
            return

        # Select the root component so ShowInLocationCmd has the right context.
        root = design.rootComponent
        design.activateRootComponent()
        ui.activeSelections.clear()
        ui.activeSelections.add(root)

        cmd_def = ui.commandDefinitions.itemById(SHOW_IN_LOCATION_CMD_ID)
        if cmd_def:
            cmd_def.execute()
            futil.log(
                f"{CMD_NAME} [{event_name}]: executed '{SHOW_IN_LOCATION_CMD_ID}'."
            )
        else:
            futil.log(
                f"{CMD_NAME} [{event_name}]: command '{SHOW_IN_LOCATION_CMD_ID}' not found."
            )
    except Exception:
        futil.log(
            f"{CMD_NAME} [{event_name}]: error executing '{SHOW_IN_LOCATION_CMD_ID}'.",
            force_console=True,
        )


# Event handler — fires at the end of every document open.
def application_documentOpened(args: adsk.core.DocumentEventArgs):
    _show_in_location("documentOpened")


# Event handler — fires when the user switches to a different document tab.
def application_documentActivated(args: adsk.core.DocumentEventArgs):
    _show_in_location("documentActivated")
