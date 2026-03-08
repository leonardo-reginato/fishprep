

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
    
