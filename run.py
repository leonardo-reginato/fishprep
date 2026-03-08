

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