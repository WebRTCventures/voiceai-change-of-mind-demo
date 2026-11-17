{
  description = "Dev shell for the change-of-mind voice agent demo (Pipecat, managed by uv)";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      devShells = forAllSystems (pkgs:
        let
          python = pkgs.python311;
          # Shared libraries that the prebuilt PyPI wheels (numpy, onnxruntime
          # for Silero VAD and Smart Turn, opencv, av, aiortc) expect to find
          # on a normal Linux system. Nix does not provide them globally.
          runtimeLibs = [
            pkgs.stdenv.cc.cc.lib # libstdc++.so.6, libgcc_s.so.1
            pkgs.zlib # libz.so.1
          ];
        in
        {
          default = pkgs.mkShell {
            packages = [ python pkgs.uv ];

            env = {
              # Use the Nix Python. uv's downloaded interpreters do not run on NixOS.
              UV_PYTHON = "${python}/bin/python";
              UV_PYTHON_DOWNLOADS = "never";
            };

            shellHook = pkgs.lib.optionalString pkgs.stdenv.isLinux ''
              export LD_LIBRARY_PATH="${pkgs.lib.makeLibraryPath runtimeLibs}''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
            '';
          };
        });
    };
}
