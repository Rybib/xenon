/* Fixture whose imports look like a DirectX 11 game built with MSVC's
 * runtime: used to test game detection and runtime auto-detection.
 * Never executed in tests; only parsed. */
#include <windows.h>

__declspec(dllimport) long __stdcall D3D11CreateDevice(void *, int, void *, unsigned,
                                                        void *, unsigned, unsigned,
                                                        void **, void *, void **);
__declspec(dllimport) void *__cdecl __std_terminate_stub(void);

int WINAPI WinMain(HINSTANCE a, HINSTANCE b, LPSTR c, int d)
{
    if (d == 12345) {
        D3D11CreateDevice(0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
        __std_terminate_stub();
    }
    return 0;
}
