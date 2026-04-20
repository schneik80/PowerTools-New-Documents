# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

from .assigndrawingnumber import entry as assigndrawingnumber
from .assignpartnumbers import entry as assignpartnumbers
from .autosave import entry as autosave
from .datatoggle import entry as datatoggle
from .defaultfolders import entry as defaultfolders
from .dochistory import entry as dochistory
from .docinfo import entry as docinfo
from .docopen import entry as docopen
from .favorites import entry as favorites
from .versiondiff import entry as versiondiff

# Fusion will automatically call the start() and stop() functions.
commands = [
    assigndrawingnumber,
    assignpartnumbers,
    autosave,
    datatoggle,
    defaultfolders,
    dochistory,
    docinfo,
    docopen,
    favorites,
    versiondiff,
]


# Assumes you defined a "start" function in each of your modules.
# The start function will be run when the add-in is started.
def start():
    for command in commands:
        command.start()


# Assumes you defined a "stop" function in each of your modules.
# The stop function will be run when the add-in is stopped.
def stop():
    for command in commands:
        command.stop()
