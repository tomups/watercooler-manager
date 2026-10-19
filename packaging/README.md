# Linux packages

Release CI builds x86_64 DEB, RPM, Arch, Flatpak, Snap, AppImage and portable tar.gz packages, plus a Nix package and its closure. Windows continues to produce WaterCoolerManager.exe. Pull requests and manual runs upload artifacts; version tags publish them to GitHub Releases after all installation checks pass. Builds do not submit packages to distribution repositories, the AUR, Flathub or the Snap Store.

## Choose a package

| Download | Install or run |
| --- | --- |
| `*-amd64.deb` | Debian 12+, Ubuntu 22.04+ and compatible derivatives: `sudo apt install ./watercooler-manager-*-amd64.deb` |
| `*-x86_64.rpm` | Fedora and RHEL/Rocky/AlmaLinux 9+: `sudo dnf install ./watercooler-manager-*.rpm`; openSUSE: `sudo zypper install ./watercooler-manager-*.rpm` |
| `*.pkg.tar.zst` | Arch, CachyOS, Omarchy and compatible derivatives: `sudo pacman -U ./watercooler-manager-*.pkg.tar.zst` |
| `*.flatpak` | `flatpak install --user ./watercooler-manager-*.flatpak`, then `flatpak run io.github.tomups.WatercoolerManager` |
| `*.snap` | `sudo snap install --dangerous ./watercooler-manager-*.snap`, then `sudo snap connect watercooler-manager:bluez :bluez` and `snap run watercooler-manager` |
| `*.AppImage` | `chmod +x ./watercooler-manager-*.AppImage`, then run it. If FUSE is unavailable, use `APPIMAGE_EXTRACT_AND_RUN=1 ./watercooler-manager-*.AppImage`. |
| `*-linux-x86_64.tar.gz` | Extract the complete directory and run its `watercooler-manager` launcher. Keep `_internal` beside the executable. |
| Nix | `nix profile install github:tomups/watercooler-manager`; see the Nix section below. |

Native packages install `watercooler-manager` and a desktop menu entry. They declare BlueZ as a dependency, so installing through apt/dnf/zypper/pacman can install the host Bluetooth service automatically. The radio and service must also be enabled. These packages do not replace system Bluetooth configuration or enable login startup without your choice.

Flatpak needs Flatpak and the Flathub runtime source; its bundle includes a runtime repository hint. Snap needs snapd and the core24 base (downloaded by snapd). GitHub Snap downloads are unsigned local packages, hence `--dangerous`; this skips store assertion verification, not confinement. Bluetooth access must be connected manually unless store auto-connection is separately approved. AppImage and tar.gz users must install and enable BlueZ through their distribution.

All formats need a working graphical desktop and StatusNotifier/AppIndicator tray host. On GNOME, enable the AppIndicator extension. See the main README for other desktops. Container tests verify startup, menus, icons and theme changes; physical Bluetooth controls still need hardware verification in the chosen packaging environment.

## Compatibility and startup

The shared binary payload is built on Rocky Linux 9 with Python 3.11 and glibc 2.34. Python, Pillow, Bleak, GTK/AppIndicator bindings and GTK runtime libraries are included. The glibc minimum is declared in native packages. This improves the old Ubuntu 24.04/glibc 2.39 baseline, but is not a promise that every distribution or graphics configuration works. RHEL 8, Ubuntu 20.04, musl distributions and other CPU architectures need a source or Nix build rather than these frozen binaries. Native installation/tray CI covers Debian 12, Ubuntu 22.04, Rocky 9, Fedora 43, Arch and openSUSE Tumbleweed. Flatpak and Snap have separate sandboxed tray checks.

Choose **Settings → Start on boot** to start at desktop login:

- Native packages and tar.gz use the persistent installed launcher through XDG Autostart.
- AppImage records the original AppImage file, never its temporary mount or extraction directory. Keep the file in place; toggle startup off/on after moving it.
- Snap uses snapd's session autostart agent and a revision-independent command. Settings live in `$SNAP_USER_COMMON/settings.json` and survive refreshes.
- Flatpak requests autostart through the desktop's Background portal. The desktop may prompt for permission; declining leaves the setting unchanged. A desktop portal backend supporting Background is required. Flatpak settings live under its private XDG config directory. The checkbox remembers the last portal-confirmed choice; outside changes to portal permissions are managed by the desktop.

Flatpak and Snap place temporary tray icons in their host-visible private cache/data directories, so tray hosts outside the sandbox can read them. Flatpak grants access specifically to BlueZ on the system bus, and the StatusNotifier watcher and desktop notifications on the session bus; it does not expose the entire buses or home directory. Source and native settings retain `~/.watercooler.json`. Switching between native and sandboxed installs does not migrate preferences automatically.

## Build locally

Use Docker for the compatibility payload rather than freezing your rolling distribution's newer libraries:

```sh
docker build -f packaging/linux/Dockerfile -t watercooler-build .
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work" watercooler-build
python3 scripts/package_linux.py stage
python3 scripts/package_linux.py native
python3 scripts/package_linux.py appimage
python3 scripts/package_linux.py snap
```

The host helpers need Python 3.11+, `snap` (for `snap pack`), and standard Linux tools. nFPM, appimagetool and the AppImage runtime download into `build/packaging-tools` from versioned URLs, verified against committed SHA256 hashes. Snap packaging uses `snap pack` directly on the frozen payload and does not need a running snap daemon, Snapcraft, or a nested VM.

An optional tools container avoids installing packaging commands on the host:

```sh
docker build -f packaging/linux/tools.Dockerfile -t watercooler-tools .
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work" watercooler-tools python3 scripts/package_linux.py snap
```

For Flatpak, install `flatpak` and `flatpak-builder`, add Flathub, and build after staging the payload:

```sh
flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
python3 scripts/package_linux.py flatpak
```

Outputs are in `dist/packages`. The intermediate frozen directory is in `build/linux/WaterCoolerManager`. `python3 scripts/package_linux.py checksums` writes SHA256SUMS for local outputs. The release workflow generates combined checksums including Windows and Nix artifacts.

The generated `*-arch-recipe.tar.gz` includes a PKGBUILD referencing the matching release tar.gz and its actual hash. It can build the same payload locally with makepkg, or serve as the starting point for a separate AUR submission. Before the matching version tag is published, place the portable tar.gz beside PKGBUILD so makepkg can use the local source file.

## Nix and NixOS

`flake.lock` pins nixpkgs. The source package uses nixpkgs Python dependencies and GTK libraries instead of the frozen EL9 runtime. The flake exposes x86_64-linux and aarch64-linux packages; CI builds and tests x86_64. ARM hardware has not been verified.

```sh
nix build .#watercooler-manager
./result/bin/watercooler-manager --help
nix profile install .#watercooler-manager
```

Install into a persistent profile before enabling login startup. The wrapper prefers the profile's launcher over the versioned store path. A NixOS flake configuration can enable both the application and BlueZ:

```nix
inputs.watercooler-manager.url = "github:tomups/watercooler-manager";
# In the NixOS system's modules list:
# inputs.watercooler-manager.nixosModules.default
# In a system module:
programs.watercooler-manager.enable = true;
```

On other distributions, the host's BlueZ service still needs to be enabled. NixOS users who install only the package can separately set `hardware.bluetooth.enable = true`.

Releases also include locked Nix source and an exported x86_64 store closure (`*.nar.zst`). With Nix and zstd installed, import the trusted downloaded closure with `zstd -dc file.nar.zst | nix-store --import`, then install the store path recorded in the accompanying `*-nix-store-path.txt` using `nix profile install /nix/store/...-watercooler-manager-2.0.0`. Store import may require an administrator under the local Nix trust policy. The normal flake installation is preferable when network access is available.
