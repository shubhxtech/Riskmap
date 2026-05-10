"""
templates — HTML/JS templates for embedded web viewers.
Templates use %%PLACEHOLDER%% syntax for variable injection.
"""

import os

_TEMPLATE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_template(name: str) -> str:
    """Load a template file by name from the templates directory."""
    path = os.path.join(_TEMPLATE_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def render_template(name: str, **kwargs) -> str:
    """
    Load a template and replace %%KEY%% placeholders with values.
    
    Example:
        render_template("viewer.html", ACCENT="#1DA1F2", BG_DEEP="#f0f2f5")
    """
    html = load_template(name)
    for key, value in kwargs.items():
        html = html.replace(f"%%{key}%%", str(value))
    return html
