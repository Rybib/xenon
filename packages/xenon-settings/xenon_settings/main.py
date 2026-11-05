"""Entry point: `xenon-settings [--page ID]` or `xenon-settings --welcome`."""

from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib  # noqa: E402

APP_ID = "org.xenon.Settings"


class XenonApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.add_main_option("welcome", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             "Show the first-boot welcome", None)
        self.add_main_option("autostart", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             "Show the welcome only if it has not been completed", None)
        self.add_main_option("page", 0, GLib.OptionFlags.NONE, GLib.OptionArg.STRING,
                             "Open a page: apps, compat, drivers, privacy, updates, about",
                             "ID")

    def do_command_line(self, command_line):
        opts = command_line.get_options_dict().end().unpack()
        if opts.get("welcome") or opts.get("autostart"):
            from .welcome import DONE_FLAG, LiveWindow, WelcomeWindow, is_live_session
            if opts.get("autostart") and "xenon.selftest-gui=" in open("/proc/cmdline").read():
                return 0
            if opts.get("autostart") and is_live_session():
                win = LiveWindow(self)
            elif opts.get("autostart") and DONE_FLAG.exists():
                return 0
            else:
                win = WelcomeWindow(self)
        else:
            from .app import SettingsWindow
            win = SettingsWindow(self, opts.get("page"))
        win.present()
        return 0


def main() -> int:
    return XenonApp().run(sys.argv)
