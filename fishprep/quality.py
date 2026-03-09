from __future__ import annotations

import math

import numpy as np

from fishprep.utils import make_rgb, open_image


def compute_blur_score(image_path: str) -> float:
    """
    Compute blur score using variance of Laplacian.

    Parameters
    ----------
    image_path : str
        Path to image.

    Returns
    -------
    float
        Blur score (lower = blurrier).
    """
    with open_image(image_path) as image:
        grayscale = np.asarray(make_rgb(image).convert("L"), dtype=np.float32)

    if grayscale.shape[0] < 3 or grayscale.shape[1] < 3:
        return 0.0

    center = grayscale[1:-1, 1:-1]
    laplacian = (
        grayscale[:-2, 1:-1]
        + grayscale[2:, 1:-1]
        + grayscale[1:-1, :-2]
        + grayscale[1:-1, 2:]
        - 4 * center
    )
    return float(laplacian.var())


def compute_resolution_score(width: int, height: int) -> float:
    """
    Compute a resolution score based on image size.

    Parameters
    ----------
    width : int
        Image width.
    height : int
        Image height.

    Returns
    -------
    float
        Resolution score.
    """
    if not width or not height:
        return 0.0
    megapixels = (float(width) * float(height)) / 1_000_000
    return float(math.sqrt(megapixels))


def compute_centering_score(image_path: str) -> float:
    """
    Estimate how centered the main visual structure is in the image.

    Parameters
    ----------
    image_path : str
        Path to image.

    Returns
    -------
    float
        Score between 0 and 1, where higher values are more centered.
    """
    with open_image(image_path) as image:
        grayscale = np.asarray(make_rgb(image).convert("L"), dtype=np.float32)

    if grayscale.size == 0:
        return 0.0

    grad_y, grad_x = np.gradient(grayscale)
    energy = np.hypot(grad_x, grad_y)
    total_energy = float(energy.sum())
    if total_energy <= 0:
        return 0.0

    yy, xx = np.indices(energy.shape)
    centroid_x = float((xx * energy).sum() / total_energy) / max(energy.shape[1] - 1, 1)
    centroid_y = float((yy * energy).sum() / total_energy) / max(energy.shape[0] - 1, 1)

    distance = math.sqrt((centroid_x - 0.5) ** 2 + (centroid_y - 0.5) ** 2)
    max_distance = math.sqrt(0.5**2 + 0.5**2)
    return round(max(0.0, 1.0 - (distance / max_distance)), 6)


def compute_quality_score(row) -> float:
    """
    Combine multiple metrics into a single image quality score.

    Parameters
    ----------
    row : pandas.Series
        Catalog row containing metadata and blur score.

    Returns
    -------
    float
        Combined quality score.
    """
    blur = float(row.get("blur_score", 0.0) or 0.0)
    resolution = float(row.get("resolution_score", 0.0) or 0.0)
    centering = float(row.get("centering_score", 0.0) or 0.0)
    filesize = float(row.get("converted_filesize_mb", row.get("filesize_mb", 0.0)) or 0.0)

    blur_component = math.log1p(max(blur, 0.0))
    resolution_component = resolution
    centering_component = centering * 3.0
    filesize_penalty = 0.05 * filesize
    return round((0.55 * blur_component) + (0.2 * resolution_component) + (0.25 * centering_component) - filesize_penalty, 6)


def select_best_image(group):
    """
    Select the best quality image from a group of duplicates.

    Parameters
    ----------
    group : list
        List of image records.

    Returns
    -------
    str
        Path to best image candidate.
    """
    if hasattr(group, "sort_values"):
        ranked = group.sort_values(
            by=["quality_score", "blur_score", "resolution_score", "converted_filesize_mb"],
            ascending=[False, False, False, True],
        )
        return ranked.iloc[0]["converted_path"]

    ranked = sorted(
        group,
        key=lambda row: (
            row.get("quality_score", 0.0),
            row.get("blur_score", 0.0),
            row.get("resolution_score", 0.0),
            -row.get("converted_filesize_mb", row.get("filesize_mb", 0.0)),
        ),
        reverse=True,
    )
    return ranked[0]["converted_path"]
