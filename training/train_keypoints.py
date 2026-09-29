"""Train the dart keypoint model (heatmaps) and export it as ONNX.

A small CenterNet-style network: a MobileNetV3 backbone from torchvision, a light FPN decoder
and one heatmap per class at stride 4, plus a two-channel sub-cell offset. It only uses
permissively licensed code and weights (PyTorch and torchvision: BSD-3-Clause).

Run on a machine with a GPU (or Apple Silicon), not on the Mac mini:

    uv run --with torch --with torchvision --with onnx --with opencv-python-headless \
        python training/train_keypoints.py --data datasets/darts

The dataset is the one written by `dartscore export-dataset`; the center of every label box is
the keypoint. The result (models/darts.onnx) goes to <data_dir>/models/darts.onnx on the
dartscore machine, exactly like the YOLO model.
"""

import argparse
import math
import random
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F  # noqa: N812
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torchvision.models import MobileNet_V3_Large_Weights, mobilenet_v3_large

NUM_CLASSES = 5  # dart tip + four calibration points, see dartscore.training.dataset
STRIDE = 4
SIGMA = 2.0  # gaussian radius on the heatmap, in output cells
MATCH_PX = 6.0  # a prediction within this distance (model input pixels) counts as a hit
# ImageNet normalization happens inside the exported model, the input stays RGB in [0, 1]
MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)


# --- data ---------------------------------------------------------------------------------


def letterbox_matrix(w: int, h: int, size: int) -> np.ndarray:
    """Affine matrix of the letterbox used at inference (dartscore.vision.model.letterbox)."""
    scale = min(size / w, size / h)
    nw, nh = round(w * scale), round(h * scale)
    return np.array([[scale, 0, (size - nw) // 2], [0, scale, (size - nh) // 2]], np.float64)


def read_labels(path: Path, w: int, h: int) -> np.ndarray:
    """(n, 3) array of class, x, y in image pixels."""
    rows = []
    if path.is_file():
        for line in path.read_text().splitlines():
            parts = line.split()
            if len(parts) >= 3:
                rows.append((int(parts[0]), float(parts[1]) * w, float(parts[2]) * h))
    return np.array(rows, np.float64).reshape(-1, 3)


class KeypointDataset(Dataset[tuple[torch.Tensor, torch.Tensor, torch.Tensor]]):
    def __init__(self, root: Path, split: str, size: int, augment: bool) -> None:
        self.images = sorted((root / "images" / split).glob("*.jpg"))
        self.labels = root / "labels" / split
        self.size = size
        self.augment = augment

    def __len__(self) -> int:
        return len(self.images)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        path = self.images[index]
        image = cv2.imread(str(path))
        h, w = image.shape[:2]
        points = read_labels(self.labels / f"{path.stem}.txt", w, h)
        matrix = letterbox_matrix(w, h, self.size)
        if self.augment:
            # like the YOLO settings: small rotation and scale, no flips (the calibration
            # classes are tied to board positions), brightness changes for the light
            angle = random.uniform(-5.0, 5.0)
            scale = random.uniform(0.8, 1.2)
            center = (
                self.size / 2 + random.uniform(-20, 20),
                self.size / 2 + random.uniform(-20, 20),
            )
            rot = cv2.getRotationMatrix2D(center, angle, scale)
            matrix = rot @ np.vstack([matrix, [0, 0, 1]])
        canvas = cv2.warpAffine(
            image,
            matrix,
            (self.size, self.size),
            flags=cv2.INTER_LINEAR,
            borderValue=(114, 114, 114),
        )
        if self.augment:
            hsv = cv2.cvtColor(canvas, cv2.COLOR_BGR2HSV).astype(np.float32)
            hsv[..., 2] *= random.uniform(0.6, 1.4)
            hsv[..., 1] *= random.uniform(0.7, 1.3)
            canvas = cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR)
        xy = points[:, 1:] @ matrix[:, :2].T + matrix[:, 2] if len(points) else points[:, 1:]
        inside = (xy[:, 0] >= 0) & (xy[:, 0] < self.size) & (xy[:, 1] >= 0) & (xy[:, 1] < self.size)
        keypoints = np.c_[points[inside, :1], xy[inside]]

        tensor = torch.from_numpy(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)).permute(2, 0, 1)
        heatmap, offset = make_targets(keypoints, self.size // STRIDE)
        return tensor.float() / 255.0, heatmap, offset


def make_targets(keypoints: np.ndarray, cells: int) -> tuple[torch.Tensor, torch.Tensor]:
    """Gaussian heatmaps (peak 1 at the keypoint's cell) and the sub-cell offset at that cell.
    The offset map carries a mask channel: (dx, dy, mask)."""
    heatmap = np.zeros((NUM_CLASSES, cells, cells), np.float32)
    offset = np.zeros((3, cells, cells), np.float32)
    ys, xs = np.mgrid[0:cells, 0:cells]
    for cls, x, y in keypoints:
        cx, cy = x / STRIDE, y / STRIDE
        ix, iy = min(int(cx), cells - 1), min(int(cy), cells - 1)
        g = np.exp(-((xs - ix) ** 2 + (ys - iy) ** 2) / (2 * SIGMA**2))
        heatmap[int(cls)] = np.maximum(heatmap[int(cls)], g)
        offset[:, iy, ix] = (cx - ix, cy - iy, 1.0)
    return torch.from_numpy(heatmap), torch.from_numpy(offset)


# --- model --------------------------------------------------------------------------------


class KeypointNet(nn.Module):
    # MobileNetV3-Large feature indices where the resolution drops next: strides 4, 8, 16, 32
    TAPS = (3, 6, 12, 16)
    TAP_CHANNELS = (24, 40, 112, 960)

    def __init__(self, pretrained: bool = True, width: int = 64) -> None:
        super().__init__()
        weights = MobileNet_V3_Large_Weights.IMAGENET1K_V1 if pretrained else None
        self.backbone = mobilenet_v3_large(weights=weights).features
        self.lateral = nn.ModuleList(nn.Conv2d(c, width, 1) for c in self.TAP_CHANNELS)
        self.smooth = nn.Sequential(
            nn.Conv2d(width, width, 3, padding=1), nn.BatchNorm2d(width), nn.ReLU(inplace=True)
        )
        self.heatmap = nn.Conv2d(width, NUM_CLASSES, 1)
        self.offset = nn.Conv2d(width, 2, 1)
        # start with a low heatmap everywhere (CenterNet): the loss is dominated by background
        nn.init.constant_(self.heatmap.bias, -2.19)
        self.register_buffer("mean", torch.tensor(MEAN).view(1, 3, 1, 1))
        self.register_buffer("std", torch.tensor(STD).view(1, 3, 1, 1))

    def features(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        x = (x - self.mean) / self.std
        taps = []
        for i, layer in enumerate(self.backbone):
            x = layer(x)
            if i in self.TAPS:
                taps.append(x)
        y = self.lateral[3](taps[3])
        for level in (2, 1, 0):
            lateral = self.lateral[level](taps[level])
            y = lateral + F.interpolate(y, size=lateral.shape[-2:], mode="nearest")
        y = self.smooth(y)
        return self.heatmap(y), self.offset(y)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Export format: (1, classes + 2, H/4, W/4) = sigmoid heatmaps, then dx, dy."""
        logits, offset = self.features(x)
        return torch.cat([torch.sigmoid(logits), offset], dim=1)


def focal_loss(logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    """Penalty-reduced focal loss from CenterNet, normalized by the number of keypoints."""
    pred = torch.sigmoid(logits).clamp(1e-4, 1 - 1e-4)
    pos = target.eq(1).float()
    neg = 1 - pos
    pos_loss = torch.log(pred) * (1 - pred) ** 2 * pos
    neg_loss = torch.log(1 - pred) * pred**2 * (1 - target) ** 4 * neg
    count = pos.sum().clamp(min=1)
    return -(pos_loss.sum() + neg_loss.sum()) / count


def offset_loss(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    mask = target[:, 2:3]
    return (F.l1_loss(pred, target[:, :2], reduction="none") * mask).sum() / mask.sum().clamp(min=1)


# --- evaluation ---------------------------------------------------------------------------


def peaks(output: np.ndarray, threshold: float) -> list[tuple[int, float, float, float]]:
    """Same decoding as dartscore.vision.model.decode_heatmaps, on one (C + 2, h, w) array."""
    heat, offset = output[:NUM_CLASSES], output[NUM_CLASSES:]
    found = []
    for cls in range(NUM_CLASSES):
        h = heat[cls]
        local_max = h == cv2.dilate(h, np.ones((3, 3), np.uint8))
        for y, x in zip(*np.nonzero(local_max & (h >= threshold)), strict=True):
            found.append(
                (
                    cls,
                    (x + offset[0, y, x]) * STRIDE,
                    (y + offset[1, y, x]) * STRIDE,
                    float(h[y, x]),
                )
            )
    return found


def truth(heatmap: np.ndarray, offset: np.ndarray) -> list[tuple[int, float, float]]:
    ys, xs = np.nonzero(offset[2] > 0)
    return [
        (
            int(heatmap[:, y, x].argmax()),
            (x + offset[0, y, x]) * STRIDE,
            (y + offset[1, y, x]) * STRIDE,
        )
        for y, x in zip(ys, xs, strict=True)
    ]


@torch.no_grad()
def evaluate(
    model: KeypointNet, loader: DataLoader, device: torch.device, threshold: float
) -> dict[str, float]:
    """Dart tips: precision, recall and the mean distance of matched tips (model pixels)."""
    model.eval()
    hits = predicted = expected = 0
    errors: list[float] = []
    for images, heatmaps, offsets in loader:
        outputs = model(images.to(device)).cpu().numpy()
        for out, hm, off in zip(outputs, heatmaps.numpy(), offsets.numpy(), strict=True):
            preds = [p for p in peaks(out, threshold) if p[0] == 0]
            gts = [t for t in truth(hm, off) if t[0] == 0]
            predicted += len(preds)
            expected += len(gts)
            free = list(preds)
            for _, gx, gy in gts:
                if not free:
                    break
                best = min(free, key=lambda p: math.hypot(p[1] - gx, p[2] - gy))
                dist = math.hypot(best[1] - gx, best[2] - gy)
                if dist <= MATCH_PX:
                    hits += 1
                    errors.append(dist)
                    free.remove(best)
    precision = hits / predicted if predicted else 0.0
    recall = hits / expected if expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "error_px": float(np.mean(errors)) if errors else float("nan"),
    }


# --- main ---------------------------------------------------------------------------------


def pick_device(name: str | None) -> torch.device:
    if name:
        return torch.device(name if not name.isdigit() else f"cuda:{name}")
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def export(model: KeypointNet, size: int, out: Path) -> None:
    import onnx

    model.eval().cpu()
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        model,
        torch.zeros(1, 3, size, size),
        str(out),
        input_names=["images"],
        output_names=["keypoints"],
        opset_version=17,
        dynamo=False,
    )
    proto = onnx.load(str(out))
    for key, value in {
        "dartscore_format": "heatmap",
        "classes": str(NUM_CLASSES),
        "stride": str(STRIDE),
    }.items():
        entry = proto.metadata_props.add()
        entry.key, entry.value = key, value
    onnx.save(proto, str(out))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--data", required=True, help="dataset folder from `dartscore export-dataset`"
    )
    parser.add_argument("--epochs", type=int, default=150)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--device", default=None, help="e.g. 0 (CUDA), mps (Apple), cpu")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--patience", type=int, default=30, help="stop after this many epochs without a better F1"
    )
    parser.add_argument("--threshold", type=float, default=0.3, help="heatmap score for a keypoint")
    parser.add_argument(
        "--no-pretrained", action="store_true", help="train from scratch, no ImageNet weights"
    )
    parser.add_argument("--out", default="models/darts.onnx")
    args = parser.parse_args()

    root = Path(args.data)
    if args.imgsz % 32:
        parser.error("--imgsz must be a multiple of 32")
    train_set = KeypointDataset(root, "train", args.imgsz, augment=True)
    val_set = KeypointDataset(root, "val", args.imgsz, augment=False)
    if not len(train_set):
        parser.error(f"no training images in {root / 'images' / 'train'}")
    train_loader = DataLoader(
        train_set,
        args.batch,
        shuffle=True,
        num_workers=args.workers,
        drop_last=len(train_set) > args.batch,
    )
    val_loader = DataLoader(val_set or train_set, args.batch, num_workers=args.workers)

    device = pick_device(args.device)
    model = KeypointNet(pretrained=not args.no_pretrained).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    schedule = torch.optim.lr_scheduler.OneCycleLR(
        optimizer, max_lr=args.lr, total_steps=args.epochs * len(train_loader), pct_start=0.05
    )
    print(f"{len(train_set)} training / {len(val_set)} validation images on {device}")

    best_f1, best_state, stale = -1.0, None, 0
    for epoch in range(1, args.epochs + 1):
        model.train()
        total = 0.0
        for images, heatmaps, offsets in train_loader:
            images, heatmaps, offsets = images.to(device), heatmaps.to(device), offsets.to(device)
            logits, offset = model.features(images)
            loss = focal_loss(logits, heatmaps) + offset_loss(offset, offsets)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            schedule.step()
            total += loss.item()
        metrics = evaluate(model, val_loader, device, args.threshold)
        print(
            f"epoch {epoch:3d}  loss {total / len(train_loader):.4f}  "
            f"P {metrics['precision']:.3f}  R {metrics['recall']:.3f}  "
            f"F1 {metrics['f1']:.3f}  error {metrics['error_px']:.2f} px"
        )
        if metrics["f1"] > best_f1:
            best_f1, stale = metrics["f1"], 0
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        else:
            stale += 1
            if stale >= args.patience:
                print(f"no improvement for {args.patience} epochs, stopping")
                break

    if best_state is not None:
        model.load_state_dict(best_state)
    export(model, args.imgsz, Path(args.out))
    print(f"Best validation F1 {best_f1:.3f}; model written to {args.out}")


if __name__ == "__main__":
    main()
