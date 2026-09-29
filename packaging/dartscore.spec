# PyInstaller spec for the release builds; run via `python packaging/build.py`.
# Produces a one-folder bundle dist/dartscore/ with the server, the built frontend and the
# config template. The frontend must be built first (frontend/dist).
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

root = Path(SPECPATH).parent
migrations = root / "backend" / "src" / "dartscore" / "storage" / "migrations"
frontend = root / "frontend" / "dist"
if not (frontend / "index.html").is_file():
    sys.exit("frontend/dist is missing - run `npm run build` in frontend/ first")

datas = [
    (str(frontend), "frontend"),
    (str(root / "packaging" / "config.template.toml"), "."),
    (str(root / "packaging" / "icons" / "dartscore.png"), "."),
    # alembic reads env.py and the revisions as files from script_location
    (str(migrations), "dartscore/storage/migrations"),
    *copy_metadata("dartscore"),
]
hiddenimports = [
    *collect_submodules("uvicorn"),
    *collect_submodules("alembic", filter=lambda name: ".testing" not in name),
    *collect_submodules("dartscore", filter=lambda name: ".migrations" not in name),
    "sqlalchemy.dialects.sqlite",
]

a = Analysis(
    [str(root / "packaging" / "entry.py")],
    pathex=[str(root / "backend" / "src")],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "mypy"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="dartscore",
    console=True,
    icon=str(root / "packaging" / "icons" / "dartscore.ico") if sys.platform == "win32" else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="dartscore")
