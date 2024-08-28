SHELL=/bin/sh

prefix=/usr/local
exec_prefix=$(prefix)
bindir=$(exec_prefix)/bin

default:
	@echo "Please run 'make install' to install the script."

install:
	install -d $(DESTDIR)$(bindir)
	install -m 755 mdproxy.py $(DESTDIR)$(bindir)/mdproxy

uninstall:
	rm -f $(DESTDIR)$(bindir)/mdproxy