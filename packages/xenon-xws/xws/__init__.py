"""Xenon Windows Subsystem (XWS).

XWS makes Windows programs behave like native parts of Xenon. It manages a
single per-user Windows environment on top of Wine, maps drives, keeps the
registry snapshotted, turns Windows Start Menu shortcuts into desktop app
entries, installs runtimes on demand and applies per-app compatibility
profiles. Users never need to know Wine is involved.

Licensed under the GNU GPL v3 or later. Wine itself is LGPL-2.1+.
"""

__version__ = "0.1.0"
