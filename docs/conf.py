"""Sphinx configuration for conda-sboms documentation."""

from __future__ import annotations

project = html_title = "conda-sboms"
copyright = "2026, Jannis Leidel"
author = "Jannis Leidel"

extensions = [
    "myst_parser",
    "sphinx_design",
]

myst_enable_extensions = ["colon_fence"]

html_theme = "conda_sphinx_theme"

html_theme_options = {
    "icon_links": [
        {
            "name": "GitHub",
            "url": "https://github.com/conda-incubator/conda-sboms",
            "icon": "fa-brands fa-square-github",
            "type": "fontawesome",
        },
    ],
}

html_baseurl = "https://conda-incubator.github.io/conda-sboms/"
exclude_patterns = ["_build"]
