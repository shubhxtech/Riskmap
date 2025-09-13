import json
from pathlib import Path
from AppLogger import Logger
logger = Logger(__name__)
from typing import Optional
from config_ import Config
config = Config(logger)

def create_index(path: Optional[Path] = None):
    data = {

        'aizawl': {'north': 23.76,'east': 92.8, 'south': 23.65,'west': 92.65},
        'india' : {'north':37.1, 'east': 97.5, 'south': 6.5, 'west': 68.0}
    }

    path = path or config.get_map_index_path()

    try:
        with open(path, 'w') as f:
            json.dump(data, f)
        logger.log_status(f'Successfully created map_index at {path}')
    except Exception as e:
        logger.log_exception(f"Encountered an error while trying to create map index. : {e}")

if __name__=="__main__":
    create_index()