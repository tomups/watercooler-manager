#!/bin/sh
# AT-SPI 2.54 still supports EL9's GLib 2.68 and glibc 2.34.
set -eu

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
archive="$work/at-spi2-core-2.54.2.tar.xz"
curl --fail --location --retry 3 \
    https://download.gnome.org/sources/at-spi2-core/2.54/at-spi2-core-2.54.2.tar.xz \
    --output "$archive"
printf '%s  %s\n' \
    510e1760a27ce9ce27a300f116d9b8a7dc8eac1f78714915685833643cb36236 \
    "$archive" | sha256sum --check --strict -
tar -xf "$archive" -C "$work"
meson setup "$work/build" "$work/at-spi2-core-2.54.2" \
    --prefix=/usr --libdir=lib64 --buildtype=release --wrap-mode=nodownload \
    -Dintrospection=enabled -Dgtk2_atk_adaptor=false -Duse_systemd=false -Dx11=enabled
meson compile -C "$work/build" -j 2
meson install -C "$work/build"
ldconfig
