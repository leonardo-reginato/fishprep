from __future__ import annotations

import re

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from fishprep.utils import make_rgb, open_image

try:
    import pytesseract
except Exception:  # pragma: no cover - optional runtime dependency
    pytesseract = None


VALID_ID_PATTERN = re.compile(r"[A-Z0-9_]+")


def crop_label_region(image: np.ndarray) -> np.ndarray:
    """
    Crop the image region where specimen labels are most likely to appear.

    The sample images tend to place labels in the upper center/right portion
    of the frame, often spanning diagonally across a wide area. This crop keeps
    a broad upper band instead of a tight box so that angled labels are not lost.
    """
    if image.ndim not in (2, 3):
        raise ValueError("Expected a 2D or 3D image array.")

    height, width = image.shape[:2]
    top = int(height * 0.02)
    bottom = int(height * 0.68)
    left = int(width * 0.12)
    right = int(width * 0.98)
    return image[top:bottom, left:right].copy()


def preprocess_for_ocr(image: np.ndarray) -> np.ndarray:
    """
    Prepare a label crop for OCR by converting to grayscale, boosting contrast,
    denoising lightly, enlarging, and applying Otsu thresholding.
    """
    pil_image = Image.fromarray(image)
    grayscale = ImageOps.grayscale(pil_image)
    grayscale = ImageOps.autocontrast(grayscale)
    grayscale = grayscale.filter(ImageFilter.MedianFilter(size=3))
    grayscale = grayscale.resize((grayscale.width * 2, grayscale.height * 2), Image.Resampling.LANCZOS)

    gray_array = np.asarray(grayscale, dtype=np.uint8)
    threshold = _otsu_threshold(gray_array)
    binary = np.where(gray_array >= threshold, 255, 0).astype(np.uint8)

    # OCR generally works better with dark text on white background.
    if binary.mean() < 127:
        binary = 255 - binary

    return binary


def extract_sample_id(image_path: str) -> str | None:
    """
    Detect and OCR a specimen ID label from an image.
    """
    if pytesseract is None:
        raise RuntimeError("pytesseract is required for OCR. Install it and ensure Tesseract is available.")

    with open_image(image_path) as image:
        rgb = make_rgb(image)
        image_array = np.asarray(rgb)

    base_crop = crop_label_region(image_array)
    crops = _candidate_crops(base_crop)
    best_candidate = None
    best_score = -1

    for crop in crops:
        for angle in (-35, -25, -15, 0, 15, 25, 35):
            rotated = _rotate_crop(crop, angle)
            processed = preprocess_for_ocr(rotated)
            text = pytesseract.image_to_string(
                processed,
                config=r"--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_",
            )
            candidate = _normalize_candidate(text)
            if candidate is None:
                continue

            score = _score_candidate(candidate)
            if score > best_score:
                best_candidate = candidate
                best_score = score

    return best_candidate


def _candidate_crops(base_crop: np.ndarray) -> list[np.ndarray]:
    height, width = base_crop.shape[:2]
    crops = [base_crop]

    # Wider upper crop for long labels, plus a slightly tighter center/right crop.
    crops.append(base_crop[: int(height * 0.90), :])
    crops.append(base_crop[int(height * 0.05) : int(height * 0.85), int(width * 0.10) :])
    return crops


def _rotate_crop(image: np.ndarray, angle: float) -> np.ndarray:
    if angle == 0:
        return image
    pil_image = Image.fromarray(image)
    rotated = pil_image.rotate(angle, expand=True, fillcolor=(255, 255, 255))
    return np.asarray(rotated)


def _normalize_candidate(text: str) -> str | None:
    cleaned = text.strip().upper()
    cleaned = cleaned.replace(" ", "")
    cleaned = cleaned.replace("-", "_").replace("—", "_").replace("/", "_")
    matches = VALID_ID_PATTERN.findall(cleaned)
    if not matches:
        return None

    candidate = max(matches, key=len)
    candidate = re.sub(r"_+", "_", candidate).strip("_")
    if len(candidate) < 4 or not re.search(r"\d", candidate):
        return None
    return candidate


def _score_candidate(candidate: str) -> int:
    score = len(candidate)
    if "_" in candidate:
        score += 4
    if re.search(r"[A-Z]", candidate):
        score += 2
    if re.search(r"\d", candidate):
        score += 2
    if re.search(r"[A-Z]{2,}\d{2,}_\d{2,}", candidate):
        score += 6
    return score


def _otsu_threshold(gray_image: np.ndarray) -> int:
    histogram, _ = np.histogram(gray_image.ravel(), bins=256, range=(0, 256))
    total = gray_image.size
    sum_total = np.dot(np.arange(256), histogram)

    sum_background = 0.0
    weight_background = 0.0
    max_variance = -1.0
    best_threshold = 127

    for threshold in range(256):
        weight_background += histogram[threshold]
        if weight_background == 0:
            continue

        weight_foreground = total - weight_background
        if weight_foreground == 0:
            break

        sum_background += threshold * histogram[threshold]
        mean_background = sum_background / weight_background
        mean_foreground = (sum_total - sum_background) / weight_foreground
        variance_between = weight_background * weight_foreground * (mean_background - mean_foreground) ** 2

        if variance_between > max_variance:
            max_variance = variance_between
            best_threshold = threshold

    return int(best_threshold)
