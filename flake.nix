{
  description = "Bluetooth laptop water cooler controls for Linux desktops";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forSystems = nixpkgs.lib.genAttrs systems;
    in {
      packages = forSystems (system:
        let pkgs = import nixpkgs { inherit system; };
        in rec {
          watercooler-manager = pkgs.callPackage ./packaging/nix/package.nix { };
          default = watercooler-manager;
        });
      checks = forSystems (system: {
        package = self.packages.${system}.default;
      });
      nixosModules.default = { config, lib, pkgs, ... }:
        let cfg = config.programs.watercooler-manager;
        in {
          options.programs.watercooler-manager = {
            enable = lib.mkEnableOption "Watercooler Manager and Bluetooth support";
            package = lib.mkOption {
              type = lib.types.package;
              default = self.packages.${pkgs.stdenv.hostPlatform.system}.default;
              description = "Watercooler Manager package to install";
            };
          };
          config = lib.mkIf cfg.enable {
            environment.systemPackages = [ cfg.package ];
            hardware.bluetooth.enable = true;
          };
        };
    };
}
