"""Package the EL9 frozen application for Linux distributions and desktops."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
from textwrap import indent
import tomllib
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build/packages'
DIST = ROOT / 'dist/packages'
COMMON = ROOT / 'packaging/linux'
APP_ID = 'io.github.tomups.WatercoolerManager'
PROJECT = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']
VERSION = PROJECT['version']
SUMMARY = PROJECT['description']
LONG_DESCRIPTION = '''Designed for coolers using the LCT21001 (Mk1) or LCT22002 (Mk2) controller, including compatible versions of:

- XMG OASIS Mk1 and Mk2
- PC Specialist Liquid Cooler 1.0 and 2.0
- Eluktronics Liquid Propulsion Package (LPP) G1 and G2
- TUXEDO Aquaris Gen5 and Gen6'''
STEM = f'watercooler-manager-{VERSION}'


def run(*command, **kwargs):
    subprocess.run([str(arg) for arg in command], check=True, cwd=ROOT, **kwargs)


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def tool(name):
    """Fetch only versioned, SHA256-pinned tools, without needing a root install."""
    config = json.loads((ROOT / 'packaging/tools.json').read_text())[name]
    directory = ROOT / 'build/packaging-tools'
    directory.mkdir(parents=True, exist_ok=True)
    download = directory / config['url'].rsplit('/', 1)[1]
    if not download.exists():
        temporary = download.with_suffix('.download')
        try:
            urllib.request.urlretrieve(config['url'], temporary)
            temporary.replace(download)
        finally:
            temporary.unlink(missing_ok=True)
    if sha256(download) != config['sha256']:
        raise ValueError(f'Checksum mismatch for {download}; remove it and retry')
    if name == 'nfpm':
        with tarfile.open(download) as archive:
            with archive.extractfile('nfpm') as source, (directory / 'nfpm').open('wb') as target:
                shutil.copyfileobj(source, target)
        download = directory / 'nfpm'
    download.chmod(0o755)
    return download


def copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def reset(path):
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True)
    return path


def desktop_files(prefix):
    copy(COMMON / f'{APP_ID}.desktop', prefix / f'share/applications/{APP_ID}.desktop')
    copy(COMMON / f'{APP_ID}.metainfo.xml', prefix / f'share/metainfo/{APP_ID}.metainfo.xml')
    copy(ROOT / 'src/icons/connected.png',
         prefix / f'share/icons/hicolor/512x512/apps/{APP_ID}.png')
    copy(ROOT / 'LICENSE', prefix / 'share/licenses/watercooler-manager/LICENSE')
    copy(ROOT / 'README.md', prefix / 'share/doc/watercooler-manager/README.md')


def stage(payload):
    if not (payload / 'WaterCoolerManager').is_file() or not (payload / '_internal').is_dir():
        raise ValueError('Build an --onedir payload first (see packaging/linux/Dockerfile)')
    # pystray prefers legacy AppIndicator over Ayatana, including a host's
    # typelib if it is absent here. Bundle both with the matching EL9 GLib
    # so a newer desktop library cannot leak into the frozen runtime.
    for name in ('libappindicator3.so.1', 'libayatana-appindicator3.so.1',
                 'gi_typelibs/AppIndicator3-0.1.typelib',
                 'gi_typelibs/AyatanaAppIndicator3-0.1.typelib'):
        if not (payload / '_internal' / name).is_file():
            raise ValueError(f'Missing bundled AppIndicator runtime: {name}; '
                             'rebuild with packaging/linux/Dockerfile')
    app = reset(BUILD / 'app')
    shutil.copytree(payload, app, dirs_exist_ok=True, symlinks=True)
    copy(payload.parent / 'snap-runtime/libxcb.so.1', BUILD / 'snap-runtime/libxcb.so.1')
    # EL9.8 backports GLIBC_2.35 symbols into its glibc 2.34 packages.
    # Its newer libgcc therefore cannot run against an older EL9 libc.
    # Use the host compiler runtime, as AppImage also recommends, rather
    # than overriding it with the build machine's libgcc.
    (app / '_internal/libgcc_s.so.1').unlink(missing_ok=True)
    for path in app.rglob('*'):
        if not path.is_file() or path.is_symlink():
            continue
        with path.open('rb') as stream:
            if stream.read(4) != b'\x7fELF':
                continue
        report = subprocess.check_output(['readelf', '--version-info', str(path)], text=True)
        versions = [tuple(map(int, value.split('.'))) for value in
                    re.findall(r'Name: GLIBC_(\d+\.\d+)', report)]
        if versions and max(versions) > (2, 34):
            raise RuntimeError(f'{path.name} exceeds the glibc 2.34 package baseline')
    copy(COMMON / 'launcher', app / 'watercooler-manager')
    (app / 'watercooler-manager').chmod(0o755)
    (app / 'WaterCoolerManager').chmod(0o755)
    portable = reset(BUILD / 'portable') / f'{STEM}-linux-x86_64'
    shutil.copytree(app, portable, symlinks=True)
    desktop_files(portable)
    with tarfile.open(DIST / f'{STEM}-linux-x86_64.tar.gz', 'w:gz') as archive:
        archive.add(portable, arcname=portable.name)


def native():
    prefix = reset(BUILD / 'native') / 'usr'
    desktop_files(prefix)
    config = {
        'name': 'watercooler-manager', 'arch': 'amd64', 'platform': 'linux',
        'version': VERSION, 'release': '1', 'section': 'utils', 'priority': 'optional',
        'maintainer': 'tomups <tomups@users.noreply.github.com>',
        'description': SUMMARY + '\n\n' + LONG_DESCRIPTION,
        'homepage': 'https://github.com/tomups/watercooler-manager',
        'license': 'GPL-3.0-only',
        'contents': [
            {'src': str(BUILD / 'app'), 'dst': '/opt/watercooler-manager', 'type': 'tree'},
            {'src': str(prefix), 'dst': '/usr', 'type': 'tree'},
            {'src': '/opt/watercooler-manager/watercooler-manager',
             'dst': '/usr/bin/watercooler-manager', 'type': 'symlink'},
        ],
        'overrides': {
            'deb': {'depends': ['bluez', 'libc6 (>= 2.34)', 'libgcc-s1', 'libxcb1']},
            'rpm': {'depends': ['bluez', 'glibc >= 2.34', 'libgcc_s.so.1()(64bit)',
                                'libxcb.so.1()(64bit)']},
            'archlinux': {'depends': ['bluez', 'glibc', 'libgcc_s.so=1-64', 'libxcb']},
        },
    }
    config_path = BUILD / 'nfpm.json'
    executable = tool('nfpm')
    for packager, suffix in [('deb', 'amd64.deb'), ('rpm', 'x86_64.rpm'),
                             ('archlinux', 'x86_64.pkg.tar.zst')]:
        if packager == 'archlinux':
            # Arch package metadata only supports a single-line description.
            config['description'] = SUMMARY
        config_path.write_text(json.dumps(config, indent=2) + '\n')
        run(executable, 'package', '--config', config_path, '--packager', packager,
            '--target', DIST / f'{STEM}-1-{suffix}')
    archive_path = DIST / f'{STEM}-linux-x86_64.tar.gz'
    recipe = reset(BUILD / 'arch-recipe')
    (recipe / 'PKGBUILD').write_text(f'''# Generated from the release payload; publish separately to the AUR if desired.
pkgname=watercooler-manager-bin
pkgver={VERSION}
pkgrel=1
pkgdesc='{SUMMARY}'
arch=('x86_64')
url='https://github.com/tomups/watercooler-manager'
license=('GPL-3.0-only')
depends=('bluez' 'glibc' 'libgcc_s.so=1-64' 'libxcb')
provides=('watercooler-manager')
conflicts=('watercooler-manager')
options=('!strip')
source=("$url/releases/download/v$pkgver/watercooler-manager-$pkgver-linux-x86_64.tar.gz")
sha256sums=('{sha256(archive_path)}')

package() {{
    cd "watercooler-manager-$pkgver-linux-x86_64"
    install -dm755 "$pkgdir/opt/watercooler-manager" "$pkgdir/usr/bin"
    cp -a WaterCoolerManager _internal watercooler-manager "$pkgdir/opt/watercooler-manager/"
    cp -a share "$pkgdir/usr/"
    ln -s /opt/watercooler-manager/watercooler-manager "$pkgdir/usr/bin/watercooler-manager"
}}
''')
    with tarfile.open(DIST / f'{STEM}-arch-recipe.tar.gz', 'w:gz') as archive:
        archive.add(recipe / 'PKGBUILD', arcname='PKGBUILD')


def appimage():
    appdir = reset(BUILD / 'WatercoolerManager.AppDir')
    shutil.copytree(BUILD / 'app', appdir / 'usr/lib/watercooler-manager', symlinks=True)
    desktop_files(appdir / 'usr')
    copy(COMMON / f'{APP_ID}.desktop', appdir / f'{APP_ID}.desktop')
    copy(ROOT / 'src/icons/connected.png', appdir / f'{APP_ID}.png')
    (appdir / 'AppRun').symlink_to('usr/lib/watercooler-manager/watercooler-manager')
    (appdir / '.DirIcon').symlink_to(f'{APP_ID}.png')
    run(tool('appimagetool'), '--appimage-extract-and-run', '--no-appstream',
        '--runtime-file', tool('appimage-runtime'), appdir,
        DIST / f'{STEM}-x86_64.AppImage', env=dict(os.environ, ARCH='x86_64'))


def snap():
    directory = reset(BUILD / 'snap')
    shutil.copytree(BUILD / 'app', directory / 'app', symlinks=True)
    copy(BUILD / 'snap-runtime/libxcb.so.1', directory / 'app/_internal/libxcb.so.1')
    metadata = directory / 'meta'
    metadata.mkdir()
    (metadata / 'snap.yaml').write_text(f'''name: watercooler-manager
version: '{VERSION}'
summary: {SUMMARY}
description: |
{indent(LONG_DESCRIPTION, '  ')}
base: core24
architectures: [amd64]
confinement: strict
grade: stable
license: GPL-3.0-only
apps:
  watercooler-manager:
    command: app/watercooler-manager
    autostart: watercooler-manager.desktop
    plugs: [bluez, desktop, desktop-legacy, wayland, x11, opengl]
''')
    desktop = (COMMON / f'{APP_ID}.desktop').read_text().replace(
        f'Icon={APP_ID}', 'Icon=${SNAP}/meta/gui/icon.png')
    (metadata / 'gui').mkdir()
    (metadata / 'gui/watercooler-manager.desktop').write_text(desktop)
    copy(ROOT / 'src/icons/connected.png', metadata / 'gui/icon.png')
    copy(ROOT / 'LICENSE', directory / 'LICENSE')
    run('snap', 'pack', directory, DIST, '--filename', f'{STEM}-amd64.snap')


def flatpak():
    run('flatpak-builder', '--user', '--force-clean', '--disable-rofiles-fuse',
        '--state-dir=' + str(BUILD / 'flatpak-builder'), '--repo=' + str(BUILD / 'flatpak-repo'),
        '--install-deps-from=flathub', BUILD / 'flatpak',
        ROOT / 'packaging/flatpak/io.github.tomups.WatercoolerManager.json')
    run('flatpak', 'build-bundle', '--runtime-repo=https://flathub.org/repo/flathub.flatpakrepo',
        BUILD / 'flatpak-repo', DIST / f'{STEM}-x86_64.flatpak', APP_ID, 'stable')


def checksums():
    with (DIST / 'SHA256SUMS').open('w') as stream:
        for path in sorted(DIST.iterdir()):
            if path.is_file() and path.name != 'SHA256SUMS':
                stream.write(sha256(path) + '  ' + path.name + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('format', choices=['stage', 'native', 'appimage', 'snap', 'flatpak', 'checksums'])
    parser.add_argument('--payload', type=Path, default=ROOT / 'build/linux/WaterCoolerManager')
    args = parser.parse_args()
    DIST.mkdir(parents=True, exist_ok=True)
    if args.format == 'stage':
        stage(args.payload.resolve())
    else:
        globals()[args.format]()


if __name__ == '__main__':
    main()
