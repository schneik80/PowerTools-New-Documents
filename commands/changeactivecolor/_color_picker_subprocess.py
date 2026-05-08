# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC
"""Standalone color-picker script run as a subprocess from ``entry.py``.

tkinter cannot take over the run loop inside Fusion's process on macOS
(Cocoa/Qt conflict — ``tk.Tk()`` hangs). Launching this script in a fresh
Python process gives Tk its own clean run loop. Emits the chosen hex on
stdout (e.g. ``#aabbcc``); empty stdout means the user cancelled.

Argument: optional initial color, hex with leading ``#`` (default ``#808080``).
"""

import sys


def main() -> int:
    try:
        import tkinter as tk
        from tkinter import colorchooser
    except ImportError as exc:
        sys.stderr.write(f"tkinter unavailable: {exc}\n")
        return 2

    initial = sys.argv[1] if len(sys.argv) > 1 else "#808080"

    root = tk.Tk()
    root.withdraw()
    try:
        root.lift()
        root.attributes("-topmost", True)
        root.update_idletasks()
    except Exception:
        pass

    try:
        _rgb, hex_str = colorchooser.askcolor(
            color=initial, parent=root, title="Pick a color"
        )
    except Exception as exc:
        sys.stderr.write(f"colorchooser error: {exc}\n")
        return 3
    finally:
        try:
            root.destroy()
        except Exception:
            pass

    if hex_str:
        sys.stdout.write(hex_str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
