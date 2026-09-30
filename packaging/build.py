"""Build the release package for the current operating system.

    python packaging/build.py [--skip-frontend]

Steps: build the frontend, bundle server + frontend with PyInstaller, then wrap the bundle
the way the platform expects it. Results land in release/:

- Linux:   dartscore-<version>-linux-<arch>.tar.gz (bundle + install.sh)
- macOS:   dartscore-<version>-macos-<arch>.tar.gz (dartscore.app + install.sh)
- Windows: dartscore-<version>-windows-x64.zip (portable) and, if Inno Setup's iscc is
           installed, dartscore-<version>-windows-x64-setup.exe
"""

import argparse
import platform
import plistlib
import shutil
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGING = ROOT / "packaging"
BUILD = ROOT / "build"
RELEASE = ROOT / "release"


def version() -> str:
    with (ROOT / "backend" / "pyproject.toml").open("rb") as f:
        return str(tomllib.load(f)["project"]["version"])


def platform_tag() -> str:
    machine = platform.machine().lower()
    arch = {"amd64": "x64", "x86_64": "x64", "aarch64": "arm64", "arm64": "arm64"}.get(
        machine, machine
    )
    if sys.platform == "win32":
        return f"windows-{arch}"
    if sys.platform == "darwin":
        return f"macos-{arch}"
    return f"linux-{'x86_64' if arch == 'x64' else arch}"


def run(*cmd: str, cwd: Path = ROOT) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def build_frontend() -> None:
    npm = shutil.which("npm") or sys.exit("npm not found")
    run(npm, "ci", "--no-audit", "--no-fund", cwd=ROOT / "frontend")
    run(npm, "run", "build", cwd=ROOT / "frontend")


def build_bundle() -> Path:
    uv = shutil.which("uv") or sys.exit("uv not found")
    run(
        uv, "run", "--project", "backend", "--group", "package",
        "pyinstaller", "--noconfirm", "--clean",
        "--distpath", str(BUILD / "dist"), "--workpath", str(BUILD / "work"),
        str(PACKAGING / "dartscore.spec"),
    )  # fmt: skip
    return BUILD / "dist" / "dartscore"


def macos_app(bundle: Path, target: Path, ver: str) -> Path:
    """dartscore.app: the launcher opens a Terminal window running `dartscore launch`, so the
    log stays visible, closing the window stops the server and macOS asks for camera access
    on behalf of Terminal."""
    app = target / "dartscore.app"
    contents = app / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    resources = contents / "Resources"
    resources.mkdir()
    shutil.copytree(bundle, resources / "dartscore", symlinks=True)
    shutil.copy(PACKAGING / "icons" / "dartscore.icns", resources / "dartscore.icns")
    for name, dest in (("launcher.sh", contents / "MacOS" / "dartscore"),
                       ("dartscore.command", resources / "dartscore.command")):  # fmt: skip
        shutil.copy(PACKAGING / "macos" / name, dest)
        dest.chmod(0o755)
    info = {
        "CFBundleName": "dartscore",
        "CFBundleDisplayName": "dartscore",
        "CFBundleIdentifier": "io.github.abartholomaei.dartscore",
        "CFBundleVersion": ver,
        "CFBundleShortVersionString": ver,
        "CFBundlePackageType": "APPL",
        "CFBundleExecutable": "dartscore",
        "CFBundleIconFile": "dartscore.icns",
        "LSMinimumSystemVersion": "14.0",
        "NSHighResolutionCapable": True,
    }
    with (contents / "Info.plist").open("wb") as f:
        plistlib.dump(info, f)
    return app


def tar_gz(folder: Path, out: Path) -> None:
    with tarfile.open(out, "w:gz") as tar:
        tar.add(folder, arcname=folder.name)


def zip_dir(folder: Path, out: Path) -> None:
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(folder.rglob("*")):
            zf.write(path, Path(folder.name) / path.relative_to(folder))


def package(bundle: Path, ver: str) -> list[Path]:
    tag = platform_tag()
    name = f"dartscore-{ver}-{tag}"
    stage = BUILD / "stage" / name
    shutil.rmtree(stage.parent, ignore_errors=True)
    stage.mkdir(parents=True)
    RELEASE.mkdir(exist_ok=True)
    shutil.copy(ROOT / "LICENSE", stage / "LICENSE.txt")
    outputs: list[Path] = []

    if sys.platform == "win32":
        shutil.copytree(bundle, stage / "dartscore")
        outputs.append(RELEASE / f"{name}.zip")
        zip_dir(stage, outputs[-1])
        iscc = shutil.which("iscc") or shutil.which(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe")
        if iscc:
            run(
                iscc, f"/DAppVersion={ver}", f"/DBundleDir={bundle}",
                f"/DOutputDir={RELEASE}", f"/DOutputName={name}-setup",
                str(PACKAGING / "windows" / "dartscore.iss"),
            )  # fmt: skip
            outputs.append(RELEASE / f"{name}-setup.exe")
        else:
            print("iscc (Inno Setup) not found - skipping the installer")
    else:
        if sys.platform == "darwin":
            macos_app(bundle, stage, ver)
        else:
            shutil.copytree(bundle, stage / "dartscore", symlinks=True)
        shutil.copy(PACKAGING / "install.sh", stage / "install.sh")
        (stage / "install.sh").chmod(0o755)
        outputs.append(RELEASE / f"{name}.tar.gz")
        tar_gz(stage, outputs[-1])
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-frontend", action="store_true", help="use the existing dist")
    args = parser.parse_args()
    ver = version()
    if not args.skip_frontend:
        build_frontend()
    bundle = build_bundle()
    for out in package(bundle, ver):
        print(f"built {out.relative_to(ROOT)} ({out.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
