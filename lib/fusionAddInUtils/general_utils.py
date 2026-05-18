#  Copyright 2022 by Autodesk, Inc.
#  Permission to use, copy, modify, and distribute this software in object code form
#  for any purpose and without fee is hereby granted, provided that the above copyright
#  notice appears in all copies and that both that copyright notice and the limited
#  warranty and restricted rights notice below appear in all supporting documentation.
#
#  AUTODESK PROVIDES THIS PROGRAM "AS IS" AND WITH ALL FAULTS. AUTODESK SPECIFICALLY
#  DISCLAIMS ANY IMPLIED WARRANTY OF MERCHANTABILITY OR FITNESS FOR A PARTICULAR USE.
#  AUTODESK, INC. DOES NOT WARRANT THAT THE OPERATION OF THE PROGRAM WILL BE
#  UNINTERRUPTED OR ERROR FREE.

import datetime
import os
import subprocess
import tempfile
import traceback
import adsk.core

app = adsk.core.Application.get()
ui = app.userInterface

# Attempt to read DEBUG flag from parent config.
try:
    from ... import config

    DEBUG = config.DEBUG
except:
    DEBUG = False


# File log that you can tail or open in Console.app — useful when no IDE
# debugger is attached, since `print()` goes to a dev null otherwise.
LOG_FILE_PATH = os.path.join(tempfile.gettempdir(), "powertools_doctools.log")


def _append_to_file_log(message: str, level_name: str) -> None:
    try:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as fh:
            fh.write(f"[{ts}] {level_name}: {message}\n")
    except Exception:
        pass


def log(
    message: str,
    level: adsk.core.LogLevels = adsk.core.LogLevels.InfoLogLevel,
    force_console: bool = False,
):
    """Log a message to every channel we have access to.

    - stdout (only visible when an IDE debugger is attached)
    - /tmp/powertools_doctools.log (tail-able / openable in Console.app)
    - Fusion's TEXT COMMANDS palette (View → Show Text Commands)
    - Fusion's log file for errors

    Arguments:
        message: The message to log.
        level: The logging severity level.
        force_console: Retained for backwards-compatibility; ignored now that
            every message is already written to the Text Command window.
    """
    # 1) stdout — only seen through an attached IDE
    print(message)

    # 2) tail-able file log
    try:
        level_name = (
            "ERROR" if level == adsk.core.LogLevels.ErrorLogLevel else "INFO"
        )
    except Exception:
        level_name = "INFO"
    _append_to_file_log(message, level_name)

    # 3) Fusion TEXT COMMANDS palette — every message, every time
    try:
        app.log(message, level, adsk.core.LogTypes.ConsoleLogType)
    except Exception:
        pass

    # 4) Fusion log file — errors only
    if level == adsk.core.LogLevels.ErrorLogLevel:
        try:
            app.log(message, level, adsk.core.LogTypes.FileLogType)
        except Exception:
            pass


def clipText(linkText):
    """Utility function to copy text to the clipboard.

    Augments:
    linkText -- string to copy to system clipboard.
    """
    if os.name == "nt":
        subprocess.run(
            ["clip.exe"], input=linkText.strip().encode("utf-8"), check=True, shell=True
        )
    else:
        os.system(f'echo "{linkText.strip()}" | pbcopy')
    app.log(f"link: {linkText} was added to clipboard")


def isSaved() -> bool:
    """Utility function to check if the active document has been saved.

    Returns:
    bool -- True if the active document has been saved, False otherwise.
    """
    # Check that the active document has been saved.
    if not app.activeDocument.isSaved:
        ui.messageBox(
            "The active document must be saved before you can continue.",
            "Please Save",
            0,
            2,
        )
        return False
    return True


def handle_error(name: str, show_message_box: bool = False):
    """Utility function to simplify error handling.

    Arguments:
    name -- A name used to label the error.
    show_message_box -- Indicates if the error should be shown in the message box.
                        If False, it will only be shown in the Text Command window
                        and logged to the log file.
    """

    log("===== Error =====", adsk.core.LogLevels.ErrorLogLevel)
    log(f"{name}\n{traceback.format_exc()}", adsk.core.LogLevels.ErrorLogLevel)

    # If desired you could show an error as a message box.
    if show_message_box:
        ui.messageBox(f"{name}\n{traceback.format_exc()}")
