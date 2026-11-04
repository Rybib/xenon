/*
 * Xenon XWS end-to-end test program. Behaves like a typical Windows
 * installer so the whole install -> app grid -> launch -> uninstall flow
 * can be tested automatically.
 *
 *   xenon-test-setup.exe          install (copies itself, registry, shortcuts)
 *   XenonTestApp.exe              "the app": writes C:\xenon-test-marker.txt
 *   XenonTestApp.exe /uninstall   removes shortcuts and registry entries
 *
 * Build: x86_64-w64-mingw32-gcc -municode -o xenon-test-setup.exe testsetup.c \
 *        testsetup.res.o -lole32 -luuid -lshell32
 */
#define COBJMACROS
#include <windows.h>
#include <shlobj.h>
#include <shobjidl.h>
#include <objbase.h>
#include <stdio.h>
#include <wchar.h>

#define UNINSTALL_KEY L"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\XenonTestApp"

static void program_dir(wchar_t *out, size_t n)
{
    wchar_t pf[MAX_PATH];
    SHGetFolderPathW(NULL, CSIDL_PROGRAM_FILES, NULL, 0, pf);
    _snwprintf(out, n, L"%ls\\XenonTest", pf);
}

static void menu_dir(wchar_t *out, size_t n)
{
    wchar_t sm[MAX_PATH];
    SHGetFolderPathW(NULL, CSIDL_COMMON_PROGRAMS, NULL, 0, sm);
    _snwprintf(out, n, L"%ls\\Xenon Test", sm);
}

static HRESULT make_link(const wchar_t *lnk, const wchar_t *target, const wchar_t *args)
{
    IShellLinkW *sl;
    IPersistFile *pf;
    HRESULT hr = CoCreateInstance(&CLSID_ShellLink, NULL, CLSCTX_INPROC_SERVER,
                                  &IID_IShellLinkW, (void **)&sl);
    if (FAILED(hr)) return hr;
    IShellLinkW_SetPath(sl, target);
    IShellLinkW_SetArguments(sl, args);
    IShellLinkW_SetDescription(sl, L"Xenon test application");
    IShellLinkW_SetIconLocation(sl, target, 0);
    hr = IShellLinkW_QueryInterface(sl, &IID_IPersistFile, (void **)&pf);
    if (SUCCEEDED(hr)) {
        hr = IPersistFile_Save(pf, lnk, TRUE);
        IPersistFile_Release(pf);
    }
    IShellLinkW_Release(sl);
    return hr;
}

static int install(void)
{
    wchar_t self[MAX_PATH], dir[MAX_PATH], exe[MAX_PATH], mdir[MAX_PATH], lnk[MAX_PATH];
    wchar_t uninst[MAX_PATH * 2];
    HKEY key;
    DWORD size = 128;

    GetModuleFileNameW(NULL, self, MAX_PATH);
    program_dir(dir, MAX_PATH);
    CreateDirectoryW(dir, NULL);
    _snwprintf(exe, MAX_PATH, L"%ls\\XenonTestApp.exe", dir);
    if (!CopyFileW(self, exe, FALSE)) { fwprintf(stderr, L"copy failed\n"); return 2; }

    if (RegCreateKeyExW(HKEY_LOCAL_MACHINE, UNINSTALL_KEY, 0, NULL, 0, KEY_WRITE, NULL,
                        &key, NULL) != ERROR_SUCCESS) return 3;
    _snwprintf(uninst, MAX_PATH * 2, L"\"%ls\" /uninstall", exe);
    RegSetValueExW(key, L"DisplayName", 0, REG_SZ, (BYTE *)L"Xenon Test App",
                   sizeof(L"Xenon Test App"));
    RegSetValueExW(key, L"Publisher", 0, REG_SZ, (BYTE *)L"Xenon Project",
                   sizeof(L"Xenon Project"));
    RegSetValueExW(key, L"DisplayVersion", 0, REG_SZ, (BYTE *)L"1.0.0", sizeof(L"1.0.0"));
    RegSetValueExW(key, L"UninstallString", 0, REG_SZ, (BYTE *)uninst,
                   (wcslen(uninst) + 1) * sizeof(wchar_t));
    RegSetValueExW(key, L"InstallLocation", 0, REG_SZ, (BYTE *)dir,
                   (wcslen(dir) + 1) * sizeof(wchar_t));
    RegSetValueExW(key, L"DisplayIcon", 0, REG_SZ, (BYTE *)exe,
                   (wcslen(exe) + 1) * sizeof(wchar_t));
    RegSetValueExW(key, L"EstimatedSize", 0, REG_DWORD, (BYTE *)&size, sizeof(size));
    RegCloseKey(key);

    menu_dir(mdir, MAX_PATH);
    CreateDirectoryW(mdir, NULL);
    CoInitialize(NULL);
    _snwprintf(lnk, MAX_PATH, L"%ls\\Xenon Test App.lnk", mdir);
    if (FAILED(make_link(lnk, exe, L""))) return 4;
    _snwprintf(lnk, MAX_PATH, L"%ls\\Uninstall Xenon Test App.lnk", mdir);
    make_link(lnk, exe, L"/uninstall");
    CoUninitialize();
    wprintf(L"installed to %ls\n", dir);
    return 0;
}

static int uninstall(void)
{
    wchar_t mdir[MAX_PATH], lnk[MAX_PATH];
    menu_dir(mdir, MAX_PATH);
    _snwprintf(lnk, MAX_PATH, L"%ls\\Xenon Test App.lnk", mdir);
    DeleteFileW(lnk);
    _snwprintf(lnk, MAX_PATH, L"%ls\\Uninstall Xenon Test App.lnk", mdir);
    DeleteFileW(lnk);
    RemoveDirectoryW(mdir);
    RegDeleteKeyW(HKEY_LOCAL_MACHINE, UNINSTALL_KEY);
    wprintf(L"uninstalled\n");
    return 0;
}

static int run_app(void)
{
    FILE *f = _wfopen(L"C:\\xenon-test-marker.txt", L"w");
    if (!f) return 5;
    fwprintf(f, L"Xenon test app ran\n");
    fclose(f);
    return 0;
}

int wmain(int argc, wchar_t **argv)
{
    wchar_t self[MAX_PATH];
    const wchar_t *base;
    if (argc > 1 && _wcsicmp(argv[1], L"/uninstall") == 0) return uninstall();
    GetModuleFileNameW(NULL, self, MAX_PATH);
    base = wcsrchr(self, L'\\');
    base = base ? base + 1 : self;
    if (_wcsicmp(base, L"XenonTestApp.exe") == 0) return run_app();
    return install();
}
