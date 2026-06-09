"""
Web interface for Synth911Gen2.

This module provides a Flask-based web application for generating synthetic 911 dispatch data
via a browser interface. It includes input validation, form handling, and result display.
"""

from flask import Flask, request, render_template_string, jsonify
import subprocess
import os
from datetime import datetime
import re

app = Flask(__name__)

# Common locales
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

def sanitize_input(user_input):
    pattern = r'^[a-zA-Z0-9\s\-.,\/\\:_]+$'
    if not re.match(pattern, user_input):
        raise ValueError("Input contains invalid characters.")
    return user_input

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        try:
            num_records = request.form.get('num_records', '10000')
            start_date = request.form.get('start_date', '2024-01-01')
            end_date = request.form.get('end_date', '2024-12-31')
            num_names = request.form.get('num_names', '8')
            locale = request.form.get('locale', 'en_US')
            output_file = request.form.get('output_file', 'computer_aided_dispatch.csv')
            agencies = request.form.get('agencies', '')
            agency_probabilities = request.form.get('agency_probabilities', '')

            # Sanitize required inputs
            sanitize_input(num_records)
            sanitize_input(start_date)
            sanitize_input(end_date)
            sanitize_input(num_names)
            sanitize_input(locale)
            sanitize_input(output_file)

            # Only sanitize agencies if it's not empty
            if agencies.strip():
                sanitize_input(agencies)

            # Only sanitize agency probabilities if provided
            if agency_probabilities.strip():
                sanitize_input(agency_probabilities)

            # Build command
            script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "synth911gen.py")
            cmd = [
                "python",
                script_path,
                "-n", num_records,
                "-s", start_date,
                "-e", end_date,
                "--num-names", num_names,
                "-l", locale,
                "-o", output_file
            ]

            # Only add agencies argument if it's not empty
            if agencies.strip():
                cmd.extend(["-a", agencies])

            # Add agency probabilities argument if provided
            if agency_probabilities.strip():
                cmd.extend(["--agency-probabilities", agency_probabilities])

            # Run process
            result = subprocess.run(
                cmd,
                shell=False,
                check=True,
                text=True,
                capture_output=True
            )

            return render_template_string('''
                <html>
                <head><title>Synth 911 Data Generator</title></head>
                <body>
                <h1>Generation Complete</h1>
                <pre>{{ result.stdout }}</pre>
                </body>
                </html>
            ''', result=result)

        except Exception as e:
            return f"Error: {str(e)}", 500

    # Get locale options for template
    locales = [(code, display) for code, display in LOCALE_OPTIONS]
    
    return render_template_string('''
        <html>
        <head>
            <title>Synth 911 Data Generator</title>
            <style>
                body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
                form { background: #f0f0f0; padding: 20px; border-radius: 8px; }
                .form-group { margin-bottom: 15px; }
                label { display: block; margin-bottom: 5px; }
                input, select { width: 100%; padding: 8px; margin-bottom: 10px; }
                button { padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; }
                button:hover { background: #0056b3; }
            </style>
        </head>
        <body>
            <h1>Synth 911 Data Generator</h1>
            <form method="post">
                <div class="form-group">
                    <label for="num_records">Number of Records:</label>
                    <input type="number" id="num_records" name="num_records" required
                           value="10000" min="1">
                </div>
                
                <div class="form-group">
                    <label for="start_date">Start Date (YYYY-MM-DD):</label>
                    <input type="date" id="start_date" name="start_date" required
                           value="2024-01-01">
                </div>
                
                <div class="form-group">
                    <label for="end_date">End Date (YYYY-MM-DD):</label>
                    <input type="date" id="end_date" name="end_date" required
                           value="2024-12-31">
                </div>
                
                <div class="form-group">
                    <label for="num_names">Names per Shift:</label>
                    <input type="number" id="num_names" name="num_names" required
                           value="8" min="1">
                </div>
                
                <div class="form-group">
                    <label for="locale">Locale:</label>
                    <select id="locale" name="locale">
                        {% for code, display in locales %}
                        <option value="{{ code }}">{{ display }}</option>
                        {% endfor %}
                    </select>
                </div>
                
                <div class="form-group">
                    <label for="agencies">Agencies (comma-separated, e.g., LAW,FIRE):</label>
                    <input type="text" id="agencies" name="agencies">
                </div>
                
                <div class="form-group">
                    <label for="agency_probabilities">Agency Probabilities (comma-separated, e.g., 0.7,0.2,0.1):</label>
                    <input type="text" id="agency_probabilities" name="agency_probabilities">
                </div>
                
                <div class="form-group">
                    <label for="output_file">Output File:</label>
                    <input type="text" id="output_file" name="output_file" required
                           value="computer_aided_dispatch.csv">
                </div>
                
                <button type="submit">Generate Data</button>
            </form>
        </body>
        </html>
    ''', locales=locales)

if __name__ == '__main__':
    app.run(host='localhost', port=8008)