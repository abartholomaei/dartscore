# Hardware setup: cameras on the Debian machine

Guide for the reference machine (Intel Mac mini running Debian) and the three OV9732 cameras. Applies analogously to any Linux machine.

## Reference machine (checked on 2026-09-26)

| Item | Finding |
| --- | --- |
| Machine | Mac mini (Late 2012), Intel Core i7-3615QM (Ivy Bridge, 4 cores / 8 threads), 16 GB RAM, Debian 12, kernel 6.1 |
| CPU instruction sets | AVX, SSE4.2 - **no AVX2/FMA** (relevant for model inference, see PRD) |
| Graphics | Intel HD 4000 - not supported by OpenVINO, inference runs on the CPU |
| Cameras | 3× Realtek UVC (`0bda:5844`, OV9732), all on one USB 2.0 hub (Genesys `05e3:0610`), hub ports 1.1, 1.2, 1.3 |
| Formats | MJPG 1280x720@30 and YUYV 1280x720@10 - MJPG is mandatory |
| Serial numbers | identical on all cameras (`200901010001`) → by-id unusable, use by-path |
| Bandwidth | all 3 at once, MJPG 1280x720: **29.5 fps per camera** (with `exposure_dynamic_framerate=0`) |
| Exposure | factory default `exposure_dynamic_framerate=1`: only ~16 fps in low light, even with a single camera |
| Other services | Autodarts (port 3180), Home Assistant in Docker (port 8123), GNOME desktop; port 8000 free |

| dartscore cameras | 3× 30.0 fps, 0 dropped frames (`dartscore bench`); server with 3 browser streams ≈ 110 % CPU (just over 1 of 8 threads) |

### Inference benchmark (2026-09-26)

Pretrained YOLO pose models (not yet trained on darts, for speed measurement only), median over 30 runs, one image per run. dartscore was running in parallel with all three cameras.

| Model | Input | ONNX Runtime 1.30 | OpenVINO 2026.4 |
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

Result: both runtimes work without AVX2. On this CPU, ONNX Runtime is consistently faster than OpenVINO (which is optimized for AVX2/AVX-512). YOLO26n-pose is the fastest model. Three camera images take about 125 ms at 320 px and about 300 ms at 480 px - both within the 500 ms target.

**Autodarts and dartscore cannot use the cameras at the same time.** Stop the Autodarts service before starting dartscore (`systemctl stop autodarts`) and start it again afterwards (`systemctl start autodarts`).

## 1. Packages and permissions

```bash
sudo apt install v4l-utils
```

```bash
sudo usermod -aG video $USER
```

Then log out and back in once so the `video` group takes effect.

## 2. Find the cameras

```bash
make install
```

```bash
uv run --project backend dartscore devices
```

The output shows the device path, the stable paths and the supported formats for each camera, for example:

```
/dev/video0  USB Camera
    by-path: /dev/v4l/by-path/pci-0000:00:14.0-usb-0:1:1.0-video-index0
    MJPG: 1280x720@30, 640x480@30
    YUYV: 1280x720@10, 640x480@30
```

Important:

- **MJPG must offer 1280x720@30.** Uncompressed (YUYV), USB 2.0 usually manages only 10 fps at 720p, and three cameras share the bandwidth.
- **Use by-path instead of /dev/videoN.** The numbers can change after every reboot. Cheap cameras often have no unique serial number, so the by-id paths are identical too. by-path is tied to the USB port and stays stable as long as each camera stays in the same port. Best to label the ports.

## 3. Configuration

```bash
cp config.example.toml config.toml
```

In `config.toml`, set `device` to the by-path path for each camera and `position_deg` to the mounting position (0 = top, clockwise).

Optionally use a fixed exposure so the brightness doesn't change between throws. The available controls are shown by:

```bash
v4l2-ctl -d /dev/video0 -l
```

The names and values then go under `v4l2_controls` in the camera configuration. For the OV9732, always set `exposure_dynamic_framerate = 0`, otherwise the frame rate drops to about 16 fps in low light. With fixed lighting, also set `auto_exposure = 1` (manual) and choose a suitable `exposure_time_absolute`.

## 4. Test the bandwidth

```bash
uv run --project backend dartscore bench --seconds 10
```

Reads all three cameras at once and measures the actual frame rate. All cameras should be close to 30 fps with 0 dropped frames. If not:

```bash
lsusb -t
```

Shows which camera is on which USB controller. If all three are on the same controller, plug one camera into a different port (other side of the machine) or into a powered USB hub.

## 5. Lens calibration (once per camera)

The 100° wide-angle lenses distort the image. Calibration measures this with a chessboard pattern and corrects it later.

1. Print a chessboard with 10×7 squares (giving 9×6 inner corners), e.g. from [calib.io](https://calib.io/pages/camera-calibration-pattern-generator). Glue it onto a rigid, flat board and measure the side length of one square.
2. Start the calibration:

```bash
uv run --project backend dartscore calibrate-lens --camera cam1 --square-mm 25
```

3. Move the chessboard slowly in front of the camera: center, all edges and corners, also slightly tilted. The program automatically takes 20 distinct captures.
4. A reprojection error below 0.5 px is very good, below 1 px acceptable.

The result is stored in `data/calibration/<camera>/lens.json`, with an undistorted preview in `lens_preview.png`. On the camera page of the UI you can then enable "Show undistorted".

## 6. Developing without hardware

For development on a laptop there are simulated cameras. In `config.toml`, simply set `source = "synthetic"` instead of `device`.
