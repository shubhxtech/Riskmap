import os
import sys
from typing import Union
StrOrBytesPath = Union[str, bytes, os.PathLike]

import tensorflow as tf
import matplotlib.pyplot as plt
from tensorflow import keras
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Flatten, Dropout
from tensorflow.keras.optimizers import Adam
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QComboBox, QProgressBar, QMessageBox, QGridLayout
)
from PyQt5.QtCore import QObject, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap

from pathlib import Path
from config_ import Config
from AppLogger import Logger
from utils import resolve_path


class Trainer(QWidget):
    def __init__(self, config: Config, logger: Logger):
        super().__init__()
        self.config = config
        self.logger = logger
        try:            
            data = self.config.get_model_training_data()
            self.data_dir = Path(resolve_path(data["data_dir"]))
            self.epochs = int(data["epochs"])
            self.learning_rate = float(data["learning_rate"])
            self.base_model = data["base_model"]
            self.custom_layers = int(data["custom_layers"])
            self.val_split = float(data["val_split"])
            self.seed = int(data["seed"])
            self.image_height = int(data["image_height"])
            self.image_width = int(data["image_width"])
            self.batch_size = int(data["batch_size"])
            self.model_names = data["model_names"].split(',')
            self.freeze_original_layers = bool(data["freeze_original_layers"])
            self.optimizer = data["optimizer"]
            self.loss_type = data["loss_type"]
            self.model_name = data["model_name"]
            self.plot_name = data["plot_name"]
            self.init_ui()
        except Exception as e:
            self.logger.log_exception(f'An error occured while __init__ of Trainer. {e}')

    def init_ui(self):
        try:
            self.setWindowTitle("ResNet Model Trainer")
            layout = QGridLayout()

            self.path_label = QLabel("Dataset Directory:")
            self.path_input = QLineEdit(f'{self.data_dir}')
            self.browse_btn = QPushButton("Browse")
            self.browse_btn.clicked.connect(self.browse_folder)

            self.epochs_label = QLabel("Epochs:")
            self.epochs_input = QLineEdit(f'{self.epochs}')

            self.lr_label = QLabel("Learning Rate:")
            self.lr_input = QLineEdit(f'{self.learning_rate}')

            self.model_selector = QComboBox()
            self.model_selector.addItems(["ResNet50", "MobileNetV2", "InceptionV3"])

            self.layer_config_label = QLabel("Custom Layers (comma-separated sizes):")
            self.layer_config_input = QLineEdit(f'{self.custom_layers}')

            self.val_split_label = QLabel("Validation split:")
            self.val_split_input = QLineEdit(f'{self.val_split}')

            # Seed
            self.seed_label = QLabel("Seed:")
            self.seed_input = QLineEdit(f'{self.seed}')

            # Image Height and Width
            self.img_height_label = QLabel("Image Height:")
            self.img_height_input = QLineEdit(f'{self.image_height}')
            self.img_width_label = QLabel("Image Width:")
            self.img_width_input = QLineEdit(f'{self.image_width}')

            # Batch Size
            self.batch_size_label = QLabel("Batch Size:")
            self.batch_size_input = QLineEdit(f'{self.batch_size}')

            # Freeze Base Model Layers (Boolean - use dropdown for clarity)
            self.freeze_label = QLabel("Freeze Base Model Layers:")
            self.freeze_input = QComboBox()
            self.freeze_input.addItems(["True", "False"])
            self.freeze_input.setCurrentText(f'{self.freeze_original_layers}')

            # Optimizer Type
            self.optimizer_label = QLabel("Optimizer:")
            self.optimizer_selector = QComboBox() # Could also use QComboBox
            # self.optimizer_selector.addItems([
            #     "SGD",
            #     "RMSprop",
            #     "Adagrad",
            #     "Adadelta",
            #     "Adam",      
            #     "Adamax",
            #     "Nadam",
            #     "Ftrl"
            # ])
            self.optimizer_selector.setCurrentText(f'{self.optimizer}')
            self.optimizer_selector.setEnabled(False)

            # Loss Type
            self.loss_label = QLabel("Loss Function:")
            self.loss_selector = QComboBox()
            self.loss_selector.addItems([
                "categorical_crossentropy",
                "sparse_categorical_crossentropy",
                "binary_crossentropy",
                "mean_squared_error",
                "mean_absolute_error",
                "hinge",
                "kullback_leibler_divergence",
                "poisson",
                "cosine_similarity"
            ])
            self.loss_selector.setCurrentText(f'{self.loss_type}')

            # Model Name (Custom name for saving)
            self.model_name_label = QLabel("Model Name:")
            self.model_name_input = QLineEdit(f'{self.model_name}')

            # Plot Filename
            self.plot_name_label = QLabel("Plot Filename:")
            self.plot_name_input = QLineEdit(f'{self.plot_name}')

            self.start_btn = QPushButton("Start Training")
            self.start_btn.clicked.connect(self.start_training)

            self.progress = QProgressBar()

            layout.addWidget(self.path_label, 0, 0)
            layout.addWidget(self.path_input, 0, 1)
            layout.addWidget(self.browse_btn, 0, 2)

            layout.addWidget(self.epochs_label, 1, 0)
            layout.addWidget(self.epochs_input, 1, 1)

            layout.addWidget(self.lr_label, 2, 0)
            layout.addWidget(self.lr_input, 2, 1)

            layout.addWidget(QLabel("Base Model:"), 3, 0)
            layout.addWidget(self.model_selector, 3, 1)

            layout.addWidget(self.layer_config_label, 4, 0)
            layout.addWidget(self.layer_config_input, 4, 1)

            layout.addWidget(self.val_split_label, 5, 0)
            layout.addWidget(self.val_split_input, 5, 1)

            layout.addWidget(self.seed_label, 6, 0)
            layout.addWidget(self.seed_input, 6, 1)

            layout.addWidget(self.img_height_label, 7, 0)
            layout.addWidget(self.img_height_input, 7, 1)

            layout.addWidget(self.img_width_label, 8, 0)
            layout.addWidget(self.img_width_input, 8, 1)

            layout.addWidget(self.batch_size_label, 9, 0)
            layout.addWidget(self.batch_size_input, 9, 1)

            layout.addWidget(self.freeze_label, 10, 0)
            layout.addWidget(self.freeze_input, 10, 1)

            layout.addWidget(self.optimizer_label, 11, 0)
            layout.addWidget(self.optimizer_selector, 11, 1)

            layout.addWidget(self.loss_label, 12, 0)
            layout.addWidget(self.loss_selector, 12, 1)

            layout.addWidget(self.model_name_label, 13, 0)
            layout.addWidget(self.model_name_input, 13, 1)

            layout.addWidget(self.plot_name_label, 14, 0)
            layout.addWidget(self.plot_name_input, 14, 1)

            layout.addWidget(self.start_btn, 15, 0, 1, 2)
            layout.addWidget(self.progress, 16, 0, 1, 2)


            self.setLayout(layout)
        except Exception as e:
            self.logger.log_exception(f'An error occured while setting up or executing UI. {e}')

    def browse_folder(self):
        try:
            folder = QFileDialog.getExistingDirectory(self, "Select Dataset Folder")
            if folder:
                self.path_input.setText(folder)
        except Exception as e:
            self.logger.log_exception(f'An error occured while browsing for input folder. {e}')

    def save_config(self):
        try:
            config = self.config.read_config()
            config["Model_Training"] = {
                "data_dir": self.path_input.text(),
                "epochs": self.epochs_input.text(),
                "learning_rate": self.lr_input.text(),
                "base_model": self.model_selector.currentText(),
                "custom_layers": self.layer_config_input.text(),
                "val_split": self.val_split_input.text(),
                "seed": self.seed_input.text(),
                "img_height": self.img_height_input.text(),
                "img_width": self.img_width_input.text(),
                "batch_size": self.batch_size_input.text(),
                "freeze_original_layers": self.freeze_input.currentText(),
                "optimizer": self.optimizer_selector.currentText(),
                "loss": self.loss_selector.currentText(),
                "model_name": self.model_name_input.text(),
                "plot_name": self.plot_name_input.text()
            }
            with open(self.config.config_file, 'w') as f:
                config.write(f)
        except Exception as e:
            self.logger.log_exception(f'An error occured while saving to config from Training. {e}')

    def start_training(self):
        try:
            self.thread = QThread()
            self.worker = TrainWorker(self)

            self.worker.moveToThread(self.thread)
            self.thread.started.connect(self.worker.run)
            self.worker.progress_signal.connect(self.progress.setValue)
            self.worker.message_signal.connect(lambda msg: QMessageBox.information(self, "Success", msg))
            self.worker.error_signal.connect(lambda err: self.logger.log_exception(f"Training error: {err}"))
            self.worker.finished_signal.connect(self.thread.quit)
            self.worker.finished_signal.connect(self.worker.deleteLater)
            self.worker.plot_ready_signal.connect(self.open_plot_image)
            self.thread.finished.connect(self.thread.deleteLater)
            
            self.thread.start()
        except Exception as e:
            self.logger.log_exception(f'An error occurred while starting the training thread. {e}')
    
    def open_plot_image(self, image_path: StrOrBytesPath):
            try:
                window = QWidget()
                window.setWindowTitle("Training Plot")
                layout = QVBoxLayout()

                label = QLabel()
                pixmap = QPixmap(image_path)
                label.setPixmap(pixmap)
                label.setScaledContents(True)  

                layout.addWidget(label)
                window.setLayout(layout)
                window.resize(pixmap.width(), pixmap.height())

                self.plot_window = window

                window.show()
                
            except Exception as e:
                self.logger.log_exception(f'An error occured while open plotted metrics. {e}')

class TrainWorker(QObject):
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)
    message_signal = pyqtSignal(str)
    plot_ready_signal = pyqtSignal(str)

    def __init__(self, trainer):
        super().__init__()
        self.trainer = trainer

    def run(self):
        try:
            self.trainer.logger.log_status("Training started.")
            self.data_dir = Path(self.trainer.path_input.text())
            self.epochs = int(self.trainer.epochs_input.text())
            self.lr = float(self.trainer.lr_input.text())
            self.base_model_name = self.trainer.model_selector.currentText()
            self.custom_layers = [int(size.strip()) for size in self.trainer.layer_config_input.text().split(',') if size.strip().isdigit()]
            self.val_split = float(self.trainer.val_split_input.text())
            self.seed = int(self.trainer.seed_input.text())
            self.img_height = int(self.trainer.img_height_input.text())
            self.img_width = int(self.trainer.img_width_input.text())
            self.batch_size = int(self.trainer.batch_size_input.text())
            self.freeze_original_layers = bool(self.trainer.freeze_input.currentText().lower())
            self.optimizer = self.trainer.optimizer_selector.currentText()
            self.loss = self.trainer.loss_selector.currentText()
            self.model_name = self.trainer.model_name_input.text() 
            self.plot_name = self.trainer.plot_name_input.text()
            self.trainer.save_config()
            self.progress_signal.emit(5)
            self.trainer.logger.log_status("Configuration and hyperparameters saved.")

            print([i for i in self.data_dir.glob('*.jpg')])

            train_ds = tf.keras.preprocessing.image_dataset_from_directory(
                self.data_dir,
                validation_split=self.val_split,
                subset="training",
                seed=123,
                image_size=(self.img_height, self.img_width),
                batch_size=self.batch_size)

            val_ds = tf.keras.preprocessing.image_dataset_from_directory(
                self.data_dir,
                validation_split=self.val_split,
                subset="validation",
                seed=123,
                image_size=(self.img_height, self.img_width),
                batch_size=self.batch_size)

            num_classes = len(train_ds.class_names)
            self.trainer.logger.log_status(f"Detected {num_classes} classes.")
            self.progress_signal.emit(20)

            input_shape = (self.img_height, self.img_width, 3)
            if self.base_model_name == "ResNet50":
                base_model = keras.applications.ResNet50(include_top=False, weights="imagenet", input_shape=input_shape, pooling='avg')
            elif self.base_model_name == "MobileNetV2":
                base_model = keras.applications.MobileNetV2(include_top=False, weights="imagenet", input_shape=input_shape, pooling='avg')
            elif self.base_model_name == "InceptionV3":
                base_model = keras.applications.InceptionV3(include_top=False, weights="imagenet", input_shape=input_shape, pooling='avg')

            if self.freeze_original_layers:
                for layer in base_model.layers:
                    layer.trainable = False

            model = Sequential()
            model.add(base_model)
            model.add(Flatten())
            for size in self.custom_layers:
                model.add(Dense(size, activation='relu'))
                model.add(Dropout(0.5))
            model.add(Dense(num_classes, activation='softmax'))

            model.compile(optimizer=Adam(learning_rate=self.lr),
                          loss=self.loss,
                          metrics=['accuracy'])

            self.progress_signal.emit(40)
            self.trainer.logger.log_status("Model architecture built and compiled.")

            history = model.fit(train_ds, validation_data=val_ds, epochs=self.epochs)

            model.save(self.model_name)
            self.trainer.logger.log_status(f"Model saved as {self.model_name}.")

            self.progress_signal.emit(100)
            self.message_signal.emit(f"Model training complete! Saved as {self.model_name}")

            plt.figure(figsize=(10, 5))
            plt.subplot(1, 2, 1)
            plt.plot(history.history['accuracy'], label='Train Accuracy')
            plt.plot(history.history['val_accuracy'], label='Validation Accuracy')
            plt.title('Model Accuracy')
            plt.xlabel('Epoch')
            plt.ylabel('Accuracy')
            plt.legend()

            plt.subplot(1, 2, 2)
            plt.plot(history.history['loss'], label='Train Loss')
            plt.plot(history.history['val_loss'], label='Validation Loss')
            plt.title('Model Loss')
            plt.xlabel('Epoch')
            plt.ylabel('Loss')
            plt.legend()
            plt.tight_layout()
            plt.savefig(f'{self.plot_name}.png')
            self.plot_ready_signal.emit(self.plot_name)

            self.trainer.logger.log_status("Training plots saved and displayed.")
            self.finished_signal.emit()

        except Exception as e:
            self.error_signal.emit(str(e))


def main():
    app = QApplication(sys.argv)
    # Dummy config and logger instances should be passed here if running independently
    # Example: Trainer(Config(), Logger())
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
