# Releasing

Releases are built by GitHub Actions ([.github/workflows/release.yml](../.github/workflows/release.yml)) and published on the [releases page](https://github.com/abartholomaei/dartscore/releases). Each release contains:

| File | Contents |
| --- | --- |
| `dartscore-<version>-linux-x86_64.tar.gz`, `-linux-arm64.tar.gz` | PyInstaller bundle + `install.sh` |
| `dartscore-<version>-macos-arm64.tar.gz` | `dartscore.app` + `install.sh` |
| `dartscore-<version>-windows-x64-setup.exe` | Inno Setup installer (per user, shortcuts) |
| `dartscore-<version>-windows-x64.zip` | the same program without installer |
| `install.sh` | installer for Linux and macOS that downloads the right archive (`curl … \| sh`) |
| `SHA256SUMS.txt` | checksums |

The bundles contain Python, the server and the built frontend; users need neither Python nor Node.js. No tip model is shipped: it is trained per board (see [training/README.md](../training/README.md)).

## Versions

[Semantic versioning](https://semver.org/) while below 1.0: `0.MINOR.PATCH`, a minor version for new features or changed configuration, a patch version for fixes. The version lives in `backend/pyproject.toml` only; the server reports it (`dartscore --version`, `/api/health`) and the release workflow refuses a tag that doesn't match it.

## Make a release

1. On `main`, with `make check` passing, set the new version in `backend/pyproject.toml` and run `uv lock` in `backend/` (the lock file records the project version).
2. Commit: `Release 0.2.0`.
3. Tag and push:

   ```bash
   git tag -a v0.2.0 -m "dartscore 0.2.0"
   ```

   ```bash
   git push origin main v0.2.0
   ```

4. The workflow builds all four targets, starts each bundle once (`packaging/smoke_test.py`) and creates the release with generated notes (merged pull requests and commits since the last tag) below the download table from [packaging/release-notes.md](../packaging/release-notes.md). Edit the notes on GitHub afterwards to highlight the main changes.

A test build without a release: Actions → Release → **Run workflow**; the packages are then attached to the run as artifacts. Pull requests that change `packaging/` build and test all targets as well.

## Build locally

```bash
make package
```

Builds the package for the current system into `release/` (on Windows, the installer only if [Inno Setup 6](https://jrsoftware.org/isinfo.php) is installed). Test the bundle with:

```bash
python3 packaging/smoke_test.py
```

## How the release build works

- `packaging/dartscore.spec` (PyInstaller, one-folder bundle) packs the `dartscore` package, the alembic migrations, the built frontend and `packaging/config.template.toml`.
- A release build runs in a per-user home folder (`dartscore.paths`): `~/.local/share/dartscore`, `~/Library/Application Support/dartscore` or `%LOCALAPPDATA%\dartscore`, overridable with `DARTSCORE_HOME`. On the first start it copies the config template there as `config.toml`; everything relative in the configuration (such as `data_dir`) is relative to that folder.
- `dartscore launch` (also the default of a release build started without arguments) starts the server and opens the browser once it answers, or only opens the browser if a dartscore already runs on the configured port. All desktop shortcuts call it.
- Shortcuts: Linux `.desktop` files with `Terminal=true`; on macOS `dartscore.app` opens `dartscore launch` in a Terminal window (this also makes macOS ask for camera access on behalf of Terminal); on Windows Start menu and desktop links to `dartscore.exe launch`, which runs in a console window.
- The builds are not code-signed. `install.sh` removes the macOS quarantine flag; the guides explain the SmartScreen warning on Windows.
- Linux builds run on Ubuntu 22.04 (glibc 2.35), so they work on Debian 12 and Raspberry Pi OS (Bookworm). macOS builds are Apple Silicon only, as ONNX Runtime has no Intel macOS wheels.
