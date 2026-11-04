# Renders Xenon artwork from SVG sources into build/ (needs librsvg2-bin).
OUT ?= build
SIZES = 16 22 24 32 48 64 128 256 512
RSVG = rsvg-convert

all: icons wallpapers plymouth misc

icons:
	@for s in $(SIZES); do \
	  mkdir -p $(OUT)/icons/hicolor/$${s}x$${s}/apps; \
	  $(RSVG) -w $$s -h $$s art/xenon-logo.svg -o $(OUT)/icons/hicolor/$${s}x$${s}/apps/xenon-logo.png; \
	  $(RSVG) -w $$s -h $$s art/xenon-windows-app.svg -o $(OUT)/icons/hicolor/$${s}x$${s}/apps/xenon-windows-app.png; \
	  $(RSVG) -w $$s -h $$s art/xenon-install.svg -o $(OUT)/icons/hicolor/$${s}x$${s}/apps/xenon-install.png; \
	done
	mkdir -p $(OUT)/icons/hicolor/scalable/apps $(OUT)/icons/hicolor/symbolic/apps
	cp art/xenon-logo.svg art/xenon-windows-app.svg art/xenon-install.svg $(OUT)/icons/hicolor/scalable/apps/
	cp art/xenon-logo-symbolic.svg $(OUT)/icons/hicolor/symbolic/apps/

wallpapers:
	mkdir -p $(OUT)/backgrounds
	$(RSVG) -w 3840 -h 2160 art/wallpaper-dark.svg -o $(OUT)/backgrounds/xenon-dark.png
	$(RSVG) -w 3840 -h 2160 art/wallpaper-light.svg -o $(OUT)/backgrounds/xenon-light.png
	$(RSVG) -w 1920 -h 1080 art/wallpaper-dark.svg -o $(OUT)/backgrounds/grub.png

plymouth:
	mkdir -p $(OUT)/plymouth
	$(RSVG) -w 160 -h 160 art/xenon-logo.svg -o $(OUT)/plymouth/logo.png
	$(RSVG) art/plymouth-bullet.svg -o $(OUT)/plymouth/bullet.png
	$(RSVG) art/plymouth-entry.svg -o $(OUT)/plymouth/entry.png

misc:
	mkdir -p $(OUT)/misc
	$(RSVG) -w 480 art/xenon-wordmark.svg -o $(OUT)/misc/xenon-wordmark.png
	$(RSVG) -w 480 art/xenon-wordmark-dark.svg -o $(OUT)/misc/xenon-wordmark-dark.png
	$(RSVG) -w 128 -h 128 art/xenon-logo.svg -o $(OUT)/misc/xenon-logo-128.png

clean:
	rm -rf build

.PHONY: all icons wallpapers plymouth misc clean
