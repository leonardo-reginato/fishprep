

def load_config(config_path: str) -> dict:
    """
    Load pipeline configuration from YAML file.

    Parameters
    ----------
    config_path : str
        Path to configuration file.

    Returns
    -------
    dict
        Configuration dictionary.
    """
    
def run_scan_step(dataset_dir: str, output_dir: str):
    """
    Run dataset scanning and catalog generation.

    Returns
    -------
    pandas.DataFrame
        Dataset catalog.
    """
    
def run_conversion_step(catalog, output_dir: str, config: dict):
    """
    Convert all images to standardized JPEG format.

    Returns
    -------
    pandas.DataFrame
        Updated catalog with converted paths.
    """
    
def run_duplicate_detection(catalog, config: dict):
    """
    Detect exact and near duplicate images.

    Returns
    -------
    list
        Duplicate image groups.
    """
    
def run_quality_filtering(catalog, duplicate_groups):
    """
    Evaluate image quality and select best candidate per group.

    Returns
    -------
    pandas.DataFrame
        Filtered catalog with selected images.
    """
    
def run_renaming_step(catalog, output_dir: str):
    """
    Apply filename cleaning and export final dataset.

    Returns
    -------
    list
        Paths of final curated images.
    """
    
def run_pipeline(dataset_dir: str, output_dir: str, config_path: str):
    """
    Execute the full fishprep preprocessing pipeline.

    Pipeline Steps
    --------------
    1. Scan dataset
    2. Build catalog
    3. Convert image formats
    4. Detect duplicates
    5. Evaluate image quality
    6. Select best images
    7. Rename and export dataset

    Returns
    -------
    None
    """