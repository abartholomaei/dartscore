# Install dartscore on Windows

For Windows 10 and 11 (64-bit). No administrator rights needed; Python and Node.js are not required.

Other systems: [Linux](linux.md) · [macOS](macos.md)

## 1. Install

1. Download `dartscore-<version>-windows-x64-setup.exe` from the [releases page](https://github.com/abartholomaei/dartscore/releases/latest).
2. Run it. The installer is not signed with a code-signing certificate, so Windows SmartScreen shows **"Windows protected your PC"**: click **More info** → **Run anyway**.
3. Choose the options:
   - **Create a desktop shortcut** (on by default)
   - **Start dartscore when I sign in to Windows** (off by default)

The installer sets up:

| What | Where |
| --- | --- |
| Program | `%LOCALAPPDATA%\Programs\dartscore` |
| Shortcuts | Start menu (**dartscore**, **dartscore settings**), desktop |
| Settings and data (created on the first start) | `%LOCALAPPDATA%\dartscore` (`config.toml`, `data\`) |

Without installing: the `dartscore-<version>-windows-x64.zip` contains the same program. Extract it anywhere and double-click `dartscore\dartscore.exe`, or create a shortcut to `dartscore.exe launch` yourself.

## 2. Start

Click **dartscore** on the desktop or in the Start menu. A console window opens with the server log and the addresses, and the browser opens the dartscore UI at http://localhost:8000. Close the console window (or press Ctrl+C in it) to stop dartscore. If dartscore is already running, the shortcut just opens the browser.

On the first start, **Windows Defender Firewall** asks whether dartscore may communicate on networks: allow **Private networks**, so phones and tablets on the home network can connect.

Phones, tablets and TVs open `http://<address of this PC>:8000`; the console window lists the addresses, and the UI shows a QR code.

## 3. Set up the cameras

Open **Command Prompt** or **PowerShell** and run:

```powershell
& "$env:LOCALAPPDATA\Programs\dartscore\dartscore.exe" devices
```

(In Command Prompt: `"%LOCALAPPDATA%\Programs\dartscore\dartscore.exe" devices`.)

It lists the connected cameras by number (`0`, `1`, `2`, …); a built-in laptop camera is usually `0`. Open the settings with Start menu → **dartscore settings** → `config.toml` (Notepad is fine; the file exists after the first start). Remove the `#` in front of the three `[[cameras]]` blocks and enter the numbers of the dart cameras as `device`. Then close the console window, start dartscore again and calibrate the board on the **Cameras** page of the UI.

Notes for Windows:

- Camera numbers can change when cameras are plugged into other ports; keep each camera in the same port.
- Windows 11 asks for camera permission per app: Settings → Privacy & security → Camera → **Let desktop apps access your camera** must be on.
- `v4l2_controls` (fixed exposure etc.) only work on Linux and are ignored here.

All options are explained in [config.example.toml](../../config.example.toml), the camera details in [hardware-setup.md](../hardware-setup.md).

## Update

Download and run the new setup `.exe`; it replaces the program and keeps settings and data. Close dartscore first.

## Uninstall

Settings → Apps → Installed apps → **dartscore** → Uninstall. Settings and data stay in `%LOCALAPPDATA%\dartscore`; delete that folder too to remove everything.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Console window says the port is in use | Another program uses port 8000: set another `port` under `[server]` in `config.toml`. |
| No camera image | Camera permission for desktop apps (see above), or another program (Teams, Zoom, Autodarts) is using the camera. |
| Phones can't connect | The firewall question was answered with "Cancel": Windows Security → Firewall & network protection → Allow an app through firewall → enable `dartscore` for Private. Check that the Wi-Fi network is set to *Private*. |
