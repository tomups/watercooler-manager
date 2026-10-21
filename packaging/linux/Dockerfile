# EL9's glibc 2.34 also runs on Debian 12+, Ubuntu 22.04+, and current Arch.
# GTK and Python are bundled; BlueZ remains the host's Bluetooth service.
FROM ghcr.io/astral-sh/uv:0.12.17 AS uv
FROM rockylinux:9
COPY --from=uv /uv /usr/local/bin/uv
RUN dnf install -y epel-release dnf-plugins-core \
    && dnf config-manager --set-enabled crb \
    && dnf install -y python3.11 python3.11-devel python3.11-pip gcc \
       gobject-introspection-devel cairo-devel cairo-gobject-devel pkgconf-pkg-config gtk3 \
       libappindicator-gtk3 libayatana-appindicator-gtk3 xorg-x11-server-Xvfb xorg-x11-xauth \
       dbus-daemon git binutils \
    && dnf clean all
WORKDIR /work
ENV UV_PROJECT_ENVIRONMENT=/opt/build-venv UV_PYTHON_DOWNLOADS=never NO_AT_BRIDGE=1
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --group build --python /usr/bin/python3.11 \
    && uv pip install --python /opt/build-venv/bin/python \
       PyGObject==3.48.2 pycairo==1.28.0
# Bindings above support EL9's libgirepository 1.x. Newer PyGObject needs 2.x.
ENV PATH="/opt/build-venv/bin:${PATH}"
CMD ["python", "scripts/build.py", "--onedir", "--distpath", "build/linux"]
