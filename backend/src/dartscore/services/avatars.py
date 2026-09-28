"""Profile pictures: stored small and without metadata (EXIF, GPS) in data/avatars."""

import time
from pathlib import Path

import cv2
import numpy as np

from dartscore.game import GameError

AVATAR_SIZE = 512
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
# the pictures shipped with the web app (frontend/public/avatars/<name>.webp)
GALLERY = (
    "fox", "owl", "bear", "cat", "dog", "panda", "frog", "penguin",
    "tiger", "lion", "monkey", "unicorn", "robot", "alien", "ghost", "pirate",
)  # fmt: skip


def avatar_url(player_id: int, avatar: str | None) -> str | None:
    if not avatar:
        return None
    kind, _, value = avatar.partition(":")
    if kind == "photo":
        return f"/api/players/{player_id}/avatar.jpg?v={value}"
    if kind == "gallery":
        return f"/avatars/{value}.webp"
    return None


def avatar_file(directory: Path, player_id: int) -> Path:
    return directory / f"{player_id}.jpg"


def save_photo(directory: Path, player_id: int, data: bytes) -> str:
    """Decodes an uploaded image, crops it square (centre), scales it down and stores it as a
    fresh JPEG (which drops all metadata). Returns the avatar value for the profile."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise GameError("invalid_image", "The picture is too large")
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise GameError("invalid_image", "The file is not a picture")
    h, w = image.shape[:2]
    side = min(h, w)
    image = image[
        (h - side) // 2 : (h - side) // 2 + side, (w - side) // 2 : (w - side) // 2 + side
    ]
    if side > AVATAR_SIZE:
        image = cv2.resize(image, (AVATAR_SIZE, AVATAR_SIZE), interpolation=cv2.INTER_AREA)
    directory.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not ok:
        raise GameError("invalid_image", "The picture could not be stored")
    avatar_file(directory, player_id).write_bytes(buf.tobytes())
    return f"photo:{int(time.time())}"


def remove_photo(directory: Path, player_id: int) -> None:
    avatar_file(directory, player_id).unlink(missing_ok=True)
