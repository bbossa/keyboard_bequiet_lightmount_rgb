# Checks without the keyboard: unit tests, then --check against the raw captures if present
# (captures/ and tools/ are private: absent from the public repository).
PYTHON ?= python3
VERSION := $(shell sed -n "s/^__version__ = '\\(.*\\)'/\\1/p" lightmount/__init__.py)

# System install (packages): make DESTDIR=... PREFIX=/usr install
PREFIX ?= /usr/local
DESTDIR ?=
LIBDIR = $(PREFIX)/lib/lightmount
SHAREDIR = $(PREFIX)/share/lightmount

.PHONY: check test captures-check fixtures install dist deb

check: test captures-check

test:
	$(PYTHON) -I -m unittest discover -s tests

captures-check:
	@if command -v tshark >/dev/null && [ -d tools ] && ls captures/*.pcapng >/dev/null 2>&1; then \
		$(PYTHON) -I tools/lightmount_color.py --check | tail -1 && \
		$(PYTHON) -I tools/lightmount_zones.py --check | tail -1; \
	else \
		echo "captures-check: skipped (tshark, tools/ or captures/ missing, the fixtures are enough)"; \
	fi

# Regenerate tests/fixtures/ from captures/ (needs tshark and the private tools/)
fixtures:
	$(PYTHON) -I tools/extract_fixtures.py

install:
	install -d $(DESTDIR)$(LIBDIR)/lightmount
	install -m644 lightmount/*.py $(DESTDIR)$(LIBDIR)/lightmount/
	install -d $(DESTDIR)$(PREFIX)/bin
	sed 's|@LIBDIR@|$(LIBDIR)|g' packaging/lightmount.in > $(DESTDIR)$(PREFIX)/bin/lightmount
	chmod 755 $(DESTDIR)$(PREFIX)/bin/lightmount
	install -d $(DESTDIR)$(PREFIX)/lib/systemd/user
	sed 's|%h/.local/bin/lightmount|$(PREFIX)/bin/lightmount|' install/lightmount.service \
		> $(DESTDIR)$(PREFIX)/lib/systemd/user/lightmount.service
	install -Dm644 install/70-bequiet-light-mount.rules $(DESTDIR)$(PREFIX)/lib/udev/rules.d/70-bequiet-light-mount.rules
	install -Dm644 install/lightmount.fish $(DESTDIR)$(PREFIX)/share/fish/vendor_conf.d/lightmount.fish
	install -Dm644 install/lightmount.bash $(DESTDIR)$(SHAREDIR)/lightmount.bash
	install -Dm644 install/lightmount.zsh $(DESTDIR)$(SHAREDIR)/lightmount.zsh
	install -Dm644 install/config.toml $(DESTDIR)$(SHAREDIR)/config.toml
	install -Dm644 README.md $(DESTDIR)$(PREFIX)/share/doc/lightmount/README.md
	install -Dm644 CHANGELOG.md $(DESTDIR)$(PREFIX)/share/doc/lightmount/CHANGELOG.md

# Source tarball of the committed tree (what the PKGBUILD downloads)
dist:
	git archive --prefix=lightmount-$(VERSION)/ -o lightmount-$(VERSION).tar.gz HEAD

deb:
	packaging/debian/build-deb.sh
