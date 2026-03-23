import os
import sys
import tempfile
import cv2
from PyQt5 import QtCore, QtGui, QtWidgets
from src.insertion import insert_message_to_video
from src.extraction import extract_message_from_video

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEO_DIR = os.path.join(BASE_DIR, "video")
OUTPUT_VIDEO_DIR = os.path.join(BASE_DIR, "output_video")
OUTPUT_MESSAGE_DIR = os.path.join(BASE_DIR, "output_pesan")

os.makedirs(OUTPUT_VIDEO_DIR, exist_ok=True)
os.makedirs(OUTPUT_MESSAGE_DIR, exist_ok=True)


def show_video_preview(parent: QtWidgets.QWidget, path: str):
    if not path:
        QtWidgets.QMessageBox.warning(parent, "Preview", "Pilih video terlebih dahulu.")
        return
    if not os.path.isfile(path):
        QtWidgets.QMessageBox.critical(parent, "Preview", "File video tidak ditemukan.")
        return
    try:
        dialog = VideoPreviewDialog(path, parent)
    except Exception as exc:
        QtWidgets.QMessageBox.critical(parent, "Preview", f"Gagal membuka video: {exc}")
        return
    dialog.resize(640, 480)
    dialog.exec_()


class EmbedWorker(QtCore.QThread):
    finished = QtCore.pyqtSignal(str)
    error = QtCore.pyqtSignal(str)

    def __init__(
        self,
        *,
        video_path: str,
        payload_type: str,
        text_content: str,
        file_path: str,
        encrypt_payload: bool,
        a51_key: str,
        mode: str,
        stego_key: str,
        codec: str,
        output_dir: str,
    ):
        super().__init__()
        self.video_path = video_path
        self.payload_type = payload_type
        self.text_content = text_content
        self.file_path = file_path
        self.encrypt_payload = encrypt_payload
        self.a51_key = a51_key
        self.mode = mode
        self.stego_key = stego_key
        self.codec = codec
        self.output_dir = output_dir
        self._tmp_path = None

    def run(self):
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            base_name = os.path.splitext(os.path.basename(self.video_path))[0] or "output"
            output_path = os.path.join(self.output_dir, f"{base_name}_stego.avi")

            if self.payload_type == "text":
                with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt", encoding="utf-8") as tmp:
                    tmp.write(self.text_content)
                    self._tmp_path = tmp.name
                secret_path = self._tmp_path
            else:
                secret_path = self.file_path

            insert_message_to_video(
                video_path=self.video_path,
                secret_path=secret_path,
                output_path=output_path,
                payload_type=self.payload_type,
                encrypt_payload=self.encrypt_payload,
                a51_key=self.a51_key,
                mode=self.mode,
                stego_key=self.stego_key,
                preferred_codec=self.codec,
            )

            self.finished.emit(output_path)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            if self._tmp_path and os.path.exists(self._tmp_path):
                os.remove(self._tmp_path)


class ExtractWorker(QtCore.QThread):
    finished = QtCore.pyqtSignal(dict)
    error = QtCore.pyqtSignal(str)

    def __init__(
        self,
        *,
        stego_video_path: str,
        a51_key: str,
        stego_key: str,
        save_as: str,
        output_dir: str,
    ):
        super().__init__()
        self.stego_video_path = stego_video_path
        self.a51_key = a51_key
        self.stego_key = stego_key
        self.save_as = save_as
        self.output_dir = output_dir

    def run(self):
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            result = extract_message_from_video(
                stego_video_path=self.stego_video_path,
                a51_key=self.a51_key,
                stego_key=self.stego_key,
                save_as_path=self.save_as,
                output_dir=self.output_dir,
                prompt_save_as=False,
            )
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class VideoPreviewDialog(QtWidgets.QDialog):
    def __init__(self, video_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Preview: {os.path.basename(video_path)}")
        self.setModal(True)
        self.cap = cv2.VideoCapture(video_path)
        if not self.cap.isOpened():
            raise IOError("Tidak bisa membuka video untuk preview")

        fps = self.cap.get(cv2.CAP_PROP_FPS) or 0
        fps = fps if fps and fps > 1e-2 else 30.0
        self.interval_ms = int(max(15, 1000.0 / fps))

        self.label = QtWidgets.QLabel()
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        self.label.setMinimumSize(320, 240)
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.label)
        self.setLayout(layout)

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._next_frame)
        self.timer.start(self.interval_ms)

    def _next_frame(self):
        if not self.cap.isOpened():
            return

        ret, frame = self.cap.read()
        if not ret:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            return

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qimg = QtGui.QImage(rgb.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
        pix = QtGui.QPixmap.fromImage(qimg)
        self.label.setPixmap(
            pix.scaled(
                self.label.size(),
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
        )

    def closeEvent(self, event):
        if self.timer.isActive():
            self.timer.stop()
        if self.cap.isOpened():
            self.cap.release()
        super().closeEvent(event)


class PrimaryButton(QtWidgets.QPushButton):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.setObjectName("primaryBtn")
        self._base_geom = None
        self.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self:
            if event.type() == QtCore.QEvent.Enter:
                self._start_scale(1.03)
            elif event.type() == QtCore.QEvent.Leave:
                self._start_scale(1.0)
        return super().eventFilter(obj, event)

    def _start_scale(self, scale: float):
        self._base_geom = self.geometry()
        geom = self._base_geom
        w = geom.width()
        h = geom.height()
        new_w = int(w * scale)
        new_h = int(h * scale)
        dx = (new_w - w) // 2
        dy = (new_h - h) // 2
        target = QtCore.QRect(geom.x() - dx, geom.y() - dy, new_w, new_h)


class EmbedTab(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.original_cap = self.stego_cap = self.embed_worker = None
        self.preview_timer = QtCore.QTimer(self)
        self.video_path_edit = QtWidgets.QLineEdit(os.path.join(VIDEO_DIR, "contoh_vid.avi"))
        self.browse_btn = PrimaryButton("˖🗀 ۫ . Browse"); self.browse_btn.setObjectName("browseBtn")
        self.preview_btn = PrimaryButton("˖⌕ ۫ .Preview"); self.preview_btn.setObjectName("previewBtn")
        
        file_row = QtWidgets.QHBoxLayout(); [file_row.addWidget(w) for w in (self.video_path_edit, self.browse_btn, self.preview_btn)]
        
        self.payload_text_radio, self.payload_file_radio = QtWidgets.QRadioButton("Text Message"), QtWidgets.QRadioButton("File")
        self.payload_text_radio.setChecked(True)
        payload_choice = QtWidgets.QHBoxLayout(); [payload_choice.addWidget(w) for w in (self.payload_text_radio, self.payload_file_radio)]; payload_choice.addStretch()
        self.message_edit = QtWidgets.QLineEdit(); self.message_edit.setPlaceholderText("Enter your message here..."); self.message_edit.setFixedHeight(30)
        text_input_widget = QtWidgets.QWidget(); t_layout = QtWidgets.QVBoxLayout(text_input_widget); t_layout.setContentsMargins(0, 0, 0, 0); t_layout.addWidget(self.message_edit)
        self.file_payload_edit = QtWidgets.QLineEdit(); self.file_payload_edit.setPlaceholderText("Select a file to embed...")
        self.file_payload_browse = PrimaryButton("˖🗀 ۫ . Browse"); self.file_payload_browse.setObjectName("browseBtn")
        file_payload_row = QtWidgets.QHBoxLayout(); [file_payload_row.addWidget(w) for w in (self.file_payload_edit, self.file_payload_browse)]
        file_input_widget = QtWidgets.QWidget(); f_layout = QtWidgets.QVBoxLayout(file_input_widget); f_layout.setContentsMargins(0, 0, 0, 0); f_layout.addLayout(file_payload_row)
        for w in (self.file_payload_edit, self.file_payload_browse, self.message_edit): w.setFixedHeight(34)

        payload_container = QtWidgets.QWidget(); payload_container.setFixedHeight(34)
        self.payload_stack = QtWidgets.QStackedLayout(payload_container); self.payload_stack.setContentsMargins(0, 0, 0, 0)
        [self.payload_stack.addWidget(w) for w in (text_input_widget, file_input_widget)]
        self.encrypt_check = QtWidgets.QCheckBox("Use A5/1 Encryption"); self.encrypt_key_edit = QtWidgets.QLineEdit(); self.encrypt_key_edit.setEnabled(False); self.encrypt_key_edit.setPlaceholderText("Enter A5/1 key")
        self.mode_combo = QtWidgets.QComboBox(); self.mode_combo.addItems(["sequential", "random"])
        self.stego_key_edit = QtWidgets.QLineEdit(); self.stego_key_edit.setEnabled(False); self.stego_key_edit.setPlaceholderText("Enter stego-key")
        self.codec_combo = QtWidgets.QComboBox(); self.codec_combo.addItems(["FFV1", "HFYU"]); self.codec_combo.setCurrentText("FFV1")
        self.start_btn = PrimaryButton("ᯓ➤ Embed ✮⋆˙"); self.start_btn.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed); self.start_btn.setMinimumWidth(340)
        orig_block, self.original_preview_label, self.original_info_label = self._create_preview_column("[ ▶︎ ] Original Video", "Original preview will appear here")
        stego_block, self.stego_preview_label, self.stego_info_label = self._create_preview_column("[ ▶︎ ] Stego Video", "Stego preview will appear here")
        comparison_widget = QtWidgets.QWidget(); comparison_widget.setObjectName("comparisonCard")
        comparison_layout = QtWidgets.QVBoxLayout(comparison_widget); comparison_layout.setSpacing(12); comparison_layout.setContentsMargins(16, 12, 16, 12)
        comparison_title = QtWidgets.QLabel("⇄ Before vs After Comparison ⇄"); comparison_title.setAlignment(QtCore.Qt.AlignCenter); comparison_title.setObjectName("sectionTitle"); comparison_title.setStyleSheet("background: transparent; color: #FBF5DB;")
        comparison_layout.addWidget(comparison_title)
        comparison_layout.addLayout(orig_block)
        comparison_layout.addLayout(stego_block)

        form = QtWidgets.QFormLayout(); form.setSpacing(12); form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        form.addRow("Select Video:", file_row); form.addRow("Payload type:", payload_choice); form.addRow("Payload:", payload_container)
        form.addRow(self.encrypt_check); form.addRow("Encryption key:", self.encrypt_key_edit)
        form.addRow("Embedding mode:", self.mode_combo); form.addRow("Stego-key:", self.stego_key_edit); form.addRow("Codec:", self.codec_combo)
        form.addRow(self.start_btn)

        self.progress = QtWidgets.QProgressBar(); self.progress.setVisible(False); self.progress.setRange(0, 1); self.progress.setValue(0)

        left_widget = QtWidgets.QWidget(); left_layout = QtWidgets.QVBoxLayout(left_widget); left_layout.setSpacing(14); left_layout.setContentsMargins(0, 0, 0, 0)
        title = QtWidgets.QLabel("✿ Embed Message ✉︎ "); title.setObjectName("sectionTitle"); title.setAlignment(QtCore.Qt.AlignLeft)
        [left_layout.addWidget(title), left_layout.addLayout(form), left_layout.addWidget(self.progress)]

        right_widget = QtWidgets.QWidget(); right_layout = QtWidgets.QVBoxLayout(right_widget); right_layout.setContentsMargins(0, 0, 0, 0); right_layout.setSpacing(0)
        right_layout.addWidget(comparison_widget)

        main_split = QtWidgets.QHBoxLayout(); main_split.setSpacing(16); main_split.addWidget(left_widget, 2); main_split.addWidget(right_widget, 3)

        outer_layout = QtWidgets.QVBoxLayout(); outer_layout.setContentsMargins(20, 20, 20, 20); outer_layout.setSpacing(14)
        outer_layout.addLayout(main_split)
        self.setLayout(outer_layout)

        self.preview_timer.timeout.connect(self._next_comparison_frame)
        for sig, slot in [
            (self.browse_btn.clicked, self._pick_video),
            (self.preview_btn.clicked, self._preview_video),
            (self.payload_text_radio.toggled, self._update_payload_type),
            (self.payload_file_radio.toggled, self._update_payload_type),
            (self.file_payload_browse.clicked, self._pick_payload_file),
            (self.encrypt_check.toggled, self._toggle_encrypt),
            (self.mode_combo.currentTextChanged, self._toggle_stego_key),
            (self.start_btn.clicked, self._start_embed),
        ]:
            sig.connect(slot)
        self._update_payload_type()

    def _toggle_encrypt(self, checked: bool):
        self.encrypt_key_edit.setEnabled(checked)

    def _toggle_stego_key(self, mode: str):
        self.stego_key_edit.setEnabled(mode == "random")

    def _update_payload_type(self):
        is_text = self.payload_text_radio.isChecked()
        self.payload_stack.setCurrentIndex(0 if is_text else 1)

    def _input_error(self):
        QtWidgets.QMessageBox.critical(self, "Error", "Something went wrong. Please check your input.")

    def _create_preview_column(self, title: str, placeholder: str):
        title_label = QtWidgets.QLabel(title)
        title_label.setObjectName("previewTitle")
        title_label.setAlignment(QtCore.Qt.AlignCenter)
        preview_label = QtWidgets.QLabel(placeholder)
        preview_label.setObjectName("videoPreviewEmbed")
        preview_label.setAlignment(QtCore.Qt.AlignCenter)
        preview_label.setMinimumWidth(320)
        preview_label.setFixedHeight(170)
        preview_label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        preview_label.setStyleSheet("border: 2px dashed #FFD21F; background: #FBF5DB; border-radius: 8px;")
        info_label = QtWidgets.QLabel("")
        info_label.setAlignment(QtCore.Qt.AlignCenter)
        info_label.setFixedHeight(0)
        title_label.setContentsMargins(0, 0, 0, 0)
        preview_label.setContentsMargins(0, 0, 0, 0)
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(title_label)
        layout.addWidget(preview_label, stretch=1)
        layout.addWidget(info_label)

        return layout, preview_label, info_label

    def _pick_payload_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select payload file",
            BASE_DIR,
            "All Files (*)",
        )
        if path:
            self.file_payload_edit.setText(path)

    def _pick_video(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select input AVI",
            VIDEO_DIR,
            "AVI Files (*.avi);;All Files (*)",
        )
        if path:
            self.video_path_edit.setText(path)

    def _preview_video(self):
        path = self.video_path_edit.text().strip()
        show_video_preview(self, path)

    def _start_embed(self):
        video_path = self.video_path_edit.text().strip()
        payload_type = "text" if self.payload_text_radio.isChecked() else "file"
        text_content = self.message_edit.text().strip()
        file_payload_path = self.file_payload_edit.text().strip()
        encrypt_payload = self.encrypt_check.isChecked()
        a51_key = self.encrypt_key_edit.text() if encrypt_payload else None
        mode = self.mode_combo.currentText()
        stego_key = self.stego_key_edit.text().strip() if mode == "random" else None
        codec = self.codec_combo.currentText().strip() or None

        if not video_path or not os.path.isfile(video_path):
            self._input_error()
            return

        if payload_type == "text" and not text_content:
            self._input_error()
            return

        if payload_type == "file" and (not file_payload_path or not os.path.isfile(file_payload_path)):
            self._input_error()
            return

        if encrypt_payload and not a51_key:
            self._input_error()
            return

        if mode == "random" and not stego_key:
            self._input_error()
            return

        self._stop_comparison_preview()
        self._set_busy(True)

        self.embed_worker = EmbedWorker(
            video_path=video_path,
            payload_type=payload_type,
            text_content=text_content,
            file_path=file_payload_path,
            encrypt_payload=encrypt_payload,
            a51_key=a51_key,
            mode=mode,
            stego_key=stego_key,
            codec=codec,
            output_dir=OUTPUT_VIDEO_DIR,
        )
        self.embed_worker.finished.connect(self._on_embed_finished)
        self.embed_worker.error.connect(self._on_embed_error)
        self.embed_worker.start()

    def _stop_comparison_preview(self):
        if self.preview_timer.isActive():
            self.preview_timer.stop()
        for cap in (self.original_cap, self.stego_cap):
            if cap is not None and cap.isOpened():
                cap.release()
        self.original_cap = None
        self.stego_cap = None

    def _start_comparison_preview(self, original_path: str, stego_path: str):
        self._stop_comparison_preview()

        if not original_path or not os.path.isfile(original_path):
            QtWidgets.QMessageBox.critical(self, "Preview", "File video asli tidak ditemukan.")
            return
        if not stego_path or not os.path.isfile(stego_path):
            QtWidgets.QMessageBox.critical(self, "Preview", "File video stego tidak ditemukan.")
            return

        orig_cap = cv2.VideoCapture(original_path)
        if not orig_cap.isOpened():
            QtWidgets.QMessageBox.critical(self, "Preview", "Tidak bisa membuka video asli untuk preview.")
            orig_cap.release()
            return

        stego_cap = cv2.VideoCapture(stego_path)
        if not stego_cap.isOpened():
            orig_cap.release()
            QtWidgets.QMessageBox.critical(self, "Preview", "Tidak bisa membuka video stego untuk preview.")
            return

        self.original_cap = orig_cap
        self.stego_cap = stego_cap

        orig_fps = orig_cap.get(cv2.CAP_PROP_FPS) or 0
        stego_fps = stego_cap.get(cv2.CAP_PROP_FPS) or 0
        fps_values = [v for v in (orig_fps, stego_fps) if v and v > 1e-2]
        fps_base = min(fps_values) if fps_values else 30.0
        interval = int(max(15, 1000.0 / fps_base))

        orig_w = int(orig_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        orig_h = int(orig_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        stego_w = int(stego_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        stego_h = int(stego_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.original_info_label.setText(f"Resolution: {orig_w}x{orig_h}")
        self.stego_info_label.setText(f"Resolution: {stego_w}x{stego_h}")

        self.preview_timer.start(interval)

    def _next_comparison_frame(self):
        if self.original_cap is None or self.stego_cap is None:
            return

        ret_orig, frame_orig = self.original_cap.read()
        ret_stego, frame_stego = self.stego_cap.read()

        if not ret_orig or not ret_stego:
            if self.original_cap is not None and self.original_cap.isOpened():
                self.original_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            if self.stego_cap is not None and self.stego_cap.isOpened():
                self.stego_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            return

        rgb_orig = cv2.cvtColor(frame_orig, cv2.COLOR_BGR2RGB)
        h1, w1, ch1 = rgb_orig.shape
        qimg_orig = QtGui.QImage(rgb_orig.data, w1, h1, ch1 * w1, QtGui.QImage.Format_RGB888)
        pix_orig = QtGui.QPixmap.fromImage(qimg_orig)
        self.original_preview_label.setPixmap(
            pix_orig.scaled(
                self.original_preview_label.size(),
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
        )

        rgb_stego = cv2.cvtColor(frame_stego, cv2.COLOR_BGR2RGB)
        h2, w2, ch2 = rgb_stego.shape
        qimg_stego = QtGui.QImage(rgb_stego.data, w2, h2, ch2 * w2, QtGui.QImage.Format_RGB888)
        pix_stego = QtGui.QPixmap.fromImage(qimg_stego)
        self.stego_preview_label.setPixmap(
            pix_stego.scaled(
                self.stego_preview_label.size(),
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
        )

    def _set_busy(self, busy: bool):
        if busy:
            self._set_inputs_enabled(False)
            self.progress.setVisible(True)
            self.progress.setRange(0, 0)
        else:
            self._set_inputs_enabled(True)
            self.progress.setRange(0, 1)
            self.progress.setVisible(False)

    def _set_inputs_enabled(self, enabled: bool):
        widgets = [
            self.video_path_edit,
            self.browse_btn,
            self.preview_btn,
            self.payload_text_radio,
            self.payload_file_radio,
            self.message_edit,
            self.file_payload_edit,
            self.file_payload_browse,
            self.encrypt_check,
            self.encrypt_key_edit,
            self.mode_combo,
            self.stego_key_edit,
            self.codec_combo,
            self.start_btn,
        ]
        for widget in widgets:
            widget.setEnabled(enabled)

    def _on_embed_finished(self, output_path: str):
        self._set_busy(False)
        self.embed_worker = None
        self._start_comparison_preview(original_path=self.video_path_edit.text().strip(), stego_path=output_path)
        QtWidgets.QMessageBox.information(
            self,
            "Success",
            f"Process completed successfully!\nSaved to:\n{output_path}",
        )

    def _on_embed_error(self, message: str):
        self._set_busy(False)
        self.embed_worker = None
        QtWidgets.QMessageBox.critical(self, "Error", f"Something went wrong. Please check your input.\n{message}")


class ExtractTab(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.extract_worker = None; self._last_saved_dir = None
        self.stego_path_edit = QtWidgets.QLineEdit(OUTPUT_VIDEO_DIR)
        self.browse_btn = PrimaryButton("˖🗀 ۫ . Browse"); self.browse_btn.setObjectName("browseBtn")
        self.preview_btn = PrimaryButton("˖⌕ ۫ .Preview"); self.preview_btn.setObjectName("previewBtn")

        stego_row = QtWidgets.QHBoxLayout(); [stego_row.addWidget(w) for w in (self.stego_path_edit, self.browse_btn, self.preview_btn)]
        self.encrypted_check = QtWidgets.QCheckBox("Encrypted (A5/1)"); self.a51_key_edit = QtWidgets.QLineEdit(); self.a51_key_edit.setEnabled(False); self.a51_key_edit.setPlaceholderText("Enter A5/1 key")
        self.random_check = QtWidgets.QCheckBox("Random mode"); self.stego_key_edit = QtWidgets.QLineEdit(); self.stego_key_edit.setEnabled(False); self.stego_key_edit.setPlaceholderText("Enter stego-key")
        self.save_as_edit = QtWidgets.QLineEdit()
        self.result_view = QtWidgets.QTextEdit(); self.result_view.setReadOnly(True); self.result_view.setPlaceholderText("No result yet")
        self.text_result_widget = QtWidgets.QWidget(); tr_layout = QtWidgets.QVBoxLayout(self.text_result_widget); tr_layout.setContentsMargins(0, 0, 0, 0); tr_layout.addWidget(self.result_view)
        self.text_result_widget.setMinimumHeight(44)
        self.file_name_label, self.file_path_label = QtWidgets.QLabel("File: -"), QtWidgets.QLabel("Saved to: -"); self.file_path_label.setWordWrap(True)
        self.file_result_widget = QtWidgets.QWidget(); fr_layout = QtWidgets.QVBoxLayout(self.file_result_widget); fr_layout.setContentsMargins(0, 0, 0, 0); fr_layout.addWidget(self.file_name_label); fr_layout.addWidget(self.file_path_label)
        self.file_result_widget.setMinimumHeight(44)
        self.open_folder_btn = PrimaryButton("🗀 Open Folder"); self.open_folder_btn.setObjectName("browseBtn"); self.open_folder_btn.setVisible(False)
        self.start_btn = PrimaryButton("ᯓ➤ Extract ✮⋆˙"); self.start_btn.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed); self.start_btn.setMinimumWidth(340)
        self.progress = QtWidgets.QProgressBar(); self.progress.setVisible(False); self.progress.setRange(0, 1); self.progress.setValue(0)

        form = QtWidgets.QFormLayout(); form.setSpacing(12); form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        form.addRow("Stego video:", stego_row); form.addRow(self.encrypted_check); form.addRow("A5/1 key:", self.a51_key_edit)
        form.addRow(self.random_check); form.addRow("Stego-key:", self.stego_key_edit); form.addRow("Save as (optional):", self.save_as_edit)
        form.addRow("Result (text):", self.text_result_widget); form.addRow("Result (file):", self.file_result_widget)
        form.addRow(self.start_btn)
        layout = QtWidgets.QVBoxLayout(); layout.setContentsMargins(20, 24, 20, 20); layout.setSpacing(14)
        title = QtWidgets.QLabel("✿ Extract Message ✉︎"); title.setObjectName("sectionTitle"); title.setAlignment(QtCore.Qt.AlignLeft); title.setContentsMargins(0, 0, 0, 8)
        [layout.addWidget(title), layout.addLayout(form), layout.addWidget(self.open_folder_btn, alignment=QtCore.Qt.AlignLeft), layout.addWidget(self.progress)]
        self.setLayout(layout)

        for sig, slot in [
            (self.browse_btn.clicked, self._pick_stego_video),
            (self.preview_btn.clicked, self._preview_stego),
            (self.encrypted_check.toggled, self._toggle_encrypt),
            (self.random_check.toggled, self._toggle_random),
            (self.open_folder_btn.clicked, self._open_output_folder),
            (self.start_btn.clicked, self._start_extract),
        ]:
            sig.connect(slot)
        self._set_result_visible(text_visible=True, file_visible=True)

    def _toggle_encrypt(self, checked: bool):
        self.a51_key_edit.setEnabled(checked)

    def _toggle_random(self, checked: bool):
        self.stego_key_edit.setEnabled(checked)

    def _pick_stego_video(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select stego video",
            OUTPUT_VIDEO_DIR,
            "AVI Files (*.avi);;All Files (*)",
        )
        if path:
            self.stego_path_edit.setText(path)

    def _preview_stego(self):
        path = self.stego_path_edit.text().strip()
        show_video_preview(self, path)

    def _start_extract(self):
        stego_video_path = self.stego_path_edit.text().strip()
        encrypted = self.encrypted_check.isChecked()
        a51_key = self.a51_key_edit.text() if encrypted else None
        random_mode = self.random_check.isChecked()
        stego_key = self.stego_key_edit.text().strip() if random_mode else None
        save_as = self.save_as_edit.text().strip() or None

        os.makedirs(OUTPUT_MESSAGE_DIR, exist_ok=True)

        if not stego_video_path or not os.path.isfile(stego_video_path):
            self._input_error()
            return

        if encrypted and not a51_key:
            self._input_error()
            return

        if random_mode and not stego_key:
            self._input_error()
            return

        self.result_view.clear()
        self.file_name_label.setText("File: -")
        self.file_path_label.setText("Saved to: -")
        self.open_folder_btn.setVisible(False)
        self._last_saved_dir = None
        self._set_result_visible(text_visible=True, file_visible=True)
        self._set_busy(True)

        self.extract_worker = ExtractWorker(
            stego_video_path=stego_video_path,
            a51_key=a51_key,
            stego_key=stego_key,
            save_as=save_as,
            output_dir=OUTPUT_MESSAGE_DIR,
        )
        self.extract_worker.finished.connect(self._on_extract_finished)
        self.extract_worker.error.connect(self._on_extract_error)
        self.extract_worker.start()

    def _set_busy(self, busy: bool):
        if busy:
            self._set_inputs_enabled(False)
            self.progress.setVisible(True)
            self.progress.setRange(0, 0)
        else:
            self._set_inputs_enabled(True)
            self.progress.setRange(0, 1)
            self.progress.setVisible(False)

    def _set_inputs_enabled(self, enabled: bool):
        widgets = [
            self.stego_path_edit,
            self.browse_btn,
            self.preview_btn,
            self.encrypted_check,
            self.a51_key_edit,
            self.random_check,
            self.stego_key_edit,
            self.save_as_edit,
            self.start_btn,
        ]
        for widget in widgets:
            widget.setEnabled(enabled)

    def _on_extract_finished(self, result: dict):
        self._set_busy(False)
        self.extract_worker = None

        saved_path = result.get("path", "")
        self._last_saved_dir = os.path.dirname(saved_path) if saved_path else None
        self.open_folder_btn.setVisible(bool(saved_path))

        if result.get("type") == "text":
            text_content = result.get("content", "")
            self.result_view.setPlainText(text_content)
            self._set_result_visible(text_visible=True, file_visible=False)
            if saved_path:
                self.file_path_label.setText(f"Saved to: {saved_path}")
            else:
                self.file_path_label.clear()
        else:
            filename = result.get("filename") or os.path.basename(saved_path)
            self.file_name_label.setText(f"File: {filename}")
            self.file_path_label.setText(f"Saved to: {saved_path}")
            self.result_view.clear()
            self._set_result_visible(text_visible=False, file_visible=True)

        QtWidgets.QMessageBox.information(self, "Extraction successful", "Extraction successful")

    def _on_extract_error(self, message: str):
        self._set_busy(False)
        self.extract_worker = None
        self.result_view.clear()
        self.file_name_label.clear()
        self.file_path_label.clear()
        self.open_folder_btn.setVisible(False)
        QtWidgets.QMessageBox.critical(self, "Error", f"Something went wrong. Please check your input.\n{message}")

    def _set_result_visible(self, *, text_visible: bool, file_visible: bool):
        self.text_result_widget.setVisible(text_visible)
        self.file_result_widget.setVisible(file_visible)

    def _open_output_folder(self):
        target_dir = self._last_saved_dir or OUTPUT_MESSAGE_DIR
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(target_dir))

    def _input_error(self):
        QtWidgets.QMessageBox.critical(self, "Error", "Something went wrong. Please check your input.")


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("➤ II4021 - Kriptografi ✉︎")
        self.setFixedSize(900, 700)
        self._apply_style()
        self._build_ui()

    def _build_ui(self):
        header = QtWidgets.QLabel("˚₊‧꒰ა Steganografi LSB pada Berkas Video AVI ໒꒱ ‧₊˚")
        header.setObjectName("headerTitle")
        header.setAlignment(QtCore.Qt.AlignCenter)
        tabs = QtWidgets.QTabWidget()
        tabs.addTab(EmbedTab(), "⌯⌲ Embed")
        tabs.addTab(ExtractTab(), "🗁 Extract")
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(header)
        layout.addStretch(1)
        layout.addWidget(tabs, alignment=QtCore.Qt.AlignHCenter)
        layout.addStretch(1)
        container = QtWidgets.QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def _apply_style(self):
        self.setStyleSheet(
            """
            QWidget, QLineEdit {
                font-size: 10pt;
                background: #FBF5DB;
                color: #76944C;
            }

            #headerTitle {
                font: 700 20pt;
                color: #76944C;
                padding: 16px;
                background: transparent;
                margin: 8px;
            }

            #sectionTitle { font: 600 14pt; }
            #previewTitle { background: transparent; }

            #comparisonCard {
                background: #C8DAA6;
                border: 1.5px solid #76944C;
                border-radius: 12px;
            }

            QLineEdit, QComboBox, QPlainTextEdit, QTextEdit {
                border: 1px solid #C0B6AC;
                border-radius: 8px;
                padding: 6px 8px;
                background: #C8DAA6;
            }

            QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus {
                border-color: #76944C;
            }

            QPushButton {
                border-radius: 12px;
                padding: 10px 14px;
                font-weight: 600;
            }

            QPushButton#primaryBtn {
                background: #FFD21F;
                color: #76944C;
                border: 1px solid #76944C;
            }

            QPushButton#browseBtn {
                background: #F3D13F;
                color: #3F3A33;
                border: 1px solid #76944C;
            }

            QPushButton#previewBtn {
                background: #C2B5AC;
                color: #3F3A33;
                border: 1px solid #76944C;
            }

            QCheckBox::indicator {
                width: 16px; height: 16px;
                border-radius: 6px;
                border: 1px solid #C0B6AC;
            }
            QCheckBox::indicator:checked { background: #76944C; }

            QTabWidget::pane {
                border: 3px solid #E3E9C4;
                border-radius: 10px;
                padding: 4px;
            }

            QTabBar::tab {
                background: #FBF5DB;
                padding: 10px 16px;
                min-width: 80px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: #C8DAA6;
                font-weight: 800;
                color: #76944C;
                min-width: 80px;
                padding: 12px 20px;
            }

            QProgressBar {
                border: 1px solid #C0B6AC;
                border-radius: 8px;
                background: #FBF5DB;
                text-align: center;
            }
            QProgressBar::chunk {
                background: #FFD21F;
                border-radius: 8px;
                width: 8px;
            }
            """
        )
def main():
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
