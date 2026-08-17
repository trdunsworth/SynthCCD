"""Sphinx configuration for the SynthCCD documentation site.

Source lives in ``docsrc/`` (``docs/`` is reserved for read-only v2-era
reference material). Build with:

    uv run python scripts/build_docs.py
"""

from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _metadata_version
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Make the package importable even when the venv install is not editable.
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

project = "SynthCCD"
author = "Tony Dunsworth"
copyright = "2026, Tony Dunsworth"

try:
    release = _metadata_version("SynthCCD")
except PackageNotFoundError:  # package not installed; fall back to pyproject value
    release = "0.9.5"
version = release.split("+")[0]

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

templates_path: list[str] = []
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# -- Options for HTML output -------------------------------------------------
html_theme = "bizstyle"
html_baseurl = "https://dunsworth-mann.com/SynthCCD/"
html_static_path = ["_static"]
html_title = "SynthCCD"

# -- Options for autodoc ------------------------------------------------------
autodoc_default_options = {
    "members": True,
    "show-inheritance": True,
    "member-order": "bysource",
}
autodoc_typehints = "description"

# -- Options for napoleon ------------------------------------------------------
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = False
