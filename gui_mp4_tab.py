import os
import shutil
import tempfile
import cv2
from PyQt5 import QtCore, QtGui, QtWidgets

try:
    from src.mp4_steganography import (
        extract_message_from_mp4,
        get_mp4_capacity,
        insert_message_to_mp4,
    )
except ImportError:
    from mp4_steganography import (
        extract_message_from_mp4,
        get_mp4_capacity,
        insert_message_to_mp4,
    )

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_VIDEO_DIR = os.path.join(BASE_DIR, "output_video")
OUTPUT_MESSAGE_DIR = os.path.join(BASE_DIR, "output_pesan")

os.makedirs(OUTPUT_VIDEO_DIR, exist_ok=True)
os.makedirs(OUTPUT_MESSAGE_DIR, exist_ok=True)

class Mp4EmbedWorker(QtCore.QThread):
    finished = QtCore.pyqtSignal(str)
    error    = QtCore.pyqtSignal(str)

    def __init__(self, *, video_path, payload_type, text_content, file_path,
                 encrypt_payload, a51_key, mode, stego_key, output_dir):
        super().__init__()
        self.video_path      = video_path
        self.payload_type    = payload_type
        self.text_content    = text_content
        self.file_path       = file_path
        self.encrypt_payload = encrypt_payload
        self.a51_key         = a51_key
        self.mode            = mode
        self.stego_key       = stego_key
        self.output_dir      = output_dir
        self._tmp_path       = None

    def run(self):
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            base_name   = os.path.splitext(os.path.basename(self.video_path))[0] or "output"
            output_path = os.path.join(self.output_dir, f"{base_name}_stego_mp4.mp4")

            if self.payload_type == "text":
                with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt",
                                                 encoding="utf-8") as tmp:
                    tmp.write(self.text_content)
                    self._tmp_path = tmp.name
                secret_path = self._tmp_path
            else:
                secret_path = self.file_path

            result = insert_message_to_mp4(
                video_path=self.video_path,
                secret_path=secret_path,
                output_path=output_path,
                payload_type=self.payload_type,
                encrypt_payload=self.encrypt_payload,
                a51_key=self.a51_key,
                mode=self.mode,
                stego_key=self.stego_key,
            )
            self.finished.emit(result["actual_output"])
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            if self._tmp_path and os.path.exists(self._tmp_path):
                os.remove(self._tmp_path)


class Mp4ExtractWorker(QtCore.QThread):
    finished = QtCore.pyqtSignal(dict)
    error    = QtCore.pyqtSignal(str)

    def __init__(self, *, stego_video_path, a51_key, stego_key, output_dir):
        super().__init__()
        self.stego_video_path = stego_video_path
        self.a51_key          = a51_key
        self.stego_key        = stego_key
        self.output_dir       = output_dir

    def run(self):
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            result = extract_message_from_mp4(
                stego_video_path=self.stego_video_path,
                a51_key=self.a51_key,
                stego_key=self.stego_key,
                output_dir=self.output_dir,
            )
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))

class _VideoPreviewDialog(QtWidgets.QDialog):
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
        qimg = QtGui.QImage(rgb.data, w, h, ch * w, QtGui.QImage.Format_RGB888)
        pix  = QtGui.QPixmap.fromImage(qimg)
        self.label.setPixmap(
            pix.scaled(self.label.size(), QtCore.Qt.KeepAspectRatio,
                       QtCore.Qt.SmoothTransformation))

    def closeEvent(self, event):
        if self.timer.isActive():
            self.timer.stop()
        if self.cap.isOpened():
            self.cap.release()
        super().closeEvent(event)


def _show_video_preview(parent, path: str):
    if not path:
        QtWidgets.QMessageBox.warning(parent, "Preview", "Pilih video terlebih dahulu.")
        return
    if not os.path.isfile(path):
        QtWidgets.QMessageBox.critical(parent, "Preview", "File video tidak ditemukan.")
        return
    try:
        dlg = _VideoPreviewDialog(path, parent)
    except Exception as exc:
        QtWidgets.QMessageBox.critical(parent, "Preview", f"Gagal membuka video: {exc}")
        return
    dlg.resize(640, 480)
    dlg.exec_()

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
        if self._base_geom is None:
            self._base_geom = self.geometry()
        g  = self._base_geom
        dw = int(g.width()  * (scale - 1) / 2)
        dh = int(g.height() * (scale - 1) / 2)
        self.setGeometry(g.x() - dw, g.y() - dh,
                         g.width() + 2 * dw, g.height() + 2 * dh)

class Mp4EmbedTab(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.original_cap = self.stego_cap = self.embed_worker = None
        self.preview_timer = QtCore.QTimer(self)

        self.video_path_edit = QtWidgets.QLineEdit()
        self.video_path_edit.setPlaceholderText("Select cover MP4 video...")
        self.browse_btn  = PrimaryButton("˖🗀 ۫ . Browse"); self.browse_btn.setObjectName("browseBtn")
        self.preview_btn = PrimaryButton("˖⌕ ۫ .Preview"); self.preview_btn.setObjectName("previewBtn")
        file_row = QtWidgets.QHBoxLayout()
        for w in (self.video_path_edit, self.browse_btn, self.preview_btn):
            file_row.addWidget(w)

        self.capacity_label = QtWidgets.QLabel("Capacity: —")
        self.capacity_label.setStyleSheet(
            "color: #76944C; font-size: 9pt; background: transparent;")

        self.payload_text_radio = QtWidgets.QRadioButton("Text Message")
        self.payload_file_radio = QtWidgets.QRadioButton("File")
        self.payload_text_radio.setChecked(True)
        payload_choice = QtWidgets.QHBoxLayout()
        payload_choice.addWidget(self.payload_text_radio)
        payload_choice.addWidget(self.payload_file_radio)
        payload_choice.addStretch()

        self.message_edit = QtWidgets.QLineEdit()
        self.message_edit.setPlaceholderText("Enter your message here...")
        self.message_edit.setFixedHeight(30)
        text_input_widget = QtWidgets.QWidget()
        tl = QtWidgets.QVBoxLayout(text_input_widget)
        tl.setContentsMargins(0, 0, 0, 0); tl.addWidget(self.message_edit)

        self.file_payload_edit   = QtWidgets.QLineEdit()
        self.file_payload_edit.setPlaceholderText("Select a file to embed...")
        self.file_payload_browse = PrimaryButton("˖🗀 ۫ . Browse")
        self.file_payload_browse.setObjectName("browseBtn")
        file_payload_row = QtWidgets.QHBoxLayout()
        file_payload_row.addWidget(self.file_payload_edit)
        file_payload_row.addWidget(self.file_payload_browse)
        file_input_widget = QtWidgets.QWidget()
        fl = QtWidgets.QVBoxLayout(file_input_widget)
        fl.setContentsMargins(0, 0, 0, 0); fl.addLayout(file_payload_row)

        for w in (self.file_payload_edit, self.file_payload_browse, self.message_edit):
            w.setFixedHeight(34)

        payload_container = QtWidgets.QWidget(); payload_container.setFixedHeight(34)
        self.payload_stack = QtWidgets.QStackedLayout(payload_container)
        self.payload_stack.setContentsMargins(0, 0, 0, 0)
        self.payload_stack.addWidget(text_input_widget)
        self.payload_stack.addWidget(file_input_widget)

        self.encrypt_check    = QtWidgets.QCheckBox("Use A5/1 Encryption")
        self.encrypt_key_edit = QtWidgets.QLineEdit()
        self.encrypt_key_edit.setEnabled(False)
        self.encrypt_key_edit.setPlaceholderText("Enter A5/1 key")

        self.mode_combo     = QtWidgets.QComboBox()
        self.mode_combo.addItems(["sequential", "random"])
        self.stego_key_edit = QtWidgets.QLineEdit()
        self.stego_key_edit.setEnabled(False)
        self.stego_key_edit.setPlaceholderText("Enter stego-key")
        
        ffmpeg_ok  = shutil.which("ffmpeg") is not None
        ffmpeg_msg = (
            "✓  ffmpeg detected — output: MP4 (lossless H.264)"
            if ffmpeg_ok else
            "✗  ffmpeg not found — output: AVI (FFV1 lossless)"
        )
        self.ffmpeg_label = QtWidgets.QLabel(ffmpeg_msg)
        self.ffmpeg_label.setStyleSheet(
            "color: #76944C; font-size: 9pt; background: transparent;")
        
        self.start_btn = PrimaryButton("ᯓ➤ Embed (MP4) ✮⋆˙")
        self.start_btn.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.start_btn.setMinimumWidth(340)

        orig_block,  self.original_preview_label, self.original_info_label = \
            self._create_preview_column("[ ▶︎ ] Original Video",
                                        "Original preview will appear here")
        stego_block, self.stego_preview_label,    self.stego_info_label    = \
            self._create_preview_column("[ ▶︎ ] Stego Video",
                                        "Stego preview will appear here")

        comparison_widget = QtWidgets.QWidget()
        comparison_widget.setObjectName("comparisonCard")
        comparison_layout = QtWidgets.QVBoxLayout(comparison_widget)
        comparison_layout.setSpacing(12); comparison_layout.setContentsMargins(16, 12, 16, 12)
        comparison_title = QtWidgets.QLabel("⇄ Before vs After Comparison ⇄")
        comparison_title.setAlignment(QtCore.Qt.AlignCenter)
        comparison_title.setObjectName("sectionTitle")
        comparison_title.setStyleSheet("background: transparent; color: #FBF5DB;")
        comparison_layout.addWidget(comparison_title)
        comparison_layout.addLayout(orig_block)
        comparison_layout.addLayout(stego_block)
        form = QtWidgets.QFormLayout(); form.setSpacing(12)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        form.addRow("Select Video (MP4):", file_row)
        form.addRow("",                    self.capacity_label)
        form.addRow("Payload type:",       payload_choice)
        form.addRow("Payload:",            payload_container)
        form.addRow(self.encrypt_check)
        form.addRow("Encryption key:",     self.encrypt_key_edit)
        form.addRow("Embedding mode:",     self.mode_combo)
        form.addRow("Stego-key:",          self.stego_key_edit)
        form.addRow("",                    self.ffmpeg_label)
        form.addRow(self.start_btn)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setVisible(False); self.progress.setRange(0, 1); self.progress.setValue(0)

        left_widget  = QtWidgets.QWidget()
        left_layout  = QtWidgets.QVBoxLayout(left_widget)
        left_layout.setSpacing(14); left_layout.setContentsMargins(0, 0, 0, 0)
        title = QtWidgets.QLabel("✿ Embed Message (MP4) ✉︎")
        title.setObjectName("sectionTitle"); title.setAlignment(QtCore.Qt.AlignLeft)
        left_layout.addWidget(title)
        left_layout.addLayout(form)
        left_layout.addWidget(self.progress)

        right_widget = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0); right_layout.setSpacing(0)
        right_layout.addWidget(comparison_widget)

        main_split = QtWidgets.QHBoxLayout()
        main_split.setSpacing(16)
        main_split.addWidget(left_widget, 2)
        main_split.addWidget(right_widget, 3)

        outer_layout = QtWidgets.QVBoxLayout(self)
        outer_layout.setContentsMargins(20, 20, 20, 20); outer_layout.setSpacing(14)
        outer_layout.addLayout(main_split)
        self.preview_timer.timeout.connect(self._next_comparison_frame)
        self.browse_btn.clicked.connect(self._pick_video)
        self.preview_btn.clicked.connect(self._preview_video)
        self.file_payload_browse.clicked.connect(self._pick_payload_file)
        self.payload_text_radio.toggled.connect(self._update_payload_type)
        self.payload_file_radio.toggled.connect(self._update_payload_type)
        self.encrypt_check.toggled.connect(self._toggle_encrypt)
        self.mode_combo.currentTextChanged.connect(self._toggle_stego_key)
        self.video_path_edit.textChanged.connect(self._update_capacity)
        self.start_btn.clicked.connect(self._start_embed)
        self._update_payload_type()

    def _create_preview_column(self, title: str, placeholder: str):
        title_label = QtWidgets.QLabel(title)
        title_label.setObjectName("previewTitle")
        title_label.setAlignment(QtCore.Qt.AlignCenter)
        preview_label = QtWidgets.QLabel(placeholder)
        preview_label.setObjectName("videoPreviewEmbed")
        preview_label.setAlignment(QtCore.Qt.AlignCenter)
        preview_label.setMinimumWidth(320)
        preview_label.setFixedHeight(170)
        preview_label.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        preview_label.setStyleSheet(
            "border: 2px dashed #FFD21F; background: #FBF5DB; border-radius: 8px;")
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

    def _toggle_encrypt(self, checked):
        self.encrypt_key_edit.setEnabled(checked)

    def _toggle_stego_key(self, mode):
        self.stego_key_edit.setEnabled(mode == "random")

    def _update_payload_type(self):
        self.payload_stack.setCurrentIndex(
            0 if self.payload_text_radio.isChecked() else 1)

    def _update_capacity(self, path):
        path = path.strip()
        if not path or not os.path.isfile(path):
            self.capacity_label.setText("Capacity: —")
            return
        try:
            cap_bytes = get_mp4_capacity(path)
            self.capacity_label.setText(
                f"Capacity: {cap_bytes:,} bytes  ({cap_bytes / 1024:.1f} KB)")
        except Exception:
            self.capacity_label.setText("Capacity: (error reading file)")

    def _pick_video(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select cover MP4", BASE_DIR,
            "MP4 Files (*.mp4);;All Video Files (*.mp4 *.avi *.mov *.mkv);;All Files (*)")
        if path:
            self.video_path_edit.setText(path)

    def _pick_payload_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select payload file", BASE_DIR, "All Files (*)")
        if path:
            self.file_payload_edit.setText(path)

    def _preview_video(self):
        _show_video_preview(self, self.video_path_edit.text().strip())

    def _input_error(self):
        QtWidgets.QMessageBox.critical(
            self, "Error", "Something went wrong. Please check your input.")

    def _start_embed(self):
        video_path      = self.video_path_edit.text().strip()
        payload_type    = "text" if self.payload_text_radio.isChecked() else "file"
        text_content    = self.message_edit.text().strip()
        file_payload    = self.file_payload_edit.text().strip()
        encrypt_payload = self.encrypt_check.isChecked()
        a51_key         = self.encrypt_key_edit.text() if encrypt_payload else None
        mode            = self.mode_combo.currentText()
        stego_key       = self.stego_key_edit.text().strip() if mode == "random" else None

        if not video_path or not os.path.isfile(video_path):
            return self._input_error()
        if payload_type == "text" and not text_content:
            return self._input_error()
        if payload_type == "file" and (not file_payload or not os.path.isfile(file_payload)):
            return self._input_error()
        if encrypt_payload and not a51_key:
            return self._input_error()
        if mode == "random" and not stego_key:
            return self._input_error()

        self._stop_comparison_preview()
        self._set_busy(True)

        self.embed_worker = Mp4EmbedWorker(
            video_path=video_path, payload_type=payload_type,
            text_content=text_content, file_path=file_payload,
            encrypt_payload=encrypt_payload, a51_key=a51_key,
            mode=mode, stego_key=stego_key, output_dir=OUTPUT_VIDEO_DIR,
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
        self.original_cap = self.stego_cap = None

    def _start_comparison_preview(self, original_path: str, stego_path: str):
        self._stop_comparison_preview()
        if not original_path or not os.path.isfile(original_path):
            return
        if not stego_path or not os.path.isfile(stego_path):
            return
        orig_cap  = cv2.VideoCapture(original_path)
        stego_cap = cv2.VideoCapture(stego_path)
        if not orig_cap.isOpened() or not stego_cap.isOpened():
            orig_cap.release(); stego_cap.release()
            return
        self.original_cap = orig_cap
        self.stego_cap    = stego_cap
        fps_values = [v for v in (orig_cap.get(cv2.CAP_PROP_FPS),
                                  stego_cap.get(cv2.CAP_PROP_FPS)) if v and v > 1e-2]
        fps_base   = min(fps_values) if fps_values else 30.0
        interval   = int(max(15, 1000.0 / fps_base))
        self.original_info_label.setText(
            f"Resolution: {int(orig_cap.get(cv2.CAP_PROP_FRAME_WIDTH))}"
            f"x{int(orig_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")
        self.stego_info_label.setText(
            f"Resolution: {int(stego_cap.get(cv2.CAP_PROP_FRAME_WIDTH))}"
            f"x{int(stego_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")
        self.preview_timer.start(interval)

    def _next_comparison_frame(self):
        if self.original_cap is None or self.stego_cap is None:
            return
        ret_orig,  frame_orig  = self.original_cap.read()
        ret_stego, frame_stego = self.stego_cap.read()
        if not ret_orig or not ret_stego:
            for cap in (self.original_cap, self.stego_cap):
                if cap and cap.isOpened():
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            return
        for frame, label in ((frame_orig,  self.original_preview_label),
                              (frame_stego, self.stego_preview_label)):
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            qimg = QtGui.QImage(rgb.data, w, h, ch * w, QtGui.QImage.Format_RGB888)
            pix  = QtGui.QPixmap.fromImage(qimg)
            label.setPixmap(pix.scaled(label.size(), QtCore.Qt.KeepAspectRatio,
                                       QtCore.Qt.SmoothTransformation))

    def _set_busy(self, busy: bool):
        if busy:
            self._set_inputs_enabled(False)
            self.progress.setVisible(True); self.progress.setRange(0, 0)
        else:
            self._set_inputs_enabled(True)
            self.progress.setRange(0, 1); self.progress.setVisible(False)

    def _set_inputs_enabled(self, enabled: bool):
        for w in (self.video_path_edit, self.browse_btn, self.preview_btn,
                  self.payload_text_radio, self.payload_file_radio,
                  self.message_edit, self.file_payload_edit, self.file_payload_browse,
                  self.encrypt_check, self.encrypt_key_edit,
                  self.mode_combo, self.stego_key_edit, self.start_btn):
            w.setEnabled(enabled)

    def _on_embed_finished(self, output_path: str):
        self._set_busy(False)
        self.embed_worker = None
        self._start_comparison_preview(
            original_path=self.video_path_edit.text().strip(),
            stego_path=output_path)
        QtWidgets.QMessageBox.information(
            self, "Success",
            f"Process completed successfully!\nSaved to:\n{output_path}")

    def _on_embed_error(self, message: str):
        self._set_busy(False)
        self.embed_worker = None
        QtWidgets.QMessageBox.critical(
            self, "Error",
            f"Something went wrong. Please check your input.\n{message}")

class Mp4ExtractTab(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.extract_worker  = None
        self._last_saved_dir = None

        self.stego_path_edit = QtWidgets.QLineEdit(OUTPUT_VIDEO_DIR)
        self.browse_btn  = PrimaryButton("˖🗀 ۫ . Browse"); self.browse_btn.setObjectName("browseBtn")
        self.preview_btn = PrimaryButton("˖⌕ ۫ .Preview"); self.preview_btn.setObjectName("previewBtn")
        stego_row = QtWidgets.QHBoxLayout()
        for w in (self.stego_path_edit, self.browse_btn, self.preview_btn):
            stego_row.addWidget(w)

        self.encrypted_check = QtWidgets.QCheckBox("Encrypted (A5/1)")
        self.a51_key_edit    = QtWidgets.QLineEdit()
        self.a51_key_edit.setEnabled(False)
        self.a51_key_edit.setPlaceholderText("Enter A5/1 key")

        self.random_check   = QtWidgets.QCheckBox("Random mode")
        self.stego_key_edit = QtWidgets.QLineEdit()
        self.stego_key_edit.setEnabled(False)
        self.stego_key_edit.setPlaceholderText("Enter stego-key")

        self.save_as_edit = QtWidgets.QLineEdit()

        self.result_view = QtWidgets.QTextEdit()
        self.result_view.setReadOnly(True)
        self.result_view.setPlaceholderText("No result yet")

        self.text_result_widget = QtWidgets.QWidget()
        tr_layout = QtWidgets.QVBoxLayout(self.text_result_widget)
        tr_layout.setContentsMargins(0, 0, 0, 0)
        tr_layout.addWidget(self.result_view)
        self.text_result_widget.setMinimumHeight(44)

        self.file_name_label = QtWidgets.QLabel("File: -")
        self.file_path_label = QtWidgets.QLabel("Saved to: -")
        self.file_path_label.setWordWrap(True)
        self.file_result_widget = QtWidgets.QWidget()
        fr_layout = QtWidgets.QVBoxLayout(self.file_result_widget)
        fr_layout.setContentsMargins(0, 0, 0, 0)
        fr_layout.addWidget(self.file_name_label)
        fr_layout.addWidget(self.file_path_label)
        self.file_result_widget.setMinimumHeight(44)

        self.open_folder_btn = PrimaryButton("🗀 Open Folder")
        self.open_folder_btn.setObjectName("browseBtn")
        self.open_folder_btn.setVisible(False)

        self.start_btn = PrimaryButton("ᯓ➤ Extract (MP4) ✮⋆˙")
        self.start_btn.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.start_btn.setMinimumWidth(340)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setVisible(False); self.progress.setRange(0, 1); self.progress.setValue(0)

        form = QtWidgets.QFormLayout(); form.setSpacing(12)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        form.addRow("Stego video:", stego_row)
        form.addRow(self.encrypted_check)
        form.addRow("A5/1 key:", self.a51_key_edit)
        form.addRow(self.random_check)
        form.addRow("Stego-key:", self.stego_key_edit)
        form.addRow("Save as (optional):", self.save_as_edit)
        form.addRow("Result (text):", self.text_result_widget)
        form.addRow("Result (file):", self.file_result_widget)
        form.addRow(self.start_btn)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 24, 20, 20); layout.setSpacing(14)
        title = QtWidgets.QLabel("✿ Extract Message (MP4) ✉︎")
        title.setObjectName("sectionTitle"); title.setAlignment(QtCore.Qt.AlignLeft)
        title.setContentsMargins(0, 0, 0, 8)
        layout.addWidget(title)
        layout.addLayout(form)
        layout.addWidget(self.open_folder_btn, alignment=QtCore.Qt.AlignLeft)
        layout.addWidget(self.progress)

        self.browse_btn.clicked.connect(self._pick_stego_video)
        self.preview_btn.clicked.connect(self._preview_stego)
        self.encrypted_check.toggled.connect(lambda c: self.a51_key_edit.setEnabled(c))
        self.random_check.toggled.connect(lambda c: self.stego_key_edit.setEnabled(c))
        self.open_folder_btn.clicked.connect(self._open_output_folder)
        self.start_btn.clicked.connect(self._start_extract)
        self._set_result_visible(text_visible=True, file_visible=True)

    def _pick_stego_video(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select stego video", OUTPUT_VIDEO_DIR,
            "Video Files (*.mp4 *.avi);;All Files (*)")
        if path:
            self.stego_path_edit.setText(path)

    def _preview_stego(self):
        _show_video_preview(self, self.stego_path_edit.text().strip())

    def _start_extract(self):
        stego_path  = self.stego_path_edit.text().strip()
        encrypted   = self.encrypted_check.isChecked()
        a51_key     = self.a51_key_edit.text() if encrypted else None
        random_mode = self.random_check.isChecked()
        stego_key   = self.stego_key_edit.text().strip() if random_mode else None

        os.makedirs(OUTPUT_MESSAGE_DIR, exist_ok=True)

        if not stego_path or not os.path.isfile(stego_path):
            QtWidgets.QMessageBox.critical(self, "Error",
                "Something went wrong. Please check your input.")
            return
        if encrypted and not a51_key:
            QtWidgets.QMessageBox.critical(self, "Error",
                "Something went wrong. Please check your input.")
            return
        if random_mode and not stego_key:
            QtWidgets.QMessageBox.critical(self, "Error",
                "Something went wrong. Please check your input.")
            return

        self.result_view.clear()
        self.file_name_label.setText("File: -")
        self.file_path_label.setText("Saved to: -")
        self.open_folder_btn.setVisible(False)
        self._last_saved_dir = None
        self._set_result_visible(text_visible=True, file_visible=True)
        self._set_busy(True)

        self.extract_worker = Mp4ExtractWorker(
            stego_video_path=stego_path,
            a51_key=a51_key, stego_key=stego_key,
            output_dir=OUTPUT_MESSAGE_DIR,
        )
        self.extract_worker.finished.connect(self._on_extract_finished)
        self.extract_worker.error.connect(self._on_extract_error)
        self.extract_worker.start()

    def _set_busy(self, busy: bool):
        if busy:
            self._set_inputs_enabled(False)
            self.progress.setVisible(True); self.progress.setRange(0, 0)
        else:
            self._set_inputs_enabled(True)
            self.progress.setRange(0, 1); self.progress.setVisible(False)

    def _set_inputs_enabled(self, enabled: bool):
        for w in (self.stego_path_edit, self.browse_btn, self.preview_btn,
                  self.encrypted_check, self.a51_key_edit,
                  self.random_check, self.stego_key_edit,
                  self.save_as_edit, self.start_btn):
            w.setEnabled(enabled)

    def _on_extract_finished(self, result: dict):
        self._set_busy(False)
        self.extract_worker = None
        saved_path = result.get("path", "")
        self._last_saved_dir = os.path.dirname(saved_path) if saved_path else None
        self.open_folder_btn.setVisible(bool(saved_path))

        if result.get("type") == "text":
            self.result_view.setPlainText(result.get("content", ""))
            self._set_result_visible(text_visible=True, file_visible=False)
            self.file_path_label.setText(f"Saved to: {saved_path}" if saved_path else "")
        else:
            filename = result.get("filename") or os.path.basename(saved_path)
            self.file_name_label.setText(f"File: {filename}")
            self.file_path_label.setText(f"Saved to: {saved_path}")
            self.result_view.clear()
            self._set_result_visible(text_visible=False, file_visible=True)

        QtWidgets.QMessageBox.information(
            self, "Extraction successful", "Extraction successful")

    def _on_extract_error(self, message: str):
        self._set_busy(False)
        self.extract_worker = None
        self.result_view.clear()
        self.file_name_label.clear(); self.file_path_label.clear()
        self.open_folder_btn.setVisible(False)
        QtWidgets.QMessageBox.critical(self, "Error",
            f"Something went wrong. Please check your input.\n{message}")

    def _set_result_visible(self, *, text_visible: bool, file_visible: bool):
        self.text_result_widget.setVisible(text_visible)
        self.file_result_widget.setVisible(file_visible)

    def _open_output_folder(self):
        target = self._last_saved_dir or OUTPUT_MESSAGE_DIR
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(target))


class Mp4BonusTab(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sub_tabs = QtWidgets.QTabWidget()
        sub_tabs.setDocumentMode(True)
        sub_tabs.addTab(Mp4EmbedTab(),   "⌯⌲ Embed")
        sub_tabs.addTab(Mp4ExtractTab(), "🗁 Extract")

        outer.addWidget(sub_tabs)