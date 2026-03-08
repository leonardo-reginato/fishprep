

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