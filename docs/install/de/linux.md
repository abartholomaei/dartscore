# dartscore unter Linux installieren

Für x86_64-PCs (Debian 12+, Ubuntu 22.04+ und ähnliche) und ARM64-Boards wie den Raspberry Pi 5 (64-Bit-Raspberry-Pi-OS). Keine Root-Rechte nötig, Python und Node.js werden nicht gebraucht.

Andere Systeme: [macOS](macos.md) · [Windows](windows.md) · aus dem Quellcode: [README](../../../README.md#setup) · English: [Linux](../linux.md)

## 1. Installieren

Im Terminal:

```bash
curl -fsSL https://github.com/abartholomaei/dartscore/releases/latest/download/install.sh | sh
```

Das Skript lädt das neueste Release für deinen Prozessor und installiert:

| Was | Wo |
| --- | --- |
| Programm | `~/.local/lib/dartscore` |
| Befehl `dartscore` | `~/.local/bin/dartscore` |
| Eintrag im App-Menü und Desktop-Verknüpfung | `~/.local/share/applications/dartscore.desktop`, `~/Desktop/dartscore.desktop` |
| Einstellungen und Daten (beim ersten Start angelegt) | `~/.local/share/dartscore` (`config.toml`, `data/`) |

Lieber von Hand herunterladen? Lade `dartscore-<version>-linux-x86_64.tar.gz` (oder `-linux-arm64`) von der [Release-Seite](https://github.com/abartholomaei/dartscore/releases), dann:

```bash
tar -xzf dartscore-*-linux-*.tar.gz
```

```bash
./dartscore-*/install.sh
```

## 2. Kamerazugriff

Linux erlaubt Kameras nur Mitgliedern der Gruppe `video`. Füge dich einmal hinzu und melde dich danach ab und wieder an:

```bash
sudo usermod -aG video $USER
```

`v4l-utils` wird empfohlen: dartscore setzt damit Kamera-Einstellungen wie eine feste Belichtung.

```bash
sudo apt install v4l-utils
```

## 3. Starten

Klicke auf **dartscore** im App-Menü oder auf dem Desktop. Ein Terminal-Fenster mit dem Server-Log und den Adressen öffnet sich, und der Browser zeigt die dartscore-Oberfläche unter http://localhost:8000. Schließe das Terminal-Fenster (oder drücke darin Strg+C), um dartscore zu beenden. Läuft dartscore bereits, öffnet die Verknüpfung nur den Browser.

GNOME: Zeigt die Desktop-Verknüpfung ein Warnsymbol, klicke sie mit rechts an und wähle **Start erlauben**. Desktop-Symbole brauchen unter GNOME die Erweiterung *Desktop Icons NG* (bei Ubuntu vorinstalliert).

Im Terminal geht dasselbe mit `dartscore launch`; `dartscore serve` startet nur den Server.

Handys, Tablets und Fernseher im Heimnetz öffnen `http://<Adresse dieses Computers>:8000`; das Terminal-Fenster zeigt die Adressen, die Oberfläche zeigt einen QR-Code.

## 4. Kameras einrichten

```bash
dartscore devices
```

Listet die angeschlossenen Kameras mit ihren stabilen Pfaden `/dev/v4l/by-path/...` auf. Öffne `~/.local/share/dartscore/config.toml`, entferne das `#` vor den drei `[[cameras]]`-Blöcken und trage diese Pfade als `device` ein. Starte dartscore dann neu und kalibriere die Scheibe auf der Seite **Kameras** der Oberfläche.

Alle Optionen (Auflösung, Belichtung, Erkennung) erklärt [config.example.toml](../../../config.example.toml), Details zu den Kameras stehen in [hardware-setup.md](../../hardware-setup.md) (englisch). Die Kamera-Befehle dort funktionieren mit der installierten Version genauso: schreibe `dartscore ...` statt `uv run --project backend dartscore ...`.

## 5. Beim Hochfahren starten (optional)

Auf einem reinen Dart-Rechner kann dartscore als systemd-Benutzerdienst laufen, der mit dem Computer startet, ohne dass sich jemand anmelden muss:

```bash
curl -fsSL https://github.com/abartholomaei/dartscore/releases/latest/download/install.sh | sh -s -- --service
```

(oder `./install.sh --service` aus dem entpackten Archiv). Die Desktop-Verknüpfung öffnet dann nur noch den Browser. Nützliche Befehle:

```bash
systemctl --user status dartscore
```

```bash
journalctl --user -u dartscore -f
```

Meldet das Skript, dass Lingering nicht aktiviert werden konnte, führe einmal `sudo loginctl enable-linger $USER` aus; sonst läuft der Dienst nur, solange du angemeldet bist.

## Aktualisieren

Den Installationsbefehl erneut ausführen. Einstellungen, Daten und ein eingerichteter Autostart-Dienst bleiben erhalten.

## Deinstallieren

```bash
curl -fsSL https://github.com/abartholomaei/dartscore/releases/latest/download/install.sh | sh -s -- --uninstall
```

Entfernt Programm, Verknüpfungen und Dienst. Einstellungen und Daten bleiben in `~/.local/share/dartscore`; lösche den Ordner auch, um alles zu entfernen.

## Fehlerbehebung

| Problem | Lösung |
| --- | --- |
| `dartscore: command not found` | `~/.local/bin` ist nicht im `PATH`. Ab- und wieder anmelden (die meisten Distributionen nehmen den Ordner automatisch auf, sobald er existiert) oder den vollen Pfad `~/.local/bin/dartscore` verwenden. |
| Kamera meldet „Cannot open camera“ | Gruppe `video` fehlt (siehe Schritt 2) oder ein anderes Programm nutzt die Kamera (`fuser /dev/video*`). |
| Terminal-Fenster schließt sich sofort | `dartscore launch` im Terminal starten, um den Fehler zu sehen. Port 8000 belegt: unter `[server]` in `config.toml` einen anderen `port` eintragen. |
| Handys verbinden sich nicht | Port 8000 in der Firewall freigeben, z. B. `sudo ufw allow 8000/tcp`. |
