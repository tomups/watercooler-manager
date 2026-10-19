# Optional local packaging tools; CI installs the same tools on its Ubuntu runner.
FROM ubuntu:24.04
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3 python3-gi python3-pil flatpak flatpak-builder snapd rpm zstd \
    desktop-file-utils appstream dbus-x11 xvfb xauth ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /work
