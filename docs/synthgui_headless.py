"""
Synth911Gen2 Headless CLI and Interactive Interface

This module provides command-line and interactive (text-based) interfaces for generating
synthetic 911 dispatch data. It supports both direct CLI argument parsing and step-by-step
interactive prompts for user configuration.
"""

#!/usr/bin/env python

import os
import sys
import subprocess
from datetime import datetime
import re
import argparse
from shared.constants import DEFAULT_LOCALE, SUPPORTED_LOCALES, validate_locale

# Common Faker locales with their display names
LOCALE_OPTIONS = [
    ("en_US", "English (US)"),
    ("en_GB", "English (UK)"),
    ("fr_FR", "French"),
    ("de_DE", "German"),
    ("es_ES", "Spanish"),
    ("it_IT", "Italian"),
    ("pt_BR", "Portuguese (Brazil)"),
    ("nl_NL", "Dutch"),
    ("pl_PL", "Polish"),
    ("ru_RU", "Russian"),
    ("ja_JP", "Japanese"),
    ("ko_KR", "Korean"),
    ("zh_CN", "Chinese (Simplified)"),
    ("ar_SA", "Arabic"),
]

# Create a mapping of locales to their descriptions
LOCALE_DESCRIPTIONS = {
    "en_US": "American English",
    "en_GB": "British English",
    "fr_FR": "French",
    "de_DE": "German",
    "es_ES": "Spanish",
    "it_IT": "Italian",
    "pt_BR": "Brazilian Portuguese",
    "nl_NL": "Dutch",
    "pl_PL": "Polish",
    "ru_RU": "Russian",
    "ja_JP": "Japanese",
    "ko_KR": "Korean",
    "zh_CN": "Chinese (Simplified)",
    "ar_SA": "Arabic",
}

def print_locales():
    """Print available locales with their descriptions"""
    print("\nAvailable locales:")
    for locale in SUPPORTED_LOCALES:
        description = LOCALE_DESCRIPTIONS.get(locale, "")
        print(f"  {locale:<8} - {description}")
    print()

def validate_date(date_str):
    """Validate date format YYYY-MM-DD"""
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return True
    except ValueError:
        return False

def validate_positive_int(value_str):
    """Validate that a string represents a positive integer"""
    try:
        value = int(value_str)
        return value > 0
    except ValueError:
        return False

def sanitize_input(user_input):
    """Sanitize user input to prevent command injection"""
    pattern = r'^[a-zA-Z0-9\s\-\.\/\\:_]+$'
    if not re.match(pattern, user_input):
        raise ValueError("Input contains invalid characters.")
    return user_input

def verify_locale(locale):
    """
    Verify if the locale is supported and print appropriate warnings

    Args:
        locale (str): The locale to verify

    Returns:
        bool: True if the locale is supported, False otherwise
    """
    if not validate_locale(locale):
        print(f"Warning: '{locale}' is not in the list of common locales.")
        print("It may still work if it's a valid Faker locale, but results may vary.")
        print_locales()
        return False
    return True

def generate_data_cli():
    """Command-line interface for generating data"""
    parser = argparse.ArgumentParser(description="Generate synthetic 911 dispatch data")
    parser.add_argument('-n', '--num-records', type=int, default=10000,
                        help='Number of records to generate (default: 10000)')
    parser.add_argument('-s', '--start-date', type=str, default='2024-01-01',
                        help='Start date in YYYY-MM-DD format (default: 2024-01-01)')
    parser.add_argument('-e', '--end-date', type=str, default='2024-12-31',
                        help='End date in YYYY-MM-DD format (default: 2024-12-31)')
    parser.add_argument('--num-names', type=int, default=8,
                        help='Number of names to generate per shift (default: 8)')
    parser.add_argument('-l', '--locale', type=str, default='en_US',
                        help='Faker locale for generating localized data (default: en_US)')
    parser.add_argument('-o', '--output-file', type=str, default='computer_aided_dispatch.csv',
                        help='Output file path (default: computer_aided_dispatch.csv)')
    parser.add_argument('-a', '--agencies', type=str, default='',
                        help='Comma-separated list of agencies to include (e.g., LAW,FIRE)')
    parser.add_argument('--agency-probabilities', type=str, default='',
                        help='Comma-separated probabilities for selected agencies (e.g., 0.7,0.2,0.1)')
    parser.add_argument('--list-locales', action='store_true',
                        help='List available locales and exit')

    args = parser.parse_args()

    if args.list_locales:
        print_locales()
        return

    # Validate inputs
    if not validate_positive_int(str(args.num_records)):
        print("Error: Number of records must be a positive integer.")
        return

    if not validate_date(args.start_date):
        print("Error: Start date must be in YYYY-MM-DD format.")
        return

    if not validate_date(args.end_date):
        print("Error: End date must be in YYYY-MM-DD format.")
        return

    if datetime.strptime(args.end_date, '%Y-%m-%d') < datetime.strptime(args.start_date, '%Y-%m-%d'):
        print("Error: End date must be after start date.")
        return

    if not validate_positive_int(str(args.num_names)):
        print("Error: Number of names must be a positive integer.")
        return

    # Check if locale is valid
    if not validate_locale(args.locale):
        print(f"Warning: '{args.locale}' is not in the list of common locales.")
        print("It may still work if it's a valid Faker locale, but results may vary.")
        print_locales()
        response = input("Do you want to continue with this locale? (y/n): ")
        if response.lower() != 'y':
            return

    # Build the command
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "synth911gen.py")
    cmd = [
        sys.executable,
        script_path,
        "-n", str(args.num_records),
        "-s", args.start_date,
        "-e", args.end_date,
        "--num-names", str(args.num_names),
        "-l", args.locale,
        "-o", args.output_file
    ]

    # Add agencies parameter if specified
    if args.agencies:
        try:
            sanitized_agencies = sanitize_input(args.agencies)
            cmd.extend(["-a", sanitized_agencies])
        except ValueError as e:
            print(f"Error: {str(e)}")
            return

    # Add agency probabilities parameter if specified
    if args.agency_probabilities:
        try:
            sanitized_probs = sanitize_input(args.agency_probabilities)
            cmd.extend(["--agency-probabilities", sanitized_probs])
        except ValueError as e:
            print(f"Error: {str(e)}")
            return

    # Run the command
    print("\nStarting data generation...")
    print(f"Number of records: {args.num_records}")
    print(f"Date range: {args.start_date} to {args.end_date}")
    print(f"Locale: {args.locale}")
    print(f"Output file: {args.output_file}")
    if args.agencies:
        print(f"Agencies: {args.agencies}")
    if args.agency_probabilities:
        print(f"Agency Probabilities: {args.agency_probabilities}")

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Get the output
        stdout, stderr = process.communicate()

        if process.returncode == 0:
            # Success
            print("\nData generation completed successfully!")
            for line in stdout.splitlines():
                print(line)
        else:
            # Error
            print("\nError during data generation:")
            for line in stderr.splitlines():
                print(line)
    except Exception as e:
        print(f"\nAn unexpected error occurred: {str(e)}")

def generate_data_interactive():
    """Interactive interface for generating data"""
    print("\nSynthetic 911 Data Generator - Interactive Mode")
    print("==============================================\n")

    # Get number of records
    while True:
        num_records = input("How many records would you like to generate? [10000]: ")
        if not num_records:
            num_records = "10000"
            break
        if validate_positive_int(num_records):
            break
        print("Please enter a positive number.")

    # Get start date
    while True:
        start_date = input("Enter start date (YYYY-MM-DD) [2024-01-01]: ")
        if not start_date:
            start_date = "2024-01-01"
            break
        if validate_date(start_date):
            break
        print("Please enter a valid date in YYYY-MM-DD format.")

    # Get end date
    while True:
        end_date = input("Enter end date (YYYY-MM-DD) [2024-12-31]: ")
        if not end_date:
            end_date = "2024-12-31"
            break
        if validate_date(end_date):
            if datetime.strptime(end_date, '%Y-%m-%d') >= datetime.strptime(start_date, '%Y-%m-%d'):
                break
            print("End date must be after start date.")
            continue
        print("Please enter a valid date in YYYY-MM-DD format.")

    # Get number of names
    while True:
        num_names = input("How many names would you like to generate per shift? [8]: ")
        if not num_names:
            num_names = "8"
            break
        if validate_positive_int(num_names):
            break
        print("Please enter a positive number.")

    # Get locale
    print_locales()
    while True:
        locale = input("Enter the Faker locale (e.g., en_US, fr_FR) [en_US]: ")
        if not locale:
            locale = "en_US"
            break
        valid_locales = [code for code, _ in LOCALE_OPTIONS]
        if locale in valid_locales:
            break
        print(f"Warning: '{locale}' is not in the list of common locales.")
        print("It may still work if it's a valid Faker locale, but results may vary.")
        response = input("Do you want to continue with this locale? (y/n): ")
        if response.lower() == 'y':
            break

    # Get agencies
    agencies = input("Enter agencies to include (comma-separated, e.g., LAW,FIRE) []: ")
    if not agencies:
        agencies = ""
    # Get agency probabilities
    agency_probabilities = input("Enter agency probabilities (comma-separated, e.g., 0.7,0.2,0.1) []: ")
    if not agency_probabilities:
        agency_probabilities = ""

    # Get output file
    output_file = input("Enter the output file path [computer_aided_dispatch.csv]: ")
    if not output_file:
        output_file = "computer_aided_dispatch.csv"

    # Sanitize inputs
    try:
        num_records = sanitize_input(num_records)
        start_date = sanitize_input(start_date)
        end_date = sanitize_input(end_date)
        num_names = sanitize_input(num_names)
        locale = sanitize_input(locale)
        output_file = sanitize_input(output_file)
        if agencies:
            agencies = sanitize_input(agencies)
        if agency_probabilities:
            agency_probabilities = sanitize_input(agency_probabilities)
    except ValueError as e:
        print(f"Error: {str(e)}")
        return

    # Build the command
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "synth911gen.py")
    cmd = [
        sys.executable,
        script_path,
        "-n", num_records,
        "-s", start_date,
        "-e", end_date,
        "--num-names", num_names,
        "-l", locale,
        "-o", output_file
    ]
    if agencies:
        cmd.extend(["-a", agencies])
    if agency_probabilities:
        cmd.extend(["--agency-probabilities", agency_probabilities])

    # Run the command
    print("\nStarting data generation...")
    print(f"Number of records: {num_records}")
    print(f"Date range: {start_date} to {end_date}")
    print(f"Locale: {locale}")
    print(f"Output file: {output_file}")
    if agencies:
        print(f"Agencies: {agencies}")
    if agency_probabilities:
        print(f"Agency Probabilities: {agency_probabilities}")

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Get the output
        stdout, stderr = process.communicate()

        if process.returncode == 0:
            # Success
            print("\nData generation completed successfully!")
            for line in stdout.splitlines():
                print(line)
        else:
            # Error
            print("\nError during data generation:")
            for line in stderr.splitlines():
                print(line)
    except Exception as e:
        print(f"\nAn unexpected error occurred: {str(e)}")

def try_launch_gui():
    """Try to launch the GUI, return True if successful, False otherwise"""
    try:
        # Set environment variable to disable threading in X11
        os.environ['PYTHONTHREADED'] = '0'

        # Try importing tkinter to see if it works
        import tkinter as tk

        # Create a small test window to see if it works
        root = tk.Tk()
        root.withdraw()  # Hide the window
        root.update()    # Process events
        root.destroy()   # Close the window

        # If we got here, tkinter is working
        return True
    except Exception as e:
        print(f"GUI initialization failed: {str(e)}")
        return False

def main():
    """Main entry point"""
    # Check if --cli flag is provided
    if "--cli" in sys.argv:
        sys.argv.remove("--cli")
        generate_data_cli()
        return

    # Check if --interactive flag is provided
    if "--interactive" in sys.argv:
        sys.argv.remove("--interactive")
        generate_data_interactive()
        return

    # Try to launch the GUI
    if try_launch_gui():
        try:
            # Import and run the GUI
            from synthgui import Synth911GenGUI
            import tkinter as tk

            root = tk.Tk()
            Synth911GenGUI(root)
            root.mainloop()
        except Exception as e:
            print(f"Error launching GUI: {str(e)}")
            print("Falling back to interactive mode...")
            generate_data_interactive()
    else:
        print("Unable to initialize GUI. Falling back to interactive mode.")
        print("You can also use --cli for command-line arguments or --interactive for guided input.")
        generate_data_interactive()

if __name__ == "__main__":
    main()