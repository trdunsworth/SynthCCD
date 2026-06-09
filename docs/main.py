#!/usr/bin/env python
"""
Main entry point for the Synth911Gen2 application.

This script determines the appropriate interface (GUI, CLI, or interactive) for generating
synthetic 911 dispatch data, based on the user's environment and command-line arguments.
It handles platform-specific GUI initialization and gracefully falls back to CLI/interactive
modes if needed.
"""

import sys
import os
import platform

# Import tkinter conditionally to handle environments where it might not be available
try:
    import tkinter
    TKINTER_AVAILABLE = True
    TclError = tkinter.TclError
except ImportError:
    tkinter = None  # Ensure tkinter is always defined
    TKINTER_AVAILABLE = False
    TclError = type('TclError', (Exception,), {})  # Type-safe dummy exception

from synthgui_headless import main as headless_main, generate_data_interactive
try:
    from synthgui import main as gui_main
except ImportError:
    gui_main = None


def try_gui_backends():
    """Try different GUI backends based on platform.

    Returns:
        bool: True if a GUI backend is available and initialized, False otherwise.
    """
    # If tkinter is not available, GUI mode is not possible
    if not TKINTER_AVAILABLE or tkinter is None:
        return False

    system = platform.system().lower()

    if system == "windows":
        try:
            root = tkinter.Tk()
            root.withdraw()
            return True
        except TclError as exc:
            print(f"Windows GUI initialization failed: {str(exc)}")
            return False
    else:
        # For Linux/Unix systems, try to detect desktop environment
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
        if desktop == "kde":
            # On KDE, prefer CLI mode
            return False

        # For other desktop environments, try normal X11
        try:
            # Set basic X11 environment
            if "DISPLAY" not in os.environ:
                os.environ["DISPLAY"] = ":0"

            root = tkinter.Tk()
            root.withdraw()
            return True
        except TclError as exc:
            print(f"GUI initialization failed: {str(exc)}")
            return False


def main():
    """Main entry point for the synth911gen2 application.

    Launches the GUI interface for generating synthetic 911 data if possible,
    otherwise falls back to CLI or interactive mode.
    """
    # Check for headless mode flags
    if "--cli" in sys.argv or "--interactive" in sys.argv:
        headless_main()
        return

    # On Windows, always try GUI first
    # On Linux/Unix, check desktop environment
    system = platform.system().lower()
    if system == "windows" or try_gui_backends():
        try:
            if gui_main is not None:
                gui_main()
            else:
                raise ImportError("synthgui module not available")
        except (ImportError, AttributeError, RuntimeError, TclError) as exc:
            print(f"Error launching GUI: {str(exc)}")
            print("Falling back to interactive mode...")
            generate_data_interactive()
    else:
        # If not Windows and GUI initialization failed, use interactive mode
        print("Using command-line interface...")
        generate_data_interactive()


if __name__ == "__main__":
    main()
