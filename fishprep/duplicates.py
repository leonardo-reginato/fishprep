from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path

import imagehash
import pandas as pd
from tqdm import tqdm

from fishprep.utils import make_rgb, open_image


def compute_md5_hash(image_path: str) -> str:
    """
    Compute the MD5 hash of an image file.

    Parameters
    ----------
    image_path : str
        Path to image file.

    Returns
    -------
    str
        MD5 hash string.
    """
    digest = hashlib.md5()
    with Path(image_path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_perceptual_hash(image_path: str):
    """
    Compute a perceptual hash (pHash) for an image.

    Parameters
    ----------
    image_path : str
        Path to image.

    Returns
    -------
    imagehash.ImageHash
        Perceptual hash object.
    """
    with open_image(image_path) as image:
        rgb = make_rgb(image)
        return imagehash.phash(rgb)


def group_exact_duplicates(catalog):
    """
    Identify images with identical file hashes.

    Parameters
    ----------
    catalog : pandas.DataFrame
        Dataset catalog with MD5 hashes.

    Returns
    -------
    dict
        Dictionary mapping hash -> list of duplicate images.
    """
    groups = {}
    if catalog.empty or "md5" not in catalog:
        return groups

    for md5, group in catalog.groupby("md5"):
        if md5 and len(group) > 1:
            groups[md5] = group["path"].tolist()
    return groups


def _phash_distance(hash_a: str, hash_b: str) -> int:
    return (int(hash_a, 16) ^ int(hash_b, 16)).bit_count()


class _BKTree:
    def __init__(self):
        self.root = None

    def add(self, value: str) -> None:
        if self.root is None:
            self.root = (value, {})
            return

        node_value, children = self.root
        while True:
            distance = _phash_distance(value, node_value)
            if distance not in children:
                children[distance] = (value, {})
                return
            node_value, children = children[distance]

    def search(self, value: str, threshold: int) -> list[str]:
        if self.root is None:
            return []

        matches = []
        stack = [self.root]
        while stack:
            node_value, children = stack.pop()
            distance = _phash_distance(value, node_value)
            if distance <= threshold:
                matches.append(node_value)
            lower = distance - threshold
            upper = distance + threshold
            for edge, child in children.items():
                if lower <= edge <= upper:
                    stack.append(child)
        return matches


def group_similar_images(catalog, phash_threshold: int = 5):
    """
    Group visually similar images using perceptual hash distance.

    Parameters
    ----------
    catalog : pandas.DataFrame
        Dataset catalog with perceptual hashes.
    phash_threshold : int
        Maximum Hamming distance to consider images similar.

    Returns
    -------
    list
        List of groups containing similar images.
    """
    if catalog.empty or "phash" not in catalog:
        return []

    valid_rows = catalog.dropna(subset=["phash"])
    if valid_rows.empty:
        return []

    tree = _BKTree()
    representative_rows = {}
    for row in valid_rows.itertuples(index=False):
        phash = str(row.phash)
        if phash not in representative_rows:
            representative_rows[phash] = row
            tree.add(phash)

    parent = {phash: phash for phash in representative_rows}

    def find(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: str, right: str) -> None:
        root_left = find(left)
        root_right = find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    for phash in tqdm(representative_rows, desc="Grouping similar images", unit="hash"):
        for match in tree.search(phash, phash_threshold):
            union(phash, match)

    grouped_hashes = defaultdict(list)
    for phash in representative_rows:
        grouped_hashes[find(phash)].append(phash)

    groups = []
    for members in grouped_hashes.values():
        group_rows = valid_rows[valid_rows["phash"].isin(members)]
        if len(group_rows) > 1:
            groups.append(group_rows["path"].tolist())
    return groups


def export_duplicate_report(catalog, exact_groups, similar_groups, output_csv: str):
    """
    Save a duplicate review table to a CSV file.

    Parameters
    ----------
    catalog : pandas.DataFrame
        Ranked catalog with metadata and quality scores.
    exact_groups : list
        Exact duplicate groups.
    similar_groups : list
        Near-duplicate groups.
    output_csv : str
        Output report file.
    """
    output_path = Path(output_csv).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []

    def add_group_rows(groups: list[list[str]], duplicate_type: str, start_group_id: int) -> int:
        group_id = start_group_id
        for group in groups:
            group_rows = catalog.loc[catalog["path"].isin(group)].copy()
            if len(group_rows) < 2:
                continue

            ranked = group_rows.sort_values(
                by=["conversion_ok", "quality_score", "blur_score", "resolution_score", "filesize_mb"],
                ascending=[False, False, False, False, True],
            )
            reference = ranked.iloc[0]

            for _, row in ranked.iterrows():
                phash_distance = None
                if duplicate_type == "similar" and pd.notna(reference.get("phash")) and pd.notna(row.get("phash")):
                    phash_distance = _phash_distance(str(reference["phash"]), str(row["phash"]))

                rows.append(
                    {
                        "group_id": group_id,
                        "duplicate_type": duplicate_type,
                        "role": "reference" if row["path"] == reference["path"] else "duplicate",
                        "reference_path": reference["path"],
                        "reference_filename": reference["filename"],
                        "reference_specimen_id": reference.get("specimen_id"),
                        "path": row["path"],
                        "original_path": row.get("original_path", row["path"]),
                        "filename": row["filename"],
                        "specimen_id": row.get("specimen_id"),
                        "working_path": row.get("working_path"),
                        "conversion_ok": row.get("conversion_ok"),
                        "md5": row.get("md5"),
                        "phash": row.get("phash"),
                        "phash_distance_to_reference": phash_distance,
                        "quality_score": row.get("quality_score"),
                        "blur_score": row.get("blur_score"),
                        "centering_score": row.get("centering_score"),
                        "resolution_score": row.get("resolution_score"),
                        "quality_rank_within_specimen": row.get("quality_rank"),
                        "selected_for_curation": row.get("is_selected"),
                        "auto_category": row.get("auto_category"),
                        "final_category": row.get("final_category"),
                        "new_filename": row.get("new_filename"),
                        "new_path": row.get("new_path"),
                    }
                )
            group_id += 1
        return group_id

    add_group_rows(similar_groups, "similar", start_group_id=1)

    report = pd.DataFrame(rows)
    if report.empty:
        report = pd.DataFrame(
            columns=[
                "group_id",
                "duplicate_type",
                "role",
                "reference_path",
                "reference_filename",
                "reference_specimen_id",
                "path",
                "original_path",
                "filename",
                "specimen_id",
                "working_path",
                "conversion_ok",
                "md5",
                "phash",
                "phash_distance_to_reference",
                "quality_score",
                "blur_score",
                "centering_score",
                "resolution_score",
                "quality_rank_within_specimen",
                "selected_for_curation",
                "auto_category",
                "final_category",
                "new_filename",
                "new_path",
            ]
        )
    report.to_csv(output_path, index=False)
