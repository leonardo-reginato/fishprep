from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageOps

SUPPORTED_EXTENSIONS = {
    ".bmp",
    ".dng",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}

try:
    import rawpy
except Exception:  # pragma: no cover - optional dependency
    rawpy = None


def ensure_directory(path: str | Path) -> Path:
    directory = Path(path).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def file_size_mb(path: str | Path) -> float:
    return Path(path).stat().st_size / (1024 * 1024)


def is_image_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_EXTENSIONS


def open_image(path: str | Path) -> Image.Image:
    """
    Open common image formats with Pillow and DNG/RAW files with rawpy when available.
    """
    image_path = Path(path).expanduser().resolve()
    suffix = image_path.suffix.lower()

    if suffix == ".dng":
        if rawpy is None:
            raise RuntimeError(
                "DNG support requires the optional 'rawpy' package. "
                f"Install it or remove DNG files from the input set: {image_path}"
            )
        with rawpy.imread(str(image_path)) as raw:
            rgb = raw.postprocess(use_camera_wb=True, no_auto_bright=True)
        return Image.fromarray(rgb)

    image = Image.open(image_path)
    image.load()
    return image


def make_rgb(image: Image.Image) -> Image.Image:
    normalized = ImageOps.exif_transpose(image)
    if normalized.mode in {"RGB", "L"}:
        return normalized.convert("RGB")
    if normalized.mode == "RGBA":
        background = Image.new("RGB", normalized.size, (255, 255, 255))
        background.paste(normalized, mask=normalized.getchannel("A"))
        return background
    return normalized.convert("RGB")


def clean_stem(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return cleaned or "image"


def unique_path(output_dir: str | Path, base_name: str, suffix: str = ".jpg") -> Path:
    directory = ensure_directory(output_dir)
    candidate = directory / f"{base_name}{suffix}"
    index = 2
    while candidate.exists():
        candidate = directory / f"{base_name}_{index}{suffix}"
        index += 1
    return candidate
