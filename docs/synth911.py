#!/usr/bin/env python
"""
Synth911 - Synthetic 911 Dispatch Data Generator

This script serves as the main entry point for the Synth911 application.
It attempts to launch the GUI version first, and if that fails, it falls back
to the headless version with an interactive command-line interface.
"""

import os
import sys
import subprocess
import shlex

def validate_choice(choice):
    """Validate user menu choice.

    Args:
        choice (str): The user's menu selection.
    Returns:
        bool: True if the choice is valid, False otherwise.
    """
    return choice in ["1", "2", "3"]

def sanitize_cli_args(args_str):
    """Sanitize command line arguments to prevent injection.

    Args:
        args_str (str): The raw command-line argument string.
    Returns:
        list: A list of sanitized arguments.
    """
    try:
        args = shlex.split(args_str)
        # Basic sanitization - only allow alphanumeric, hyphen, space
        return [arg for arg in args if arg.replace("-", "").replace(" ", "").isalnum()]
    except ValueError as e:
        print(f"Error parsing arguments: {str(e)}")
        return []

def run_subprocess(cmd, check=False):
    """Run a subprocess with proper error handling.

    Args:
        cmd (list): The command and arguments to run.
        check (bool): Whether to raise an error on non-zero exit.
    Returns:
        subprocess.CompletedProcess or None: The result object, or None on error.
    """
    try:
        result = subprocess.run(cmd, check=check, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return result
    except subprocess.CalledProcessError as e:
        print(f"Command failed with exit code {e.returncode}: {str(e)}")
        return None
    except FileNotFoundError as e:
        print(f"File not found error running command: {str(e)}")
        return None
    except PermissionError as e:
        print(f"Permission error running command: {str(e)}")
        return None
    except OSError as e:
        print(f"OS error running command: {str(e)}")
        return None
    except ValueError as e:
        print(f"Value error running command: {str(e)}")
        return None

def main():
    """Main entry point for the application."""
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # First, try to run the GUI version
    try:
        # Set environment variables that might help with X11 issues
        os.environ['PYTHONTHREADED'] = '0'
        os.environ['XCB_ALLOW_SLOPPY_LOCK'] = '1'

        # Try running the GUI version
        print("Attempting to launch GUI version...")
        result = run_subprocess([sys.executable, os.path.join(script_dir, "synthgui_headless.py")])

        # If the GUI version exited successfully, we're done
        if result and result.returncode == 0:
            return

        # If we get here, the GUI version failed
        print("\nGUI version failed to launch. Falling back to headless version.")
    except (OSError, subprocess.CalledProcessError, ValueError) as e:
        print(f"\nError launching GUI: {str(e)}")
        print("Falling back to headless version.")

    # If we get here, we need to run the headless version
    while True:
        print("\nSynth911 - Headless Mode")
        print("======================")
        print("1. Interactive mode (guided prompts)")
        print("2. Command-line mode (pass arguments)")
        print("3. Exit")

        choice = input("\nEnter your choice (1-3): ")

        if not validate_choice(choice):
            print("Invalid choice. Please enter 1, 2, or 3.")
            continue

        if choice == "3":
            print("Exiting...")
            break

        if choice == "1":
            # Run interactive mode
            result = run_subprocess(
                [sys.executable, os.path.join(script_dir, "synthgui_headless.py"), "--interactive"]
            )
            if not result:
                print("Failed to run interactive mode.")
            break

        elif choice == "2":
            # Show help for command-line mode
            print("\nCommand-line mode usage:")
            run_subprocess(
                [sys.executable, os.path.join(script_dir, "synthgui_headless.py"), "--cli", "--help"]
            )

            # Ask if they want to continue
            while True:
                cont = input("\nDo you want to continue with command-line mode? (y/n): ").lower()
                if cont in ['y', 'n']:
                    break
                print("Please enter 'y' or 'n'")

            if cont == "y":
                # Get and validate the command-line arguments
                args = input("\nEnter command-line arguments: ")
                sanitized_args = sanitize_cli_args(args)

                if not sanitized_args:
                    print("Invalid or empty arguments provided.")
                    continue

                # Run the command with sanitized arguments
                result = run_subprocess(
                    [sys.executable, os.path.join(script_dir, "synthgui_headless.py"), "--cli"] + sanitized_args
                )
                if not result:
                    print("Failed to run command-line mode.")
            break

if __name__ == "__main__":
    main()
    