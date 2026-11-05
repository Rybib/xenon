/*
 * A window that draws its own title bar, like Chromium/Electron apps,
 * Steam, Discord or Spotify: no WS_CAPTION, but resizable (WS_THICKFRAME)
 * with minimize/maximize boxes. On GNOME, Wine asks the window manager for
 * "border + resize handles", which Mutter turns into a full title bar on
 * top of the program's own: the double-header bug XWS fixes.
 */
#include <windows.h>

#define TITLE_H 36

static LRESULT CALLBACK proc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp)
{
    switch (msg) {
    case WM_PAINT: {
        PAINTSTRUCT ps;
        RECT rc, bar;
        HDC dc = BeginPaint(hwnd, &ps);
        HBRUSH title = CreateSolidBrush(RGB(124, 58, 237));
        GetClientRect(hwnd, &rc);
        FillRect(dc, &rc, GetStockObject(WHITE_BRUSH));
        bar = rc;
        bar.bottom = TITLE_H;
        FillRect(dc, &bar, title);
        SetBkMode(dc, TRANSPARENT);
        SetTextColor(dc, RGB(255, 255, 255));
        bar.left += 12;
        DrawTextA(dc, "Custom title bar (drawn by the app)", -1, &bar,
                  DT_SINGLELINE | DT_VCENTER);
        DeleteObject(title);
        EndPaint(hwnd, &ps);
        return 0;
    }
    case WM_NCCALCSIZE:
        /* Like Chromium: no system frame at all; the client area is the
         * whole window and the app handles edges itself (WM_NCHITTEST). */
        if (wp) return 0;
        break;
    case WM_NCHITTEST: {
        POINT pt = { (short)LOWORD(lp), (short)HIWORD(lp) };
        RECT rc;
        const int B = 8;
        int l, r, t, b;
        ScreenToClient(hwnd, &pt);
        GetClientRect(hwnd, &rc);
        l = pt.x < B; r = pt.x >= rc.right - B; t = pt.y < B; b = pt.y >= rc.bottom - B;
        if (t && l) return HTTOPLEFT;
        if (t && r) return HTTOPRIGHT;
        if (b && l) return HTBOTTOMLEFT;
        if (b && r) return HTBOTTOMRIGHT;
        if (l) return HTLEFT;
        if (r) return HTRIGHT;
        if (t) return HTTOP;
        if (b) return HTBOTTOM;
        return pt.y < TITLE_H ? HTCAPTION : HTCLIENT;
    }
    case WM_DESTROY:
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcA(hwnd, msg, wp, lp);
}

int WINAPI WinMain(HINSTANCE inst, HINSTANCE prev, LPSTR cmd, int show)
{
    WNDCLASSA wc = {0};
    MSG msg;
    HWND hwnd;
    wc.lpfnWndProc = proc;
    wc.hInstance = inst;
    wc.hCursor = LoadCursor(NULL, IDC_ARROW);
    wc.lpszClassName = "XenonCustomFrame";
    RegisterClassA(&wc);
    hwnd = CreateWindowExA(0, wc.lpszClassName, "Custom frame test",
                           WS_POPUP | WS_THICKFRAME | WS_SYSMENU |
                           WS_MINIMIZEBOX | WS_MAXIMIZEBOX,
                           120, 120, 560, 300, NULL, NULL, inst, NULL);
    ShowWindow(hwnd, show ? show : SW_SHOW);
    while (GetMessageA(&msg, NULL, 0, 0) > 0) {
        TranslateMessage(&msg);
        DispatchMessageA(&msg);
    }
    return 0;
}
