from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from tqdm import tqdm

from fishprep.convert import compress_image_to_size, convert_to_jpeg
from fishprep.duplicates import (
    compute_md5_hash,
    compute_perceptual_hash,
    export_duplicate_report,
    group_exact_duplicates,
    group_similar_images,
)
from fishprep.ocr import extract_sample_id
from fishprep.quality import (
    compute_blur_score,
    compute_centering_score,
    compute_quality_score,
    compute_resolution_score,
)
from fishprep.rename import extract_id_from_filename
from fishprep.scan import build_catalog, scan_dataset
from fishprep.utils import clean_stem, ensure_directory, file_size_mb


OUTPUT_DIRS = {
    "standard": "standard",
    "duplicate": "duplicates",
    "low_quality": "low_quality",
}


def load_config(config_path: str) -> dict:
    with Path(config_path).expanduser().resolve().open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def normalize_config(config: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(config)
    dataset_dir, output_dir = _resolve_pipeline_paths(normalized)
    normalized["dataset_dir"] = dataset_dir
    normalized["output_dir"] = output_dir
    return normalized


def _resolve_pipeline_paths(config: dict) -> tuple[str, str]:
    dataset_dir = config.get("dataset_dir")
    output_dir = config.get("output_dir")

    if not dataset_dir:
        raise ValueError("Config is missing required field 'dataset_dir'.")
    if not output_dir:
        raise ValueError("Config is missing required field 'output_dir'.")

    return str(Path(dataset_dir).expanduser().resolve()), str(Path(output_dir).expanduser().resolve())


def _catalog_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / "catalog.csv"


def _duplicate_report_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / "duplicate_groups.csv"


def _summary_log_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / "summary.txt"


def _work_dir(output_dir: str | Path) -> Path:
    return Path(output_dir) / ".fishprep_work"


def _log_line(log_lines: list[str], message: str, level: str = "INFO") -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_lines.append(f"{timestamp} [{level}] {message}")


def _log_config(log_lines: list[str], config: dict[str, Any]) -> None:
    _log_line(log_lines, "Configuration settings:")
    for key in sorted(config):
        _log_line(log_lines, f"  {key}={config[key]}")


def _read_summary_log(output_dir: str | Path) -> list[str]:
    path = _summary_log_path(output_dir)
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def _write_summary_log(output_dir: str | Path, log_lines: list[str]) -> None:
    path = _summary_log_path(output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")


def _log_decisions(log_lines: list[str], decisions: pd.DataFrame | None) -> None:
    if decisions is None or decisions.empty:
        _log_line(log_lines, "No manual review decisions were provided.")
        return

    reviewed_rows = decisions.loc[decisions["role"] != "reference"].copy()
    if reviewed_rows.empty:
        _log_line(log_lines, "No duplicate candidates were reviewed.")
        return

    counts = reviewed_rows["decision"].fillna("undecided").value_counts().to_dict()
    _log_line(log_lines, f"Review decisions summary: {counts}")
    for row in reviewed_rows.itertuples(index=False):
        _log_line(
            log_lines,
            f"Decision group={row.group_id} type={row.duplicate_type} file={row.filename} role={row.role} decision={row.decision}",
        )


def _scan_and_convert(dataset_dir: str, output_dir: str, config: dict) -> pd.DataFrame:
    del output_dir, config
    image_paths = scan_dataset(dataset_dir=dataset_dir, recursive=True)
    catalog = build_catalog(image_paths)
    if catalog.empty:
        return pd.DataFrame()

    catalog["specimen_id"] = catalog["filename"].map(extract_id_from_filename)
    catalog["original_path"] = catalog["path"]
    catalog = catalog.copy()
    catalog["working_path"] = catalog.apply(
        lambda row: row["path"] if pd.isna(row.get("error")) else None,
        axis=1,
    )
    catalog["conversion_ok"] = catalog["working_path"].notna()
    catalog["working_filesize_mb"] = catalog["filesize_mb"]
    catalog["ocr_sample_id"] = _extract_ocr_ids(catalog["working_path"].tolist())
    catalog["ocr_label_detected"] = catalog["ocr_sample_id"].notna()
    return catalog


def _extract_ocr_ids(image_paths: list[str | None]) -> list[str | None]:
    extracted_ids: list[str | None] = []
    ocr_available = True

    for image_path in tqdm(image_paths, desc="Reading label OCR", unit="image"):
        if not image_path or not Path(image_path).exists():
            extracted_ids.append(None)
            continue

        if not ocr_available:
            extracted_ids.append(None)
            continue

        try:
            extracted_ids.append(extract_sample_id(image_path))
        except RuntimeError:
            ocr_available = False
            extracted_ids.append(None)
        except Exception:
            extracted_ids.append(None)

    return extracted_ids


def _score_images(catalog: pd.DataFrame, config: dict) -> pd.DataFrame:
    working = catalog.copy()
    working["md5"] = working["working_path"].map(lambda path: _safe_file_metric(path, compute_md5_hash))
    working["phash"] = working["working_path"].map(
        lambda path: _safe_file_metric(path, lambda value: str(compute_perceptual_hash(value)))
    )
    working["blur_score"] = working["working_path"].map(
        lambda path: _safe_file_metric(path, compute_blur_score, fallback=0.0)
    )
    working["centering_score"] = working["working_path"].map(
        lambda path: _safe_file_metric(path, compute_centering_score, fallback=0.0)
    )
    working["resolution_score"] = working.apply(
        lambda row: compute_resolution_score(row.get("width"), row.get("height")),
        axis=1,
    )
    working["quality_score"] = working.apply(compute_quality_score, axis=1)

    blur_threshold = float(config.get("blur_threshold", 5.0))
    enable_centering_check = bool(config.get("enable_centering_check", False))
    centering_threshold = float(config.get("centering_threshold", 0.2))
    working["is_blurry"] = working["blur_score"] < blur_threshold
    working["is_off_center"] = enable_centering_check & (working["centering_score"] < centering_threshold)
    working["is_low_quality"] = working["is_blurry"] | working["is_off_center"]
    working["low_quality_reason"] = working.apply(_build_low_quality_reason, axis=1)
    working = working.sort_values(
        by=["specimen_id", "conversion_ok", "quality_score", "blur_score", "resolution_score"],
        ascending=[True, False, False, False, False],
    ).reset_index(drop=True)
    working["quality_rank"] = working.groupby("specimen_id").cumcount() + 1
    return working


def _build_low_quality_reason(row: pd.Series) -> str:
    reasons = []
    if bool(row.get("is_blurry")):
        reasons.append("blurry")
    if bool(row.get("is_off_center")):
        reasons.append("off_center")
    return ",".join(reasons)


def _safe_file_metric(path: str | None, func, fallback=None):
    if not path or not Path(path).exists():
        return fallback
    try:
        return func(path)
    except Exception:
        return fallback


def _assign_exact_groups(catalog: pd.DataFrame) -> tuple[pd.DataFrame, list[list[str]]]:
    working = catalog.copy()
    working["exact_group_id"] = pd.NA
    working["exact_reference_path"] = pd.NA
    working["is_exact_duplicate"] = False

    exact_groups = list(group_exact_duplicates(working).values())
    for group_index, group_paths in enumerate(exact_groups, start=1):
        group_rows = working.loc[working["path"].isin(group_paths)].copy()
        ranked = group_rows.sort_values(
            by=["conversion_ok", "quality_score", "blur_score", "resolution_score", "working_filesize_mb"],
            ascending=[False, False, False, False, True],
        )
        reference_path = ranked.iloc[0]["path"]
        group_mask = working["path"].isin(group_paths)
        working.loc[group_mask, "exact_group_id"] = group_index
        working.loc[group_mask, "exact_reference_path"] = reference_path
        working.loc[group_mask & (working["path"] != reference_path), "is_exact_duplicate"] = True
    return working, exact_groups


def _assign_similar_groups(catalog: pd.DataFrame, config: dict) -> tuple[pd.DataFrame, list[list[str]]]:
    working = catalog.copy()
    working["similar_group_id"] = pd.NA
    working["similar_reference_path"] = pd.NA
    working["is_similar_duplicate"] = False

    candidates = working.loc[~working["is_exact_duplicate"]].copy()
    tolerance = int(config.get("duplicate_tolerance", config.get("phash_threshold", 5)))
    similar_groups = group_similar_images(candidates, phash_threshold=tolerance)

    for group_index, group_paths in enumerate(similar_groups, start=1):
        group_rows = working.loc[working["path"].isin(group_paths)].copy()
        if len(group_rows) < 2:
            continue
        ranked = group_rows.sort_values(
            by=["conversion_ok", "quality_score", "blur_score", "resolution_score", "working_filesize_mb"],
            ascending=[False, False, False, False, True],
        )
        reference_path = ranked.iloc[0]["path"]
        group_mask = working["path"].isin(group_paths)
        working.loc[group_mask, "similar_group_id"] = group_index
        working.loc[group_mask, "similar_reference_path"] = reference_path
        working.loc[group_mask & (working["path"] != reference_path), "is_similar_duplicate"] = True
    return working, similar_groups


def _apply_category_flags(catalog: pd.DataFrame, decisions: pd.DataFrame | None = None) -> pd.DataFrame:
    working = catalog.copy()
    working["manual_duplicate_decision"] = pd.NA

    if decisions is not None and not decisions.empty:
        working = _apply_manual_reference_selection(working, decisions)
        decision_map = decisions.set_index("path")["decision"].to_dict()
        working["manual_duplicate_decision"] = working["path"].map(decision_map)

    working["is_duplicate"] = working["is_exact_duplicate"] | working["is_similar_duplicate"]
    working["auto_category"] = working.apply(_auto_category_for_row, axis=1)
    working["final_category"] = working.apply(_final_category_for_row, axis=1)
    working["duplicate_flag"] = working["final_category"] == "duplicate"
    working["low_quality_flag"] = working["final_category"] == "low_quality"
    working["is_selected"] = working["final_category"] == "standard"
    return working


def _apply_manual_reference_selection(catalog: pd.DataFrame, decisions: pd.DataFrame) -> pd.DataFrame:
    working = catalog.copy()
    required_columns = {"group_id", "duplicate_type", "path", "role"}
    if not required_columns.issubset(decisions.columns):
        return working

    grouped = decisions.dropna(subset=["group_id", "duplicate_type", "path", "role"]).groupby(
        ["duplicate_type", "group_id"],
        sort=False,
    )
    for (duplicate_type, group_id), group in grouped:
        reference_rows = group.loc[group["role"] == "reference"]
        if len(reference_rows) != 1:
            continue

        reference_path = str(reference_rows.iloc[0]["path"])
        group_paths = group["path"].astype(str).tolist()
        group_mask = working["path"].isin(group_paths)
        reference_mask = working["path"] == reference_path
        duplicate_mask = group_mask & ~reference_mask

        if duplicate_type == "exact":
            working.loc[group_mask, "exact_group_id"] = group_id
            working.loc[group_mask, "exact_reference_path"] = reference_path
            working.loc[group_mask, "is_exact_duplicate"] = False
            working.loc[duplicate_mask, "is_exact_duplicate"] = True
        elif duplicate_type == "similar":
            working.loc[group_mask, "similar_group_id"] = group_id
            working.loc[group_mask, "similar_reference_path"] = reference_path
            working.loc[group_mask, "is_similar_duplicate"] = False
            working.loc[duplicate_mask, "is_similar_duplicate"] = True

    return working


def _auto_category_for_row(row: pd.Series) -> str:
    if bool(row.get("is_exact_duplicate")):
        return "duplicate"
    if bool(row.get("is_low_quality")):
        return "low_quality"
    return "standard"


def _final_category_for_row(row: pd.Series) -> str:
    decision = row.get("manual_duplicate_decision")
    if pd.isna(decision):
        decision = None
    if decision == "keep":
        return "low_quality" if bool(row.get("is_low_quality")) else "standard"
    if decision == "exclude":
        return "duplicate"
    return str(row.get("auto_category"))


def _reserve_name(base_name: str, suffix: str, used_names: set[str]) -> str:
    candidate = f"{base_name}{suffix}.jpg"
    index = 1
    while candidate.lower() in used_names:
        candidate = f"{base_name}{suffix}_{index:02d}.jpg"
        index += 1
    used_names.add(candidate.lower())
    return candidate


def _assign_output_names(catalog: pd.DataFrame, output_dir: str) -> pd.DataFrame:
    working = catalog.copy()
    working["new_filename"] = pd.NA
    working["new_path"] = pd.NA
    working["reference_base_name"] = pd.NA

    used_names = {key: set() for key in OUTPUT_DIRS}
    output_root = Path(output_dir)

    standard_like = working.loc[working["final_category"].isin(["standard", "low_quality"])].copy()
    standard_like = standard_like.sort_values(by=["final_category", "quality_score"], ascending=[True, False])

    for row in standard_like.itertuples(index=False):
        category = row.final_category
        base_name = clean_stem(Path(row.filename).stem)
        filename = _reserve_name(base_name, "", used_names[category])
        new_path = output_root / OUTPUT_DIRS[category] / filename
        mask = working["path"] == row.path
        working.loc[mask, "new_filename"] = filename
        working.loc[mask, "new_path"] = str(new_path)
        working.loc[mask, "reference_base_name"] = Path(filename).stem

    exact_duplicate_rows = working.loc[working["final_category"] == "duplicate"].copy()
    exact_duplicate_rows = exact_duplicate_rows.loc[exact_duplicate_rows["is_exact_duplicate"]].copy()
    for group_id, group_rows in exact_duplicate_rows.groupby("exact_group_id", dropna=True, sort=True):
        reference_path = group_rows["exact_reference_path"].iloc[0]
        reference_base = _reference_base_name(working, reference_path)
        ordered_rows = group_rows.sort_values(by=["filename", "path"])
        for position, row in enumerate(ordered_rows.itertuples(index=False)):
            suffix = "_dup" if position == 0 else f"_dup{position:02d}"
            filename = _reserve_name(reference_base, suffix, used_names["duplicate"])
            new_path = output_root / OUTPUT_DIRS["duplicate"] / filename
            mask = working["path"] == row.path
            working.loc[mask, "new_filename"] = filename
            working.loc[mask, "new_path"] = str(new_path)
            working.loc[mask, "reference_base_name"] = reference_base

    similar_duplicate_rows = working.loc[working["final_category"] == "duplicate"].copy()
    similar_duplicate_rows = similar_duplicate_rows.loc[~similar_duplicate_rows["is_exact_duplicate"] & similar_duplicate_rows["is_similar_duplicate"]].copy()
    for group_id, group_rows in similar_duplicate_rows.groupby("similar_group_id", dropna=True, sort=True):
        reference_path = group_rows["similar_reference_path"].iloc[0]
        reference_base = _reference_base_name(working, reference_path)
        ordered_rows = group_rows.sort_values(by=["filename", "path"])
        for position, row in enumerate(ordered_rows.itertuples(index=False), start=1):
            suffix = f"_{position:02d}"
            filename = _reserve_name(reference_base, suffix, used_names["duplicate"])
            new_path = output_root / OUTPUT_DIRS["duplicate"] / filename
            mask = working["path"] == row.path
            working.loc[mask, "new_filename"] = filename
            working.loc[mask, "new_path"] = str(new_path)
            working.loc[mask, "reference_base_name"] = reference_base

    return working


def _reference_base_name(catalog: pd.DataFrame, reference_path: str) -> str:
    reference_row = catalog.loc[catalog["path"] == reference_path]
    if reference_row.empty:
        return clean_stem(Path(reference_path).stem)

    new_filename = reference_row.iloc[0].get("new_filename")
    if isinstance(new_filename, str) and new_filename:
        return Path(new_filename).stem
    return clean_stem(Path(reference_row.iloc[0]["filename"]).stem)


def _prepare_output_dirs(output_dir: str) -> None:
    output_root = Path(output_dir)
    for folder_name in OUTPUT_DIRS.values():
        destination = output_root / folder_name
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True, exist_ok=True)


def _cleanup_work_dir(output_dir: str) -> None:
    work_dir = _work_dir(output_dir)
    if work_dir.exists():
        shutil.rmtree(work_dir)


def _materialize_outputs(catalog: pd.DataFrame, output_dir: str, config: dict[str, Any]) -> None:
    _prepare_output_dirs(output_dir)
    quality = int(config.get("jpeg_quality", 90))
    max_size_mb = float(config.get("max_size_mb", 10.0))
    for row in catalog.itertuples(index=False):
        if not row.new_path:
            continue
        destination = Path(row.new_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_path = getattr(row, "original_path", None) or row.path
        if not source_path:
            continue
        converted_path = convert_to_jpeg(str(source_path), str(destination), quality=quality)
        compress_image_to_size(converted_path, max_size_mb=max_size_mb)


def save_catalog(catalog: pd.DataFrame, output_csv: str) -> None:
    output_path = Path(output_csv).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    catalog.to_csv(output_path, index=False)


def analyze_pipeline_from_config(config: dict[str, Any]) -> dict:
    config = normalize_config(config)
    dataset_dir, output_dir = _resolve_pipeline_paths(config)
    output_root = ensure_directory(output_dir)
    log_lines: list[str] = []
    _log_line(log_lines, "fishprep analysis started.")
    _log_config(log_lines, config)

    catalog = _scan_and_convert(dataset_dir, str(output_root), config)
    _log_line(log_lines, f"Scan complete. images_scanned={len(catalog)}")
    if catalog.empty:
        save_catalog(catalog, str(_catalog_path(output_root)))
        _log_line(log_lines, "No images found. Catalog written with 0 rows.", level="WARNING")
        _log_line(log_lines, "Analysis finished with no images to process.")
        _write_summary_log(output_root, log_lines)
        return {
            "catalog": catalog,
            "exact_groups": [],
            "similar_groups": [],
            "output_dir": str(output_root),
        }

    catalog = _score_images(catalog, config)
    _log_line(
        log_lines,
        "Scoring complete. "
        f"conversion_ok={int(catalog['conversion_ok'].fillna(False).sum())} "
        f"ocr_detected={int(catalog['ocr_label_detected'].fillna(False).sum())} "
        f"low_quality={int(catalog['is_low_quality'].fillna(False).sum())}",
    )
    catalog, exact_groups = _assign_exact_groups(catalog)
    exact_duplicate_count = int(catalog["is_exact_duplicate"].fillna(False).sum())
    _log_line(log_lines, f"Exact grouping complete. groups={len(exact_groups)} duplicates={exact_duplicate_count}")
    catalog, similar_groups = _assign_similar_groups(catalog, config)
    similar_duplicate_count = int(catalog["is_similar_duplicate"].fillna(False).sum())
    _log_line(
        log_lines,
        f"Similar grouping complete. groups_for_review={len(similar_groups)} candidates={similar_duplicate_count}",
    )
    catalog = _apply_category_flags(catalog)
    catalog = _assign_output_names(catalog, str(output_root))
    _log_line(log_lines, "Output names assigned.")

    save_catalog(catalog, str(_catalog_path(output_root)))
    export_duplicate_report(catalog, exact_groups, similar_groups, str(_duplicate_report_path(output_root)))
    _log_line(log_lines, "Catalog and duplicate review report written.")
    _log_line(log_lines, "Analysis phase finished successfully.")
    _write_summary_log(output_root, log_lines)
    return {
        "catalog": catalog,
        "exact_groups": exact_groups,
        "similar_groups": similar_groups,
        "output_dir": str(output_root),
    }


def analyze_pipeline(config_path: str) -> dict:
    return analyze_pipeline_from_config(load_config(config_path))


def finalize_review_from_config(config: dict[str, Any], decisions: pd.DataFrame | None = None) -> dict:
    config = normalize_config(config)
    _, output_dir = _resolve_pipeline_paths(config)
    catalog_path = _catalog_path(output_dir)
    if not catalog_path.exists():
        raise FileNotFoundError(f"Catalog not found. Run the analysis first: {catalog_path}")

    log_lines = _read_summary_log(output_dir)
    if not log_lines:
        _log_line(log_lines, "fishprep finalize started without an existing analysis log.", level="WARNING")
        _log_config(log_lines, config)
    _log_line(log_lines, "Finalize review started.")

    catalog = pd.read_csv(catalog_path)
    _log_line(log_lines, f"Loaded catalog rows={len(catalog)}")
    _log_decisions(log_lines, decisions)
    catalog = _apply_category_flags(catalog, decisions=decisions)
    catalog = _assign_output_names(catalog, output_dir)
    save_catalog(catalog, str(catalog_path))
    _log_line(log_lines, "Updated catalog written.")
    _materialize_outputs(catalog, output_dir, config)
    _log_line(log_lines, "Final output files materialized.")
    _cleanup_work_dir(output_dir)
    _log_line(log_lines, "Temporary work directory cleaned up.")

    _log_line(
        log_lines,
        "Final counts: "
        f"images_scanned={len(catalog)} "
        f"standard_images={int((catalog['final_category'] == 'standard').sum())} "
        f"duplicate_images={int((catalog['final_category'] == 'duplicate').sum())} "
        f"low_quality_images={int((catalog['final_category'] == 'low_quality').sum())}",
    )
    _log_line(log_lines, "fishprep run finished successfully.")
    _write_summary_log(output_dir, log_lines)
    return {"catalog": catalog, "output_dir": output_dir}


def finalize_review(config_path: str, decisions: pd.DataFrame | None = None) -> dict:
    return finalize_review_from_config(load_config(config_path), decisions=decisions)


def run_pipeline_from_config(config: dict[str, Any], finalize_outputs: bool = True) -> dict:
    result = analyze_pipeline_from_config(config)
    if finalize_outputs and not result["catalog"].empty:
        return finalize_review_from_config(config)

    if finalize_outputs:
        log_lines = _read_summary_log(result["output_dir"])
        if not log_lines:
            _log_line(log_lines, "fishprep run started.")
        _log_line(log_lines, "No images were available for finalization.")
        _log_line(log_lines, "fishprep run finished successfully.")
        _write_summary_log(result["output_dir"], log_lines)
    return result


def run_pipeline(config_path: str, finalize_outputs: bool = True) -> dict:
    result = analyze_pipeline(config_path)
    if finalize_outputs and not result["catalog"].empty:
        return finalize_review(config_path)

    if finalize_outputs:
        log_lines = _read_summary_log(result["output_dir"])
        if not log_lines:
            _log_line(log_lines, "fishprep run started.")
        _log_line(log_lines, "No images were available for finalization.")
        _log_line(log_lines, "fishprep run finished successfully.")
        _write_summary_log(result["output_dir"], log_lines)
    return result
