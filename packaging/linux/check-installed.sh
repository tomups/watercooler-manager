#!/bin/sh
# Run only in a disposable distro container. Installs the package and exercises
# its actual GTK tray with a private display and D-Bus session; no Bluetooth I/O.
set -eu
. /etc/os-release
cd /work
case "$ID" in
    debian|ubuntu)
        apt-get update
        DEBIAN_FRONTEND=noninteractive apt-get install -y python3-gi python3-pil xvfb dbus-x11 ./dist/packages/*.deb
        ;;
    rocky|fedora)
        if [ "$ID" = rocky ]; then
            dnf install -y epel-release
        fi
        dnf install -y python3-gobject python3-pillow xorg-x11-server-Xvfb dbus-daemon ./dist/packages/*.rpm
        ;;
    arch)
        pacman -Syu --noconfirm python-gobject python-pillow xorg-server-xvfb dbus bluez
        pacman -U --noconfirm ./dist/packages/*.pkg.tar.zst
        ;;
    opensuse-tumbleweed)
        zypper --non-interactive install --allow-unsigned-rpm python3-gobject python3-Pillow xorg-x11-server-Xvfb dbus-1-tools ./dist/packages/*.rpm
        ;;
    *) exit 1 ;;
esac
watercooler-manager --help
Xvfb :99 -screen 0 1280x720x24 &
display_pid=$!
trap 'kill "$display_pid"' EXIT
export DISPLAY=:99 NO_AT_BRIDGE=1
sleep 1
dbus-run-session -- python3 tests/smoke_linux_tray.py --virtual-host --executable /usr/bin/watercooler-manager --exit-via-menu
