# Builds the Windows test fixtures with mingw-w64 (apt install mingw-w64).
CC64 = x86_64-w64-mingw32-gcc
CC32 = i686-w64-mingw32-gcc
WINDRES = x86_64-w64-mingw32-windres
DLLTOOL = x86_64-w64-mingw32-dlltool
OUT ?= build

all: $(OUT)/xenon-test-setup.exe $(OUT)/game64.exe $(OUT)/hello32.exe $(OUT)/customframe.exe

$(OUT):
	mkdir -p $(OUT)

$(OUT)/testsetup.res.o: testsetup.rc | $(OUT)
	$(WINDRES) $< -O coff -o $@

$(OUT)/xenon-test-setup.exe: testsetup.c $(OUT)/testsetup.res.o
	$(CC64) -O2 -municode -o $@ $^ -lole32 -luuid -lshell32

$(OUT)/libvcruntime140.a: | $(OUT)
	printf 'LIBRARY vcruntime140.dll\nEXPORTS\n__std_terminate_stub\n' > $(OUT)/vcruntime140.def
	$(DLLTOOL) -d $(OUT)/vcruntime140.def -l $@

$(OUT)/game64.exe: game.c $(OUT)/libvcruntime140.a
	$(CC64) -O2 -mwindows -o $@ game.c -L$(OUT) -ld3d11 -lvcruntime140

$(OUT)/hello32.exe: | $(OUT)
	printf '#include <stdio.h>\nint main(void){puts("hello from 32-bit");return 0;}\n' > $(OUT)/hello32.c
	$(CC32) -O2 -o $@ $(OUT)/hello32.c

$(OUT)/customframe.exe: customframe.c | $(OUT)
	$(CC64) -O2 -mwindows -o $@ $< -lgdi32

clean:
	rm -rf $(OUT)
