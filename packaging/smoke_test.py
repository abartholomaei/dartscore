"""Start the built bundle in a temporary home folder and check that it serves UI and API.

python packaging/smoke_test.py [path to the dartscore executable]
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 18765


def get(path: str) -> bytes:
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=2) as response:
        return bytes(response.read())


def main() -> None:
    exe_name = "dartscore.exe" if sys.platform == "win32" else "dartscore"
    exe = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "build/dist/dartscore" / exe_name
    with tempfile.TemporaryDirectory() as home:
        env = {**os.environ, "DARTSCORE_HOME": home, "DARTSCORE_SERVER__PORT": str(PORT)}
        version = subprocess.run(
            [exe, "--version"], env=env, capture_output=True, text=True, check=True
        )
        print(version.stdout.strip())
        proc = subprocess.Popen([exe, "launch", "--no-browser"], env=env)
        try:
            deadline = time.monotonic() + 90
            while True:
                try:
                    health = json.loads(get("/api/health"))
                    break
                except OSError:
                    if proc.poll() is not None or time.monotonic() > deadline:
                        sys.exit("server did not come up")
                    time.sleep(1)
            assert health["status"] == "ok", health
            assert b'<div id="root">' in get("/"), "frontend not served"
            assert b"<!doctype html>" in get("/settings").lower(), "SPA fallback missing"
            assert json.loads(get("/api/players")) == [], "players API"
            assert (Path(home) / "config.toml").is_file(), "config.toml not created"
            assert (Path(home) / "data" / "dartscore.db").is_file(), "database not created"
            print(f"smoke test passed: {health}")
        finally:
            proc.terminate()
            proc.wait(timeout=30)


if __name__ == "__main__":
    main()
