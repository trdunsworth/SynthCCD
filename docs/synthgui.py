"""
Synth911Gen2 GUI (Tkinter-based Graphical User Interface)

This module provides a graphical user interface for generating synthetic 911 dispatch data
using Tkinter. It allows users to configure parameters and generate data via a desktop app.
"""

#!/usr/bin/env python

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import sys
from datetime import datetime
import subprocess
import re

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
    ("ja_JP", "Japanese"),
    ("zh_CN", "Chinese"),
    ("ru_RU", "Russian"),
    ("ar_EG", "Arabic"),
    ("hi_IN", "Hindi"),
    ("ko_KR", "Korean"),
    ("sv_SE", "Swedish"),
    ("fi_FI", "Finnish"),
    ("no_NO", "Norwegian"),
    ("da_DK", "Danish"),
    ("cs_CZ", "Czech"),
    ("pl_PL", "Polish")
]

class Synth911GenGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Synth911Gen - 911 Data Generator")
        self.root.geometry("600x550")  # Increased height to accommodate the new field
        self.root.resizable(True, True)

        # Set the icon if available
        try:
            self.root.iconbitmap("icon.ico")
        except:
            pass

        self.create_widgets()

    def create_widgets(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Title
        title_label = ttk.Label(main_frame, text="Synthetic 911 Data Generator", font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20), sticky="w")

        # Number of records
        ttk.Label(main_frame, text="Number of Records:").grid(row=1, column=0, sticky="w", pady=5)
        self.num_records_var = tk.StringVar(value="10000")
        num_records_entry = ttk.Entry(main_frame, textvariable=self.num_records_var, width=15)
        num_records_entry.grid(row=1, column=1, sticky="w", pady=5)

        # Start date
        ttk.Label(main_frame, text="Start Date (YYYY-MM-DD):").grid(row=2, column=0, sticky="w", pady=5)
        self.start_date_var = tk.StringVar(value="2024-01-01")
        start_date_entry = ttk.Entry(main_frame, textvariable=self.start_date_var, width=15)
        start_date_entry.grid(row=2, column=1, sticky="w", pady=5)

        # End date
        ttk.Label(main_frame, text="End Date (YYYY-MM-DD):").grid(row=3, column=0, sticky="w", pady=5)
        self.end_date_var = tk.StringVar(value="2024-12-31")
        end_date_entry = ttk.Entry(main_frame, textvariable=self.end_date_var, width=15)
        end_date_entry.grid(row=3, column=1, sticky="w", pady=5)

        # Number of names per shift
        ttk.Label(main_frame, text="Names per Shift:").grid(row=4, column=0, sticky="w", pady=5)
        self.num_names_var = tk.StringVar(value="8")
        num_names_entry = ttk.Entry(main_frame, textvariable=self.num_names_var, width=15)
        num_names_entry.grid(row=4, column=1, sticky="w", pady=5)

        # Locale selection
        ttk.Label(main_frame, text="Locale:").grid(row=5, column=0, sticky="w", pady=5)
        self.locale_var = tk.StringVar(value="en_US")

        # Create dictionaries for mapping between display names and locale codes
        self.locale_display_to_code = {display: code for code, display in LOCALE_OPTIONS}
        self.locale_code_to_display = {code: display for code, display in LOCALE_OPTIONS}

        # Create the dropdown with display names
        self.locale_display_var = tk.StringVar(value=self.locale_code_to_display["en_US"])
        locale_dropdown = ttk.Combobox(main_frame, textvariable=self.locale_display_var, width=20, state="readonly")
        locale_dropdown['values'] = [display for _, display in LOCALE_OPTIONS]
        locale_dropdown.grid(row=5, column=1, sticky="w", pady=5)

        # Bind the selection event to update the locale_var with the actual locale code
        locale_dropdown.bind('<<ComboboxSelected>>', self.update_locale_code)

        # Agencies selection
        ttk.Label(main_frame, text="Agencies (comma-separated, e.g., LAW,FIRE):").grid(row=6, column=0, sticky="w", pady=5)
        self.agencies_var = tk.StringVar(value="")
        agencies_entry = ttk.Entry(main_frame, textvariable=self.agencies_var, width=30)
        agencies_entry.grid(row=6, column=1, sticky="ew", pady=5)

        # Output file
        ttk.Label(main_frame, text="Output File:").grid(row=7, column=0, sticky="w", pady=5)
        self.output_file_var = tk.StringVar(value="computer_aided_dispatch.csv")
        output_file_entry = ttk.Entry(main_frame, textvariable=self.output_file_var, width=30)
        output_file_entry.grid(row=7, column=1, sticky="ew", pady=5)

        # Browse button
        browse_button = ttk.Button(main_frame, text="Browse...", command=self.browse_output_file)
        browse_button.grid(row=7, column=2, sticky="w", padx=(5, 0), pady=5)

        # Agency probabilities
        ttk.Label(main_frame, text="Agency Probabilities (comma-separated, e.g., 0.7,0.2,0.1):").grid(row=8, column=0, sticky="w", pady=5)
        self.agency_probabilities_var = tk.StringVar(value="")
        agency_probabilities_entry = ttk.Entry(main_frame, textvariable=self.agency_probabilities_var, width=30)
        agency_probabilities_entry.grid(row=8, column=1, sticky="ew", pady=5)

        # Status frame
        status_frame = ttk.LabelFrame(main_frame, text="Status", padding="10")
        status_frame.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(20, 10))

        # Status text
        self.status_text = tk.Text(status_frame, height=10, width=60, wrap=tk.WORD)
        self.status_text.pack(fill=tk.BOTH, expand=True)
        self.status_text.config(state=tk.DISABLED)

        # Add a scrollbar to the status text
        scrollbar = ttk.Scrollbar(self.status_text, command=self.status_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.status_text.config(yscrollcommand=scrollbar.set)

        # Buttons frame
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.grid(row=10, column=0, columnspan=3, pady=(10, 0))

        # Generate button
        generate_button = ttk.Button(buttons_frame, text="Generate Data", command=self.generate_data)
        generate_button.pack(side=tk.LEFT, padx=5)

        # Exit button
        exit_button = ttk.Button(buttons_frame, text="Exit", command=self.root.destroy)
        exit_button.pack(side=tk.LEFT, padx=5)

    def update_locale_code(self, event):
        """Update the locale variable with the correct code when a display name is selected"""
        selected_display = self.locale_display_var.get()
        if selected_display in self.locale_display_to_code:
            self.locale_var.set(self.locale_display_to_code[selected_display])

    def browse_output_file(self):
        """Open a file dialog to select the output file location"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=self.output_file_var.get()
        )
        if filename:
            self.output_file_var.set(filename)

    def update_status(self, message):
        """Update the status text widget with a new message"""
        self.status_text.config(state=tk.NORMAL)
        self.status_text.insert(tk.END, message + "\n")
        self.status_text.see(tk.END)
        self.status_text.config(state=tk.DISABLED)
        self.root.update()

    def validate_inputs(self):
        """Validate all user inputs before generating data"""
        # Validate number of records
        try:
            num_records = int(self.num_records_var.get())
            if num_records <= 0:
                messagebox.showerror("Input Error", "Number of records must be a positive integer.")
                return False
        except ValueError:
            messagebox.showerror("Input Error", "Number of records must be a valid integer.")
            return False

        # Validate dates
        try:
            start_date = datetime.strptime(self.start_date_var.get(), '%Y-%m-%d')
        except ValueError:
            messagebox.showerror("Input Error", "Start date must be in YYYY-MM-DD format.")
            return False

        try:
            end_date = datetime.strptime(self.end_date_var.get(), '%Y-%m-%d')
        except ValueError:
            messagebox.showerror("Input Error", "End date must be in YYYY-MM-DD format.")
            return False

        if end_date < start_date:
            messagebox.showerror("Input Error", "End date must be after start date.")
            return False

        # Validate number of names
        try:
            num_names = int(self.num_names_var.get())
            if num_names <= 0:
                messagebox.showerror("Input Error", "Number of names must be a positive integer.")
                return False
        except ValueError:
            messagebox.showerror("Input Error", "Number of names must be a valid integer.")
            return False

        # Validate output file
        output_file = self.output_file_var.get()
        if not output_file:
            messagebox.showerror("Input Error", "Output file path cannot be empty.")
            return False

        # Check if the directory exists
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
            except:
                messagebox.showerror("Input Error", f"Cannot create directory: {output_dir}")
                return False

        return True

    def sanitize_input(self, user_input):
        """Sanitize user input to prevent command injection"""
        pattern = r'^[a-zA-Z0-9\s\-.,\/\\:_]+$'
        if not re.match(pattern, user_input):
            raise ValueError("Input contains invalid characters.")
        return user_input

    def generate_data(self):
        """Generate the synthetic 911 data using the synth911gen.py script"""
        if not self.validate_inputs():
            return

        try:
            # Clear the status text
            self.status_text.config(state=tk.NORMAL)
            self.status_text.delete(1.0, tk.END)
            self.status_text.config(state=tk.DISABLED)

            # Get the sanitized parameters
            num_records = self.sanitize_input(self.num_records_var.get())
            start_date = self.sanitize_input(self.start_date_var.get())
            end_date = self.sanitize_input(self.end_date_var.get())
            num_names = self.sanitize_input(self.num_names_var.get())
            locale = self.sanitize_input(self.locale_var.get())
            output_file = self.sanitize_input(self.output_file_var.get())
            agencies = self.sanitize_input(self.agencies_var.get())
            agency_probabilities = self.sanitize_input(self.agency_probabilities_var.get())

            # Update status
            self.update_status("Starting data generation...")
            self.update_status(f"Number of records: {num_records}")
            self.update_status(f"Date range: {start_date} to {end_date}")
            self.update_status(f"Locale: {locale}")
            self.update_status(f"Output file: {output_file}")
            if agencies:
                self.update_status(f"Agencies: {agencies}")
            if agency_probabilities:
                self.update_status(f"Agency Probabilities: {agency_probabilities}")

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

            # Add agencies parameter if specified
            if agencies:
                cmd.extend(["-a", agencies])
            # Add agency probabilities if specified
            if agency_probabilities:
                cmd.extend(["--agency-probabilities", agency_probabilities])

            # Run the command
            self.update_status("Running data generation process...")
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
                self.update_status("Data generation completed successfully!")
                for line in stdout.splitlines():
                    self.update_status(line)

                # Show success message
                messagebox.showinfo("Success", f"Data generation completed successfully!\nOutput saved to: {output_file}")
            else:
                # Error
                self.update_status("Error during data generation:")
                for line in stderr.splitlines():
                    self.update_status(line)

                # Show error message
                messagebox.showerror("Error", f"Data generation failed. See status for details.")
        except Exception as e:
            self.update_status(f"Error: {str(e)}")
            messagebox.showerror("Error", f"An unexpected error occurred: {str(e)}")

def main():
    root = tk.Tk()
    app = Synth911GenGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()