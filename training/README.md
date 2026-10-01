# Training the dart tip model

dartscore detects darts with classic image processing out of the box. A trained model finds the dart tips more reliably (partly hidden darts, difficult light). The model is trained on your own board: every detected dart is recorded with images, and the positions come from the calibration, so no manual labeling is needed.

## 1. Collect data

Play with automatic detection switched on. Correct wrong detections in the game view; corrected darts with an unknown position are left out of the training set. A few hundred darts are a good start, a few thousand are better. Vary the light and throw at all areas of the board.

## 2. Export the dataset (on the dartscore machine)

```bash
uv run --project backend dartscore export-dataset --out datasets/darts
```

## 3. Train (on a machine with a GPU or Apple Silicon)

Copy `datasets/darts` over, then train the keypoint network:

```bash
uv run --with torch --with torchvision --with onnx --with opencv-python-headless python training/train_keypoints.py --data datasets/darts
```

Use `--device mps` on Apple Silicon or `--device 0` with an NVIDIA GPU. The network predicts one heatmap per keypoint class on a MobileNetV3 backbone. It only uses permissively licensed code and weights (PyTorch and torchvision, BSD-3-Clause); `--no-pretrained` trains without the ImageNet weights.

`training/train.py` trains a YOLO model with Ultralytics instead. Ultralytics and its weights are AGPL-3.0, so a model trained that way is not suitable for closed-source or commercial use without an Ultralytics license. It stays for comparison and will be removed once the keypoint network matches it.

## 4. Install the model

Copy `models/darts.onnx` to `data/models/darts.onnx` on the dartscore machine and restart dartscore. The settings page shows the model under automatic detection. Without a model file, the classic detection is used.
