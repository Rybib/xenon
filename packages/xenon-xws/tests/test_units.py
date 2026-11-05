"""Unit tests for XWS. Run: python3 -m pytest packages/xenon-xws/tests"""

import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xws import apps, compat, config, lnk, menu, pe, registry, runtimes, winpath  # noqa: E402

REPO = ROOT.parents[1]

SAMPLE_REG = r'''WINE REGISTRY Version 2
;; All keys relative to \\Machine

#arch=win64

[Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{A1B2}] 1730000000
#time=1db0e0e0e0e0e0e
"DisplayName"="Ableton Live 12 Suite"
"DisplayVersion"="12.1"
"Publisher"="Ableton"
"UninstallString"="MsiExec.exe /I{A1B2}"
"EstimatedSize"=dword:00200000

[Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Hidden] 1730000000
"DisplayName"="Some Component"
"SystemComponent"=dword:00000001

[Software\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Steam] 1730000000
"DisplayName"="Steam"
"UninstallString"="C:\\Program Files (x86)\\Steam\\uninstall.exe"
"InstallLocation"=str(2):"C:\\Program Files (x86)\\Steam"
"Escapes"="tab\there \"quoted\" caf\x00e9"
"Multi"=str(7):"one\0two\0"
"Blob"=hex:01,02,\
  03,04

[Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Wine Mono Runtime] 1730000000
"DisplayName"="Wine Mono Runtime"
'''


def test_registry_parse_values():
    reg = registry.parse_reg(SAMPLE_REG)
    steam = reg[r"Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Steam"]
    assert steam["UninstallString"].data == r"C:\Program Files (x86)\Steam\uninstall.exe"
    assert steam["InstallLocation"].type == "expand_sz"
    assert steam["Escapes"].data == 'tab\there "quoted" café'
    assert steam["Multi"].data == ["one", "two"]
    assert steam["Blob"].data == b"\x01\x02\x03\x04"
    ableton = reg[r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{A1B2}"]
    assert registry.get_dword(ableton, "estimatedsize") == 0x200000


def test_apps_from_registry(tmp_path):
    (tmp_path / "system.reg").write_text(SAMPLE_REG)
    (tmp_path / "user.reg").write_text("WINE REGISTRY Version 2\n")
    from xws.prefix import Prefix
    prefix = Prefix(tmp_path, "main")
    found = apps.list_apps([prefix])
    assert [a.name for a in found] == ["Ableton Live 12 Suite", "Steam"]
    with_rt = apps.list_apps([prefix], include_runtimes=True)
    assert any(a.is_runtime and a.name == "Wine Mono Runtime" for a in with_rt)
    ableton = found[0]
    assert apps.uninstall_command(ableton) == ["msiexec", "/x", "{A1B2}"]
    assert apps.uninstall_command(found[1]) == [r"C:\Program Files (x86)\Steam\uninstall.exe"]
    assert apps.size_human(ableton.size_kb) == "2 GB"


@pytest.mark.parametrize("cmdline,expected", [
    (r'"C:\Program Files\A\u.exe" /S', [r"C:\Program Files\A\u.exe", "/S"]),
    (r'a "b c" d', ["a", "b c", "d"]),
    (r'a\\\"b', ['a\\"b']),
    (r'"x""y"', ['x"y']),
    ("", []),
])
def test_split_command_line(cmdline, expected):
    assert winpath.split_command_line(cmdline) == expected


def test_split_uninstall_unquoted():
    assert winpath.split_uninstall_string(
        r"C:\Program Files\My App\unins000.exe /SILENT") == \
        [r"C:\Program Files\My App\unins000.exe", "/SILENT"]


def test_winpath_roundtrip(tmp_path):
    (tmp_path / "drive_c" / "Program Files" / "Foo").mkdir(parents=True)
    (tmp_path / "dosdevices").mkdir()
    (tmp_path / "dosdevices" / "c:").symlink_to("../drive_c")
    unix = winpath.to_unix(tmp_path, r"c:\PROGRAM FILES\foo\app.exe")
    assert unix == tmp_path / "drive_c" / "Program Files" / "Foo" / "app.exe"
    assert winpath.to_windows(tmp_path, unix) == r"C:\Program Files\Foo\app.exe"


WINE_EXEC = (r'env WINEPREFIX="/home/u/.local/share/xenon/windows" wine-stable '
             r'C:\\\\ProgramData\\\\Microsoft\\\\Windows\\\\Start\\ Menu\\\\Programs\\\\'
             r'Foo\\\\Foo.lnk')


def test_menu_rewrite_exec():
    new = menu.rewrite_exec(WINE_EXEC)
    assert new.startswith('xws exec --prefix "/home/u/.local/share/xenon/windows" -- C:')
    assert menu.rewrite_exec('env WINEPREFIX="/p" /opt/wine-stable/bin/wine start /x') \
        == 'xws exec --prefix "/p" -- start /x'
    assert menu.rewrite_exec("firefox %u") is None


def test_menu_shortcut_of():
    prefix, win = menu.shortcut_of(WINE_EXEC)
    assert str(prefix) == "/home/u/.local/share/xenon/windows"
    assert win == r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Foo\Foo.lnk"


@pytest.mark.parametrize("name,skip", [
    ("Uninstall Foo", True), ("Foo Readme", True), ("Foo Website", True),
    ("Foo", False), ("Remote Desktop Helper", False), ("Photoshop", False),
])
def test_menu_skip(name, skip):
    assert menu.should_skip({"Name": name, "Exec": "xws"}) is skip


def test_menu_sync_generates_and_cleans(tmp_path):
    prefix = tmp_path / "pfx"
    (prefix / "dosdevices").mkdir(parents=True)
    (prefix / "drive_c" / "ProgramData" / "Microsoft" / "Windows" / "Start Menu" /
     "Programs").mkdir(parents=True)
    (prefix / "dosdevices" / "c:").symlink_to("../drive_c")
    lnk_file = prefix / "drive_c/ProgramData/Microsoft/Windows/Start Menu/Programs/App.lnk"
    lnk_file.write_bytes(b"x")
    apps_dir = tmp_path / "applications"
    src = apps_dir / "wine" / "Programs" / "App.desktop"
    src.parent.mkdir(parents=True)
    src.write_text("[Desktop Entry]\nName=App\nType=Application\nIcon=1234_app.0\n"
                   f'Exec=env WINEPREFIX="{prefix}" wine C:\\\\\\\\ProgramData\\\\\\\\'
                   "Microsoft\\\\\\\\Windows\\\\\\\\Start\\ Menu\\\\\\\\Programs\\\\\\\\App.lnk\n")
    stats = menu.sync(apps_dir)
    assert stats["added"] == 1
    out = (apps_dir / "xenon-windows" / "Programs-App.desktop").read_text()
    assert "Exec=xws exec" in out and "Icon=1234_app.0" in out
    assert "NoDisplay=true" in src.read_text()
    lnk_file.unlink()  # uninstaller removed the shortcut
    stats = menu.sync(apps_dir)
    assert stats["removed"] == 1 and not src.exists()


def test_compat_profiles_in_repo_are_valid():
    profiles = compat.load_profiles([REPO / "compat" / "profiles"])
    assert len(profiles) >= 5
    ids = [p.id for p in profiles]
    assert len(ids) == len(set(ids))
    for p in profiles:
        for verb in p.runtimes:
            assert verb in runtimes.KNOWN, (p.id, verb)


def test_compat_matching():
    prof = compat.from_dict({
        "app": {"id": "x", "name": "X"},
        "match": {"exe": ["Ableton Live*.exe"], "product": ["Ableton Live*"],
                  "company": ["Ableton*"]},
    })
    assert prof.matches("ableton live 12 suite.exe", None)
    info = pe.PEInfo("a", pe.MACHINE_AMD64, 2, False, False,
                     version={"ProductName": "Ableton Live 12", "CompanyName": "Ableton AG"})
    assert prof.matches("setup.exe", info)
    info.version["CompanyName"] = "Other"
    assert not prof.matches("setup.exe", info)
    with pytest.raises(compat.ProfileError):
        compat.from_dict({"app": {"id": "y", "name": "Y"}, "match": {}})


def test_runtime_detection():
    info = pe.PEInfo("a", pe.MACHINE_AMD64, 2, False, False,
                     imports=["KERNEL32.dll", "MSVCP140.dll", "VCRUNTIME140_1.dll",
                              "d3dx9_43.dll", "MSVCR100.dll"])
    assert runtimes.detect(info) == ["vcrun2022", "d3dx9", "vcrun2010"] or \
        sorted(runtimes.detect(info)) == ["d3dx9", "vcrun2010", "vcrun2022"]


def test_settings_roundtrip(tmp_path, monkeypatch):
    path = tmp_path / "xws.toml"
    monkeypatch.setattr(config, "CONFIG_FILES", [path])
    config.write_user_setting("graphics_driver", "wayland")
    config.write_user_setting("gamemode", False)
    s = config.Settings.load([path])
    assert s.graphics_driver == "wayland" and s.gamemode is False
    with open(path, "rb") as fh:
        tomllib.load(fh)


def test_registry_defaults_is_valid_regedit():
    from xws.prefix import registry_defaults
    text = registry_defaults(config.Settings(dxvk=False))
    assert text.startswith("Windows Registry Editor Version 5.00")
    assert '"d3d11"="builtin"' in text and '"d3d12"="native,builtin"' in text


# --- tests that need real Windows binaries (built with mingw) -------------

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def built(tmp_path_factory):
    if not shutil.which("x86_64-w64-mingw32-gcc"):
        pytest.skip("mingw-w64 not installed")
    out = tmp_path_factory.mktemp("fx")
    subprocess.run(["make", "-s", "-C", str(FIXTURES), f"OUT={out}"], check=True)
    return out


def test_pe_real_binaries(built):
    setup = pe.parse(built / "xenon-test-setup.exe")
    assert setup.bits == 64 and not setup.is_dotnet
    assert setup.version["ProductName"] == "Xenon Test App"
    assert "ole32.dll" in setup.imports_lower
    game = pe.parse(built / "game64.exe")
    assert game.is_gui and {"d3d11.dll", "vcruntime140.dll"} <= game.imports_lower
    assert runtimes.detect(game) == ["vcrun2022"]
    hello = pe.parse(built / "hello32.exe")
    assert hello.bits == 32 and not hello.is_gui
    assert pe.file_kind(built / "hello32.exe") == "pe"


def test_pe_rejects_garbage(tmp_path):
    bad = tmp_path / "bad.exe"
    bad.write_bytes(b"MZ" + b"\0" * 100)
    with pytest.raises(pe.PEError):
        pe.parse(bad)


def test_lnk_rejects_garbage():
    with pytest.raises(lnk.LnkError):
        lnk.parse_bytes(b"not a link" * 10)


def test_low_disk_space_is_reported_clearly(tmp_path, monkeypatch):
    from collections import namedtuple
    from xws import prefix as prefix_mod
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(prefix_mod.shutil, "disk_usage", lambda p: usage(10, 9, 200 * 2**20))
    p = prefix_mod.Prefix(tmp_path / "pfx", "main")
    with pytest.raises(prefix_mod.PrefixError, match="Not enough free space.*200 MB is free"):
        p.create(tmp_path / "log.txt")


@pytest.mark.parametrize("hints,expected", [
    ([0x3, 0x3e, 0x6, 0, 0], [0x3, 0x3e, 0x0, 0, 0]),   # border+resize, no title
    ([0x3, 0x3e, 0x2, 0, 0], [0x3, 0x3e, 0x0, 0, 0]),   # border only: Mutter adds a title
    ([0x3, 0x3e, 0x7a, 0, 0], None),                    # normal caption: GNOME draws it
    ([0x3, 0x3e, 0x0, 0, 0], None),                     # already undecorated
    ([0x1, 0x3e, 0x6, 0, 0], None),                     # decorations not specified
    ([0x3, 0x3e, 0x1, 0, 0], None),                     # MWM_DECOR_ALL
])
def test_frame_hint_correction(hints, expected):
    from xws import frames
    assert frames.corrected_hints(hints) == expected


def test_frame_helper_targets_only_windows_programs():
    from xws import frames
    assert frames.is_windows_program(("vlc.exe", "vlc.exe"))
    assert frames.is_windows_program(("Steam.EXE", "steam.exe"))
    assert not frames.is_windows_program(("org.gnome.Nautilus", "Nautilus"))
    assert not frames.is_windows_program(None)
