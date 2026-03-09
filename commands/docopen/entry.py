import adsk.core
from ...lib import fusionAddInUtils as futil

app = adsk.core.Application.get()

CMD_NAME = "Show In Location on Open"

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


def _show_in_location(document: adsk.core.Document, event_name: str):
    """Set the active data project to the opened document's parent project."""
    try:
        data_file = document.dataFile
        if not data_file:
            futil.log(f"{CMD_NAME} [{event_name}]: document has no dataFile, skipping.")
            return

        project = data_file.parentFolder.parentProject
        if not project:
            futil.log(
                f"{CMD_NAME} [{event_name}]: could not resolve parent project, skipping."
            )
            return

        app.data.activeProject = project
        futil.log(f"{CMD_NAME} [{event_name}]: active project set to '{project.name}'.")

    except Exception:
        futil.log(
            f"{CMD_NAME} [{event_name}]: error setting active project.",
            force_console=True,
        )


# Event handler — fires at the end of every document open.
def application_documentOpened(args: adsk.core.DocumentEventArgs):
    _show_in_location(args.document, "documentOpened")


# Event handler — fires when the user switches to a different document tab.
def application_documentActivated(args: adsk.core.DocumentEventArgs):
    _show_in_location(args.document, "documentActivated")
