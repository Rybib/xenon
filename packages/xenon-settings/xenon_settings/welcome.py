"""First-boot Welcome: privacy choices, hardware check, a quick tour."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from . import hardware, util  # noqa: E402
from .app import _gsettings, status_icon  # noqa: E402

DONE_FLAG = Path(GLib.get_user_config_dir()) / "xenon" / "welcome-done"

KIND_TITLES = {"gpu": "Graphics", "network": "Network", "audio": "Sound",
               "bluetooth": "Bluetooth"}


def _page(icon: str, title: str, description: str) -> tuple[Gtk.Box, Gtk.Box]:
    """A centered page; returns (page, body box for extra widgets)."""
    page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER,
                   hexpand=True, vexpand=True)
    clamp = Adw.Clamp(maximum_size=560, margin_start=24, margin_end=24)
    inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    img = Gtk.Image.new_from_icon_name(icon)
    img.set_pixel_size(112 if icon == "xenon-logo" else 72)
    inner.append(img)
    t = Gtk.Label(label=title, wrap=True, justify=Gtk.Justification.CENTER)
    t.add_css_class("title-1")
    inner.append(t)
    d = Gtk.Label(label=description, wrap=True, justify=Gtk.Justification.CENTER)
    d.add_css_class("body")
    d.add_css_class("dim-label")
    inner.append(d)
    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=18)
    inner.append(body)
    clamp.set_child(inner)
    page.append(clamp)
    return page, body


class WelcomeWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Welcome to Xenon",
                         default_width=760, default_height=640)
        self.set_size_request(360, 480)
        self.carousel = Adw.Carousel(allow_scroll_wheel=False, allow_long_swipes=False,
                                     vexpand=True)
        self.carousel.connect("page-changed", self.on_page_changed)

        # 1 — welcome
        p, _ = _page("xenon-logo", "Welcome to Xenon",
                     "A fast, private desktop that runs your Linux and Windows apps. "
                     "Let's get a few things ready — it takes less than a minute.")
        self.carousel.append(p)

        # 2 — privacy
        p, body = _page("security-high-symbolic", "Your privacy",
                        "Xenon collects no telemetry, shows no ads and sends no crash "
                        "reports. These are the only choices to make:")
        group = Adw.PreferencesGroup()
        loc = Adw.SwitchRow(title="Location services",
                            subtitle="Allow apps such as Maps and Weather to ask for "
                                     "your location")
        settings = _gsettings("org.gnome.system.location")
        if settings:
            from gi.repository import Gio
            settings.bind("enabled", loc, "active", Gio.SettingsBindFlags.DEFAULT)
        group.add(loc)
        fw = Adw.ActionRow(title="Firewall",
                           subtitle="On — incoming connections are blocked. Change it "
                                    "any time in Xenon Settings.")
        fw.add_prefix(status_icon("ok" if util.firewall_enabled() else "warn"))
        group.add(fw)
        body.append(group)
        self.carousel.append(p)

        # 3 — hardware
        p, body = _page("computer-symbolic", "Hardware check",
                        "Checking that your graphics, network and sound work.")
        self.hw_group = Adw.PreferencesGroup()
        self.hw_rows: list = []
        spinner = Adw.ActionRow(title="Checking…")
        self.hw_group.add(spinner)
        self.hw_rows.append(spinner)
        body.append(self.hw_group)
        self.carousel.append(p)
        self.hw_checked = False

        # 4 — Windows apps
        p, body = _page("xenon-windows-app", "Windows apps just work",
                        "Download a Windows program from its website and open the "
                        "installer, just like on Windows. It appears in your app grid "
                        "when it's done. Games run through Vulkan for full speed.")
        tips = Adw.PreferencesGroup()
        for icon, title, sub in (
                ("system-software-install-symbolic", "Linux apps",
                 "Find thousands of apps in Software, including Flathub."),
                ("applications-games-symbolic", "Games",
                 "Steam, Epic and standalone games. Games that need kernel-level "
                 "anti-cheat (for example Valorant) cannot run."),
                ("emblem-system-symbolic", "Manage Windows apps",
                 "Uninstall programs and see compatibility in Xenon Settings.")):
            row = Adw.ActionRow(title=title, subtitle=sub)
            row.add_prefix(Gtk.Image.new_from_icon_name(icon))
            tips.add(row)
        body.append(tips)
        self.carousel.append(p)

        # 5 — done
        p, body = _page("emblem-ok-symbolic", "You're all set",
                        "Enjoy Xenon. You can find all of this again in Xenon Settings.")
        box = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
        sw = Gtk.Button(label="Open Software")
        sw.add_css_class("pill")
        sw.connect("clicked", lambda *_: (subprocess.Popen(["gnome-software"],
                                                           start_new_session=True),
                                          self.finish()))
        box.append(sw)
        done = Gtk.Button(label="Start using Xenon")
        done.add_css_class("pill")
        done.add_css_class("suggested-action")
        done.connect("clicked", lambda *_: self.finish())
        box.append(done)
        body.append(box)
        self.carousel.append(p)

        # navigation
        self.back = Gtk.Button(label="Back")
        self.back.connect("clicked", lambda *_: self.go(-1))
        self.next = Gtk.Button(label="Next")
        self.next.add_css_class("suggested-action")
        self.next.connect("clicked", lambda *_: self.go(1))
        dots = Adw.CarouselIndicatorDots(carousel=self.carousel)
        bar = Gtk.CenterBox(margin_start=12, margin_end=12, margin_top=12, margin_bottom=12)
        bar.set_start_widget(self.back)
        bar.set_center_widget(dots)
        bar.set_end_widget(self.next)

        view = Adw.ToolbarView()
        header = Adw.HeaderBar(show_title=False)
        view.add_top_bar(header)
        view.set_content(self.carousel)
        view.add_bottom_bar(bar)
        self.set_content(view)
        self.on_page_changed(self.carousel, 0)
        start = os.environ.get("XENON_WELCOME_PAGE")  # for screenshots and tests
        if start and start.isdigit():
            GLib.timeout_add(300, lambda: (self.carousel.scroll_to(
                self.carousel.get_nth_page(int(start)), False), False)[1])

    def go(self, delta: int) -> None:
        idx = int(round(self.carousel.get_position())) + delta
        idx = max(0, min(idx, self.carousel.get_n_pages() - 1))
        self.carousel.scroll_to(self.carousel.get_nth_page(idx), True)

    def on_page_changed(self, carousel, index):
        last = index >= carousel.get_n_pages() - 1
        self.back.set_visible(index > 0)
        self.next.set_visible(not last)
        if index == 2 and not self.hw_checked:
            self.hw_checked = True
            util.call_async(hardware.summary, self.show_hardware)

    def show_hardware(self, summary, error):
        for row in self.hw_rows:
            self.hw_group.remove(row)
        self.hw_rows.clear()
        summary = summary or {}
        for kind in ("gpu", "network", "audio", "bluetooth"):
            devices = summary.get(kind, [])
            if not devices:
                if kind == "bluetooth":
                    continue
                row = Adw.ActionRow(title=KIND_TITLES[kind],
                                    subtitle="Nothing detected")
                row.add_prefix(status_icon("warn"))
            else:
                worst = max(devices, key=lambda d: ("ok", "warn", "fail").index(d.status))
                row = Adw.ActionRow(
                    title=KIND_TITLES[kind],
                    subtitle=GLib.markup_escape_text(
                        "; ".join(d.name for d in devices)
                        + ("" if worst.status == "ok" else f" — {worst.detail}")))
                row.add_prefix(status_icon(worst.status))
                for action in worst.actions:
                    b = Gtk.Button(label="Install driver", valign=Gtk.Align.CENTER)
                    b.add_css_class("suggested-action")
                    b.connect("clicked", self.install_driver, action)
                    row.add_suffix(b)
            self.hw_group.add(row)
            self.hw_rows.append(row)

    def install_driver(self, button, flavour):
        button.set_sensitive(False)
        button.set_label("Installing…")

        def done(rc, out, err):
            button.set_label("Installed — restart to use it" if rc == 0 else "Failed")
            if rc == 0 and "MOK" in out:
                dialog = Adw.AlertDialog(heading="One more step at restart",
                                         body=out.strip())
                dialog.add_response("ok", "OK")
                dialog.present(self)
        util.admin(["drivers", "install", flavour], done)

    def finish(self):
        DONE_FLAG.parent.mkdir(parents=True, exist_ok=True)
        DONE_FLAG.touch()
        self.close()


class LiveWindow(Adw.ApplicationWindow):
    """Shown at login in the live session: try Xenon or install it."""

    def __init__(self, app):
        super().__init__(application=app, title="Xenon", default_width=620,
                         default_height=500)
        self.set_size_request(360, 400)
        page, body = _page("xenon-logo", "Try or install Xenon",
                           "You are running Xenon from the USB stick. Nothing on your "
                           "computer has been changed. Try it out, or install it when "
                           "you're ready.")
        box = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
        try_btn = Gtk.Button(label="Try Xenon")
        try_btn.add_css_class("pill")
        try_btn.connect("clicked", lambda *_: self.close())
        box.append(try_btn)
        install = Gtk.Button(label="Install Xenon")
        install.add_css_class("pill")
        install.add_css_class("suggested-action")
        install.connect("clicked", self.on_install)
        box.append(install)
        body.append(box)
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar(show_title=False))
        view.set_content(page)
        self.set_content(view)

    def on_install(self, *_):
        subprocess.Popen(["xenon-install"], start_new_session=True)
        self.close()


def is_live_session() -> bool:
    return Path("/run/live/medium").is_dir()
