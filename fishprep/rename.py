from __future__ import annotations

import re
import shutil
from pathlib import Path

from fishprep.utils import clean_stem, ensure_directory, unique_path


def extract_id_from_filename(filename: str) -> str:
    """
    Extract specimen ID from a filename.

    Parameters
    ----------
    filename : str
        Original filename containing metadata.

    Returns
    -------
    str
        Extracted ID string.
    """
    stem = Path(filename).stem
    tokens = [token for token in re.split(r"[^A-Za-z0-9]+", stem) if token]
    if not tokens:
        return clean_stem(stem)

    candidates = [token for token in tokens if re.search(r"\d", token)]
    if candidates:
        return clean_stem(max(candidates, key=len))
    return clean_stem(tokens[0])


def rename_image(image_path: str, new_id: str, output_dir: str) -> str:
    """
    Rename an image file using a cleaned ID.

    Parameters
    ----------
    image_path : str
        Original image path.
    new_id : str
        Clean identifier for the image.
    output_dir : str
        Directory where renamed image will be saved.

    Returns
    -------
    str
        Path to renamed image.
    """
    destination = unique_path(output_dir, clean_stem(new_id), suffix=".jpg")
    shutil.copy2(image_path, destination)
    return str(destination)


def batch_rename_images(catalog, output_dir: str):
    """
    Rename all images in the catalog using cleaned IDs.

    Parameters
    ----------
    catalog : pandas.DataFrame
        Dataset catalog.
    output_dir : str
        Destination folder.
    """
    ensure_directory(output_dir)
    renamed_paths = []
    for row in catalog.itertuples(index=False):
        specimen_id = getattr(row, "specimen_id", None) or extract_id_from_filename(row.filename)
        renamed_paths.append(rename_image(row.converted_path, specimen_id, output_dir))
    return renamed_paths
