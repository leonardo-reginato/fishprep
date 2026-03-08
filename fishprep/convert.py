
def convert_to_jpeg(image_path: str, output_path: str, quality: int = 90) -> str:
    """
    Convert an image to JPEG format.

    Parameters
    ----------
    image_path : str
        Path to original image.
    output_path : str
        Path where converted image will be saved.
    quality : int
        JPEG compression quality (0–100).

    Returns
    -------
    str
        Path to converted JPEG file.
    """
    
def compress_image_to_size(image_path: str, max_size_mb: float) -> str:
    """
    Compress an image until its file size is below a specified limit.

    Parameters
    ----------
    image_path : str
        Path to image.
    max_size_mb : float
        Maximum allowed file size.

    Returns
    -------
    str
        Path to compressed image.
    """
    
def batch_convert_images(image_paths: list, output_dir: str, config: dict) -> list:
    """
    Convert a batch of images to standardized JPEG format.

    Parameters
    ----------
    image_paths : list
        List of image paths.
    output_dir : str
        Directory for converted images.
    config : dict
        Configuration parameters (quality, size limits).

    Returns
    -------
    list
        List of converted image paths.
    """