"""
workers/train_worker.py — Background QObject for model training.
Extracted from ``model_training.py``.

Runs in a QThread via ``moveToThread()`` pattern (not QThread subclass)
to keep the training loop off the UI thread.
"""

from pathlib import Path
from PyQt5.QtCore import QObject, pyqtSignal


class TrainWorker(QObject):
    """
    Reads hyperparameters from a Trainer widget, builds a Keras model,
    trains it, and emits progress/metrics signals.

    Signals
    -------
    progress_signal(int)
        Training progress percentage 0–100.
    finished_signal()
        Emitted when training completes (success or not).
    error_signal(str)
        Emitted with error message on failure.
    message_signal(str)
        Success message for the user.
    plot_ready_signal(str)
        Path to the saved training plot image.
    log_signal(str)
        Per-step log messages for the training console.
    epoch_end_signal(int, dict)
        ``(epoch_number, logs_dict)`` for real-time graph updates.
    """

    progress_signal   = pyqtSignal(int)
    finished_signal   = pyqtSignal()
    error_signal      = pyqtSignal(str)
    message_signal    = pyqtSignal(str)
    plot_ready_signal = pyqtSignal(str)
    log_signal        = pyqtSignal(str)
    epoch_end_signal  = pyqtSignal(int, dict)

    def __init__(self, trainer):
        super().__init__()
        self.trainer = trainer

    def log(self, message):
        """Helper to log to both file and UI."""
        self.trainer.logger.log_status(message)
        self.log_signal.emit(message)

    def run(self):
        try:
            # Lazy load TensorFlow when training starts
            self.trainer._ensure_tensorflow_loaded()

            self.log("Training started.")

            self.data_dir = Path(self.trainer.path_input.text())
            self.epochs = int(self.trainer.epochs_input.text())
            self.lr = float(self.trainer.lr_input.text())
            self.base_model_name = self.trainer.model_selector.currentText()
            # Parse custom layers
            try:
                self.custom_layers = [
                    int(size.strip())
                    for size in self.trainer.layer_config_input.text().split(',')
                    if size.strip().isdigit()
                ]
            except Exception:
                self.custom_layers = [256]  # Default fallback

            self.val_split = float(self.trainer.val_split_input.text())
            self.seed = int(self.trainer.seed_input.text())
            self.img_height = int(self.trainer.img_height_input.text())
            self.img_width = int(self.trainer.img_width_input.text())
            self.batch_size = int(self.trainer.batch_size_input.text())
            self.freeze_original_layers = bool(
                self.trainer.freeze_input.currentText().lower() == 'true'
            )
            self.optimizer = self.trainer.optimizer_selector.currentText()
            self.loss = self.trainer.loss_selector.currentText()
            self.model_name = self.trainer.model_name_input.text()
            self.plot_name = self.trainer.plot_name_input.text()

            self.trainer.save_config()
            self.progress_signal.emit(5)
            self.log("Configuration saved.")

            train_ds = self.trainer._tf.keras.preprocessing.image_dataset_from_directory(
                self.data_dir,
                validation_split=self.val_split,
                subset="training",
                seed=self.seed,
                image_size=(self.img_height, self.img_width),
                batch_size=self.batch_size,
            )

            val_ds = self.trainer._tf.keras.preprocessing.image_dataset_from_directory(
                self.data_dir,
                validation_split=self.val_split,
                subset="validation",
                seed=self.seed,
                image_size=(self.img_height, self.img_width),
                batch_size=self.batch_size,
            )

            num_classes = len(train_ds.class_names)
            self.log(f"Detected {num_classes} classes: {train_ds.class_names}")
            self.progress_signal.emit(20)

            input_shape = (self.img_height, self.img_width, 3)
            self.log(f"Building base model: {self.base_model_name}")

            if self.base_model_name == "ResNet50":
                base = self.trainer._keras.applications.ResNet50(
                    include_top=False, weights="imagenet",
                    input_shape=input_shape, pooling='avg',
                )
            elif self.base_model_name == "MobileNetV2":
                base = self.trainer._keras.applications.MobileNetV2(
                    include_top=False, weights="imagenet",
                    input_shape=input_shape, pooling='avg',
                )
            elif self.base_model_name == "InceptionV3":
                base = self.trainer._keras.applications.InceptionV3(
                    include_top=False, weights="imagenet",
                    input_shape=input_shape, pooling='avg',
                )
            else:
                base = self.trainer._keras.applications.ResNet50(
                    include_top=False, weights="imagenet",
                    input_shape=input_shape, pooling='avg',
                )

            if self.freeze_original_layers:
                base.trainable = False

            model = self.trainer.Sequential()
            model.add(base)
            model.add(self.trainer.Flatten())
            for size in self.custom_layers:
                model.add(self.trainer.Dense(size, activation='relu'))
                model.add(self.trainer.Dropout(0.5))
            model.add(self.trainer.Dense(num_classes, activation='softmax'))

            model.compile(
                optimizer=self.trainer.Adam(learning_rate=self.lr),
                loss=self.loss,
                metrics=['accuracy'],
            )

            self.progress_signal.emit(40)
            self.log("Model compiled.")

            # Custom callback for emitting epoch stats
            class LogCallback(self.trainer._keras.callbacks.Callback):
                def __init__(self, worker_self):
                    self.worker = worker_self

                def on_epoch_end(self, epoch, logs=None):
                    self.worker.epoch_end_signal.emit(epoch + 1, logs)
                    msg = (
                        f"Epoch {epoch+1}: "
                        f"loss={logs['loss']:.4f}, "
                        f"acc={logs['accuracy']:.4f}, "
                        f"val_loss={logs['val_loss']:.4f}, "
                        f"val_acc={logs['val_accuracy']:.4f}"
                    )
                    self.worker.log(msg)

            history = model.fit(
                train_ds, validation_data=val_ds,
                epochs=self.epochs, callbacks=[LogCallback(self)],
            )

            model.save(self.model_name)
            self.log(f"Model saved to {self.model_name}")
            self.progress_signal.emit(100)
            self.message_signal.emit(
                f"Training complete. Saved as {self.model_name}"
            )
            self.finished_signal.emit()

        except Exception as e:
            self.error_signal.emit(str(e))
