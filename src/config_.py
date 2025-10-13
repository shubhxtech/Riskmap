import configparser
from pathlib import Path
from AppLogger import Logger
from utils import current_w_folder, resolve_path
import sys, os, json


class Config:
    def __init__(self, logger : Logger, path=None):
        """
        Initializes the config object by reading the configuration file and ensuring its validity.
        Sets up a Logger for logging configuration issues.
        """
        if path is None:
            base_dir = Path(__file__).parent  # directory of config_.py
            self.config_file = (base_dir / "config_.ini").resolve()
            logger.log_status(f'used the path is none path. {self.config_file.resolve()}')
        else:
            self.config_file = Path(path)
        self.logger = logger
        self.logger.log_status(f"using config file at {self.config_file}")

        self.parser = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())

        # self.read_config()
        # Read the config file if it exists or create a default one if missing
        if not self.config_file.exists():
            self.logger.log_status(f"Configuration file {self.config_file} not found, creating default.", "WARNING")
            self.create_default_config()
        else:
            self.read_config()
        
# --- Root functions ---

    def create_default_config(self):
        """
        Creates a default configuration file with necessary sections and settings.
        Matches the structure and content of the uploaded config_.ini file.
        """
        try:
            self.parser["General"] = {
                "name_of_main_app": "ML Assist",
                "version": "1.0.0",
                "allowed_file_types": ".jpg,.png,.jpeg",
                "size_of_images": "2048,1024",
                "blur_region_height": "250",
                "name_of_api_window": "Download",
                "name_of_crop_window": "Process Files",
                "name_of_BUILDING_DETECTION": "Building Detection",
                "name_of_duplicates_window": "Remove Duplicates",
                "name_of_classification": "Classify",
                "name_of_training_window": "Train Model",
                "region": "aizawl",
                "config_file": "config_.ini"
            }

            self.parser["Paths"] = {
                "current_folder": "data",
                "log_file": "app_logs.json",
                "file_path": "data\\Raw",
                "geoscatter_path": "classified_data.txt",
                "map_index_path": "index_map.json",
                "classification_save_folder_path": "data\\Classified",
                "metadata_database_path": "scan_data.db",
                "secrets_path": "secrets.env"
            }

            self.parser["Download"] = {
                "face_size": "1024",
                "coarse_spacing": "0.003",
                "fine_spacing": "0.001",
                "file_name": "map.html"
            }

            self.parser["BUILDING_DETECTION"] = {
                "model_path": "models\\faster_rcnn",
                "model_url": "https://tfhub.dev/google/faster_rcnn/openimages_v4/inception_resnet_v2/1?tf-hub-format=compressed, Dummy",
                "target_classes": "House,Building,Skyscraper,Tower",
                "model_data_path": "model_data.json",
                "input_dir": "data\\Processed_files",
                "output_dir": "data\\detected",
                "threshold": "0.3",
                "expand_factor": "0.1",
                "min_dim": "200"
            }

            self.parser["Duplicates"] = {
                "source_folder": "data\\detected",
                "destination_parent_folder": "data\\Duplicates",
                "image_extensions": ".jpg,.jpeg,.png,.bmp,.tiff",
                "batch_size": "200",
                "img_size": "600,600",
                "base_path": "data\\duplicates",
                "metadata_file_name": "metadata.json"
            }

            self.parser["Classification"] = {
                "parent_folder": "data\\duplicates",
                "output_folder": "data\\classified",
                "model_path": "models\\classifier",
                "class_names": "AD_H1,AD_H2,MR_H1 flat roof,MR_H1 gable roof,MR_H2 flat roof,MR_H2 gable roof,MR_H3,Metal_H1,Non_Building,RCC_H1 flat roof,RCC_H1 gable roof,RCC_H2 flat roof,RCC_H2 gable roof,RCC_H3 flat roof,RCC_H3 gable roof,RCC_H4 flat roof,RCC_H4 gable roof,RCC_H5,RCC_H6,RCC_OS_H1,RCC_OS_H2,RCC_OS_H3,RCC_OS_H4,Timber",
                "classif_folder_name": "classified",
                "confidence_threshold": "0.5",
                "model_ext": ".pth",
                "available_models": "best_model,data_model",
                "image_extensions": ".jpg,.jpeg,.png,.bmp,.tiff",
                "output_file": "geoscatter_plot.png"
            }

            self.parser["Processed"] = {
                "input_folder": "data\\Raw",
                "save_folder": "data\\Processed"
            }

            self.parser["Model_Training"] = {
                "data_dir": "data\\Classified",
                "epochs": "10",
                "learning_rate": "0.001",
                "base_model": "ResNet50",
                "custom_layers": "512",
                "val_split": "0.2",
                "seed": "123",
                "image_height": "180",
                "image_width": "180",
                "batch_size": "32",
                "model_names": "ResNet50, MobileNetV2, InceptionV3",
                "freeze_original_layers": "True",
                "extra_layer_type": "Dense",
                "optimizer": "Adam",  # corrected from optimizer_type
                "loss_type": "sparse_categorical_crossentropy",
                "model_name": "custom_resnet_model",
                "plot_name": "training_plot"
            }

            with open(self.config_file, "w") as configfile:
                self.parser.write(configfile)
            self.logger.log_status(f"Default config file created at {self.config_file}", "INFO")
        
        except Exception as e:
            self.logger.log_exception(e)

    def save_config(self, configfile = None):
        """
        Save the current configuration to the config file.
        """
        configfile = self.config_file if configfile is None else configfile
        try:
            with open(configfile, "w") as file:
                self.parser.write(file)
            self.logger.log_status(f"Configuration saved to {configfile}", "INFO")
        except Exception as e:
            self.logger.log_exception(e)

    def read_config(self):
        """
        Reads the configuration file.
        """
        try:
            self.parser.read(self.config_file)
            self.logger.log_status(f"Config File Read Successfully")
            return self.parser
        except Exception as e:
            self.logger.log_exception(e)

    def get(self, section, option, fallback=None):
        """
        Get the value of a configuration option, with a fallback value if the option is missing.
        
        Args:
            section (str): The section name in the config file.
            option (str): The option name within the section.
            fallback: The default value to return if the option doesn't exist.
        
        Returns:
            str: The value of the option or the fallback value.
        """
        try:
            return self.parser.get(section, option)
        except configparser.NoOptionError:
            self.logger.log_status(f"Option {option} in section {section} not found. Using fallback value.", "WARNING")
            return fallback
    
    def get_all(self, section):
        """
        Get the values of all values in a configuration section.
        
        Args:
            section (str): The section name in the config file.
        
        Returns:
            dict[name:value]: A dict storing name-value pairs of items in the section
        """
        try:
            return dict(self.parser.items(section))
        except configparser.NoSectionError:
            self.logger.log_exception(f"Section {section} not found.")

    def set(self, section, option, value):
        """
        Set the value of a configuration option.
        
        Args:
            section (str): The section name in the config file.
            option (str): The option name within the section.
            value (str): The new value to set.
        """
        try:
            if not self.parser.has_section(section):
                self.parser.add_section(section)
            self.parser.set(section, option, value)
            self.save_config()
            self.logger.log_status(f'Set {section}: {option} to {value}')
        except Exception as e:
            self.logger.log_exception(e)


# --- sub functions ---

    def get_log_file(self):
        """
        Get the log file path from the config.
        """
        return self.get(section="Paths", option="Log_file", fallback=resolve_path("app_logs.json"))

    # --- all functions to get entire sections ---

    def get_general_data(self):
        """
        Get all general Settings
        """
        section = "General"
        return self.get_all(section=section)

    def get_paths_data(self):
        """
        Get all data of Paths
        """
        section = "Paths"
        return self.get_all(section=section)
    
    def get_download_data(self):
        """
        Get all download data
        """
        section = 'Download'
        return self.get_all(section = section)

    def get_BUILDING_DETECTION_data(self) -> dict:
        """
        Get the current Building Detection settings
        """
        section_name = "BUILDING_DETECTION"
        return self.get_all(section=section_name)

    def get_duplicates_data(self):
        """
        Gets all data required by the duplicate seperation script
        """
        section = "Duplicates"
        return self.get_all(section=section)
    
    def get_classification_data(self):
        """
        Gets the configuration for the model as well as other settings for the map classification
        """
        section = 'Classification'
        return self.get_all(section=section)
  
    def get_processed_data(self):
        """
        Get all Processing files data
        """
        section = "Processed"
        return self.get_all(section=section)

    def get_model_training_data(self):
        """
        Get all the data for training the model
        """
        section = "Model_Training"
        return self.get_all(section=section)

    def get_BUILDING_DETECTION_recommended(self) -> dict[str, str]:
        """
        Returns a dictionary of recommended/default hyperparameter values
        for BUILDING_DETECTION. Format: {option_name: string_value}.
        """
        return {
            "model_path":    r"C:\Users\lenovo\Desktop\2_Intern_6mth\pyQT\models\faster_rcnn",
            "target_classes":"House,Building,Skyscraper,Tower",
            "input_dir":     r"C:\Users\lenovo\Desktop\2_Intern_6mth\pyQT\data\Processed_files",
            "output_dir":    r"C:\Users\lenovo\Desktop\2_Intern_6mth\pyQT\data\detected",
            "threshold":     "0.3",
            "expand_factor": "0.1",
            "min_dim":       "200"
        }

    # ------------------------------------------------------------------
    # 2. Helper to set an individual BUILDING_DETECTION option and save.
    # ------------------------------------------------------------------
    def set_BUILDING_DETECTION_param(self, option: str, value: str) -> bool:
        """
        Sets one hyperparameter under section “BUILDING_DETECTION” to value (as string),
        writes it immediately to the .ini, and logs the change. Returns True on success.
        """
        section = "BUILDING_DETECTION"
        try:
            # If section doesn’t exist, add it automatically.
            if not self.parser.has_section(section):
                self.parser.add_section(section)
            self.parser.set(section, option, value)
            self.save_config()  # writes to file
            self.logger.log_status(f"BUILDING_DETECTION => Set {option} = {value}", "INFO")
            return True
        except Exception as e:
            self.logger.log_exception(f"Failed to set BUILDING_DETECTION {option}: {e}")
            return False

    # ------------------------------------------------------------------
    # 3. Convenience getters for individual hyperparameters (typed).
    #    You can call these directly from the UI to pre‐populate fields.
    # ------------------------------------------------------------------
    def get_bd_model_path(self) -> Path:
        return Path(resolve_path(self.get("BUILDING_DETECTION", "model_path", fallback="")))

    def get_bd_target_classes(self) -> list[str]:
        raw = self.get("BUILDING_DETECTION", "target_classes",
                       fallback="House,Building,Skyscraper,Tower")
        # Split and strip whitespace:
        return [cls.strip() for cls in raw.split(",") if cls.strip()]

    def get_bd_input_dir(self) -> Path:
        return Path(resolve_path(self.get("BUILDING_DETECTION", "input_dir", fallback='')))

    def get_bd_output_dir(self) -> Path:
        return Path(resolve_path(self.get("BUILDING_DETECTION", "output_dir", fallback="detected")))

    def get_bd_threshold(self) -> float:
        return float(self.get("BUILDING_DETECTION", "threshold", fallback="0.3"))

    def get_bd_expand_factor(self) -> float:
        return float(self.get("BUILDING_DETECTION", "expand_factor", fallback="0.1"))

    def get_bd_min_dim(self) -> int:
        return int(self.get("BUILDING_DETECTION", "min_dim", fallback="200"))



    # -- others ---

    def get_map_index_path(self) -> Path:
        """
        Get the path where the map_index will be saved
        """
        return Path(resolve_path(self.get_paths_data()['map_index_path']))

    def get_database_path(self) -> Path:
        """
        Get the path to the SQLite Database that stores all coordinates and panaroma IDs
        """
        return Path(resolve_path(self.get_paths_data()['metadata_database_path']))

    def get_current_working_folder(self) -> Path:
        """
        Get the current folder path from the config.
        """
        return Path(resolve_path(self.get(section="Paths", option="Current_folder", fallback='')))
    
    def get_allowed_file_types(self):
        """
        Get the Allowed File Types from the General Config
        """
        return self.get(section='General', option='allowed_file_types', fallback='.jpg,.png,.jpeg')
    
    def get_image_size(self):
        """
        Get the size of images. I believe it should be set by the downloader and should have something to prepare for different image sizes
        """
        section_name = "General"
        return self.get(section=section_name, option="size_of_images", fallback= (2048,1024))
    
    def get_blur_size(self):
        """
        Blur size as defined in the config.ini file
        """
        return int(self.get("General", "blur_region_height", fallback=1000))

    def get_model_save_folder(self):
        """
        Gets the value of model folder
        Returns: model_path
        """
        section_name = "BUILDING_DETECTION"
        return Path(resolve_path(self.get(section=section_name, option="model_path")))

    def get_target_classes(self):
        """
        Returns the list of classes targeted in building classification
        """
        section = "BUILDING_DETECTION"
        option = "target_classes"
        classes = self.get(section=section, option=option, fallback=["House", "Building", "Skyscraper", "Tower"])
        if type(classes) == str :
            classes = classes.strip()
            classes = classes.split(',')
        return classes

    def get_foldr_names_classif(self):
        """
        Get the names of all 25 classes to be classified into
        """
        section = 'Classification'
        return self.get(section, 'class_names', fallback='AD_H1,AD_H2,MR_H1 flat roof,MR_H1 gable roof,MR_H2 flat roof,MR_H2 gable roof,MR_H3,Metal_H1,Non_Building,RCC_H1 flat roof,RCC_H1 gable roof,RCC_H2 flat roof,RCC_H2 gable roof,RCC_H3 flat roof,RCC_H3 gable roof,RCC_H4 flat roof,RCC_H4 gable roof,RCC_H5,RCC_H6,RCC_OS_H1,RCC_OS_H2,RCC_OS_H3,RCC_OS_H4,Timber')

    def get_classif_folder_name(self):
        """
        Get the name of the folder in which we will create the classified folders in 
        From config.ini
        """
        section = 'Classification'
        return self.get(section=section, option = 'classif_folder_name', fallback='classified')

    def get_img_ext(self):
        """
        Get allowed image extensions for classification
        """
        section = 'Classification'
        option = 'image_extensions'
        return self.get(section=section, option=option, fallback= '.jpg,.jpeg,.png,.bmp,.tiff')
    
    def get_current_input_folder_class(self):
        """
        Gets the folder path of the duplicates input folder
        """
        return Path(resolve_path(self.get_duplicates_data()["source_folder"]))

    def get_current_input_folder_process(self):
        """
        Gets the folder path of the processor input folder
        """
        return Path(resolve_path(self.get(section="Processed", option="input_folder", fallback="data\\Raw")))

    def get_model_file_path(self):
        """
        Get the file where the data for models is stored 
        Return:
            dict{str:{str:Path, str:[str]}}
        """
        dir = Path(resolve_path("model_data.json"))
        if not dir.exists():
            self.logger.log_status('model_data.json not found. Creating...')
            data = {
            'faster_rcnn': {'url': 'https://tfhub.dev/google/faster_rcnn/openimages_v4/inception_resnet_v2/1?tf-hub-format=compressed', 'classes': ['House','Building','Skyscraper','Tower']},
            'data': {'url':'data', 'classes': ['A', 'B', 'C']}
            }

            try:
                with open(dir, 'w') as f:
                    json.dump(data, f)
            except Exception as e:
                self.logger.log_exception(f'An error occured while creating file. {e}')

        return dir

    def get_model_data(self):
        """
        Parses the .json file that stored the model data and returns it
        """
        dir = resolve_path(self.get_model_file_path())
        with open(dir, 'r') as f:
            data = json.load(f)

        return data

    def get_dwnd_file_path(self) -> Path:
        """
        Gets the folder in which we save images by default
        """
        section = "Paths"
        option = "file_path"
        return Path(resolve_path(self.get(section=section, option=option, fallback="data\\Raw")))

# --- set ---

    def set_model_data(self, new_data: dict[str, tuple[str]]):
        file_name, data = self.get_model_file_path(), self.get_model_data()
        try:
            data.update(new_data)
            with open(file_name, 'w') as f:
                json.dump(data, f)
            return True
        except Exception as e:
            self.logger.log_exception(f'An exception occured while setting new model data. {e}')

    def set_save_folder(self, folder):
        section_name = "Paths"
        self.set(section_name, "Current_folder", folder)
        self.logger.log_status(f"Current save folder changed to {folder}", "INFO")
        self.save_config() # Add exception handing here
        return True

    def set_save_folder_process(self, folder):
        """
        Sets output folder for process module
        """
        section_name = "Processed"
        self.set(section=section_name, option="save_folder", value=folder)

    def set_input_folder_process(self, folder):
        """
        Sets the input folder that feeds to the process files module
        """
        section_name = "Processed"
        self.set(section=section_name, option="input_folder", value=folder)

    def set_input_folder_detection(self, folder):
        """
        Sets the input folder that feeds to the BuildingDetection module
        """
        section_name = "BUILDING_DETECTION"
        self.set(section=section_name, option="input_dir", value=folder)

    def set_size_of_images(self, height: int, width:int):
        section_name = "General"
        self.set(section=section_name, option="size_of_images", value=f'{width},{height}')

    def set_blur_size(self, blur_height: str):
        """
        Change blur size
        """
        section_name = "General"
        self.set(section=section_name, option="blur_region_height", value=blur_height)

    def set_model_path(self, model_path):
        """
        Set the value of model_path in building detection
        """
        section_name = "BUILDING_DETECTION"
        self.set(section=section_name, option="model_path", value=model_path)

    def set_output_detection_path(self, output_path):
        """
        Set the value of output_dir in building detection
        """
        section_name = "BUILDING_DETECTION"
        self.set(section=section_name, option="output_dir", value=output_path)

    def set_classif_output_foldr(self, output_folder:str):
        """
        Set the output folder option in the Classification section 
        """
        section_name = "Classification"
        self.set(section=section_name, option="output_folder", value=output_folder)
    
    def set_classif_input_foldr(self, input_folder:str):
        """
        Set the input folder option in the Classification section 
        """
        section_name = "Classification"
        self.set(section=section_name, option="parent_folder", value=input_folder)

    def set_duplicates_destination_folder(self, folder: str):
        """
        Set the output folder of duplicates module processing
        """
        section_name="Duplicates"
        self.set(section=section_name, option="destination_parent_folder", value=folder)

    def set_duplicates_source_folder(self, folder: str):
        """
        Set the output folder of duplicates module processing
        """
        section_name="Duplicates"
        self.set(section=section_name, option="source_folder", value=folder)

    def get_duplicates_destination_folder(self):
        """
        Get the destination parent folder option of the duplicates  module
        """
        section_name = "Duplicates"
        return Path(resolve_path(self.get(section=section_name, option="destination_parent_folder")))

    def get_duplicates_source_folder(self):
        """
        Get the source folder option of the duplicates module
        """
        section_name = "Duplicates"
        return Path(resolve_path(self.get(section=section_name, option="source_folder")))

    def get_duplicates_model_folder(self):
        """
        Get the model folder for duplicates module
        """
        section = "Duplicates"
        return Path(resolve_path(self.get(section=section, option="model_folder")))

if __name__ == "__main__":
    Config(Logger(__name__))