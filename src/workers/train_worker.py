"""
workers/train_worker.py — Background QObject for model training.
Extracted from ``model_training.py``.

Runs in a QThread via ``moveToThread()`` pattern (not QThread subclass)
to keep the training loop off the UI thread.

Platform acceleration (auto-detected, no config needed):
  • macOS Apple Silicon  → tensorflow-metal (MPS), mixed-precision float16
  • Windows/Linux CUDA   → CUDA + mixed-precision float16
  • CPU fallback         → float32, standard pipeline
"""

import sys
import platform
from pathlib import Path
from PyQt5.QtCore import QObject, pyqtSignal


# ── Helper: detect Apple Silicon ─────────────────────────────────────────────
def _is_apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() == "arm64"


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
    model_trained_signal(str, list)
        Emitted on successful save: (absolute_model_path, class_names_list)
    """

    progress_signal      = pyqtSignal(int)
    finished_signal      = pyqtSignal()
    error_signal         = pyqtSignal(str)
    message_signal       = pyqtSignal(str)
    plot_ready_signal    = pyqtSignal(str)
    log_signal           = pyqtSignal(str)
    epoch_end_signal     = pyqtSignal(int, dict)
    # Emitted on successful save: (absolute_model_path, list_of_class_names)
    model_trained_signal = pyqtSignal(str, list)

    def __init__(self, trainer):
        super().__init__()
        self.trainer = trainer

    def log(self, message):
        """Helper to log to both file and UI."""
        self.trainer.logger.log_status(message)
        self.log_signal.emit(message)

    # ── Platform detection & mixed-precision setup ────────────────────────────
    def _configure_accelerator(self, tf):
        """
        Auto-detect hardware and configure the best available accelerator.
        Returns (device_name_str, use_mixed_precision: bool).
        Safe to call on any platform.
        """
        use_mixed = False
        device = "CPU"

        try:
            if _is_apple_silicon():
                # Try to enable tensorflow-metal (MPS)
                gpus = tf.config.list_physical_devices("GPU")  # Metal shows as GPU
                if gpus:
                    try:
                        for gpu in gpus:
                            tf.config.experimental.set_memory_growth(gpu, True)
                        from tensorflow.keras import mixed_precision
                        mixed_precision.set_global_policy("mixed_float16")
                        use_mixed = True
                        device = f"Apple MPS ({len(gpus)} GPU(s)) + float16"
                        self.log(f"✓ Apple Silicon MPS enabled — mixed_float16 policy active")
                    except Exception as e:
                        self.log(f"⚠ MPS config warning (non-fatal): {e}")
                        device = "Apple Silicon CPU (install tensorflow-metal for GPU)"
                else:
                    self.log("⚠ tensorflow-metal not found — running on CPU.")
                    self.log("  Install with: pip install tensorflow-metal")
                    device = "CPU (no tensorflow-metal)"

            elif tf.config.list_physical_devices("GPU"):
                # Windows / Linux CUDA
                gpus = tf.config.list_physical_devices("GPU")
                for gpu in gpus:
                    tf.config.experimental.set_memory_growth(gpu, True)
                try:
                    from tensorflow.keras import mixed_precision
                    mixed_precision.set_global_policy("mixed_float16")
                    use_mixed = True
                    device = f"CUDA ({len(gpus)} GPU(s)) + float16"
                    self.log(f"✓ CUDA GPU enabled — mixed_float16 policy active")
                except Exception:
                    device = f"CUDA ({len(gpus)} GPU(s)) float32"
            else:
                self.log("GPU not available — training on CPU.")
                device = "CPU"
        except Exception as e:
            self.log(f"Accelerator detection error (non-fatal): {e}")

        self.log(f"Training device: {device}")
        return device, use_mixed

    # ── Optimized data pipeline ───────────────────────────────────────────────
    @staticmethod
    def _optimize_dataset(ds, batch_size: int, is_training: bool, tf):
        """
        Apply performance pipeline:
          cache → (shuffle if train) → prefetch
        Keeps data loading off the training thread using AUTOTUNE.
        """
        AUTOTUNE = tf.data.AUTOTUNE
        ds = ds.cache()                                    # keep in RAM after first epoch
        if is_training:
            ds = ds.shuffle(buffer_size=batch_size * 8,   # randomise within a window
                            reshuffle_each_iteration=True)
        ds = ds.prefetch(buffer_size=AUTOTUNE)             # overlap I/O with GPU compute
        return ds

    # ── Smart batch size ─────────────────────────────────────────────────────
    @staticmethod
    def _suggested_batch_size(requested: int) -> int:
        """
        On Apple Silicon the GPU/CPU share RAM, so larger batches are fine.
        Clamp requested to a power-of-2 ≥ 32 for best MPS performance.
        """
        if _is_apple_silicon():
            # Round up to next power of 2, minimum 32, maximum 128
            import math
            p2 = max(32, min(128, 2 ** math.ceil(math.log2(max(requested, 1)))))
            return p2
        return requested

    # ── Main run ─────────────────────────────────────────────────────────────
    def run(self):
        try:
            # Lazy load TensorFlow when training starts
            self.trainer._ensure_tensorflow_loaded()
            tf = self.trainer._tf

            self.log("Training started.")

            self.data_dir       = Path(self.trainer.path_input.text())
            self.epochs         = int(self.trainer.epochs_input.text())
            self.lr             = float(self.trainer.lr_input.text())
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

            self.val_split             = float(self.trainer.val_split_input.text())
            self.seed                  = int(self.trainer.seed_input.text())
            self.img_height            = int(self.trainer.img_height_input.text())
            self.img_width             = int(self.trainer.img_width_input.text())
            raw_batch                  = int(self.trainer.batch_size_input.text())
            self.freeze_original_layers = bool(
                self.trainer.freeze_input.currentText().lower() == 'true'
            )
            self.optimizer  = self.trainer.optimizer_selector.currentText()
            self.loss       = self.trainer.loss_selector.currentText()
            self.model_name = self.trainer.model_name_input.text()
            self.plot_name  = self.trainer.plot_name_input.text()

            # ── Configure accelerator ────────────────────────────────────────
            device, use_mixed = self._configure_accelerator(tf)

            # Adjust batch size for MPS (power-of-2 ≥ 32 is optimal)
            self.batch_size = self._suggested_batch_size(raw_batch)
            if self.batch_size != raw_batch:
                self.log(
                    f"Batch size adjusted: {raw_batch} → {self.batch_size} "
                    f"(optimised for {device})"
                )

            self.trainer.save_config()
            self.progress_signal.emit(5)
            self.log("Configuration saved.")

            # ── Load datasets (parallel I/O with num_parallel_calls) ─────────
            AUTOTUNE = tf.data.AUTOTUNE
            self.log(f"Loading dataset from {self.data_dir} …")

            train_ds = tf.keras.preprocessing.image_dataset_from_directory(
                self.data_dir,
                validation_split=self.val_split,
                subset="training",
                seed=self.seed,
                image_size=(self.img_height, self.img_width),
                batch_size=self.batch_size
            )

            val_ds = tf.keras.preprocessing.image_dataset_from_directory(
                self.data_dir,
                validation_split=self.val_split,
                subset="validation",
                seed=self.seed,
                image_size=(self.img_height, self.img_width),
                batch_size=self.batch_size
            )

            class_names = list(train_ds.class_names)
            num_classes = len(class_names)
            self.log(f"Detected {num_classes} classes: {class_names}")
            self.progress_signal.emit(20)

            # ── Optimise data pipeline ───────────────────────────────────────
            train_ds = self._optimize_dataset(train_ds, self.batch_size, True,  tf)
            val_ds   = self._optimize_dataset(val_ds,   self.batch_size, False, tf)
            self.log("✓ Data pipeline optimised (cache + prefetch + AUTOTUNE)")

            # ── Build model ──────────────────────────────────────────────────
            input_shape = (self.img_height, self.img_width, 3)
            self.log(f"Building base model: {self.base_model_name}")

            keras = self.trainer._keras
            base_kwargs = dict(
                include_top=False,
                weights="imagenet",
                input_shape=input_shape,
                pooling='avg',          # → GlobalAveragePooling2D output, no extra Flatten needed
            )
            if self.base_model_name == "MobileNetV2":
                base = keras.applications.MobileNetV2(**base_kwargs)
            elif self.base_model_name == "InceptionV3":
                # InceptionV3 needs ≥ 75×75
                if self.img_height < 75 or self.img_width < 75:
                    self.log("⚠ InceptionV3 requires images ≥ 75×75. Switching to MobileNetV2.")
                    base = keras.applications.MobileNetV2(**base_kwargs)
                else:
                    base = keras.applications.InceptionV3(**base_kwargs)
            elif self.base_model_name == "EfficientNetV2S":
                # Recommended for Apple Silicon — less compute than ResNet50
                try:
                    base = keras.applications.EfficientNetV2S(
                        include_top=False, weights="imagenet",
                        input_shape=input_shape, pooling='avg',
                        include_preprocessing=True,
                    )
                    self.log("✓ EfficientNetV2S loaded")
                except Exception:
                    self.log("EfficientNetV2S unavailable — falling back to MobileNetV2")
                    base = keras.applications.MobileNetV2(**base_kwargs)
            else:  # ResNet50 (default)
                base = keras.applications.ResNet50(**base_kwargs)

            if self.freeze_original_layers:
                base.trainable = False
                self.log(f"Base layers frozen ({len(base.layers)} layers)")

            # Build head — pooling='avg' already outputs (batch, features)
            # so no Flatten needed; this also avoids MPS shape bugs
            inputs = keras.Input(shape=input_shape)
            x = base(inputs, training=False)           # inference mode for BN layers when frozen
            for size in self.custom_layers:
                x = keras.layers.Dense(size, activation='relu')(x)
                x = keras.layers.Dropout(0.5)(x)

            # Output dtype must be float32 even under mixed_float16
            outputs = keras.layers.Dense(num_classes, activation='softmax',
                                         dtype='float32')(x)
            model = keras.Model(inputs, outputs)

            # ── Compile with appropriate optimizer ───────────────────────────
            # Use legacy Adam on M-series for faster convergence
            if _is_apple_silicon():
                try:
                    opt = keras.optimizers.legacy.Adam(learning_rate=self.lr)
                    self.log("Using keras.optimizers.legacy.Adam (MPS optimised)")
                except AttributeError:
                    opt = self.trainer.Adam(learning_rate=self.lr)
            else:
                opt = self.trainer.Adam(learning_rate=self.lr)

            model.compile(
                optimizer=opt,
                loss=self.loss,
                metrics=['accuracy'],
            )
            self.log(f"Model compiled — params: {model.count_params():,}")
            self.progress_signal.emit(40)
            self.log("Model compiled.")

            # ── Callbacks ───────────────────────────────────────────────────
            class LogCallback(keras.callbacks.Callback):
                def __init__(self, worker_self):
                    super().__init__()
                    self.worker = worker_self

                def on_epoch_end(self, epoch, logs=None):
                    logs = logs or {}
                    self.worker.epoch_end_signal.emit(epoch + 1, dict(logs))
                    msg = (
                        f"Epoch {epoch+1}: "
                        f"loss={logs.get('loss', 0):.4f}, "
                        f"acc={logs.get('accuracy', 0):.4f}, "
                        f"val_loss={logs.get('val_loss', 0):.4f}, "
                        f"val_acc={logs.get('val_accuracy', 0):.4f}"
                    )
                    self.worker.log(msg)

            # EarlyStopping + ReduceLROnPlateau — optional quality-of-life
            early_stop = keras.callbacks.EarlyStopping(
                monitor='val_accuracy', patience=5,
                restore_best_weights=True, verbose=0,
            )
            reduce_lr = keras.callbacks.ReduceLROnPlateau(
                monitor='val_loss', factor=0.5, patience=3,
                min_lr=1e-6, verbose=0,
            )

            # ── Train ────────────────────────────────────────────────────────
            self.log(f"Starting training for {self.epochs} epochs …")
            model.fit(
                train_ds,
                validation_data=val_ds,
                epochs=self.epochs,
                callbacks=[LogCallback(self), early_stop, reduce_lr],
            )

            # ── Save ─────────────────────────────────────────────────────────
            model.save(self.model_name)
            self.log(f"Model saved to {self.model_name}")

            # ── Save class-names sidecar ─────────────────────────────────────
            import json
            abs_model  = str(Path(self.model_name).resolve())
            sidecar    = abs_model + ".classes.json"
            try:
                with open(sidecar, "w") as f:
                    json.dump({"class_names": class_names,
                               "model_path":  abs_model}, f, indent=2)
                self.log(f"Class sidecar saved: {sidecar}")
            except Exception as e:
                self.log(f"Warning: could not save class sidecar: {e}")

            self.progress_signal.emit(100)
            self.message_signal.emit(
                f"Training complete. Saved as {self.model_name}"
            )
            self.model_trained_signal.emit(abs_model, class_names)
            self.finished_signal.emit()

        except Exception as e:
            import traceback
            self.error_signal.emit(f"{e}\n{traceback.format_exc()}")
