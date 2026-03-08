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
    
def export_duplicate_report(groups, output_csv: str):
    """
    Save duplicate groups to a CSV file.

    Parameters
    ----------
    groups : list
        Duplicate image groups.
    output_csv : str
        Output report file.
    """
    