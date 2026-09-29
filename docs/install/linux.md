# Install dartscore on Linux

For x86_64 PCs (Debian 12+, Ubuntu 22.04+, similar) and ARM64 boards such as the Raspberry Pi 5 (64-bit Raspberry Pi OS). No root rights needed; Python and Node.js are not required.

Other systems: [macOS](macos.md) · [Windows](windows.md) · from source: [README](../../README.md#setup)

## 1. Install

In a terminal:

```bash
curl -fsSL https://github.com/abartholomaei/dartscore/releases/latest/download/install.sh | sh
```

The script downloads the latest release for your processor and installs:

| What | Where |
| --- | --- |
| Program | `~/.local/lib/dartscore` |
| `dartscore` command | `~/.local/bin/dartscore` |
| App menu entry and desktop shortcut | `~/.local/share/applications/dartscore.desktop`, `~/Desktop/dartscore.desktop` |
| Settings and data (created on the first start) | `~/.local/share/dartscore` (`config.toml`, `data/`) |

Prefer to download by hand? Get `dartscore-<version>-linux-x86_64.tar.gz` (or `-linux-arm64`) from the [releases page](https://github.com/abartholomaei/dartscore/releases), then:

```bash
tar -xzf dartscore-*-linux-*.tar.gz
```

```bash
./dartscore-*/install.sh
```

## 2. Camera access

Linux only lets members of the `video` group use cameras. Add yourself once, then log out and back in:

```bash
sudo usermod -aG video $USER
```

`v4l-utils` is recommended: dartscore uses it to set camera controls such as a fixed exposure.

```bash
sudo apt install v4l-utils
```

## 3. Start

Click **dartscore** in the app menu or on the desktop. A terminal window opens with the server log and the addresses, and the browser opens the dartscore UI at http://localhost:8000. Close the terminal window (or press Ctrl+C in it) to stop dartscore. If dartscore is already running, the shortcut just opens the browser.

GNOME: if the desktop shortcut shows a warning sign, right-click it and choose **Allow Launching**. The desktop icons of GNOME need the *Desktop Icons NG* extension (preinstalled on Ubuntu).

From a terminal the same is `dartscore launch`; `dartscore serve` starts only the server.

Phones, tablets and TVs on the home network open `http://<address of this computer>:8000`; the terminal window lists the addresses, and the UI shows a QR code.

## 4. Set up the cameras

```bash
dartscore devices
```

Lists the connected cameras with their stable `/dev/v4l/by-path/...` paths. Open `~/.local/share/dartscore/config.toml`, remove the `#` in front of the three `[[cameras]]` blocks and enter these paths as `device`. Then restart dartscore and calibrate the board on the **Cameras** page of the UI.

All options (resolution, exposure, detection) are explained in [config.example.toml](../../config.example.toml); the camera details in [hardware-setup.md](../hardware-setup.md). The camera commands there work the same with the installed version: write `dartscore ...` instead of `uv run --project backend dartscore ...`.

## 5. Start at boot (optional)

For a dedicated darts computer, dartscore can run as a systemd user service that starts with the computer, without anyone logging in:

```bash
curl -fsSL https://github.com/abartholomaei/dartscore/releases/latest/download/install.sh | sh -s -- --service
```

(or `./install.sh --service` from the extracted archive). The desktop shortcut then only opens the browser. Useful commands:

```bash
systemctl --user status dartscore
```

```bash
journalctl --user -u dartscore -f
```

If the script reports that lingering could not be enabled, run `sudo loginctl enable-linger $USER` once; without it the service only runs while you are logged in.

## Update

Run the install command again. Settings, data and an autostart service are kept.

## Uninstall

```bash
curl -fsSL https://github.com/abartholomaei/dartscore/releases/latest/download/install.sh | sh -s -- --uninstall
```

This removes the program, the shortcuts and the service. Settings and data stay in `~/.local/share/dartscore`; delete that folder too to remove everything.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `dartscore: command not found` | `~/.local/bin` is not on your `PATH`. Log out and back in (most distributions add it automatically once it exists) or use the full path `~/.local/bin/dartscore`. |
| Camera shows "Cannot open camera" | Group `video` missing (see step 2) or another program uses the camera (`fuser /dev/video*`). |
| Terminal window closes right away | Start `dartscore launch` from a terminal to see the error. Port 8000 in use: set another `port` under `[server]` in `config.toml`. |
| Phones can't connect | Allow port 8000 in the firewall, e.g. `sudo ufw allow 8000/tcp`. |
