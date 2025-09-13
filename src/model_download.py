import os
import requests
import tarfile
from config_ import Config
from AppLogger import Logger
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential
from requests.exceptions import Timeout, HTTPError

def retry_if_transient_error(exception):
    """Retry for all network level errors"""
    return (
        isinstance(exception, (ConnectionError, Timeout)) or
        (isinstance(exception, HTTPError) and exception.response is not None and 500 <= exception.response.status_code < 600)
    )
    

@retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception(retry_if_transient_error)
)
def safe_get(url, stream = True):
    return requests.get(url=url, stream=stream)

def is_safe(member, target_dir):
    abs_target = os.path.abspath(target_dir)
    abs_member = os.path.abspath(os.path.join(target_dir, member.name))
    return abs_member.startswith(abs_target)

def download_model(logger: Logger, config: Config, model_name = 'faster_rcnn'):

    MODEL_DIR = config.get_model_save_folder()
    model_data = config.get_model_data()
    MODEL_URL = model_data[model_name]['url']

    #MODEL_DIR, MODEL_URL = config.get_model_dwld()
    print(MODEL_DIR)
    os.makedirs(MODEL_DIR, exist_ok=True)
    MODEL_PATH = os.path.join(MODEL_DIR, "model.tar.gz")
    logger.log_status(f"Downloading model from {MODEL_URL} to {MODEL_PATH}...")
    
    response = safe_get(MODEL_URL, stream=True)
    
    if response.status_code == 200:
        tmp_path = MODEL_PATH + ".part"
        with open(tmp_path, "wb") as f:
            for chunk in response.iter_content(1024):
                if chunk:
                    f.write(chunk)
        os.replace(tmp_path, MODEL_PATH)
        logger.log_status("Download complete.")
    else:
        logger.log_exception(f"Failed to download. HTTP Status Code: {response.status_code}")
        response.raise_for_status()
        return

    # Extract model
    logger.log_status("Extracting model...")
    try:
        with tarfile.open(MODEL_PATH, "r:gz") as tar:
            safe_members = [m for m in tar.getmembers() if is_safe(m, MODEL_DIR)]
            tar.extractall(MODEL_DIR, members=safe_members)
        logger.log_status(f"Model extracted successfully to {os.path.abspath('.') + str(MODEL_DIR)}.")
    except Exception as e:
        logger.log_exception(f"An exception occured while extracting model: {e}")
