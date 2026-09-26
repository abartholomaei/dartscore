# Hardware-Setup: Kameras am Debian-Rechner

Anleitung für den Referenzrechner (Intel Mac mini mit Debian) und die drei OV9732-Kameras. Gilt sinngemäß für jeden Linux-Rechner.

## Referenzrechner (geprüft am 2026-09-26)

| Punkt | Befund |
| --- | --- |
| Rechner | Mac mini (Late 2012), Intel Core i7-3615QM (Ivy Bridge, 4 Kerne / 8 Threads), 16 GB RAM, Debian 12, Kernel 6.1 |
| CPU-Befehlssätze | AVX, SSE4.2 – **kein AVX2/FMA** (relevant für die Modell-Inferenz, siehe PRD) |
| Grafik | Intel HD 4000 – von OpenVINO nicht unterstützt, Inferenz läuft auf der CPU |
| Kameras | 3× Realtek-UVC (`0bda:5844`, OV9732), alle an einem USB-2.0-Hub (Genesys `05e3:0610`), Hub-Ports 1.1, 1.2, 1.3 |
| Formate | MJPG 1280x720@30 und YUYV 1280x720@10 – MJPG ist Pflicht |
| Seriennummern | alle Kameras gleich (`200901010001`) → by-id unbrauchbar, by-path verwenden |
| Bandbreite | alle 3 gleichzeitig MJPG 1280x720: **29,5 fps je Kamera** (mit `exposure_dynamic_framerate=0`) |
| Belichtung | ab Werk `exposure_dynamic_framerate=1`: bei wenig Licht nur ~16 fps, auch bei einer Kamera allein |
| Weitere Dienste | Autodarts (Port 3180), Home Assistant in Docker (Port 8123), GNOME-Desktop; Port 8000 frei |

| dartscore-Kameras | 3× 30,0 fps, 0 verlorene Bilder (`dartscore bench`); Server mit 3 Browser-Streams ≈ 110 % CPU (gut 1 von 8 Threads) |

### Inferenz-Benchmark (2026-09-26)

Vortrainierte YOLO-Pose-Modelle (noch nicht auf Darts trainiert, nur zur Geschwindigkeitsmessung), Median über 30 Durchläufe, ein Bild pro Durchlauf. Parallel lief dartscore mit allen drei Kameras.

| Modell | Eingabe | ONNX Runtime 1.30 | OpenVINO 2026.4 |
| --- | --- | --- | --- |
| YOLO26n-pose | 320 px | **41 ms** | 59 ms |
| YOLO26n-pose | 480 px | **100 ms** | 123 ms |
| YOLO26n-pose | 640 px | **139 ms** | 220 ms |
| YOLO11n-pose | 320 px | 62 ms | 71 ms |
| YOLO11n-pose | 480 px | 123 ms | 164 ms |
| YOLO11n-pose | 640 px | 349 ms | 355 ms |
| YOLO11s-pose | 320 px | 136 ms | 165 ms |
| YOLO11s-pose | 480 px | 227 ms | 338 ms |
| YOLO11s-pose | 640 px | 627 ms | 719 ms |

Ergebnis: Beide Laufzeiten funktionieren ohne AVX2. ONNX Runtime ist auf dieser CPU durchweg schneller als OpenVINO (das auf AVX2/AVX-512 optimiert ist). YOLO26n-pose ist das schnellste Modell. Drei Kamerabilder dauern bei 320 px etwa 125 ms, bei 480 px etwa 300 ms – beides innerhalb des Ziels von 500 ms.

**Autodarts und dartscore können die Kameras nicht gleichzeitig nutzen.** Vor dem Start von dartscore den Autodarts-Dienst anhalten (`systemctl stop autodarts`) und danach wieder starten (`systemctl start autodarts`).

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

Die Namen und Werte kommen dann unter `v4l2_controls` in die Kamera-Konfiguration. Bei den OV9732 immer `exposure_dynamic_framerate = 0` setzen, sonst sinkt die Bildrate bei wenig Licht auf etwa 16 fps. Mit fester Beleuchtung zusätzlich `auto_exposure = 1` (manuell) und `exposure_time_absolute` passend wählen.

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
