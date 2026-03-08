def scan_dataset(dataset_dir: str, recursive: bool = True) -> list:
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
    
def build_catalog(image_paths: list) -> "pd.DataFrame":
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