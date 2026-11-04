"""Xenon Settings: Windows apps, Windows compatibility, graphics drivers,
privacy, updates and system information in one place."""

from __future__ import annotations

import os
import subprocess

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from . import __version__, hardware, util  # noqa: E402

STATUS_ICONS = {"ok": "emblem-ok-symbolic", "warn": "dialog-warning-symbolic",
                "fail": "dialog-error-symbolic"}
STATUS_CLASSES = {"ok": "success", "warn": "warning", "fail": "error"}


def status_icon(status: str) -> Gtk.Image:
    img = Gtk.Image.new_from_icon_name(STATUS_ICONS.get(status, "dialog-question-symbolic"))
    img.add_css_class(STATUS_CLASSES.get(status, "dim-label"))
    return img


def confirm(parent: Gtk.Widget, heading: str, body: str, action: str,
            on_yes, destructive: bool = True) -> None:
    dialog = Adw.AlertDialog(heading=heading, body=body)
    dialog.add_response("cancel", "Cancel")
    dialog.add_response("ok", action)
    dialog.set_response_appearance(
        "ok", Adw.ResponseAppearance.DESTRUCTIVE if destructive
        else Adw.ResponseAppearance.SUGGESTED)
    dialog.set_default_response("cancel")
    dialog.connect("response", lambda _d, r: on_yes() if r == "ok" else None)
    dialog.present(parent)


def clear_group(group: Adw.PreferencesGroup, rows: list) -> None:
    for row in rows:
        group.remove(row)
    rows.clear()


class Page(Adw.PreferencesPage):
    title = ""
    icon = ""
    page_id = ""

    def __init__(self, window: "SettingsWindow"):
        super().__init__(title=self.title, icon_name=self.icon)
        self.window = window

    def toast(self, text: str) -> None:
        self.window.toast(text)

    def refresh(self) -> None:
        pass


# --------------------------------------------------------------------------
class AppsPage(Page):
    title = "Windows Apps"
    icon = "xenon-windows-app"
    page_id = "apps"

    def __init__(self, window):
        super().__init__(window)
        self.set_description("Windows programs install like on Windows: download an "
                             "installer (.exe or .msi) and open it. They appear in your "
                             "app grid automatically.")
        top = Adw.PreferencesGroup()
        install = Adw.ActionRow(title="Install a Windows program…",
                                subtitle="Choose an installer you downloaded",
                                activatable=True)
        install.add_prefix(Gtk.Image.new_from_icon_name("list-add-symbolic"))
        install.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        install.connect("activated", self.on_install)
        top.add(install)
        self.add(top)

        self.group = Adw.PreferencesGroup(title="Installed")
        self.rows: list = []
        self.add(self.group)
        self.runtimes = Adw.PreferencesGroup(
            title="Components",
            description="Windows runtimes installed automatically when programs need them.")
        self.rt_rows: list = []
        self.add(self.runtimes)

    def refresh(self):
        util.xws_json(["apps", "--json", "--all"], self.populate)

    def populate(self, data, error):
        clear_group(self.group, self.rows)
        clear_group(self.runtimes, self.rt_rows)
        apps = data or []
        programs = [a for a in apps if not a.get("is_runtime")]
        comps = [a for a in apps if a.get("is_runtime")]
        if not programs:
            row = Adw.ActionRow(title="No Windows programs yet",
                                subtitle="Installed programs will be listed here.")
            row.add_prefix(Gtk.Image.new_from_icon_name("folder-download-symbolic"))
            self.group.add(row)
            self.rows.append(row)
        for app in programs:
            self.rows.append(self._app_row(app, self.group))
        for app in comps:
            row = Adw.ActionRow(title=GLib.markup_escape_text(app["name"]),
                                subtitle=GLib.markup_escape_text(app.get("version", "")))
            self.runtimes.add(row)
            self.rt_rows.append(row)
        self.runtimes.set_visible(bool(comps))

    def _app_row(self, app, group):
        parts = [p for p in (app.get("publisher"), app.get("version"),
                             _size(app.get("size_kb", 0))) if p]
        if app.get("environment") != "main":
            parts.append("own environment")
        row = Adw.ActionRow(title=GLib.markup_escape_text(app["name"]),
                            subtitle=GLib.markup_escape_text(" · ".join(parts)))
        row.add_prefix(Gtk.Image.new_from_icon_name("xenon-windows-app"))
        if app.get("install_location"):
            folder = Gtk.Button(icon_name="folder-open-symbolic", valign=Gtk.Align.CENTER,
                                tooltip_text="Open install folder")
            folder.add_css_class("flat")
            folder.connect("clicked", lambda *_: self.open_folder(app))
            row.add_suffix(folder)
        remove = Gtk.Button(label="Uninstall", valign=Gtk.Align.CENTER)
        remove.add_css_class("destructive-action")
        remove.connect("clicked", lambda *_: self.uninstall(app))
        row.add_suffix(remove)
        group.add(row)
        return row

    def open_folder(self, app):
        prefix =os.path.expanduser("~/.local/share/xenon/windows" if app["environment"] == "main"
                                    else f"~/.local/share/xenon/isolated/{app['environment']}")
        loc = app["install_location"]
        if len(loc) > 2 and loc[1] == ":":
            path = os.path.join(prefix, "dosdevices", loc[0].lower() + ":",
                                *[p for p in loc[2:].replace("\\", "/").split("/") if p])
            util.open_uri(GLib.filename_to_uri(os.path.realpath(path)))

    def uninstall(self, app):
        def go():
            self.toast(f"Uninstalling {app['name']}…")
            util.run_async(["xws", "uninstall", app["id"]], lambda rc, out, err: (
                self.toast(f"{app['name']} was uninstalled" if rc == 0
                           else f"{app['name']} was not uninstalled"),
                self.refresh()))
        confirm(self, f"Uninstall {app['name']}?",
                "The program's own uninstaller will open. Your documents are kept.",
                "Uninstall", go)

    def on_install(self, *_):
        dialog = Gtk.FileDialog(title="Choose a Windows installer")
        filt = Gtk.FileFilter(name="Windows programs and installers")
        for pattern in ("*.exe", "*.EXE", "*.msi", "*.MSI"):
            filt.add_pattern(pattern)
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(filt)
        dialog.set_filters(store)
        downloads = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
        if downloads:
            dialog.set_initial_folder(Gio.File.new_for_path(downloads))

        def chosen(dlg, result):
            try:
                f = dlg.open_finish(result)
            except GLib.Error:
                return
            subprocess.Popen(["xws", "run", f.get_path()], start_new_session=True)
            self.toast("Starting installer…")
        dialog.open(self.window, None, chosen)


def _size(kb: int) -> str:
    if not kb:
        return ""
    for unit in ("KB", "MB", "GB"):
        if kb < 1024:
            return f"{kb:.0f} {unit}"
        kb /= 1024
    return f"{kb:.1f} TB"


# --------------------------------------------------------------------------
class CompatPage(Page):
    title = "Windows Compatibility"
    icon = "applications-games-symbolic"
    page_id = "compat"

    def __init__(self, window):
        super().__init__(window)
        self.loading = True
        g = Adw.PreferencesGroup(title="Graphics and games")
        self.switches = {}
        for key, title, sub in (
                ("dxvk", "DirectX 8–11 via Vulkan (DXVK)",
                 "Fast DirectX for games and creative apps"),
                ("vkd3d_proton", "DirectX 12 via Vulkan (VKD3D-Proton)",
                 "Needed by most recent games"),
                ("gamemode", "Game performance mode",
                 "Prioritize games while they run (GameMode)"),
                ("mangohud", "Performance overlay",
                 "Show FPS and GPU load in games (MangoHud)")):
            row = Adw.SwitchRow(title=title, subtitle=sub)
            row.connect("notify::active", self.on_switch, key)
            g.add(row)
            self.switches[key] = row
        self.add(g)

        g = Adw.PreferencesGroup(title="Behaviour")
        for key, title, sub in (
                ("auto_runtimes", "Install components automatically",
                 "Visual C++, DirectX extras and similar, downloaded from Microsoft "
                 "when a program needs them"),
                ("compat_profiles", "Apply known fixes",
                 "Use community compatibility profiles for specific programs")):
            row = Adw.SwitchRow(title=title, subtitle=sub)
            row.connect("notify::active", self.on_switch, key)
            g.add(row)
            self.switches[key] = row
        self.graphics = Adw.ComboRow(
            title="Window system for Windows apps",
            subtitle="XWayland is the most compatible; native Wayland is newer",
            model=Gtk.StringList.new(["XWayland (recommended)", "Native Wayland"]))
        self.graphics.connect("notify::selected", self.on_graphics)
        g.add(self.graphics)
        self.winver_values = ["win11", "win10", "win81", "win7"]
        self.winver = Adw.ComboRow(
            title="Reported Windows version",
            model=Gtk.StringList.new(["Windows 11", "Windows 10", "Windows 8.1",
                                      "Windows 7"]))
        self.winver.connect("notify::selected", self.on_winver)
        g.add(self.winver)
        self.add(g)

        self.health = Adw.PreferencesGroup(title="Health check")
        recheck = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Check again",
                             valign=Gtk.Align.CENTER)
        recheck.add_css_class("flat")
        recheck.connect("clicked", lambda *_: self.load_health())
        self.health.set_header_suffix(recheck)
        self.health_rows: list = []
        self.add(self.health)

        self.profiles = Adw.PreferencesGroup(
            title="Known fixes",
            description="Compatibility profiles applied automatically. Ratings: platinum "
                        "works perfectly … broken does not work; untested means not yet "
                        "verified on Xenon.")
        self.profile_rows: list = []
        self.add(self.profiles)

        danger = Adw.PreferencesGroup(title="Troubleshooting")
        stop = Adw.ActionRow(title="Stop all Windows programs",
                             subtitle="Closes every running Windows program immediately")
        b = Gtk.Button(label="Stop", valign=Gtk.Align.CENTER)
        b.connect("clicked", lambda *_: util.run_async(
            ["xws", "--no-gui", "kill"], lambda *a: self.toast("Windows programs stopped")))
        stop.add_suffix(b)
        danger.add(stop)
        reset = Adw.ActionRow(title="Reset Windows environment",
                              subtitle="Removes all installed Windows programs and their "
                                       "settings")
        b = Gtk.Button(label="Reset…", valign=Gtk.Align.CENTER)
        b.add_css_class("destructive-action")
        b.connect("clicked", self.on_reset)
        reset.add_suffix(b)
        danger.add(reset)
        self.add(danger)

    def refresh(self):
        self.loading = True
        util.run_async(["xws", "--no-gui", "config"], self.load_config)
        self.load_health()
        util.xws_json(["profiles", "--json"], self.load_profiles)

    def load_config(self, rc, out, err):
        values = {}
        for line in out.splitlines():
            if " = " in line:
                k, v = line.split(" = ", 1)
                values[k.strip()] = v.strip().strip("'\"")
        for key, row in self.switches.items():
            row.set_active(values.get(key, "True") == "True")
        self.graphics.set_selected(1 if values.get("graphics_driver") == "wayland" else 0)
        wv = values.get("windows_version", "win10")
        self.winver.set_selected(self.winver_values.index(wv)
                                 if wv in self.winver_values else 1)
        self.loading = False

    def _set(self, key, value):
        if self.loading:
            return
        util.run_async(["xws", "--no-gui", "config", key, str(value).lower()
                        if isinstance(value, bool) else str(value)],
                       lambda rc, o, e: self.toast("Saved" if rc == 0 else f"Error: {e}"))

    def on_switch(self, row, _pspec, key):
        self._set(key, row.get_active())

    def on_graphics(self, row, _pspec):
        self._set("graphics_driver", "wayland" if row.get_selected() == 1 else "x11")

    def on_winver(self, row, _pspec):
        self._set("windows_version", self.winver_values[row.get_selected()])

    def load_health(self):
        util.xws_json(["doctor", "--json"], self.show_health)

    def show_health(self, data, error):
        clear_group(self.health, self.health_rows)
        for check in data or []:
            row = Adw.ActionRow(title=GLib.markup_escape_text(check["title"]),
                                subtitle=GLib.markup_escape_text(check["detail"]))
            row.add_prefix(status_icon(check["status"]))
            self.health.add(row)
            self.health_rows.append(row)
        if not data:
            row = Adw.ActionRow(title="Could not run the health check",
                                subtitle=GLib.markup_escape_text(str(error or "")[:200]))
            row.add_prefix(status_icon("fail"))
            self.health.add(row)
            self.health_rows.append(row)

    def load_profiles(self, data, error):
        clear_group(self.profiles, self.profile_rows)
        for p in data or []:
            row = Adw.ExpanderRow(title=GLib.markup_escape_text(p["name"]),
                                  subtitle=p["rating"].capitalize())
            notes = " ".join((p.get("notes") or "").split())
            if p.get("isolated"):
                notes += " Runs in its own environment."
            if p.get("runtimes"):
                notes += " Components: " + ", ".join(p["runtimes"]) + "."
            label = Gtk.Label(label=notes.strip() or "No notes.", wrap=True, xalign=0,
                              margin_start=12, margin_end=12, margin_top=8,
                              margin_bottom=8)
            label.add_css_class("dim-label")
            row.add_row(label)
            self.profiles.add(row)
            self.profile_rows.append(row)

    def on_reset(self, *_):
        confirm(self, "Reset the Windows environment?",
                "Every installed Windows program and its settings will be deleted. "
                "Files in your Documents, Downloads and Desktop folders are kept.",
                "Reset", lambda: util.run_async(
                    ["xws", "--no-gui", "reset", "--yes"],
                    lambda rc, o, e: self.toast("Windows environment reset" if rc == 0
                                                else "Reset failed")))


# --------------------------------------------------------------------------
class DriversPage(Page):
    title = "Graphics & Drivers"
    icon = "video-display-symbolic"
    page_id = "drivers"

    def __init__(self, window):
        super().__init__(window)
        self.group = Adw.PreferencesGroup(title="Graphics cards")
        self.rows: list = []
        self.add(self.group)
        info = Adw.PreferencesGroup(
            title="About drivers",
            description="AMD and Intel graphics work out of the box with the open-source "
                        "Mesa drivers, which Xenon keeps up to date. NVIDIA cards start "
                        "with the basic open-source driver; install NVIDIA's driver here "
                        "for full gaming performance.")
        fw = Adw.ActionRow(title="Device firmware updates",
                           subtitle="BIOS and device firmware updates appear in Software",
                           activatable=True)
        fw.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        fw.connect("activated", lambda *_: subprocess.Popen(
            ["gnome-software", "--mode=updates"], start_new_session=True))
        info.add(fw)
        self.add(info)

    def refresh(self):
        util.call_async(hardware.gpus, self.populate)

    def populate(self, gpus, error):
        clear_group(self.group, self.rows)
        for gpu in gpus or []:
            row = Adw.ActionRow(title=GLib.markup_escape_text(gpu.name),
                                subtitle=GLib.markup_escape_text(gpu.detail))
            row.add_prefix(status_icon(gpu.status))
            for action in gpu.actions:
                b = Gtk.Button(label="Install NVIDIA driver", valign=Gtk.Align.CENTER)
                b.add_css_class("suggested-action")
                b.connect("clicked", self.install_nvidia, action)
                row.add_suffix(b)
            self.group.add(row)
            self.rows.append(row)
        if not gpus:
            row = Adw.ActionRow(title="No graphics card detected")
            self.group.add(row)
            self.rows.append(row)

    def install_nvidia(self, button, flavour):
        def go():
            button.set_sensitive(False)
            button.set_label("Installing…")
            util.admin(["drivers", "install", flavour], self.installed)
        open_note = (" This uses NVIDIA's open kernel modules, recommended for your card."
                     if flavour == "nvidia-open" else "")
        confirm(self, "Install the NVIDIA driver?",
                "The driver is downloaded from Debian's archive and needs an internet "
                "connection. A restart is needed afterwards." + open_note,
                "Install", go, destructive=False)

    def installed(self, rc, out, err):
        msg = out.strip().splitlines()[-1] if out.strip() else ""
        if rc == 0:
            body = "Restart your computer to start using it."
            if "MOK" in out:
                body = out.strip()
            dialog = Adw.AlertDialog(heading="NVIDIA driver installed", body=body)
            dialog.add_response("ok", "OK")
            dialog.present(self)
        else:
            self.toast(f"Installation failed {msg}".strip())
        self.refresh()


# --------------------------------------------------------------------------
class PrivacyPage(Page):
    title = "Privacy & Security"
    icon = "security-high-symbolic"
    page_id = "privacy"

    def __init__(self, window):
        super().__init__(window)
        g = Adw.PreferencesGroup(title="Your data")
        row = Adw.ActionRow(title="No telemetry",
                            subtitle="Xenon does not collect or send usage data, crash "
                                     "reports or identifiers. There is nothing to turn off.")
        row.add_prefix(status_icon("ok"))
        g.add(row)
        self.location = Adw.SwitchRow(title="Location services",
                                      subtitle="Let apps ask for your location")
        self.settings_loc = _gsettings("org.gnome.system.location")
        if self.settings_loc:
            self.settings_loc.bind("enabled", self.location, "active",
                                   Gio.SettingsBindFlags.DEFAULT)
        g.add(self.location)
        self.add(g)

        g = Adw.PreferencesGroup(title="Protection")
        self.firewall = Adw.SwitchRow(title="Firewall",
                                      subtitle="Block incoming connections from the network")
        self.firewall.set_active(util.firewall_enabled())
        self.firewall.connect("notify::active", self.on_firewall)
        g.add(self.firewall)
        self.sb = Adw.ActionRow(title="Secure Boot")
        g.add(self.sb)
        self.enc = Adw.ActionRow(title="Disk encryption")
        g.add(self.enc)
        self.add(g)
        self._busy = False

    def refresh(self):
        sb = hardware.secure_boot()
        self.sb.set_subtitle({True: "On: only signed boot software can start",
                              False: "Off (can be enabled in your PC's firmware settings)",
                              None: "Not available (legacy BIOS boot)"}[sb])
        util.run_async(["lsblk", "-rno", "TYPE"], lambda rc, out, err: self.enc.set_subtitle(
            "On: your files are encrypted on disk" if "crypt" in out.split()
            else "Off: can only be enabled when installing Xenon"))
        self._busy = True
        self.firewall.set_active(util.firewall_enabled())
        self._busy = False

    def on_firewall(self, row, _pspec):
        if self._busy:
            return
        want = row.get_active()

        def done(rc, out, err):
            if rc != 0:
                self._busy = True
                row.set_active(not want)
                self._busy = False
                self.toast("Firewall setting was not changed")
            else:
                self.toast("Firewall on" if want else "Firewall off")
        util.admin(["firewall", "on" if want else "off"], done)


def _gsettings(schema: str) -> Gio.Settings | None:
    source = Gio.SettingsSchemaSource.get_default()
    if source and source.lookup(schema, True):
        return Gio.Settings.new(schema)
    return None


# --------------------------------------------------------------------------
class UpdatesPage(Page):
    title = "Updates"
    icon = "software-update-available-symbolic"
    page_id = "updates"

    def __init__(self, window):
        super().__init__(window)
        g = Adw.PreferencesGroup()
        self.auto = Adw.SwitchRow(title="Automatic security updates",
                                  subtitle="Install security fixes quietly in the background")
        self.auto.connect("notify::active", self.on_auto)
        g.add(self.auto)
        check = Adw.ActionRow(title="Check for updates",
                              subtitle="Apps, system and firmware updates in Software",
                              activatable=True)
        check.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        check.connect("activated", lambda *_: subprocess.Popen(
            ["gnome-software", "--mode=updates"], start_new_session=True))
        g.add(check)
        self.add(g)
        self._busy = False

    def refresh(self):
        self._busy = True
        self.auto.set_active(util.auto_updates_enabled())
        self._busy = False

    def on_auto(self, row, _pspec):
        if self._busy:
            return
        want = row.get_active()

        def done(rc, out, err):
            if rc != 0:
                self._busy = True
                row.set_active(not want)
                self._busy = False
                self.toast("Setting was not changed")
        util.admin(["updates", "on" if want else "off"], done)


# --------------------------------------------------------------------------
class AboutPage(Page):
    title = "About"
    icon = "help-about-symbolic"
    page_id = "about"

    def __init__(self, window):
        super().__init__(window)
        header = Adw.PreferencesGroup()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                      halign=Gtk.Align.CENTER, margin_top=12, margin_bottom=12)
        logo = Gtk.Image.new_from_icon_name("xenon-logo")
        logo.set_pixel_size(96)
        box.append(logo)
        osr = util.os_release()
        name = Gtk.Label(label=osr.get("PRETTY_NAME", "Xenon"))
        name.add_css_class("title-1")
        box.append(name)
        tag = Gtk.Label(label="Fast, private, and runs your Windows apps.")
        tag.add_css_class("dim-label")
        box.append(tag)
        header.add(box)
        self.add(header)
        self.info = Adw.PreferencesGroup(title="System")
        self.rows: list = []
        self.add(self.info)
        links = Adw.PreferencesGroup(title="Project")
        for title, uri in (("Website and source code", osr.get("HOME_URL", "")),
                           ("Report a problem", osr.get("BUG_REPORT_URL", ""))):
            if not uri:
                continue
            row = Adw.ActionRow(title=title, subtitle=uri, activatable=True)
            row.add_suffix(Gtk.Image.new_from_icon_name("adw-external-link-symbolic"))
            row.connect("activated", lambda _r, u=uri: util.open_uri(u))
            links.add(row)
        self.add(links)

    def refresh(self):
        def gather():
            gpus = ", ".join(g.name for g in hardware.gpus()) or "Unknown"
            wine = ""
            try:
                wine = subprocess.run(["xws", "--no-gui", "doctor", "--json"],
                                      capture_output=True, text=True, timeout=30).stdout
                import json
                wine = next((c["detail"] for c in json.loads(wine) if c["id"] == "wine"), "")
            except (OSError, ValueError, subprocess.TimeoutExpired):
                pass
            return [("Processor", hardware.cpu_name()),
                    ("Memory", f"{hardware.memory_gib():.1f} GiB"),
                    ("Graphics", gpus),
                    ("Linux kernel", util.kernel_release()),
                    ("Windows subsystem", wine or "Not installed"),
                    ("Xenon Settings", __version__)]

        def show(items, error):
            clear_group(self.info, self.rows)
            for k, v in items or []:
                row = Adw.ActionRow(title=k, subtitle=GLib.markup_escape_text(v))
                row.add_css_class("property")
                self.info.add(row)
                self.rows.append(row)
        util.call_async(gather, show)


PAGES = [AppsPage, CompatPage, DriversPage, PrivacyPage, UpdatesPage, AboutPage]


class SettingsWindow(Adw.ApplicationWindow):
    def __init__(self, app, start_page: str | None = None):
        super().__init__(application=app, title="Xenon Settings",
                         default_width=980, default_height=720)
        self.set_size_request(360, 480)
        self.toasts = Adw.ToastOverlay()
        self.pages = [cls(self) for cls in PAGES]
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        for page in self.pages:
            self.stack.add_named(page, page.page_id)

        listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        listbox.add_css_class("navigation-sidebar")
        for page in self.pages:
            row = Gtk.Box(spacing=12, margin_top=6, margin_bottom=6, margin_start=6)
            row.append(Gtk.Image.new_from_icon_name(page.icon))
            row.append(Gtk.Label(label=page.title, xalign=0))
            listbox.append(row)
        listbox.connect("row-selected", self.on_select)

        sidebar = Adw.ToolbarView()
        sidebar.add_top_bar(Adw.HeaderBar(title_widget=Adw.WindowTitle(title="Xenon")))
        sidebar.set_content(Gtk.ScrolledWindow(child=listbox,
                                               hscrollbar_policy=Gtk.PolicyType.NEVER))
        self.content_title = Adw.WindowTitle()
        content = Adw.ToolbarView()
        content.add_top_bar(Adw.HeaderBar(title_widget=self.content_title))
        content.set_content(self.stack)

        self.split = Adw.NavigationSplitView(
            sidebar=Adw.NavigationPage(title="Xenon", child=sidebar),
            content=Adw.NavigationPage(title="Settings", child=content))
        self.toasts.set_child(self.split)
        self.set_content(self.toasts)

        bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 640sp"))
        bp.add_setter(self.split, "collapsed", True)
        self.add_breakpoint(bp)

        index = next((i for i, p in enumerate(self.pages) if p.page_id == start_page), 0)
        listbox.select_row(listbox.get_row_at_index(index))

    def on_select(self, _listbox, row):
        if row is None:
            return
        page = self.pages[row.get_index()]
        self.stack.set_visible_child(page)
        self.content_title.set_title(page.title)
        self.split.set_show_content(True)
        page.refresh()

    def toast(self, text: str) -> None:
        self.toasts.add_toast(Adw.Toast(title=GLib.markup_escape_text(text), timeout=3))
