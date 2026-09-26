# Hardware-Setup: Kameras am Debian-Rechner

Anleitung für den Referenzrechner (Intel Mac mini mit Debian) und die drei OV9732-Kameras. Gilt sinngemäß für jeden Linux-Rechner.

## 1. Pakete und Rechte

```bash
sudo apt install v4l-utils
```

```bash
sudo usermod -aG video $USER
```

Danach einmal ab- und wieder anmelden, damit die Gruppe `video` greift.

## 2. Kameras finden

```bash
make install
```

```bash
uv run --project backend dartscore devices
```

Die Ausgabe zeigt pro Kamera den Gerätepfad, die stabilen Pfade und die unterstützten Formate, zum Beispiel:

```
/dev/video0  USB Camera
    by-path: /dev/v4l/by-path/pci-0000:00:14.0-usb-0:1:1.0-video-index0
    MJPG: 1280x720@30, 640x480@30
    YUYV: 1280x720@10, 640x480@30
```

Wichtig:

- **MJPG muss 1280x720@30 anbieten.** Unkomprimiert (YUYV) schafft USB 2.0 bei 720p meist nur 10 fps, und drei Kameras teilen sich die Bandbreite.
- **by-path statt /dev/videoN verwenden.** Die Nummern können sich nach jedem Neustart ändern. Günstige Kameras haben oft keine eindeutige Seriennummer, dann sind auch die by-id-Pfade gleich. by-path hängt am USB-Anschluss und bleibt stabil, solange jede Kamera im selben Anschluss steckt. Die Anschlüsse am besten beschriften.

## 3. Konfiguration

```bash
cp config.example.toml config.toml
```

In `config.toml` für jede Kamera `device` auf den by-path-Pfad setzen und `position_deg` auf die Montageposition (0 = oben, im Uhrzeigersinn).

Optional feste Belichtung, damit sich die Helligkeit zwischen den Würfen nicht ändert. Die verfügbaren Controls zeigt:

```bash
v4l2-ctl -d /dev/video0 -l
```

Die Namen und Werte kommen dann unter `v4l2_controls` in die Kamera-Konfiguration, z. B. `{ auto_exposure = 1, exposure_time_absolute = 150 }`.

## 4. Bandbreite testen

```bash
uv run --project backend dartscore bench --seconds 10
```

Liest alle drei Kameras gleichzeitig und misst die echte Bildrate. Alle Kameras sollten nahe 30 fps und 0 verlorene Bilder haben. Falls nicht:

```bash
lsusb -t
```

Zeigt, welche Kamera an welchem USB-Controller hängt. Hängen alle drei am selben Controller, eine Kamera an einen anderen Anschluss (andere Seite des Geräts) oder einen aktiven USB-Hub stecken.

## 5. Linsenkalibrierung (einmal pro Kamera)

Die 100°-Weitwinkel-Linsen verzerren das Bild. Die Kalibrierung misst das mit einem Schachbrettmuster und rechnet es später heraus.

1. Schachbrett mit 10×7 Feldern ausdrucken (ergibt 9×6 innere Ecken), z. B. von [calib.io](https://calib.io/pages/camera-calibration-pattern-generator). Auf eine feste, ebene Platte kleben und die Kantenlänge eines Feldes nachmessen.
2. Kalibrierung starten:

```bash
uv run --project backend dartscore calibrate-lens --camera cam1 --square-mm 25
```

3. Das Schachbrett langsam vor der Kamera bewegen: Mitte, alle Ränder und Ecken, auch leicht gekippt. Das Programm nimmt automatisch 20 unterschiedliche Aufnahmen.
4. Ein Reprojektionsfehler unter 0,5 px ist sehr gut, unter 1 px in Ordnung.

Das Ergebnis liegt in `data/calibration/<kamera>/lens.json`, eine entzerrte Vorschau in `lens_preview.png`. Auf der Kameraseite der Oberfläche lässt sich dann „Entzerrt anzeigen“ einschalten.

## 6. Ohne Hardware entwickeln

Für die Entwicklung am Laptop gibt es simulierte Kameras. In der `config.toml` statt `device` einfach `source = "synthetic"` setzen.
