#!/bin/sh
# dartscore installer for Linux and macOS (no root needed).
#
# Run it from an extracted release archive, or directly from GitHub, which downloads the
# latest release for this computer first:
#
#   curl -fsSL https://github.com/abartholomaei/dartscore/releases/latest/download/install.sh | sh
#
# Options:
#   --service     Linux: also start dartscore at boot as a systemd user service
#   --version X   download release X (e.g. 0.2.0) instead of the latest one
#   --uninstall   remove the program and the shortcuts (settings and data are kept)
#
# What it installs:
#   Linux:  ~/.local/lib/dartscore (program), ~/.local/bin/dartscore (command),
#           an app menu entry and a desktop shortcut
#   macOS:  /Applications/dartscore.app (or ~/Applications), a Desktop shortcut and the
#           command ~/.local/bin/dartscore
# Settings and data: ~/.local/share/dartscore (Linux), ~/Library/Application Support/dartscore
set -eu

REPO="abartholomaei/dartscore"
SERVICE=0
UNINSTALL=0
VERSION=""
while [ $# -gt 0 ]; do
  case "$1" in
    --service) SERVICE=1 ;;
    --uninstall) UNINSTALL=1 ;;
    --version) VERSION="${2:?--version needs a value}"; shift ;;
    -h|--help) sed -n '2,20p' "$0" 2>/dev/null | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

say() { printf '%s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

OS="$(uname -s)"
case "$OS" in
  Linux) PLATFORM=linux ;;
  Darwin) PLATFORM=macos ;;
  *) die "unsupported system $OS - on Windows use the setup .exe from the releases page" ;;
esac
case "$(uname -m)" in
  x86_64|amd64) ARCH=x86_64 ;;
  aarch64|arm64) ARCH=arm64 ;;
  *) die "unsupported processor $(uname -m)" ;;
esac
[ "$PLATFORM" = macos ] && [ "$ARCH" != arm64 ] &&
  die "release builds for Intel Macs are not available - install from source (see README)"

BIN_DIR="$HOME/.local/bin"
if [ "$PLATFORM" = linux ]; then
  LIB_DIR="$HOME/.local/lib/dartscore"
  DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
  APPS_DIR="$DATA_HOME/applications"
  ICON_DIR="$DATA_HOME/icons/hicolor/512x512/apps"
  UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
  DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
  HOME_DIR="$DATA_HOME/dartscore"
else
  if [ -n "${DARTSCORE_APP_DIR:-}" ]; then APP_DIR="$DARTSCORE_APP_DIR"
  elif [ -d "$HOME/Applications/dartscore.app" ] || [ ! -w /Applications ]; then
    APP_DIR="$HOME/Applications"
  else APP_DIR=/Applications; fi
  DESKTOP_DIR="$HOME/Desktop"
  HOME_DIR="$HOME/Library/Application Support/dartscore"
fi

uninstall() {
  if [ "$PLATFORM" = linux ]; then
    if [ -f "$UNIT_DIR/dartscore.service" ]; then
      systemctl --user disable --now dartscore.service 2>/dev/null || true
      rm -f "$UNIT_DIR/dartscore.service"
      systemctl --user daemon-reload 2>/dev/null || true
    fi
    rm -rf "$LIB_DIR"
    rm -f "$APPS_DIR/dartscore.desktop" "$DESKTOP_DIR/dartscore.desktop" "$ICON_DIR/dartscore.png"
  else
    rm -rf "$APP_DIR/dartscore.app"
    rm -f "$DESKTOP_DIR/dartscore"
  fi
  rm -f "$BIN_DIR/dartscore"
}

if [ "$UNINSTALL" = 1 ]; then
  uninstall
  say "dartscore removed. Settings and data are still in: $HOME_DIR"
  exit 0
fi

# Find the package: next to this script (extracted archive) or download it.
SRC=""
case "$0" in
  */*) here="$(cd "$(dirname "$0")" && pwd)" ;;
  *) here="" ;;
esac
if [ -n "$here" ] && { [ -d "$here/dartscore" ] || [ -d "$here/dartscore.app" ]; }; then
  SRC="$here"
else
  command -v curl >/dev/null || die "curl is needed to download dartscore"
  if [ -z "$VERSION" ]; then
    VERSION="$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" |
      sed -n 's/.*"tag_name": *"v\{0,1\}\([^"]*\)".*/\1/p' | head -n 1)"
    [ -n "$VERSION" ] || die "could not find the latest release"
  fi
  NAME="dartscore-$VERSION-$PLATFORM-$ARCH"
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  say "Downloading $NAME ..."
  curl -fL --progress-bar -o "$TMP/$NAME.tar.gz" \
    "https://github.com/$REPO/releases/download/v$VERSION/$NAME.tar.gz" ||
    die "download failed"
  tar -xzf "$TMP/$NAME.tar.gz" -C "$TMP"
  SRC="$TMP/$NAME"
fi

# an update keeps an existing autostart service (uninstall stops it, it is set up again below)
[ "$PLATFORM" = linux ] && [ -f "$UNIT_DIR/dartscore.service" ] && SERVICE=1
uninstall
mkdir -p "$BIN_DIR"

if [ "$PLATFORM" = linux ]; then
  mkdir -p "$(dirname "$LIB_DIR")" "$APPS_DIR" "$ICON_DIR"
  cp -R "$SRC/dartscore" "$LIB_DIR"
  ln -sf "$LIB_DIR/dartscore" "$BIN_DIR/dartscore"
  cp "$LIB_DIR/_internal/dartscore.png" "$ICON_DIR/dartscore.png"
  cat > "$APPS_DIR/dartscore.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=dartscore
Comment=Auto-scoring for steel-tip darts
Exec="$LIB_DIR/dartscore" launch
Icon=dartscore
Terminal=true
Categories=Game;
EOF
  chmod +x "$APPS_DIR/dartscore.desktop"
  if [ -d "$DESKTOP_DIR" ]; then
    cp "$APPS_DIR/dartscore.desktop" "$DESKTOP_DIR/dartscore.desktop"
    chmod +x "$DESKTOP_DIR/dartscore.desktop"
    # GNOME only starts desktop files that are marked as trusted
    gio set "$DESKTOP_DIR/dartscore.desktop" metadata::trusted true 2>/dev/null || true
  fi
  update-desktop-database "$APPS_DIR" 2>/dev/null || true

  if [ "$SERVICE" = 1 ]; then
    mkdir -p "$UNIT_DIR"
    cat > "$UNIT_DIR/dartscore.service" <<EOF
[Unit]
Description=dartscore - local auto-scoring for steel-tip darts
After=network-online.target

[Service]
ExecStart="$LIB_DIR/dartscore" serve
Environment=DARTSCORE_LOGGING__JSON_OUTPUT=true
Restart=on-failure
RestartSec=5
TimeoutStopSec=15
SuccessExitStatus=143

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable --now dartscore.service
    # user services normally stop at logout; lingering keeps dartscore running from boot
    loginctl enable-linger "$(id -un)" 2>/dev/null ||
      say "Note: run 'sudo loginctl enable-linger $(id -un)' so dartscore starts at boot."
  fi

  if ! id -nG | tr ' ' '\n' | grep -qx video; then
    say "Note: to use the cameras, add yourself to the video group and log in again:"
    say "  sudo usermod -aG video $(id -un)"
  fi
  command -v v4l2-ctl >/dev/null ||
    say "Note: 'sudo apt install v4l-utils' is recommended (camera settings, stable names)."
else
  mkdir -p "$APP_DIR"
  cp -R "$SRC/dartscore.app" "$APP_DIR/dartscore.app"
  # the release is not notarized; files downloaded by a browser would be blocked
  xattr -dr com.apple.quarantine "$APP_DIR/dartscore.app" 2>/dev/null || true
  ln -sf "$APP_DIR/dartscore.app/Contents/Resources/dartscore/dartscore" "$BIN_DIR/dartscore"
  [ -d "$DESKTOP_DIR" ] && ln -sfn "$APP_DIR/dartscore.app" "$DESKTOP_DIR/dartscore"
fi

say ""
say "dartscore installed."
if [ "$PLATFORM" = linux ]; then
  say "  Start:     'dartscore' in the app menu or on the desktop"
else
  say "  Start:     dartscore in $APP_DIR (Launchpad) or on the Desktop"
fi
say "  Cameras:   dartscore devices   (then enter them in config.toml)"
say "  Settings:  $HOME_DIR/config.toml (created on the first start)"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) say "  Note: add $BIN_DIR to your PATH to use the 'dartscore' command." ;;
esac
