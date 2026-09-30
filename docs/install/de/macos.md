# dartscore unter macOS installieren

Für Macs mit Apple Silicon (M1 oder neuer) und macOS 14 Sonoma oder neuer. Python und Node.js werden nicht gebraucht. Intel-Macs: Installation [aus dem Quellcode](../../../README.md#setup).

Andere Systeme: [Linux](linux.md) · [Windows](windows.md) · English: [macOS](../macos.md)

## 1. Installieren

Öffne das **Terminal** (Programme → Dienstprogramme) und führe aus:

```bash
curl -fsSL https://github.com/abartholomaei/dartscore/releases/latest/download/install.sh | sh
```

Das Skript lädt das neueste Release und installiert:

| Was | Wo |
| --- | --- |
| App | `/Applications/dartscore.app` (`~/Applications`, falls `/Applications` nicht beschreibbar ist) |
| Verknüpfung | `dartscore` auf dem Schreibtisch |
| Befehl `dartscore` | `~/.local/bin/dartscore` |
| Einstellungen und Daten (beim ersten Start angelegt) | `~/Library/Application Support/dartscore` (`config.toml`, `data/`) |

Lieber von Hand herunterladen? Lade `dartscore-<version>-macos-arm64.tar.gz` von der [Release-Seite](https://github.com/abartholomaei/dartscore/releases), entpacke es per Doppelklick im Download-Ordner, zieh dann `install.sh` aus dem entpackten Ordner in ein Terminal-Fenster und drücke Return.

Warum ein Skript statt die App in den Programme-Ordner zu ziehen? Das Release ist nicht mit einem Apple-Entwicklerzertifikat signiert, deshalb würde macOS eine per Browser geladene App blockieren („kann nicht geöffnet werden, da Apple sie nicht auf Schadsoftware überprüfen kann“). Das Skript entfernt diese Download-Markierung von dartscore.app. Hast du die App selbst verschoben, führe einmal aus:

```bash
xattr -dr com.apple.quarantine /Applications/dartscore.app
```

## 2. Starten

Doppelklicke **dartscore** auf dem Schreibtisch, im Launchpad oder im Programme-Ordner. Ein Terminal-Fenster mit dem Server-Log und den Adressen öffnet sich, und der Browser zeigt die dartscore-Oberfläche unter http://localhost:8000. Schließe das Terminal-Fenster (oder drücke darin Ctrl+C), um dartscore zu beenden. Läuft dartscore bereits, öffnet die App nur den Browser.

Beim ersten Start fragt macOS:

- **„Terminal möchte auf die Kamera zugreifen“** – erlauben, dartscore liest die Kameras über das Terminal-Fenster. Später änderbar unter Systemeinstellungen → Datenschutz & Sicherheit → Kamera.
- **„Soll das Programm eingehende Netzwerkverbindungen akzeptieren?“** – erlauben, damit Handys und Tablets sich verbinden können.

Um dartscore aus dem Dock zu starten, zieh `dartscore.app` aus dem Programme-Ordner ins Dock.

Handys, Tablets und Fernseher im Heimnetz öffnen `http://<Adresse dieses Macs>:8000`; das Terminal-Fenster zeigt die Adressen, die Oberfläche zeigt einen QR-Code.

## 3. Kameras einrichten

Im Terminal:

```bash
~/.local/bin/dartscore devices
```

Die Kameras werden mit Nummer aufgelistet (`0`, `1`, `2`, …); die eingebaute FaceTime-Kamera ist meist `0`. Öffne die Einstellungsdatei:

```bash
open -e ~/Library/Application\ Support/dartscore/config.toml
```

Entferne das `#` vor den drei `[[cameras]]`-Blöcken und trage die Nummern der Dart-Kameras als `device` ein. Beende und starte dartscore dann neu und kalibriere die Scheibe auf der Seite **Kameras** der Oberfläche.

Hinweise für macOS:

- Kameranummern können sich ändern, wenn Kameras an andere Anschlüsse gesteckt werden; lass jede Kamera im selben Anschluss.
- `v4l2_controls` (feste Belichtung usw.) gibt es nur unter Linux, hier werden sie ignoriert.

Alle Optionen erklärt [config.example.toml](../../../config.example.toml), Details zu den Kameras stehen in [hardware-setup.md](../../hardware-setup.md) (englisch).

## 4. Bei der Anmeldung starten (optional)

Systemeinstellungen → Allgemein → Anmeldeobjekte → **+** → `dartscore.app` wählen. dartscore öffnet sich dann nach jeder Anmeldung in einem Terminal-Fenster.

## Aktualisieren

Den Installationsbefehl erneut ausführen. Einstellungen und Daten bleiben erhalten.

## Deinstallieren

```bash
curl -fsSL https://github.com/abartholomaei/dartscore/releases/latest/download/install.sh | sh -s -- --uninstall
```

Entfernt die App, die Schreibtisch-Verknüpfung und den Befehl. Einstellungen und Daten bleiben in `~/Library/Application Support/dartscore`; lösche den Ordner auch, um alles zu entfernen.

## Fehlerbehebung

| Problem | Lösung |
| --- | --- |
| „dartscore.app ist beschädigt“ oder „kann nicht geöffnet werden“ | Den `xattr`-Befehl aus Schritt 1 ausführen. |
| Kein Kamerabild, im Log steht „not authorized to capture video“ | Systemeinstellungen → Datenschutz & Sicherheit → Kamera → Terminal aktivieren, dann dartscore neu starten. |
| Port 8000 ist belegt | Unter `[server]` in `config.toml` einen anderen `port` eintragen. |
| Handys verbinden sich nicht | Systemeinstellungen → Netzwerk → Firewall → Optionen: eingehende Verbindungen für `dartscore` erlauben. |
