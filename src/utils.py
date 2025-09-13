from pathlib import Path
import shutil
import os, cv2, sys

def resolve_path(rel_path: str) -> str:
    """
    Resolve relative paths in both source and PyInstaller bundled executables.
    """
    # If absolute path, return directly
    if Path(rel_path).is_absolute():
        return rel_path

    # Handle PyInstaller _MEIPASS
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.abspath(os.path.join(base_path, rel_path))


def current_w_folder() -> Path:
    """
    Returns the current working folder
    """
    return resolve_path('')

def get_downloads_folder():
    """
    Gets the path to the user's default downloads folder.
    
    Returns:
        Path: Path to the Downloads folder.
    """
    # Configure logger for utility functions
    import AppLogger
    logger = AppLogger.Logger(__name__)
    try:
        downloads_path = Path.home() / "Downloads"
        print(downloads_path)
        logger.log_status(f"Downloads folder path resolved: {downloads_path}","DEBUG")
        return downloads_path
    except Exception as e:
        logger.log_exception(f"Error resolving Downloads folder path: {e}")
        raise

def validate_path(path): # I don't think this has a need but whatever
    """
    Validates whether the provided path exists and is accessible.
    
    Args:
        path (Path or str): Path to validate.
    
    Returns:
        bool: True if the path exists and is accessible, False otherwise.
    """
    # Configure logger for utility functions
    import AppLogger
    logger = AppLogger.Logger(__name__)
    path = Path(path)
    if path.exists():
        logger.log_status(f"Validated path exists: {path}")
        return True
    else:
        logger.log_status(f"Path does not exist: {path}",  "WARNING")
        return False

def ensure_directory_exists(directory):
    """
    Ensures the given directory exists. Creates it if it doesn't.
    
    Args:
        directory (Path or str): The directory to check or create.
    
    Returns:
        Path: The validated or newly created directory path.
    """
    # Configure logger for utility functions
    import AppLogger
    logger = AppLogger.Logger(__name__)
    directory = Path(directory)
    if not directory.exists():
        try:
            directory.mkdir(parents=True, exist_ok=True)
            logger.log_status(f"Directory created: {directory}")
        except Exception as e:
            logger.log_exception(f"Error creating directory: {directory} - {e}")
            raise
    else:
        logger.log_status(f"Directory already exists: {directory}")
    return directory

def apply_config(obj):
    """
    Applies row and column grid configure with index=0, and weight =1 
    """
    obj.grid_rowconfigure(0, weight=1)
    obj.grid_columnconfigure(0, weight=1)

def run_cleanup(folder: Path) -> bool:
    """
    Deletes the folder and all its subdirectories
    """
    # Configure logger for utility functions
    import AppLogger
    logger = AppLogger.Logger(__name__)
    try: 
        shutil.rmtree(folder)
        logger.log_status(f"Deleted folder {folder}")
        return True
    except Exception as e:
        logger.log_exception(f'Failed to delete folder {folder}. Exception : {e}')
        return False
    
def cleanup_process(check_value, folder: Path):
    if check_value:
        return run_cleanup(folder)

def save_image(image, path, logger=None):
    try:
        cv2.imwrite(str(path), image)
        logger.log_status(f"Saved image to {path}")
        return True, path
    except Exception as e:
        if logger:
            logger.log_exception(e)
        return False, path