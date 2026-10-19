{ lib, stdenvNoCC, python3, makeWrapper, wrapGAppsHook3, gtk3,
  libayatana-appindicator, gobject-introspection }:

let
  project = builtins.fromTOML (builtins.readFile ../../pyproject.toml);
  python = python3.withPackages (ps: with ps; [ bleak pillow pystray pygobject3 pycairo ]);
in stdenvNoCC.mkDerivation {
  pname = "watercooler-manager";
  version = project.project.version;
  src = lib.fileset.toSource {
    root = ../..;
    fileset = lib.fileset.unions [
      ../../src ../../pyproject.toml ../../LICENSE ../../README.md ../linux
    ];
  };
  nativeBuildInputs = [ makeWrapper wrapGAppsHook3 ];
  buildInputs = [ gtk3 libayatana-appindicator gobject-introspection ];
  dontBuild = true;

  installPhase = ''
    runHook preInstall
    mkdir -p $out/lib/watercooler-manager $out/bin
    cp -r src/. $out/lib/watercooler-manager/
    makeShellWrapper ${python}/bin/python $out/bin/watercooler-manager \
      --add-flags "$out/lib/watercooler-manager/main.py" \
      --set WATERCOOLER_LAUNCHER "$out/bin/watercooler-manager" \
      --run 'candidate=$(command -v watercooler-manager || true); if [ -n "$candidate" ]; then export WATERCOOLER_LAUNCHER="$candidate"; fi' \
      --set-default PYSTRAY_BACKEND appindicator
    install -Dm644 packaging/linux/io.github.tomups.WatercoolerManager.desktop \
      $out/share/applications/io.github.tomups.WatercoolerManager.desktop
    install -Dm644 packaging/linux/io.github.tomups.WatercoolerManager.metainfo.xml \
      $out/share/metainfo/io.github.tomups.WatercoolerManager.metainfo.xml
    install -Dm644 src/icons/connected.png \
      $out/share/icons/hicolor/512x512/apps/io.github.tomups.WatercoolerManager.png
    install -Dm644 LICENSE $out/share/licenses/watercooler-manager/LICENSE
    runHook postInstall
  '';
  doInstallCheck = true;
  installCheckPhase = ''
    $out/bin/watercooler-manager --help
    PYTHONPATH=$out/lib/watercooler-manager PYSTRAY_BACKEND=dummy \
      ${python}/bin/python -c 'from watercooler_manager import WaterCoolerManager'
  '';
  meta = {
    description = "System tray controls for Bluetooth laptop water coolers";
    homepage = "https://github.com/tomups/watercooler-manager";
    license = lib.licenses.gpl3Only;
    platforms = lib.platforms.linux;
    mainProgram = "watercooler-manager";
  };
}
