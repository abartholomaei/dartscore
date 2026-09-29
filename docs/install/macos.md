# Install dartscore on macOS

For Macs with Apple Silicon (M1 or newer) and macOS 14 Sonoma or newer. Python and Node.js are not required. Intel Macs: install [from source](../../README.md#setup).

Other systems: [Linux](linux.md) · [Windows](windows.md)

## 1. Install

Open **Terminal** (Applications → Utilities) and run:

```bash
curl -fsSL https://github.com/abartholomaei/dartscore/releases/latest/download/install.sh | sh
```

The script downloads the latest release and installs:

| What | Where |
| --- | --- |
| App | `/Applications/dartscore.app` (`~/Applications` if you can't write to `/Applications`) |
| Shortcut | `dartscore` on the Desktop |
| `dartscore` command | `~/.local/bin/dartscore` |
| Settings and data (created on the first start) | `~/Library/Application Support/dartscore` (`config.toml`, `data/`) |

Prefer to download by hand? Get `dartscore-<version>-macos-arm64.tar.gz` from the [releases page](https://github.com/abartholomaei/dartscore/releases), double-click it in Downloads to extract it, then drag the `install.sh` from the extracted folder into a Terminal window and press Return.

Why a script instead of dragging the app to Applications? The release is not signed with an Apple developer certificate, so macOS would refuse to open an app downloaded by the browser ("cannot be opened because Apple cannot check it for malicious software"). The script removes that download mark from dartscore.app. If you did drag the app yourself, run this once:

```bash
xattr -dr com.apple.quarantine /Applications/dartscore.app
```

## 2. Start

Double-click **dartscore** on the Desktop, in Launchpad or in Applications. A Terminal window opens with the server log and the addresses, and the browser opens the dartscore UI at http://localhost:8000. Close the Terminal window (or press Ctrl+C in it) to stop dartscore. If dartscore is already running, the app just opens the browser.

On the first start, macOS asks:

- **"Terminal would like to access the camera"** – allow it, dartscore reads the cameras through the Terminal window. Changed later in System Settings → Privacy & Security → Camera.
- **"Do you want the application to accept incoming network connections?"** – allow it, so phones and tablets can connect.

To start it from the Dock, drag `dartscore.app` from Applications to the Dock.

Phones, tablets and TVs on the home network open `http://<address of this Mac>:8000`; the Terminal window lists the addresses, and the UI shows a QR code.

## 3. Set up the cameras

In Terminal:

```bash
~/.local/bin/dartscore devices
```

Lists the connected cameras by number (`0`, `1`, `2`, …); the built-in FaceTime camera is usually `0`. Open the settings file:

```bash
open -e ~/Library/Application\ Support/dartscore/config.toml
```

Remove the `#` in front of the three `[[cameras]]` blocks and enter the numbers of the dart cameras as `device`. Then quit and restart dartscore and calibrate the board on the **Cameras** page of the UI.

Notes for macOS:

- Camera numbers can change when cameras are plugged into other ports; keep each camera in the same port.
- `v4l2_controls` (fixed exposure etc.) only work on Linux and are ignored here.

All options are explained in [config.example.toml](../../config.example.toml), the camera details in [hardware-setup.md](../hardware-setup.md).

## 4. Start at login (optional)

System Settings → General → Login Items → **+** → choose `dartscore.app`. dartscore then opens in a Terminal window after every login.

## Update

Run the install command again. Settings and data are kept.

## Uninstall

```bash
curl -fsSL https://github.com/abartholomaei/dartscore/releases/latest/download/install.sh | sh -s -- --uninstall
```

This removes the app, the Desktop shortcut and the command. Settings and data stay in `~/Library/Application Support/dartscore`; delete that folder too to remove everything.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| "dartscore.app is damaged" or "cannot be opened" | Run the `xattr` command from step 1. |
| No camera image, log says "not authorized to capture video" | System Settings → Privacy & Security → Camera → enable Terminal, then restart dartscore. |
| Port 8000 in use | Set another `port` under `[server]` in `config.toml`. |
| Phones can't connect | System Settings → Network → Firewall → Options: allow incoming connections for `dartscore`. |
