# Developer shortcuts. See docs/BUILDING.md.

.PHONY: help test e2e lint art packages iso iso-docker test-iso

help:
	@echo "make test        unit tests (no Wine needed)"
	@echo "make e2e         end-to-end Windows subsystem test (needs wine, mingw-w64, xvfb)"
	@echo "make lint        shellcheck + desktop file validation"
	@echo "make art         render branding artwork into packages/xenon-branding/build"
	@echo "make packages    build all .deb packages into build/debs"
	@echo "make iso         build the ISO (root, Debian 13)"
	@echo "make iso-docker  build the ISO in a Debian 13 container"
	@echo "make test-iso    boot-test out/*.iso in QEMU"

test:
	python3 -m pytest -q packages/xenon-xws/tests packages/xenon-settings/tests

e2e:
	packages/xenon-xws/tests/e2e.sh

lint:
	shellcheck build-iso.sh tools/*.sh kernel/build-kernel.sh \
	  packages/xenon-xws/tests/e2e.sh packages/xenon-system/vm-selftest \
	  packages/xenon-xws/data/xws-binfmt packages/xenon-installer/scripts/* live/auto/*
	cd packages/xenon-xws-thirdparty && shellcheck -x fetch.sh
	shellcheck -s sh live/config/hooks/normal/*.hook.chroot
	for f in packages/*/data/*.desktop packages/xenon-installer/live/*.desktop; do \
	  desktop-file-validate $$f || exit 1; done

art:
	$(MAKE) -C packages/xenon-branding

packages:
	tools/build-packages.sh

iso:
	./build-iso.sh

iso-docker:
	tools/build-in-docker.sh

test-iso:
	tools/test-iso.sh $$(ls out/*.iso | head -n 1)
