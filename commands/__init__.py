from .autosave import entry as autosave
from .changetype import entry as changetype
from .datatoggle import entry as datatoggle
from .dochistory import entry as dochistory
from .docinfo import entry as docinfo
from .makeassemblyfrom import entry as makeassemblyfrom
from .new import entry as new

# Fusion will automatically call the start() and stop() functions.
commands = [
    autosave,
    datatoggle,
    changetype,
    dochistory,
    docinfo,
    makeassemblyfrom,
    new,
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
