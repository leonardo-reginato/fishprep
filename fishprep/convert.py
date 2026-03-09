from __future__ import annotations

import tempfile
from pathlib import Path

from PIL import Image
from tqdm import tqdm

from fishprep.rename import extract_id_from_filename
from fishprep.utils import clean_stem, ensure_directory, file_size_mb, make_rgb, open_image, unique_path


def convert_to_jpeg(image_path: str, output_path: str, quality: int = 90) -> str:
    """
    Convert an image to JPEG format.

    Parameters
    ----------
    image_path : str
        Path to original image.
    output_path : str
        Path where converted image will be saved.
    quality : int
        JPEG compression quality (0–100).

    Returns
    -------
    str
        Path to converted JPEG file.
    """
    destination = Path(output_path).expanduser().resolve()
    ensure_directory(destination.parent)

    with open_image(image_path) as image:
        rgb = make_rgb(image)
        rgb.save(destination, format="JPEG", quality=int(quality), optimize=True, progressive=True)

    return str(destination)


def compress_image_to_size(image_path: str, max_size_mb: float) -> str:
    """
    Compress an image until its file size is below a specified limit.

    Parameters
    ----------
    image_path : str
        Path to image.
    max_size_mb : float
        Maximum allowed file size.

    Returns
    -------
    str
        Path to compressed image.
    """
    path = Path(image_path).expanduser().resolve()
    if file_size_mb(path) <= max_size_mb:
        return str(path)

    target_bytes = int(max_size_mb * 1024 * 1024)
    with Image.open(path) as image:
        rgb = make_rgb(image)

        quality_candidates = [90, 85, 80, 75, 70, 65, 60, 55, 50, 45, 40]
        current = rgb
        for quality in quality_candidates:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                temp_path = Path(tmp.name)
            current.save(temp_path, format="JPEG", quality=quality, optimize=True, progressive=True)
            if temp_path.stat().st_size <= target_bytes:
                temp_path.replace(path)
                return str(path)
            temp_path.unlink(missing_ok=True)

        width, height = rgb.size
        while width >= 800 and height >= 800:
            width = int(width * 0.9)
            height = int(height * 0.9)
            current = rgb.resize((width, height), Image.Resampling.LANCZOS)
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                temp_path = Path(tmp.name)
            current.save(temp_path, format="JPEG", quality=45, optimize=True, progressive=True)
            if temp_path.stat().st_size <= target_bytes:
                temp_path.replace(path)
                return str(path)
            temp_path.unlink(missing_ok=True)

    return str(path)


def batch_convert_images(image_paths: list, output_dir: str, config: dict) -> list:
    """
    Convert a batch of images to standardized JPEG format.

    Parameters
    ----------
    image_paths : list
        List of image paths.
    output_dir : str
        Directory for converted images.
    config : dict
        Configuration parameters (quality, size limits).

    Returns
    -------
    list
        List of converted image paths.
    """
    output_root = ensure_directory(output_dir)
    quality = int(config.get("jpeg_quality", 90))
    max_size_mb = float(config.get("max_size_mb", 10.0))
    converted_paths = []

    for image_path in tqdm(image_paths, desc="Converting images", unit="image"):
        source = Path(image_path)
        specimen_id = extract_id_from_filename(source.name)
        base_name = clean_stem(specimen_id or source.stem)
        try:
            destination = unique_path(output_root, base_name, suffix=".jpg")
            converted = convert_to_jpeg(str(source), str(destination), quality=quality)
            converted = compress_image_to_size(converted, max_size_mb=max_size_mb)
            converted_paths.append(converted)
        except Exception:
            converted_paths.append(None)

    return converted_paths
