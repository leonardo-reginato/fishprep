from __future__ import annotations

from pathlib import Path

import pandas as pd
from PIL import ExifTags
from tqdm import tqdm

from fishprep.utils import file_size_mb, is_image_file, open_image


EXIF_TAGS = {value: key for key, value in ExifTags.TAGS.items()}


def scan_dataset(dataset_dir: str, recursive: bool = True) -> list[str]:
    """
    Scan a directory and return a list of image file paths.

    Parameters
    ----------
    dataset_dir : str
        Root directory containing images.
    recursive : bool
        If True, search subdirectories.

    Returns
    -------
    list
        List of absolute file paths to image files.
    """
    root = Path(dataset_dir).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Dataset directory does not exist: {root}")

    iterator = root.rglob("*") if recursive else root.glob("*")
    return sorted(str(path.resolve()) for path in iterator if path.is_file() and is_image_file(path))


def extract_image_metadata(image_path: str) -> dict:
    """
    Extract basic metadata from an image.

    Parameters
    ----------
    image_path : str
        Path to the image file.

    Returns
    -------
    dict
        Metadata including:
        - filename
        - width
        - height
        - file size (MB)
        - format
    """
    path = Path(image_path).expanduser().resolve()
    metadata = {
        "path": str(path),
        "filename": path.name,
        "stem": path.stem,
        "parent": str(path.parent),
        "suffix": path.suffix.lower(),
        "format": path.suffix.lower().lstrip("."),
        "width": None,
        "height": None,
        "filesize_mb": file_size_mb(path),
        "camera_make": None,
        "camera_model": None,
        "datetime_original": None,
        "error": None,
    }

    try:
        with open_image(path) as image:
            metadata["width"], metadata["height"] = image.size
            metadata["format"] = (image.format or metadata["format"]).lower()

            exif = image.getexif() if hasattr(image, "getexif") else None
            if exif:
                metadata["camera_make"] = exif.get(EXIF_TAGS.get("Make"))
                metadata["camera_model"] = exif.get(EXIF_TAGS.get("Model"))
                metadata["datetime_original"] = exif.get(EXIF_TAGS.get("DateTimeOriginal"))
    except Exception as exc:
        metadata["error"] = str(exc)

    return metadata


def build_catalog(image_paths: list) -> pd.DataFrame:
    """
    Build a catalog table describing the dataset.

    Parameters
    ----------
    image_paths : list
        List of image file paths.

    Returns
    -------
    pandas.DataFrame
        Table containing metadata for each image.
    """
    records = [extract_image_metadata(path) for path in tqdm(image_paths, desc="Scanning images", unit="image")]
    catalog = pd.DataFrame.from_records(records)
    if catalog.empty:
        return pd.DataFrame(
            columns=[
                "path",
                "filename",
                "stem",
                "parent",
                "suffix",
                "format",
                "width",
                "height",
                "filesize_mb",
                "camera_make",
                "camera_model",
                "datetime_original",
                "error",
            ]
        )
    return catalog


def save_catalog(catalog, output_csv: str) -> None:
    """
    Save catalog metadata to a CSV file.

    Parameters
    ----------
    catalog : pandas.DataFrame
        Dataset catalog.
    output_csv : str
        Output file path.
    """
    output_path = Path(output_csv).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    catalog.to_csv(output_path, index=False)
