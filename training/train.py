"""Train the dart tip model and export it as ONNX.

Run on a machine with a GPU (or Apple Silicon), not on the Mac mini:

    uv run --with ultralytics python training/train.py --data datasets/darts/data.yaml

The result (models/darts.onnx) goes to <data_dir>/models/darts.onnx on the dartscore machine.
"""

import argparse
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--data", required=True, help="data.yaml from `dartscore export-dataset`")
    parser.add_argument("--model", default="yolo26n.pt", help="base model (pretrained weights)")
    parser.add_argument("--epochs", type=int, default=150)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--device", default=None, help="e.g. 0 (CUDA), mps (Apple), cpu")
    parser.add_argument("--out", default="models/darts.onnx")
    args = parser.parse_args()

    from ultralytics import YOLO

    model = YOLO(args.model)
    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        # keypoint boxes are tiny: no mosaic crops that cut them, mild color/geometry changes
        mosaic=0.0,
        fliplr=0.0,
        degrees=5.0,
        scale=0.2,
        hsv_v=0.4,
        patience=30,
    )
    exported = Path(model.export(format="onnx", imgsz=args.imgsz, opset=17, simplify=True))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(exported, out)
    print(f"Model written to {out}")


if __name__ == "__main__":
    main()
