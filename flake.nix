{
  description = "make4db provider for Snowflake";

  inputs = {
    nixpkgs.url     = "github:nixos/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    snowflake.url   = "github:padhia/snowflake";
    yappt.url       = "github:padhia/yappt";
    make4db-api.url = "github:padhia/make4db-api";
    sfconn.url      = "github:padhia/sfconn";

    snowflake.inputs.nixpkgs.follows   = "nixpkgs";
    yappt.inputs.nixpkgs.follows       = "nixpkgs";
    make4db-api.inputs.nixpkgs.follows = "nixpkgs";
    sfconn.inputs.nixpkgs.follows      = "nixpkgs";

    snowflake.inputs.flake-utils.follows   = "flake-utils";
    yappt.inputs.flake-utils.follows       = "flake-utils";
    make4db-api.inputs.flake-utils.follows = "flake-utils";
    sfconn.inputs.flake-utils.follows      = "flake-utils";

    sfconn.inputs.snowflake.follows = "snowflake";
  };

  outputs = { self, nixpkgs, flake-utils, sfconn, snowflake, yappt, make4db-api }:
  let
    inherit (nixpkgs.lib) composeManyExtensions;

    overlays.default =
    let
      pkgOverlay = final: prev: {
        pythonPackagesExtensions = prev.pythonPackagesExtensions ++ [
          (py-final: py-prev: {
            make4db-snowflake = py-final.callPackage ./make4db-snowflake.nix {};
          })
        ];
      };
    in composeManyExtensions [
      snowflake.overlays.default
      yappt.overlays.default
      sfconn.overlays.default
      make4db-api.overlays.default
      pkgOverlay
    ];

    eachSystem = system:
    let
      pkgs = import nixpkgs {
        inherit system;
        config.allowUnfree = true;
        overlays = [ self.overlays.default ];
      };

      pyPkgs = pkgs.python312Packages;

    in {
      devShells.default = pkgs.mkShell {
        name = "m4db-sf";
        venvDir = "./.venv";
        buildInputs = [
          pkgs.ruff
          pkgs.uv
          pyPkgs.python
          pyPkgs.venvShellHook
          pyPkgs.pytest
          pyPkgs.snowflake-snowpark-python
          pyPkgs.sfconn
          pyPkgs.yappt
          pyPkgs.make4db-api
        ];
      };
    };

  in {
    inherit overlays;
    inherit (flake-utils.lib.eachDefaultSystem eachSystem) devShells;
  };
}
