# Training the dart tip model

dartscore detects darts with classic image processing out of the box. A trained model finds the dart tips more reliably (partly hidden darts, difficult light). The model is trained on your own board: every detected dart is recorded with images, and the positions come from the calibration, so no manual labeling is needed.

## 1. Collect data

Play with automatic detection switched on. Correct wrong detections in the game view; corrected darts with an unknown position are left out of the training set. A few hundred darts are a good start, a few thousand are better. Vary the light and throw at all areas of the board.

## 2. Export the dataset (on the dartscore machine)

```bash
uv run --project backend dartscore export-dataset --out datasets/darts
```

## 3. Train (on a machine with a GPU or Apple Silicon)

Copy `datasets/darts` over, then:

```bash
uv run --with ultralytics python training/train.py --data datasets/darts/data.yaml
```

Use `--device mps` on Apple Silicon or `--device 0` with an NVIDIA GPU.

## 4. Install the model

Copy `models/darts.onnx` to `data/models/darts.onnx` on the dartscore machine and restart dartscore. The settings page shows the model under automatic detection. Without a model file, the classic detection is used.
