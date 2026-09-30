# dartscore unter Windows installieren

Für Windows 10 und 11 (64 Bit). Keine Administratorrechte nötig, Python und Node.js werden nicht gebraucht.

Andere Systeme: [Linux](linux.md) · [macOS](macos.md) · English: [Windows](../windows.md)

## 1. Installieren

1. Lade `dartscore-<version>-windows-x64-setup.exe` von der [Release-Seite](https://github.com/abartholomaei/dartscore/releases/latest) herunter.
2. Starte die Datei. Das Setup ist nicht mit einem Code-Signing-Zertifikat signiert, deshalb zeigt Windows SmartScreen **„Der Computer wurde durch Windows geschützt“**: Klicke auf **Weitere Informationen** → **Trotzdem ausführen**.
3. Wähle die Optionen:
   - **Desktop-Symbol erstellen** (standardmäßig an)
   - **dartscore bei der Windows-Anmeldung starten** (standardmäßig aus)

Das Setup richtet ein:

| Was | Wo |
| --- | --- |
| Programm | `%LOCALAPPDATA%\Programs\dartscore` |
| Verknüpfungen | Startmenü (**dartscore**, **dartscore-Einstellungen**), Desktop |
| Einstellungen und Daten (beim ersten Start angelegt) | `%LOCALAPPDATA%\dartscore` (`config.toml`, `data\`) |

Ohne Installation: `dartscore-<version>-windows-x64.zip` enthält dasselbe Programm. Irgendwo entpacken und `dartscore\dartscore.exe` doppelklicken.

## 2. Starten

Klicke auf **dartscore** auf dem Desktop oder im Startmenü. Ein Konsolenfenster mit dem Server-Log und den Adressen öffnet sich, und der Browser zeigt die dartscore-Oberfläche unter http://localhost:8000. Schließe das Konsolenfenster (oder drücke darin Strg+C), um dartscore zu beenden. Läuft dartscore bereits, öffnet die Verknüpfung nur den Browser.

Beim ersten Start fragt die **Windows Defender Firewall**, ob dartscore in Netzwerken kommunizieren darf: Erlaube **Private Netzwerke**, damit Handys und Tablets im Heimnetz sich verbinden können.

Handys, Tablets und Fernseher öffnen `http://<Adresse dieses PCs>:8000`; das Konsolenfenster zeigt die Adressen, die Oberfläche zeigt einen QR-Code.

## 3. Kameras einrichten

Öffne **Eingabeaufforderung** oder **PowerShell** und führe aus:

```powershell
& "$env:LOCALAPPDATA\Programs\dartscore\dartscore.exe" devices
```

(In der Eingabeaufforderung: `"%LOCALAPPDATA%\Programs\dartscore\dartscore.exe" devices`.)

Die Kameras werden mit Nummer aufgelistet (`0`, `1`, `2`, …); eine eingebaute Laptop-Kamera ist meist `0`. Öffne die Einstellungen über Startmenü → **dartscore-Einstellungen** → `config.toml` (der Editor reicht; die Datei gibt es nach dem ersten Start). Entferne das `#` vor den drei `[[cameras]]`-Blöcken und trage die Nummern der Dart-Kameras als `device` ein. Schließe dann das Konsolenfenster, starte dartscore neu und kalibriere die Scheibe auf der Seite **Kameras** der Oberfläche.

Hinweise für Windows:

- Kameranummern können sich ändern, wenn Kameras an andere Anschlüsse gesteckt werden; lass jede Kamera im selben Anschluss.
- Windows 11 fragt die Kamera-Berechtigung pro App ab: Einstellungen → Datenschutz und Sicherheit → Kamera → **Desktop-Apps den Zugriff auf die Kamera erlauben** muss an sein.
- `v4l2_controls` (feste Belichtung usw.) gibt es nur unter Linux, hier werden sie ignoriert.

Alle Optionen erklärt [config.example.toml](../../../config.example.toml), Details zu den Kameras stehen in [hardware-setup.md](../../hardware-setup.md) (englisch).

## Aktualisieren

Lade das neue Setup herunter und starte es; es ersetzt das Programm, Einstellungen und Daten bleiben. Beende dartscore vorher.

## Deinstallieren

Einstellungen → Apps → Installierte Apps → **dartscore** → Deinstallieren. Einstellungen und Daten bleiben in `%LOCALAPPDATA%\dartscore`; lösche den Ordner auch, um alles zu entfernen.

## Fehlerbehebung

| Problem | Lösung |
| --- | --- |
| Konsolenfenster meldet, der Port sei belegt | Ein anderes Programm nutzt Port 8000: trage unter `[server]` in `config.toml` einen anderen `port` ein. |
| Kein Kamerabild | Kamera-Berechtigung für Desktop-Apps (siehe oben), oder ein anderes Programm (Teams, Zoom, Autodarts) nutzt die Kamera. |
| Handys verbinden sich nicht | Die Firewall-Frage wurde mit „Abbrechen“ beantwortet: Windows-Sicherheit → Firewall- & Netzwerkschutz → App durch die Firewall zulassen → `dartscore` für Privat aktivieren. Prüfe außerdem, dass das WLAN als *Privat* eingestuft ist. |
