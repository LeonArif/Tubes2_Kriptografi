import os
import shutil
import tempfile
import cv2
from PyQt5 import QtCore, QtGui, QtWidgets
from gui import (PrimaryButton, show_video_preview, create_preview_column, StegoWorker, BASE_DIR, OUTPUT_VIDEO_DIR, OUTPUT_MESSAGE_DIR, frame_to_pixmap, create_hist_panel, update_metrics_ui, estimate_payload_bits,)

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
        self.capacity_label.setStyleSheet("color: #76944C; font-size: 9pt; background: transparent;")

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
        self.ffmpeg_label.setStyleSheet("color: #76944C; font-size: 9pt; background: transparent;" if ffmpeg_ok else "color: #B03A2E; font-size: 9pt; background: transparent;")
        
        self.start_btn = PrimaryButton("ᯓ➤ Embed (MP4) ✮⋆˙")
        self.start_btn.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.start_btn.setMinimumWidth(340)

        orig_block, self.original_preview_label, self.original_info_label = create_preview_column(
            "Original Video", "Original preview will appear here"
        )
        stego_block, self.stego_preview_label, self.stego_info_label = create_preview_column(
            "Stego Video", "Stego preview will appear here"
        )

        self.metrics_label = QtWidgets.QLabel("MSE: - | PSNR: - dB | Capacity: - / Payload: -")
        self.metrics_label.setAlignment(QtCore.Qt.AlignCenter)
        self.metrics_label.setObjectName("metricsLabel")
        self.metrics_label.setStyleSheet("font-weight: 600; color: #76944C;")

        hist_widget, self.orig_hist_label, self.stego_hist_label = create_hist_panel()

        comparison_widget = QtWidgets.QWidget()
        comparison_widget.setObjectName("comparisonCard")
        comparison_layout = QtWidgets.QVBoxLayout(comparison_widget)
        comparison_layout.setSpacing(12)
        comparison_layout.setContentsMargins(16, 12, 16, 12)
        comparison_title = QtWidgets.QLabel("⇄ Comparison ⇄")
        comparison_title.setAlignment(QtCore.Qt.AlignCenter)
        comparison_title.setObjectName("sectionTitle")
        comparison_title.setStyleSheet("background: transparent; color: #FBF5DB;")
        comparison_layout.addWidget(comparison_title)
        orig_block.setContentsMargins(8, 8, 8, 8)
        orig_block.setSpacing(8)
        stego_block.setContentsMargins(8, 8, 8, 8)
        stego_block.setSpacing(8)
        comparison_layout.addLayout(orig_block, 1)
        comparison_layout.addLayout(stego_block, 1)
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
        left_layout.setSpacing(14); left_layout.setContentsMargins(12, 0, 12, 0)
        title = QtWidgets.QLabel("✿ Embed Message (MP4) ✉︎")
        title.setObjectName("sectionTitle"); title.setAlignment(QtCore.Qt.AlignLeft)
        left_layout.addWidget(title)
        left_layout.addLayout(form)
        left_layout.addWidget(self.progress)

        right_widget = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        right_layout.addWidget(self.metrics_label)
        row_container = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(row_container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)
        comparison_widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        comparison_widget.setContentsMargins(10, 10, 10, 10)

        hist_widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        hist_widget.setContentsMargins(10, 10, 10, 10)

        grid.addWidget(comparison_widget, 0, 0)
        grid.addWidget(hist_widget,       0, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(0, 1)

        row_container.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        right_layout.addWidget(row_container)

        main_split = QtWidgets.QHBoxLayout()
        main_split.setSpacing(16)
        main_split.addWidget(left_widget, 2)
        main_split.addWidget(right_widget, 3)

        try:
            MAX_H = 16777215
            PREVIEW_STYLE = "border: 2px dashed #FFD21F; background: #FBF5DB; border-radius: 8px;"

            for lbl in (self.original_preview_label, self.stego_preview_label):
                lbl.setMinimumWidth(260)
                lbl.setFixedHeight(140)
                lbl.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
                lbl.setStyleSheet(PREVIEW_STYLE)

            for hlbl in (self.orig_hist_label, self.stego_hist_label):
                hlbl.setMinimumWidth(260)
                hlbl.setFixedHeight(140)
                hlbl.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
                hlbl.setStyleSheet(PREVIEW_STYLE)

            try:
                comparison_layout.setStretch(0, 0)  
                comparison_layout.setStretch(1, 1) 
                comparison_layout.setStretch(2, 1)
            except Exception:
                pass

            try:
                h_layout = hist_widget.layout()
                h_layout.setStretch(0, 0)
                h_layout.setStretch(1, 1)
                h_layout.setStretch(2, 1)
            except Exception:
                pass

            self.original_info_label.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
            self.stego_info_label.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        except Exception:
            pass

        outer_layout = QtWidgets.QVBoxLayout(self)
        outer_layout.setContentsMargins(20, 20, 20, 20)
        outer_layout.setSpacing(14)
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

    def _toggle_encrypt(self, checked):
        self.encrypt_key_edit.setEnabled(checked)

    def _toggle_stego_key(self, mode):
        self.stego_key_edit.setEnabled(mode == "random")

    def _update_payload_type(self):
        self.payload_stack.setCurrentIndex(0 if self.payload_text_radio.isChecked() else 1)

    def _update_capacity(self, path):
        path = path.strip()
        if not path or not os.path.isfile(path):
            self.capacity_label.setText("Capacity: —")
            return
        try:
            cap_bytes = get_mp4_capacity(path)
            self.capacity_label.setText(f"Capacity: {cap_bytes:,} bytes  ({cap_bytes / 1024:.1f} KB)")
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
        show_video_preview(self, self.video_path_edit.text().strip())

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

        invalid_input = any([
            not video_path or not os.path.isfile(video_path),
            payload_type == "text" and not text_content,
            payload_type == "file" and (not file_payload or not os.path.isfile(file_payload)),
            encrypt_payload and not a51_key,
            mode == "random" and not stego_key,
        ])
        if invalid_input:
            return self._input_error()

        try:
            cap_bytes = get_mp4_capacity(video_path)
            capacity_bits = cap_bytes * 8
            payload_bits = estimate_payload_bits(payload_type, text_content, file_payload, encrypt_payload, mode)
            if payload_bits > capacity_bits:
                self._show_capacity_warning(capacity_bits, payload_bits)
                return
        except Exception:
            pass

        self._stop_comparison_preview()
        self._set_busy(True)
        self.embed_worker = StegoWorker(insert_message_to_mp4, video_path=video_path, payload_type=payload_type, text_content=text_content, file_path=file_payload, encrypt_payload=encrypt_payload, a51_key=a51_key, mode=mode, stego_key=stego_key, output_dir=OUTPUT_VIDEO_DIR, output_ext="_stego_mp4.mp4")
        self.embed_worker.finished.connect(self._on_embed_finished)
        self.embed_worker.error.connect(self._on_embed_error)
        self.embed_worker.start()

    def _show_capacity_warning(self, capacity_bits: int, payload_bits: int):
        cap_bytes = capacity_bits / 8
        pay_bytes = payload_bits / 8
        QtWidgets.QMessageBox.warning(
            self,"Payload melebihi kapasitas",
            (f"Payload ({pay_bytes:,.0f} bytes) lebih besar dari kapasitas video ({cap_bytes:,.0f} bytes).\n"
                "Kurangi ukuran pesan atau pilih video dengan kapasitas lebih besar."
            ),
        )

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
        self.original_info_label.setText(f"Resolution: {int(orig_cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(orig_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")
        self.stego_info_label.setText(f"Resolution: {int(stego_cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(stego_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")
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
        for frame, label in ((frame_orig, self.original_preview_label), (frame_stego, self.stego_preview_label)):
            label.setPixmap(frame_to_pixmap(frame, label))

    def _set_busy(self, busy: bool):
        self._set_inputs_enabled(not busy)
        self.progress.setVisible(busy); self.progress.setRange(0, 0 if busy else 1)

    def _set_inputs_enabled(self, enabled: bool):
        for w in (self.video_path_edit, self.browse_btn, self.preview_btn,
                  self.payload_text_radio, self.payload_file_radio,
                  self.message_edit, self.file_payload_edit, self.file_payload_browse,
                  self.encrypt_check, self.encrypt_key_edit,
                  self.mode_combo, self.stego_key_edit, self.start_btn):
            w.setEnabled(enabled)

    def _on_embed_finished(self, result):
        self._set_busy(False)
        self.embed_worker = None
        if isinstance(result, dict):
            output_path = result.get("actual_output") or result.get("output_path") or ""
            metrics = result.get("metrics")
        else:
            output_path = str(result)
            metrics = None

        if metrics:
            try:
                update_metrics_ui(self, metrics)
            except Exception:
                pass
        self._start_comparison_preview(original_path=self.video_path_edit.text().strip(),stego_path=output_path,)
        QtWidgets.QMessageBox.information(self, "Success", f"Process completed successfully!\nSaved to:\n{output_path}")

    def _on_embed_error(self, message: str):
        self._set_busy(False)
        self.embed_worker = None
        warn_prefix = "Payload terlalu besar"
        if message and warn_prefix.lower() in message.lower():
            QtWidgets.QMessageBox.warning(
                self,
                "Payload melebihi kapasitas",
                "Payload lebih besar dari kapasitas video. Kurangi ukuran pesan atau pilih video dengan kapasitas lebih besar.\n\n" + message,
            )
        else:
            QtWidgets.QMessageBox.critical(
                self,
                "Error",
                f"Something went wrong. Please check your input.\n{message}",
            )

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
        self.start_btn.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
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
        show_video_preview(self, self.stego_path_edit.text().strip())

    def _start_extract(self):
        stego_path  = self.stego_path_edit.text().strip()
        encrypted   = self.encrypted_check.isChecked()
        a51_key     = self.a51_key_edit.text() if encrypted else None
        random_mode = self.random_check.isChecked()
        stego_key   = self.stego_key_edit.text().strip() if random_mode else None

        if any([
            not stego_path or not os.path.isfile(stego_path),
            encrypted and not a51_key,
            random_mode and not stego_key,
        ]):
            QtWidgets.QMessageBox.critical(self, "Error", "Something went wrong. Please check your input.")
            return

        self.result_view.clear()
        self.file_name_label.setText("File: -")
        self.file_path_label.setText("Saved to: -")
        self.open_folder_btn.setVisible(False)
        self._last_saved_dir = None
        self._set_result_visible(text_visible=True, file_visible=True)
        self._set_busy(True)

        save_as = self.save_as_edit.text().strip() or None

        self.extract_worker = StegoWorker(extract_message_from_mp4, stego_video_path=stego_path, a51_key=a51_key, stego_key=stego_key, save_as_path=save_as, output_dir=OUTPUT_MESSAGE_DIR)
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
        self.mp4_mode = "embed"
        self.embed_view = None
        self.extract_view = None

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(12)

        header = QtWidgets.QLabel("✦ MP4 Bonus Section ✦")
        header.setAlignment(QtCore.Qt.AlignCenter)
        header.setObjectName("sectionTitle")
        header.setStyleSheet("padding: 6px; background: transparent;")
        outer.addWidget(header)

        self.embed_btn = PrimaryButton("[ Embed MP4 ]")
        self.extract_btn = PrimaryButton("[ Extract MP4 ]")
        for btn in (self.embed_btn, self.extract_btn):
            btn.setMinimumWidth(160)
            btn.setCheckable(True)

        switch_row = QtWidgets.QHBoxLayout()
        switch_row.setSpacing(8)
        switch_row.addStretch(1)
        switch_row.addWidget(self.embed_btn)
        switch_row.addWidget(self.extract_btn)
        switch_row.addStretch(1)
        switch_wrap = QtWidgets.QWidget()
        switch_wrap.setObjectName("modeSwitcher")
        sw_layout = QtWidgets.QVBoxLayout(switch_wrap)
        sw_layout.setContentsMargins(8, 6, 8, 6)
        sw_layout.addLayout(switch_row)

        self.mp4_container = QtWidgets.QWidget()
        self.mp4_container.setObjectName("mp4Container")
        container_layout = QtWidgets.QVBoxLayout(self.mp4_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        outer.addWidget(switch_wrap)
        outer.addWidget(self.mp4_container)

        self.embed_btn.clicked.connect(lambda: self.switch_mp4_mode("embed"))
        self.extract_btn.clicked.connect(lambda: self.switch_mp4_mode("extract"))
        self._update_mode_buttons()
        self.render_mp4_content()

    def build_embed_mp4_ui(self, parent):
        if self.embed_view is None:
            self.embed_view = Mp4EmbedTab(parent)
        return self.embed_view

    def build_extract_mp4_ui(self, parent):
        if self.extract_view is None:
            self.extract_view = Mp4ExtractTab(parent)
        return self.extract_view

    def switch_mp4_mode(self, mode: str):
        if mode == self.mp4_mode:
            return
        self.mp4_mode = mode
        self._update_mode_buttons()
        self.render_mp4_content()

    def render_mp4_content(self):
        self.clear_container(self.mp4_container)
        target_layout = self.mp4_container.layout()
        widget = self.build_embed_mp4_ui(self.mp4_container) if self.mp4_mode == "embed" else self.build_extract_mp4_ui(self.mp4_container)
        target_layout.addWidget(widget)

    def clear_container(self, container: QtWidgets.QWidget):
        layout = container.layout()
        if not layout:
            return
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

    def _update_mode_buttons(self):
        is_embed = self.mp4_mode == "embed"
        self.embed_btn.setChecked(is_embed)
        self.extract_btn.setChecked(not is_embed)
        active_style = "background: #FFD21F; color: #76944C; border: 2px solid #76944C;"
        inactive_style = "background: #C8DAA6; color: #76944C; border: 1px solid #76944C;"
        self.embed_btn.setStyleSheet(active_style if is_embed else inactive_style)
        self.extract_btn.setStyleSheet(active_style if not is_embed else inactive_style)