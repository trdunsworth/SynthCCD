#!/usr/bin/env python3
"""Generate a PDF for copyright submission with syntax highlighting."""

from __future__ import annotations

import re
from pathlib import Path

from fpdf import FPDF


class CopyrightPDF(FPDF):
    def __init__(self):
        super().__init__("P", "mm", "Letter")
        self.set_auto_page_break(auto=True, margin=20)
        self.add_font("DejaVu", "", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf")
        self.add_font("DejaVu", "B", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf")
        self.add_font("DejaVu", "I", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf")
        self.add_font("DejaVu", "BI", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf")
        self.add_font("DejaVuMono", "", "/System/Library/Fonts/Supplemental/Courier New.ttf")
        self.add_font("DejaVuMono", "B", "/System/Library/Fonts/Supplemental/Courier New Bold.ttf")
        self.set_margins(15, 15, 15)

    def header(self):
        if self.page_no() > 1:
            self.set_font("DejaVu", "I", 8)
            self.cell(0, 5, "SynthCCD - Copyright Submission", align="C")
            self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font("DejaVu", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def add_title_page(self, title: str, subtitle: str = ""):
        self.add_page()
        self.ln(50)
        self.set_font("DejaVu", "B", 28)
        self.multi_cell(0, 12, title, align="C")
        if subtitle:
            self.ln(10)
            self.set_font("DejaVu", "", 16)
            self.multi_cell(0, 10, subtitle, align="C")
        self.ln(20)
        self.set_font("DejaVu", "", 12)
        self.cell(0, 8, "Generated for Copyright Office Submission", align="C")
        self.ln(8)
        self.cell(0, 8, "SynthCCD - Synthetic 911 CAD Data Generator", align="C")


def clean_text(text: str) -> str:
    """Clean text for PDF - handle special characters."""
    text = text.replace('\u2014', ' -- ')
    text = text.replace('\u2013', '-')
    text = text.replace('\u2018', "'")
    text = text.replace('\u2019', "'")
    text = text.replace('\u201c', '"')
    text = text.replace('\u201d', '"')
    text = text.replace('\u2026', '...')
    text = text.replace('\u2022', '-')
    text = text.replace('\u25cf', '-')
    text = text.replace('\u25aa', '-')
    text = text.replace('\u2713', '[x]')
    text = text.replace('\u2717', '[ ]')
    text = text.replace('\u00a0', ' ')
    text = text.replace('\u00b7', '.')
    return text


def add_markdown(pdf: CopyrightPDF, content: str):
    """Add markdown content to PDF with basic formatting."""
    for line in content.split('\n'):
        line = clean_text(line)

        if not line.strip():
            pdf.ln(4)
            continue

        if line.startswith('# '):
            pdf.set_font("DejaVu", "B", 18)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 10, line[2:])
            pdf.ln(3)
        elif line.startswith('## '):
            pdf.set_font("DejaVu", "B", 15)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 8, line[3:])
            pdf.ln(2)
        elif line.startswith('### '):
            pdf.set_font("DejaVu", "B", 13)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 7, line[4:])
            pdf.ln(2)
        elif line.startswith('#### '):
            pdf.set_font("DejaVu", "B", 11)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 6, line[5:])
            pdf.ln(1)
        elif line.startswith('- ') or line.startswith('* '):
            pdf.set_font("DejaVu", "", 10)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 5, "  - " + line[2:])
        elif line.startswith('  - ') or line.startswith('  * '):
            pdf.set_font("DejaVu", "", 9)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 5, "    - " + line[4:])
        elif '|' in line and line.count('|') > 1 and not line.strip().startswith('|---'):
            pdf.set_font("DejaVuMono", "", 8)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 4, line)
        elif line.strip().startswith('```'):
            pdf.set_font("DejaVuMono", "", 8)
        else:
            pdf.set_font("DejaVu", "", 10)
            pdf.set_x(pdf.l_margin)
            formatted = re.sub(r'\*\*(.+?)\*\*', r'\1', line)
            formatted = re.sub(r'\*(.+?)\*', r'\1', formatted)
            formatted = re.sub(r'`(.+?)`', r'\1', formatted)
            pdf.multi_cell(0, 5, formatted)


def add_code_file(pdf: CopyrightPDF, filepath: Path, title: str):
    """Add a code file with line numbers to PDF."""
    pdf.add_page()
    pdf.set_font("DejaVu", "B", 14)
    pdf.multi_cell(0, 8, title)
    pdf.ln(3)

    content = clean_text(filepath.read_text(encoding='utf-8'))

    pdf.set_font("DejaVuMono", "", 7.5)
    line_height = 3.5
    line_num = 1
    for line in content.split('\n'):
        pdf.set_x(pdf.l_margin)
        if line.strip():
            pdf.set_font("DejaVuMono", "", 7)
            pdf.set_text_color(128, 128, 128)
            pdf.cell(12, line_height, f"{line_num:4d} ", align="R")
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("DejaVuMono", "", 7.5)
            pdf.multi_cell(0, line_height, line)
        else:
            pdf.cell(12, line_height, f"{line_num:4d} ", align="R")
            pdf.ln(line_height)
        line_num += 1

    pdf.set_text_color(0, 0, 0)


def main():
    base_path = Path("/Users/trdunsworth/Documents/GitHub/synth911gen3")
    output_path = base_path / "output" / "SynthCCD.pdf"
    output_path.parent.mkdir(exist_ok=True)

    pdf = CopyrightPDF()
    pdf.alias_nb_pages()

    pdf.add_title_page(
        "SynthCCD",
        "Synthetic 911 CAD Incident and Hourly Phone-Center Data Generator\n\nCopyright Submission Package"
    )

    pdf.add_page()
    pdf.set_font("DejaVu", "B", 16)
    pdf.cell(0, 10, "Table of Contents", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    toc_items = [
        ("1.", "README.md", "Project Overview"),
        ("2.", "USERSGUIDE.md", "User Guide"),
        ("3.", "REALISMGUIDE.md", "Realism Guide"),
        ("4.", "src/synth911gen3/app.py", "Application Orchestrator"),
        ("5.", "src/synth911gen3/generators/incidents.py", "Incident Generator (Core)"),
        ("6.", "src/synth911gen3/generators/phone_metrics.py", "Phone Metrics Generator"),
        ("7.", "src/synth911gen3/cli.py", "Command-Line Interface"),
        ("8.", "src/synth911gen3/tui.py", "Textual User Interface"),
    ]

    for num, file, desc in toc_items:
        pdf.set_font("DejaVu", "B", 11)
        pdf.cell(12, 7, num)
        pdf.set_font("DejaVu", "", 11)
        pdf.cell(0, 7, f"{file} - {desc}", new_x="LMARGIN", new_y="NEXT")

    files_to_include = [
        ("README.md", "README.md - Project Overview"),
        ("USERSGUIDE.md", "USERSGUIDE.md - User Guide"),
        ("REALISMGUIDE.md", "REALISMGUIDE.md - Realism Guide"),
        ("src/synth911gen3/app.py", "src/synth911gen3/app.py - Application Orchestrator"),
        ("src/synth911gen3/generators/incidents.py", "src/synth911gen3/generators/incidents.py - Incident Generator"),
        ("src/synth911gen3/generators/phone_metrics.py", "src/synth911gen3/generators/phone_metrics.py - Phone Metrics Generator"),
        ("src/synth911gen3/cli.py", "src/synth911gen3/cli.py - Command-Line Interface"),
        ("src/synth911gen3/tui.py", "src/synth911gen3/tui.py - Textual User Interface"),
    ]

    for filepath, title in files_to_include:
        full_path = base_path / filepath
        if not full_path.exists():
            print(f"Warning: {filepath} not found, skipping")
            continue
        print(f"Processing {filepath}...")
        if filepath.endswith('.md'):
            pdf.add_page()
            pdf.set_font("DejaVu", "B", 14)
            pdf.multi_cell(0, 8, title)
            pdf.ln(3)
            add_markdown(pdf, full_path.read_text(encoding='utf-8'))
        else:
            add_code_file(pdf, full_path, title)

    pdf.output(str(output_path))
    print(f"\nPDF generated: {output_path}")
    print(f"Pages: {pdf.page_no()}")


if __name__ == "__main__":
    main()