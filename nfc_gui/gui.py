#!/usr/bin/env python3
"""
NFC GUI Application - PyQt5-based GUI for NFC tag reading/writing
Based on ACS ACR1252 USB NFC Reader/Writer
"""

import sys
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QLineEdit,
    QCheckBox,
    QSpinBox,
    QGroupBox,
    QMessageBox,
    QFrame,
    QProgressBar,
    QSystemTrayIcon,
    QMenu,
    QAction,
    QShortcut,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject, pyqtSlot
from PyQt5.QtGui import QFont, QIcon, QPixmap, QKeySequence
import pyperclip
import subprocess
import os
from .nfc_handler import NFCHandler
from .settings import Settings


class NFCSignals(QObject):
    """Signal emitter for thread-safe GUI updates"""

    tag_read = pyqtSignal(str)  # URL read from tag
    tag_written = pyqtSignal(str)  # Message about write completion
    tag_updated = pyqtSignal(str, str, bool)  # old_url, new_url, success
    outdated_detected = pyqtSignal(
        str, str
    )  # old_url, new_url (when old tag scanned in update mode)
    update_tag_scanned = pyqtSignal(
        str, str
    )  # original_url, suggested_url (empty if no match)
    locked_tag_with_url = pyqtSignal(str)  # URL from locked tag in write mode
    log_message = pyqtSignal(str, str)  # message, level


class SettingsDialog(QWidget):
    """Settings dialog for configuring URL rewrite rules and showing reader info."""

    def __init__(self, settings: Settings, reader_info: str = None, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.reader_info = reader_info
        self.parent_window = parent
        self.setWindowTitle("Settings")
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint)
        self.setMinimumWidth(500)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # Reader info section
        if self.reader_info:
            reader_group = QGroupBox("Connected Reader")
            reader_layout = QVBoxLayout()

            reader_label = QLabel(self.reader_info)
            reader_label.setStyleSheet("font-family: monospace; color: #333;")
            reader_label.setWordWrap(True)
            reader_layout.addWidget(reader_label)

            reader_group.setLayout(reader_layout)
            layout.addWidget(reader_group)

        # Voice announcements section
        voice_group = QGroupBox("Voice Announcements")
        voice_layout = QVBoxLayout()

        self.tts_checkbox = QCheckBox("Enable voice announcements")
        self.tts_checkbox.setChecked(self.settings.tts_enabled)
        self.tts_checkbox.setToolTip(
            "Play British accent voice announcements for events like 'Tag opened', 'Batch finished', etc."
        )
        voice_layout.addWidget(self.tts_checkbox)

        # Test button
        test_voice_btn = QPushButton("Test Voice")
        test_voice_btn.setMaximumWidth(120)
        test_voice_btn.clicked.connect(self.test_voice)
        voice_layout.addWidget(test_voice_btn)

        voice_group.setLayout(voice_layout)
        layout.addWidget(voice_group)

        # Write mode behavior section
        write_group = QGroupBox("Write Mode Behavior")
        write_layout = QVBoxLayout()

        self.open_locked_url_checkbox = QCheckBox(
            "Auto-switch to read mode when locked tag detected"
        )
        self.open_locked_url_checkbox.setChecked(self.settings.open_locked_tag_url)
        self.open_locked_url_checkbox.setToolTip(
            "In write mode: if a locked tag with a URL is detected, automatically open the URL in browser and switch to read mode"
        )
        write_layout.addWidget(self.open_locked_url_checkbox)

        write_group.setLayout(write_layout)
        layout.addWidget(write_group)

        # Source pattern section
        pattern_group = QGroupBox("Source URL Pattern (regex)")
        pattern_layout = QVBoxLayout()

        self.pattern_input = QLineEdit()
        self.pattern_input.setText(self.settings.source_pattern)
        self.pattern_input.setPlaceholderText(
            r"^https?://10\.0\.0\.\d+(?::\d+)?/+item/(.+)$"
        )
        self.pattern_input.textChanged.connect(self.update_test_result)
        pattern_layout.addWidget(self.pattern_input)

        pattern_help = QLabel(
            "Use (.+) to capture the item ID that will be appended to the target URL"
        )
        pattern_help.setStyleSheet("color: #666; font-size: 11px;")
        pattern_layout.addWidget(pattern_help)

        pattern_group.setLayout(pattern_layout)
        layout.addWidget(pattern_group)

        # Target URL section
        target_group = QGroupBox("Target Base URL")
        target_layout = QVBoxLayout()

        self.target_input = QLineEdit()
        self.target_input.setText(self.settings.target_base_url)
        self.target_input.setPlaceholderText("https://your-domain.com/item/")
        self.target_input.textChanged.connect(self.update_test_result)
        target_layout.addWidget(self.target_input)

        target_help = QLabel(
            "Item ID will be appended automatically (e.g., https://domain.com/item/{id})"
        )
        target_help.setStyleSheet("color: #666; font-size: 11px;")
        target_layout.addWidget(target_help)

        target_group.setLayout(target_layout)
        layout.addWidget(target_group)

        # Test section
        test_group = QGroupBox("Test Rewrite")
        test_layout = QVBoxLayout()

        test_url_layout = QHBoxLayout()
        test_url_layout.addWidget(QLabel("Test URL:"))
        self.test_input = QLineEdit()
        self.test_input.setPlaceholderText("http://10.0.0.1:3100/item/abc123")
        self.test_input.textChanged.connect(self.update_test_result)
        test_url_layout.addWidget(self.test_input)
        test_layout.addLayout(test_url_layout)

        result_layout = QHBoxLayout()
        result_layout.addWidget(QLabel("Result:"))
        self.result_label = QLabel("Enter a test URL above")
        self.result_label.setStyleSheet("color: #666;")
        self.result_label.setWordWrap(True)
        result_layout.addWidget(self.result_label, 1)
        test_layout.addLayout(result_layout)

        test_group.setLayout(test_layout)
        layout.addWidget(test_group)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.close)
        button_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(
            "background-color: #4CAF50; color: white; font-weight: bold;"
        )
        save_btn.clicked.connect(self.save_settings)
        button_layout.addWidget(save_btn)

        layout.addLayout(button_layout)

    def update_test_result(self):
        """Update the test result preview."""
        test_url = self.test_input.text().strip()
        if not test_url:
            self.result_label.setText("Enter a test URL above")
            self.result_label.setStyleSheet("color: #666;")
            return

        pattern = self.pattern_input.text().strip()
        target = self.target_input.text().strip()

        if not pattern or not target:
            self.result_label.setText("Configure pattern and target first")
            self.result_label.setStyleSheet("color: #ff9800;")
            return

        import re

        try:
            match = re.match(pattern, test_url)
            if match:
                item_id = match.group(1)
                target_base = target.rstrip("/") + "/"
                result = f"{target_base}{item_id}"
                self.result_label.setText(result)
                self.result_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
            else:
                self.result_label.setText("Pattern does not match test URL")
                self.result_label.setStyleSheet("color: #f44336;")
        except re.error as e:
            self.result_label.setText(f"Invalid regex: {e}")
            self.result_label.setStyleSheet("color: #f44336;")

    def test_voice(self):
        """Play a test voice announcement."""
        if self.parent_window:
            self.parent_window._play_tts("tag_opened")

    def save_settings(self):
        """Save settings and close dialog."""
        pattern = self.pattern_input.text().strip()
        target = self.target_input.text().strip()

        if not pattern or not target:
            QMessageBox.warning(
                self, "Warning", "Please fill in both pattern and target URL"
            )
            return

        # Validate regex
        import re

        try:
            re.compile(pattern)
        except re.error as e:
            QMessageBox.critical(self, "Error", f"Invalid regex pattern:\n{e}")
            return

        self.settings.set_rewrite_rule(pattern, target)
        self.settings.tts_enabled = self.tts_checkbox.isChecked()
        self.settings.open_locked_tag_url = self.open_locked_url_checkbox.isChecked()
        if self.settings.save():
            QMessageBox.information(self, "Success", "Settings saved successfully")
            self.close()
        else:
            QMessageBox.critical(self, "Error", "Failed to save settings")


class NFCGui(QMainWindow):
    def __init__(self):
        super().__init__()

        # Load settings
        self.settings = Settings()

        # Create signals for thread-safe communication
        self.signals = NFCSignals()
        self.signals.tag_read.connect(self.on_tag_read)
        self.signals.tag_written.connect(self.on_tag_written)
        self.signals.tag_updated.connect(self.on_tag_updated)
        self.signals.outdated_detected.connect(self.on_outdated_detected)
        self.signals.update_tag_scanned.connect(self.on_update_tag_scanned)
        self.signals.locked_tag_with_url.connect(self.on_locked_tag_with_url)
        self.signals.log_message.connect(self.log_message)

        # NFC Handler with settings
        self.nfc_handler = NFCHandler(debug_mode=False, settings=self.settings)
        self.current_mode = "read"
        self.read_mode_type = (
            "default"  # "default" opens browser, "copy_url" only copies
        )
        self.last_url = None
        self.settings_dialog = None

        # Setup UI
        self.init_ui()

        # Setup system tray
        self.setup_system_tray()

        # Initialize NFC
        self.initialize_nfc()

    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("NFC Reader/Writer - ACS ACR1252 - v1.4.11")
        self.setGeometry(100, 100, 800, 500)

        # Set modern stylesheet with contemporary design
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f8fafc;
            }
            QGroupBox {
                font-weight: 600;
                font-size: 13px;
                color: #475569;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                margin-top: 16px;
                padding: 16px 12px 12px 12px;
                background-color: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 16px;
                padding: 0 8px;
                background-color: #ffffff;
            }
            QPushButton {
                padding: 10px 20px;
                border-radius: 8px;
                font-weight: 600;
                min-width: 120px;
                font-size: 13px;
                border: none;
            }
            QPushButton:pressed {
                padding-top: 11px;
                padding-bottom: 9px;
            }
            QPushButton#readBtn {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #22c55e, stop:1 #16a34a);
                color: white;
                min-width: 140px;
            }
            QPushButton#readBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #16a34a, stop:1 #15803d);
            }
            QPushButton#copyUrlBtn {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #06b6d4, stop:1 #0891b2);
                color: white;
                min-width: 140px;
            }
            QPushButton#copyUrlBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #0891b2, stop:1 #0e7490);
            }
            QPushButton#writeBtn {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3b82f6, stop:1 #2563eb);
                color: white;
                min-width: 140px;
            }
            QPushButton#writeBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2563eb, stop:1 #1d4ed8);
            }
            QPushButton#updateBtn {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #a855f7, stop:1 #9333ea);
                color: white;
                min-width: 140px;
            }
            QPushButton#updateBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #9333ea, stop:1 #7e22ce);
            }
            QPushButton#actionBtn {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #f97316, stop:1 #ea580c);
                color: white;
                padding: 14px 28px;
                font-size: 14px;
                min-width: 150px;
            }
            QPushButton#actionBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ea580c, stop:1 #c2410c);
            }
            QPushButton#secondaryBtn {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #64748b, stop:1 #475569);
                color: white;
            }
            QPushButton#secondaryBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #475569, stop:1 #334155);
            }
            QLineEdit {
                padding: 10px 12px;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                background-color: #ffffff;
                font-size: 13px;
                selection-background-color: #3b82f6;
            }
            QLineEdit:focus {
                border: 2px solid #3b82f6;
                padding: 9px 11px;
            }
            QTextEdit {
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                background-color: #ffffff;
                font-family: 'SF Mono', 'Consolas', monospace;
                padding: 8px;
            }
            QCheckBox {
                spacing: 10px;
                font-size: 13px;
                color: #334155;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 2px solid #cbd5e1;
                background-color: #ffffff;
            }
            QCheckBox::indicator:checked {
                background-color: #3b82f6;
                border-color: #3b82f6;
            }
            QCheckBox::indicator:hover {
                border-color: #3b82f6;
            }
            QLabel#statusLabel {
                padding: 12px 16px;
                border-radius: 10px;
                font-weight: 600;
                font-size: 13px;
            }
            QSpinBox {
                padding: 8px 12px;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                background-color: #ffffff;
                font-size: 13px;
                min-width: 80px;
            }
            QSpinBox:focus {
                border: 2px solid #3b82f6;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                border: none;
                width: 20px;
            }
            QProgressBar {
                border: none;
                border-radius: 6px;
                background-color: #e2e8f0;
                height: 12px;
                text-align: center;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3b82f6, stop:1 #8b5cf6);
                border-radius: 6px;
            }
            QMessageBox {
                background-color: #ffffff;
            }
            QMessageBox QPushButton {
                min-width: 80px;
                padding: 8px 16px;
            }
        """)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(25, 25, 25, 25)

        # Header
        header_layout = QHBoxLayout()
        title_label = QLabel("NFC Reader/Writer")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title_label.setFont(title_font)
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        self.status_label = QLabel("Initializing...")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #fbbf24, stop:1 #f59e0b); color: white;"
        )
        header_layout.addWidget(self.status_label)

        # Settings button
        settings_btn = QPushButton("Settings")
        settings_btn.setObjectName("secondaryBtn")
        settings_btn.setToolTip("Configure URL rewrite settings")
        settings_btn.clicked.connect(self.open_settings)
        header_layout.addWidget(settings_btn)

        main_layout.addLayout(header_layout)

        # URL display box for Copy URL Mode (hidden by default)
        self.url_display_frame = QFrame()
        self.url_display_frame.setStyleSheet("""
            QFrame {
                background-color: #f0f9ff;
                border: 2px solid #06b6d4;
                border-radius: 10px;
                padding: 8px;
            }
        """)
        url_display_layout = QVBoxLayout(self.url_display_frame)
        url_display_layout.setContentsMargins(12, 8, 12, 8)

        url_display_header = QLabel("Copied URL:")
        url_display_header.setStyleSheet(
            "color: #0e7490; font-weight: 600; font-size: 12px; border: none;"
        )
        url_display_layout.addWidget(url_display_header)

        self.copied_url_display = QLabel("Present a tag to copy its URL")
        self.copied_url_display.setStyleSheet("""
            QLabel {
                color: #164e63;
                font-size: 14px;
                font-family: 'SF Mono', 'Consolas', monospace;
                padding: 8px;
                background-color: #ffffff;
                border: 1px solid #cffafe;
                border-radius: 6px;
            }
        """)
        self.copied_url_display.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.copied_url_display.setWordWrap(True)
        url_display_layout.addWidget(self.copied_url_display)

        self.url_display_frame.setVisible(False)  # Hidden by default
        main_layout.addWidget(self.url_display_frame)

        # Update mode UI frame (hidden by default)
        self.update_mode_frame = QFrame()
        self.update_mode_frame.setStyleSheet("""
            QFrame {
                background-color: #faf5ff;
                border: 2px solid #a855f7;
                border-radius: 10px;
                padding: 8px;
            }
        """)
        update_mode_layout = QVBoxLayout(self.update_mode_frame)
        update_mode_layout.setContentsMargins(12, 8, 12, 8)
        update_mode_layout.setSpacing(10)

        # Original URL display (read-only)
        original_url_header = QLabel("Scanned URL:")
        original_url_header.setStyleSheet(
            "color: #7e22ce; font-weight: 600; font-size: 12px; border: none;"
        )
        update_mode_layout.addWidget(original_url_header)

        self.update_original_url_display = QLabel("Present a tag to scan")
        self.update_original_url_display.setStyleSheet("""
            QLabel {
                color: #581c87;
                font-size: 13px;
                font-family: 'SF Mono', 'Consolas', monospace;
                padding: 8px;
                background-color: #ffffff;
                border: 1px solid #e9d5ff;
                border-radius: 6px;
            }
        """)
        self.update_original_url_display.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        self.update_original_url_display.setWordWrap(True)
        update_mode_layout.addWidget(self.update_original_url_display)

        # Target URL input (editable, pre-populated with suggestion)
        target_url_header = QLabel("New URL to write:")
        target_url_header.setStyleSheet(
            "color: #7e22ce; font-weight: 600; font-size: 12px; border: none;"
        )
        update_mode_layout.addWidget(target_url_header)

        target_input_layout = QHBoxLayout()
        self.update_target_url_input = QLineEdit()
        self.update_target_url_input.setPlaceholderText(
            "Auto-suggestion will appear here, or paste your own URL..."
        )
        self.update_target_url_input.setStyleSheet("""
            QLineEdit {
                padding: 10px 12px;
                border: 1px solid #e9d5ff;
                border-radius: 8px;
                background-color: #ffffff;
                font-size: 13px;
                font-family: 'SF Mono', 'Consolas', monospace;
            }
            QLineEdit:focus {
                border: 2px solid #a855f7;
                padding: 9px 11px;
            }
        """)
        target_input_layout.addWidget(self.update_target_url_input, 1)

        self.update_paste_btn = QPushButton("Paste")
        self.update_paste_btn.setObjectName("secondaryBtn")
        self.update_paste_btn.clicked.connect(self.paste_update_url)
        target_input_layout.addWidget(self.update_paste_btn)

        update_mode_layout.addLayout(target_input_layout)

        # Confirm button
        confirm_layout = QHBoxLayout()
        confirm_layout.addStretch()

        self.update_confirm_btn = QPushButton("Confirm & Ready to Write")
        self.update_confirm_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #a855f7, stop:1 #9333ea);
                color: white;
                font-weight: 600;
                padding: 12px 24px;
                border-radius: 8px;
                font-size: 14px;
                min-width: 180px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #9333ea, stop:1 #7e22ce);
            }
            QPushButton:disabled {
                background: #d4d4d4;
                color: #737373;
            }
        """)
        self.update_confirm_btn.setEnabled(False)
        self.update_confirm_btn.clicked.connect(self.confirm_update_write)
        confirm_layout.addWidget(self.update_confirm_btn)

        self.update_cancel_btn = QPushButton("Cancel")
        self.update_cancel_btn.setObjectName("secondaryBtn")
        self.update_cancel_btn.clicked.connect(self.cancel_update)
        self.update_cancel_btn.setVisible(False)
        confirm_layout.addWidget(self.update_cancel_btn)

        confirm_layout.addStretch()
        update_mode_layout.addLayout(confirm_layout)

        self.update_mode_frame.setVisible(False)  # Hidden by default
        main_layout.addWidget(self.update_mode_frame)

        # Control panel
        control_group = QGroupBox("Controls")
        control_layout = QVBoxLayout()

        # Mode selection - centered
        mode_layout = QHBoxLayout()
        mode_layout.addStretch()

        self.read_btn = QPushButton("Read Mode")
        self.read_btn.setObjectName("readBtn")
        self.read_btn.setToolTip(
            "Switch to read mode - automatically opens scanned URLs (Ctrl+R)"
        )
        self.read_btn.clicked.connect(self.set_read_mode)
        mode_layout.addWidget(self.read_btn)

        self.write_btn = QPushButton("Write Mode")
        self.write_btn.setObjectName("writeBtn")
        self.write_btn.setToolTip(
            "Switch to write mode - write URLs to NFC tags (Ctrl+W)"
        )
        self.write_btn.clicked.connect(self.set_write_mode)
        mode_layout.addWidget(self.write_btn)

        self.copy_url_btn = QPushButton("Copy URL Mode")
        self.copy_url_btn.setObjectName("copyUrlBtn")
        self.copy_url_btn.setToolTip(
            "Switch to copy URL mode - copies scanned URLs to clipboard without opening (Ctrl+Shift+R)"
        )
        self.copy_url_btn.clicked.connect(self.set_copy_url_mode)
        mode_layout.addWidget(self.copy_url_btn)

        self.update_btn = QPushButton("Update Mode")
        self.update_btn.setObjectName("updateBtn")
        self.update_btn.setToolTip(
            "Switch to update mode - rewrites old local URLs to new public format (Ctrl+U)"
        )
        self.update_btn.clicked.connect(self.set_update_mode)
        mode_layout.addWidget(self.update_btn)

        mode_layout.addStretch()
        control_layout.addLayout(mode_layout)

        # URL input - Write mode only
        self.url_label = QLabel("URL:")
        self.url_layout = QHBoxLayout()
        self.url_layout.addWidget(self.url_label)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter URL to write to tag...")
        self.url_input.textChanged.connect(
            self._on_url_changed
        )  # Auto-update on URL change
        self.url_layout.addWidget(self.url_input, 1)

        self.paste_btn = QPushButton("Paste")
        self.paste_btn.setObjectName("secondaryBtn")
        self.paste_btn.setToolTip("Paste URL from clipboard (Ctrl+V)")
        self.paste_btn.clicked.connect(self.paste_url)
        self.url_layout.addWidget(self.paste_btn)

        control_layout.addLayout(self.url_layout)

        # Options - Write mode only
        self.options_layout = QHBoxLayout()

        self.lock_checkbox = QCheckBox("Lock tag after writing")
        self.lock_checkbox.setChecked(True)
        self.lock_checkbox.setToolTip(
            "Lock tag to prevent further writes (recommended for single-use tags)"
        )
        self.lock_checkbox.stateChanged.connect(self._on_write_options_changed)
        self.options_layout.addWidget(self.lock_checkbox)

        self.overwrite_checkbox = QCheckBox("Allow overwrite")
        self.overwrite_checkbox.setChecked(False)
        self.overwrite_checkbox.setToolTip(
            "Allow writing to tags that already contain data"
        )
        self.overwrite_checkbox.stateChanged.connect(self._on_write_options_changed)
        self.options_layout.addWidget(self.overwrite_checkbox)

        self.options_layout.addStretch()
        control_layout.addLayout(self.options_layout)

        # Batch write - Write mode only
        self.batch_layout = QHBoxLayout()
        self.batch_label = QLabel("Batch count:")
        self.batch_layout.addWidget(self.batch_label)

        # Minus button
        self.batch_minus_btn = QPushButton("−")
        self.batch_minus_btn.setFixedSize(32, 32)
        self.batch_minus_btn.setToolTip("Decrease batch count")
        self.batch_minus_btn.clicked.connect(self._decrease_batch)
        self.batch_layout.addWidget(self.batch_minus_btn)

        self.batch_spinbox = QSpinBox()
        self.batch_spinbox.setMinimum(1)
        self.batch_spinbox.setMaximum(100)
        self.batch_spinbox.setValue(1)
        self.batch_spinbox.setToolTip("Number of tags to write with the same URL")
        self.batch_spinbox.valueChanged.connect(self._on_batch_changed)
        self.batch_spinbox.setButtonSymbols(QSpinBox.NoButtons)  # Hide built-in arrows
        self.batch_spinbox.setFixedWidth(50)
        self.batch_spinbox.setAlignment(Qt.AlignCenter)
        self.batch_layout.addWidget(self.batch_spinbox)

        # Plus button
        self.batch_plus_btn = QPushButton("+")
        self.batch_plus_btn.setFixedSize(32, 32)
        self.batch_plus_btn.setToolTip("Increase batch count")
        self.batch_plus_btn.clicked.connect(self._increase_batch)
        self.batch_layout.addWidget(self.batch_plus_btn)

        self.batch_layout.addStretch()
        control_layout.addLayout(self.batch_layout)

        control_group.setLayout(control_layout)
        main_layout.addWidget(control_group)

        # Batch progress indicator - Write mode only
        self.progress_group = QGroupBox("Batch Progress")
        progress_layout = QVBoxLayout()

        self.progress_label = QLabel("Not active")
        self.progress_label.setAlignment(Qt.AlignCenter)
        progress_font = QFont()
        progress_font.setPointSize(12)
        progress_font.setBold(True)
        self.progress_label.setFont(progress_font)
        progress_layout.addWidget(self.progress_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        progress_layout.addWidget(self.progress_bar)

        self.progress_group.setLayout(progress_layout)
        main_layout.addWidget(self.progress_group)
        self.progress_group.setVisible(False)  # Hidden by default

        # Simple status message area (replacing verbose activity log)
        self.status_message = QLabel("Ready - present an NFC tag")
        self.status_message.setAlignment(Qt.AlignCenter)
        self.status_message.setStyleSheet("""
            QLabel {
                padding: 24px;
                font-size: 15px;
                font-weight: 500;
                color: #475569;
                background-color: #ffffff;
                border-radius: 12px;
                border: 1px solid #e2e8f0;
            }
        """)
        self.status_message.setMinimumHeight(100)
        main_layout.addWidget(self.status_message)

        # Bottom buttons - centered
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        copy_btn = QPushButton("Copy Last URL")
        copy_btn.setObjectName("secondaryBtn")
        copy_btn.setToolTip("Copy the last scanned URL to clipboard")
        copy_btn.clicked.connect(self.copy_last_url)
        bottom_layout.addWidget(copy_btn)

        open_btn = QPushButton("Open Last URL")
        open_btn.setObjectName("secondaryBtn")
        open_btn.setToolTip("Open the last scanned URL in Chrome")
        open_btn.clicked.connect(self.open_last_url)
        bottom_layout.addWidget(open_btn)

        # Background mode button
        background_btn = QPushButton("Background Read Mode")
        background_btn.setObjectName("secondaryBtn")
        background_btn.setToolTip(
            "Minimize to tray and continuously read tags in background"
        )
        background_btn.clicked.connect(self.enable_background_mode)
        bottom_layout.addWidget(background_btn)

        bottom_layout.addStretch()
        main_layout.addLayout(bottom_layout)

        # Keyboard shortcuts for mode selection
        self.shortcut_read = QShortcut(QKeySequence("Ctrl+R"), self)
        self.shortcut_read.activated.connect(self.set_read_mode)

        self.shortcut_copy_url = QShortcut(QKeySequence("Ctrl+Shift+R"), self)
        self.shortcut_copy_url.activated.connect(self.set_copy_url_mode)

        self.shortcut_write = QShortcut(QKeySequence("Ctrl+W"), self)
        self.shortcut_write.activated.connect(self.set_write_mode)

        self.shortcut_update = QShortcut(QKeySequence("Ctrl+U"), self)
        self.shortcut_update.activated.connect(self.set_update_mode)

    def log_message(self, message, level="info"):
        """Update status message with color coding

        Args:
            message: The message to display
            level: One of 'success', 'error', 'warning', 'info'
        """
        # Modern color palette with subtle backgrounds
        styles = {
            "success": ("color: #166534; background-color: #f0fdf4;", "#22c55e"),
            "error": ("color: #991b1b; background-color: #fef2f2;", "#ef4444"),
            "warning": ("color: #9a3412; background-color: #fff7ed;", "#f97316"),
            "info": ("color: #1e40af; background-color: #eff6ff;", "#3b82f6"),
        }

        style, border_color = styles.get(level, styles["info"])

        self.status_message.setStyleSheet(f"""
            QLabel {{
                padding: 24px;
                font-size: 15px;
                font-weight: 500;
                {style}
                border-radius: 12px;
                border: 2px solid {border_color};
            }}
        """)
        self.status_message.setText(message)

        # Play TTS for error/warning messages from nfc_handler callbacks
        if level == "error" or level == "warning":
            msg_lower = message.lower()
            if "no url found" in msg_lower or "empty tag" in msg_lower:
                self._play_tts("no_tag_found")
            elif "communication error" in msg_lower:
                self._play_tts("comm_error")
            elif "failed to read" in msg_lower:
                self._play_tts("read_failed")

    def initialize_nfc(self):
        """Initialize NFC reader"""
        try:
            if self.nfc_handler.initialize_reader():
                self.status_label.setText("Connected")
                self.status_label.setStyleSheet(
                    "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #22c55e, stop:1 #16a34a); color: white;"
                )
                self.log_message("Reader connected", "success")

                # Start monitoring with signal emitters as callbacks (thread-safe)
                self.nfc_handler.start_monitoring(
                    read_callback=lambda url: self.signals.tag_read.emit(url),
                    write_callback=lambda msg: self.signals.tag_written.emit(msg),
                    update_callback=lambda old,
                    new,
                    success: self.signals.tag_updated.emit(old, new, success),
                    log_callback=lambda msg,
                    level="info": self.signals.log_message.emit(msg, level),
                    outdated_callback=lambda old,
                    new: self.signals.outdated_detected.emit(old, new),
                    update_scan_callback=lambda orig,
                    sugg: self.signals.update_tag_scanned.emit(orig, sugg),
                    locked_tag_callback=lambda url: self.signals.locked_tag_with_url.emit(
                        url
                    ),
                )

                # Start in read mode
                self.set_read_mode()
            else:
                self.status_label.setText("No Reader")
                self.status_label.setStyleSheet(
                    "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ef4444, stop:1 #dc2626); color: white;"
                )
                self.log_message("No NFC reader found", "error")
                self._play_tts("no_reader")
                QMessageBox.critical(
                    self,
                    "Error",
                    "No NFC reader found.\nPlease connect ACS ACR1252 USB reader.",
                )
        except Exception as e:
            self.status_label.setText("Error")
            self.status_label.setStyleSheet(
                "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ef4444, stop:1 #dc2626); color: white;"
            )
            self.log_message("Failed to connect to reader", "error")
            QMessageBox.critical(self, "Error", f"Failed to initialize reader:\n{e}")

    def set_read_mode(self):
        """Switch to read mode (default - opens URLs in browser)"""
        self.current_mode = "read"
        self.read_mode_type = "default"
        self.nfc_handler.set_read_mode()
        self.log_message("Ready to read - present NFC tag")

        # Update mode indicator (red underline on active button)
        self._update_mode_indicator(self.read_btn)

        # Hide write-mode controls and other mode displays
        self._toggle_write_controls(False)
        self.url_display_frame.setVisible(False)
        self.update_mode_frame.setVisible(False)

        self._play_tts("read_mode")

    def set_copy_url_mode(self):
        """Switch to copy URL mode (copies URLs to clipboard without opening browser)"""
        self.current_mode = "read"
        self.read_mode_type = "copy_url"
        self.nfc_handler.set_read_mode()
        self.log_message("Copy URL mode - present NFC tag to copy URL")

        # Update mode indicator (red underline on active button)
        self._update_mode_indicator(self.copy_url_btn)

        # Hide write-mode controls and update mode, show URL display
        self._toggle_write_controls(False)
        self.url_display_frame.setVisible(True)
        self.update_mode_frame.setVisible(False)
        self.copied_url_display.setText("Present a tag to copy its URL")

        self._play_tts("copy_url_mode")

    def set_write_mode(self):
        """Switch to write mode"""
        self.current_mode = "write"

        # Update mode indicator (red underline on active button)
        self._update_mode_indicator(self.write_btn)

        # Show write-mode controls, hide other mode displays
        self._toggle_write_controls(True)
        self.url_display_frame.setVisible(False)
        self.update_mode_frame.setVisible(False)

        # Auto-focus URL input for quick workflow
        self.url_input.setFocus()
        self.url_input.selectAll()  # Select any existing text

        # If there's already a URL in the input, apply it immediately
        url = self.url_input.text().strip()
        if url:
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            self.nfc_handler.set_write_mode(
                url,
                lock_after_write=self.lock_checkbox.isChecked(),
                allow_overwrite=self.overwrite_checkbox.isChecked(),
            )
            self.nfc_handler.batch_total = self.batch_spinbox.value()
            self.nfc_handler.batch_count = 0
            self.log_message("URL ready - present tag to write", "info")
        else:
            self.log_message("Ready to write - enter URL and present tag")

        self._play_tts("ready_to_write")

    def set_update_mode(self):
        """Switch to update mode - interactive: scan tag, edit/confirm URL, write to new tag"""
        self.current_mode = "update"
        self.nfc_handler.set_update_mode()

        self.log_message("Present a tag to scan its URL")

        # Update mode indicator (red underline on active button)
        self._update_mode_indicator(self.update_btn)

        # Hide write-mode controls and copy URL display
        self._toggle_write_controls(False)
        self.url_display_frame.setVisible(False)

        # Show update mode frame and reset its state
        self.update_mode_frame.setVisible(True)
        self.update_original_url_display.setText("Present a tag to scan")
        self.update_target_url_input.clear()
        self.update_target_url_input.setEnabled(False)
        self.update_confirm_btn.setEnabled(False)
        self.update_cancel_btn.setVisible(False)

        self._play_tts("update_mode")

    def open_settings(self):
        """Open the settings dialog"""
        if self.settings_dialog is None or not self.settings_dialog.isVisible():
            # Get reader info
            reader_info = (
                str(self.nfc_handler.reader)
                if self.nfc_handler.reader
                else "No reader connected"
            )
            self.settings_dialog = SettingsDialog(self.settings, reader_info, self)
            self.settings_dialog.show()
        else:
            self.settings_dialog.activateWindow()
            self.settings_dialog.raise_()

    def _toggle_write_controls(self, visible):
        """Show or hide write-mode specific controls"""
        # URL input controls
        self.url_label.setVisible(visible)
        self.url_input.setVisible(visible)
        self.paste_btn.setVisible(visible)

        # Options controls
        self.lock_checkbox.setVisible(visible)
        self.overwrite_checkbox.setVisible(visible)

        # Batch controls
        self.batch_label.setVisible(visible)
        self.batch_minus_btn.setVisible(visible)
        self.batch_spinbox.setVisible(visible)
        self.batch_plus_btn.setVisible(visible)

    def _update_mode_indicator(self, active_button):
        """Update the red underline indicator on mode buttons"""
        # Define base styles for each button (without underline)
        button_styles = {
            self.read_btn: """
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #22c55e, stop:1 #16a34a);
                    color: white;
                    min-width: 140px;
                    padding: 10px 20px;
                    border-radius: 8px;
                    font-weight: 600;
                    font-size: 13px;
                    border: none;
                    %s
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #16a34a, stop:1 #15803d);
                }
            """,
            self.write_btn: """
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #3b82f6, stop:1 #2563eb);
                    color: white;
                    min-width: 140px;
                    padding: 10px 20px;
                    border-radius: 8px;
                    font-weight: 600;
                    font-size: 13px;
                    border: none;
                    %s
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #2563eb, stop:1 #1d4ed8);
                }
            """,
            self.copy_url_btn: """
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #06b6d4, stop:1 #0891b2);
                    color: white;
                    min-width: 140px;
                    padding: 10px 20px;
                    border-radius: 8px;
                    font-weight: 600;
                    font-size: 13px;
                    border: none;
                    %s
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #0891b2, stop:1 #0e7490);
                }
            """,
            self.update_btn: """
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #a855f7, stop:1 #9333ea);
                    color: white;
                    min-width: 140px;
                    padding: 10px 20px;
                    border-radius: 8px;
                    font-weight: 600;
                    font-size: 13px;
                    border: none;
                    %s
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #9333ea, stop:1 #7e22ce);
                }
            """,
        }

        # Red underline style
        underline = "border-bottom: 3px solid #ef4444;"

        for btn, style_template in button_styles.items():
            if btn == active_button:
                btn.setStyleSheet(style_template % underline)
            else:
                btn.setStyleSheet(style_template % "")

    def paste_url(self):
        """Paste URL from clipboard and prepare for writing"""
        try:
            clipboard_content = pyperclip.paste().strip()
            if clipboard_content:
                # Clean URL: strip any characters before http:// or https://
                # This handles cases where stray characters get prepended
                clipboard_content = self._clean_url(clipboard_content)

                # Switch to write mode if not already
                if self.current_mode != "write":
                    self.set_write_mode()

                self.url_input.setText(clipboard_content)
                # _on_url_changed will handle updating the handler and TTS
            else:
                self.log_message("Clipboard is empty", "warning")
                QMessageBox.warning(self, "Warning", "Clipboard is empty")
        except Exception as e:
            self.log_message("Failed to paste from clipboard", "error")
            QMessageBox.critical(self, "Error", f"Failed to paste from clipboard:\n{e}")

    def _clean_url(self, url: str) -> str:
        """Clean URL by removing any characters before http:// or https://

        This handles cases where stray characters get prepended during paste
        (e.g., 'ahttps://example.com' -> 'https://example.com')
        """
        url = url.strip()
        if not url:
            return url

        # If URL already starts correctly, return as-is
        if url.startswith(('http://', 'https://')):
            return url

        # Look for http:// or https:// anywhere in the string
        for prefix in ('https://', 'http://'):
            pos = url.find(prefix)
            if pos > 0:
                # Found the prefix after some stray characters - strip them
                cleaned = url[pos:]
                return cleaned

        # No http prefix found - return original (https:// will be added later)
        return url

    def _on_url_changed(self, url: str):
        """Handle URL text changes - auto-update write mode configuration"""
        url = url.strip()
        if not url:
            return

        # Only auto-update when in write mode
        if self.current_mode != "write":
            return

        # Add https:// if not present
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        # Update the NFC handler with new URL
        self.nfc_handler.set_write_mode(
            url,
            lock_after_write=self.lock_checkbox.isChecked(),
            allow_overwrite=self.overwrite_checkbox.isChecked(),
        )

        # Preserve batch settings
        batch_count = self.batch_spinbox.value()
        if self.nfc_handler.batch_total != batch_count:
            self.nfc_handler.batch_total = batch_count
            self.nfc_handler.batch_count = 0

        # Play TTS and update status
        self._play_tts("url_updated")
        self.log_message("URL updated - present tag to write", "info")

    def _on_batch_changed(self, count: int):
        """Handle batch count changes - auto-update write mode configuration"""
        if self.current_mode != "write":
            return

        self.nfc_handler.batch_total = count
        self.nfc_handler.batch_count = 0

        # Show/hide progress indicator based on batch count
        if count > 1:
            self.progress_group.setVisible(True)
            self.progress_label.setText(f"Tag 0 of {count}")
            self.progress_bar.setValue(0)
        else:
            self.progress_group.setVisible(False)

    def _decrease_batch(self):
        """Decrease batch count by 1"""
        current = self.batch_spinbox.value()
        if current > self.batch_spinbox.minimum():
            self.batch_spinbox.setValue(current - 1)

    def _increase_batch(self):
        """Increase batch count by 1"""
        current = self.batch_spinbox.value()
        if current < self.batch_spinbox.maximum():
            self.batch_spinbox.setValue(current + 1)

    def _on_write_options_changed(self):
        """Handle lock/overwrite checkbox changes - auto-update write mode configuration"""
        if self.current_mode != "write":
            return

        url = self.url_input.text().strip()
        if not url:
            return

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        # Update the handler with new options
        self.nfc_handler.set_write_mode(
            url,
            lock_after_write=self.lock_checkbox.isChecked(),
            allow_overwrite=self.overwrite_checkbox.isChecked(),
        )

    def write_tags(self):
        """Write URL to tag(s)"""
        url = self.url_input.text().strip()

        if not url:
            QMessageBox.warning(self, "Warning", "Please enter a URL")
            return

        # Add https:// if not present
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        batch_count = self.batch_spinbox.value()

        # Set write mode
        self.nfc_handler.set_write_mode(
            url,
            lock_after_write=self.lock_checkbox.isChecked(),
            allow_overwrite=self.overwrite_checkbox.isChecked(),
        )

        # Set batch parameters
        self.nfc_handler.batch_count = 0
        self.nfc_handler.batch_total = batch_count

        # Show/update progress indicator for batch operations
        if batch_count > 1:
            self.progress_group.setVisible(True)
            self.progress_label.setText(f"Tag 0 of {batch_count}")
            self.progress_bar.setValue(0)
            self.log_message(f"Present tag 1 of {batch_count}")
        else:
            self.progress_group.setVisible(False)
            self.log_message("Present tag to write")

    @pyqtSlot(str)
    def on_tag_read(self, url):
        """Handle tag read event (thread-safe slot)"""
        self.last_url = url
        self._play_beep("read")  # Short beep for successful read

        # Copy to clipboard
        try:
            pyperclip.copy(url)
        except Exception:
            pass

        if self.read_mode_type == "copy_url":
            # Copy URL Mode: display URL and copy to clipboard, don't open browser
            self.copied_url_display.setText(url)
            self.log_message("URL copied to clipboard", "success")
            self._play_tts("url_copied")  # Voice announcement for copy mode
        else:
            # Default Read Mode: open in browser
            self.log_message("Tag read - opened in browser", "success")
            self._play_tts("tag_opened")  # Voice announcement
            self._open_in_browser(url)

    @pyqtSlot(str)
    def on_tag_written(self, message):
        """Handle tag write event (thread-safe slot)"""
        # Check for locked tag prevention first (must come before general "locked" check)
        is_locked_prevention = "writing prevented" in message.lower()
        is_locked_detected = "locked tag detected" in message.lower()
        is_success = "Written" in message and not is_locked_prevention

        if is_success:
            if "locked" in message.lower():
                self.log_message("Tag written and locked", "success")
            else:
                self.log_message("Tag written", "success")
            self._play_tts("tag_written")  # Voice announcement
        else:
            if is_locked_detected:
                # Locked tag without URL
                self.log_message("Locked tag detected", "error")
                self._play_tts("tag_locked_detected")
            elif is_locked_prevention:
                # Legacy message or edge case
                self.log_message("Locked tag - writing prevented", "error")
                self._play_tts("locked_write_prevented")
            elif "existing data" in message.lower() or "blocked" in message.lower():
                self.log_message("Write blocked: tag has existing data", "error")
                self._play_tts("tag_has_data")
            else:
                self.log_message("Write failed", "error")
                self._play_tts("write_failed")

        self._play_beep("write" if is_success else "error")

        # Update batch progress only on success
        if self.nfc_handler.batch_total > 1 and is_success:
            # Update progress bar and label
            progress_percentage = int(
                (self.nfc_handler.batch_count / self.nfc_handler.batch_total) * 100
            )
            self.progress_bar.setValue(progress_percentage)
            self.progress_label.setText(
                f"Tag {self.nfc_handler.batch_count} of {self.nfc_handler.batch_total}"
            )

            if self.nfc_handler.batch_count < self.nfc_handler.batch_total:
                self.log_message(
                    f"Present tag {self.nfc_handler.batch_count + 1} of {self.nfc_handler.batch_total}"
                )
            else:
                self.log_message("All tags written", "success")
                self.progress_group.setVisible(False)  # Hide progress after completion
                self._play_tts(
                    "batch_finished"
                )  # Voice announcement for batch complete
                QMessageBox.information(
                    self,
                    "Success",
                    f"Successfully wrote {self.nfc_handler.batch_total} tags",
                )

    @pyqtSlot(str, str)
    def on_outdated_detected(self, old_url, new_url):
        """Handle outdated tag detected event (step 1 of update mode)"""
        self._play_beep("read")  # Acknowledge the scan
        self._play_tts("outdated_tag_detected")  # Voice announcement
        self.log_message("Outdated tag detected - present new blank tag", "success")

        # Update status to show we're waiting for a new tag
        self.status_label.setText("PRESENT NEW TAG")
        self.status_label.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f97316, stop:1 #ea580c); color: white;"
        )

    @pyqtSlot(str, str, bool)
    def on_tag_updated(self, old_url, new_url, success):
        """Handle tag update event (thread-safe slot)"""
        if success:
            self.last_url = new_url
            self.log_message("New tag written and locked", "success")
            self._play_beep("write")  # Two-tone beep for update success
            self._play_tts("tag_updated")  # Voice announcement

            # Reset UI for next update
            self.status_label.setText("Connected")
            self.status_label.setStyleSheet(
                "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #22c55e, stop:1 #16a34a); color: white;"
            )
            self.update_original_url_display.setText("Present a tag to scan")
            self.update_target_url_input.clear()
            self.update_target_url_input.setEnabled(False)
            self.update_confirm_btn.setEnabled(False)
            self.update_cancel_btn.setVisible(False)
        else:
            if old_url == new_url:
                # URL didn't need rewriting (scanned in step 1)
                self.log_message("Tag doesn't match old URL pattern", "warning")
                self._play_tts("tag_up_to_date")
            else:
                self.log_message("Update failed", "error")
                self._play_beep("error")
                self._play_tts("update_failed")

    @pyqtSlot(str, str)
    def on_update_tag_scanned(self, original_url, suggested_url):
        """Handle tag scanned in update mode (interactive workflow)"""
        self._play_beep("read")  # Acknowledge the scan

        # Display the original URL
        self.update_original_url_display.setText(original_url)

        # Pre-populate target input with suggestion (if available)
        if suggested_url:
            self.update_target_url_input.setText(suggested_url)
            self.log_message(
                "URL matched - suggestion ready, edit or confirm", "success"
            )
            self._play_tts("url_validated")
        else:
            self.update_target_url_input.clear()
            self.log_message("No pattern match - paste your target URL", "warning")

        # Enable editing and confirm button
        self.update_target_url_input.setEnabled(True)
        self.update_target_url_input.setFocus()
        self.update_confirm_btn.setEnabled(True)
        self.update_cancel_btn.setVisible(True)

    @pyqtSlot(str)
    def on_locked_tag_with_url(self, url):
        """Handle locked tag with URL detected in write mode"""
        # Check if the setting is enabled
        if not self.settings.open_locked_tag_url:
            return

        # Store the URL
        self.last_url = url

        # Play TTS announcement
        self.play_sound("tag_url_switch_read")

        # Open in browser
        self._open_in_browser(url)

        # Switch to read mode
        self.set_read_mode()
        self.log_message(f"Tag with URL detected - switched to read mode", "info")

    def paste_update_url(self):
        """Paste URL from clipboard into update target input"""
        try:
            clipboard_content = pyperclip.paste().strip()
            if clipboard_content:
                # Clean URL: strip any stray characters before http://
                clipboard_content = self._clean_url(clipboard_content)
                self.update_target_url_input.setText(clipboard_content)
                self.update_target_url_input.setFocus()
            else:
                self.log_message("Clipboard is empty", "warning")
        except Exception as e:
            self.log_message("Failed to paste from clipboard", "error")

    def confirm_update_write(self):
        """Confirm the target URL and prepare to write to new tag"""
        target_url = self.update_target_url_input.text().strip()

        if not target_url:
            self.log_message("Enter a target URL first", "warning")
            return

        # Add https:// if not present
        if not target_url.startswith(("http://", "https://")):
            target_url = "https://" + target_url
            self.update_target_url_input.setText(target_url)

        # Store the confirmed URL and advance handler to write step
        original_url = self.update_original_url_display.text()
        self.nfc_handler.pending_original_url = original_url
        self.nfc_handler.pending_rewrite_url = target_url
        self.nfc_handler.update_step = "write_new"

        # Update UI to show we're ready for new tag
        self.status_label.setText("PRESENT NEW TAG")
        self.status_label.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f97316, stop:1 #ea580c); color: white;"
        )
        self.log_message("Present a blank tag to write", "info")
        self._play_tts("present_tag")

        # Disable further editing until write completes or cancel
        self.update_target_url_input.setEnabled(False)
        self.update_confirm_btn.setEnabled(False)

    def cancel_update(self):
        """Cancel the pending update operation"""
        self.nfc_handler.cancel_pending_update()

        # Reset UI
        self.status_label.setText("Connected")
        self.status_label.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #22c55e, stop:1 #16a34a); color: white;"
        )
        self.update_original_url_display.setText("Present a tag to scan")
        self.update_target_url_input.clear()
        self.update_target_url_input.setEnabled(False)
        self.update_confirm_btn.setEnabled(False)
        self.update_cancel_btn.setVisible(False)
        self.log_message("Update cancelled - present a tag to scan")

    def copy_last_url(self):
        """Copy last URL to clipboard"""
        if self.last_url:
            try:
                pyperclip.copy(self.last_url)
                self.log_message("URL copied to clipboard", "success")
            except Exception as e:
                self.log_message("Failed to copy to clipboard", "error")
                QMessageBox.critical(
                    self, "Error", f"Failed to copy to clipboard:\n{e}"
                )
        else:
            self.log_message("No URL to copy - read a tag first", "warning")
            QMessageBox.warning(self, "Warning", "No URL to copy - read a tag first")

    def open_last_url(self):
        """Open last URL in browser"""
        if self.last_url:
            self._open_in_browser(self.last_url)
        else:
            QMessageBox.warning(self, "Warning", "No URL to open - read a tag first")

    def _open_in_browser(self, url: str):
        """Open URL in Chrome (or fallback browser)"""
        try:
            subprocess.Popen(
                ["google-chrome", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            try:
                subprocess.Popen(
                    ["chromium-browser", url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except FileNotFoundError:
                try:
                    subprocess.Popen(
                        ["xdg-open", url],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except Exception as e:
                    self.log_message(f"Failed to open browser: {e}", "error")

    def _play_beep(self, beep_type: str = "success"):
        """Play a confirmation beep sound

        Args:
            beep_type: Type of beep - "read" for single short beep,
                       "write" for two-tone success beep,
                       "error" for error sound
        """
        try:
            if beep_type == "read":
                # Single short beep for successful read
                sound = "/usr/share/sounds/freedesktop/stereo/message.oga"
                if os.path.exists(sound):
                    subprocess.Popen(
                        ["paplay", sound],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
            elif beep_type == "write":
                # Two-tone success beep for write & lock
                sound1 = "/usr/share/sounds/freedesktop/stereo/message.oga"
                sound2 = "/usr/share/sounds/freedesktop/stereo/complete.oga"
                if os.path.exists(sound1) and os.path.exists(sound2):
                    subprocess.Popen(
                        ["paplay", sound1],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    subprocess.Popen(
                        ["bash", "-c", f"sleep 0.15 && paplay {sound2}"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
            elif beep_type == "error":
                sound = "/usr/share/sounds/freedesktop/stereo/dialog-error.oga"
                if os.path.exists(sound):
                    subprocess.Popen(
                        ["paplay", sound],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
        except Exception:
            pass

    def _play_tts(self, announcement: str):
        """Play a TTS voice announcement

        Args:
            announcement: One of "tag_opened", "tag_written", "batch_started", "batch_finished"
        """
        if not self.settings.tts_enabled:
            return

        try:
            # Get the sounds directory relative to this module
            sounds_dir = os.path.join(os.path.dirname(__file__), "sounds")
            sound_file = os.path.join(sounds_dir, f"{announcement}.ogg")

            if os.path.exists(sound_file):
                subprocess.Popen(
                    ["paplay", sound_file],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except Exception:
            pass

    def setup_system_tray(self):
        """Setup system tray icon and menu"""
        # Create system tray icon
        self.tray_icon = QSystemTrayIcon(self)

        # Create a simple icon (colored circle)
        icon = self.create_tray_icon()
        self.tray_icon.setIcon(QIcon(icon))

        # Create tray menu
        tray_menu = QMenu()

        # Show/Hide window action
        show_action = QAction("Show Window", self)
        show_action.triggered.connect(self.show_window)
        tray_menu.addAction(show_action)

        hide_action = QAction("Minimize to Tray", self)
        hide_action.triggered.connect(self.hide_to_tray)
        tray_menu.addAction(hide_action)

        tray_menu.addSeparator()

        # Background read mode toggle
        self.background_read_action = QAction("Background Read Mode", self)
        self.background_read_action.setCheckable(True)
        self.background_read_action.setChecked(False)
        self.background_read_action.triggered.connect(self.toggle_background_read)
        tray_menu.addAction(self.background_read_action)

        tray_menu.addSeparator()

        # Quit action
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)

        # Double-click to show window
        self.tray_icon.activated.connect(self.tray_icon_activated)

        # Show the tray icon
        self.tray_icon.show()

        self.tray_icon.setToolTip("NFC Reader/Writer - Ready")

    def create_tray_icon(self):
        """Create a simple colored icon for system tray"""
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)

        from PyQt5.QtGui import QPainter, QColor

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw a blue circle
        painter.setBrush(QColor(33, 150, 243))  # Blue color
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(4, 4, 56, 56)

        painter.end()
        return pixmap

    def tray_icon_activated(self, reason):
        """Handle tray icon activation (click)"""
        if reason == QSystemTrayIcon.Trigger or reason == QSystemTrayIcon.DoubleClick:
            self.show_window()

    def show_window(self):
        """Show and restore the window"""
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
        self.activateWindow()

    def hide_to_tray(self):
        """Minimize window to system tray"""
        self.hide()
        self.tray_icon.showMessage(
            "NFC Reader/Writer",
            "Application minimized to system tray. Double-click icon to restore.",
            QSystemTrayIcon.Information,
            2000,
        )

    def enable_background_mode(self):
        """Enable background read mode from main window button"""
        self.background_read_action.setChecked(True)
        self.toggle_background_read(True)

    def toggle_background_read(self, checked):
        """Toggle background read mode"""
        if checked:
            # Enable background read mode
            self.set_read_mode()
            self.hide_to_tray()
            self.tray_icon.setToolTip("NFC Reader/Writer - Background Read Mode Active")
            self.tray_icon.showMessage(
                "Background Read Mode",
                "NFC reader is now in continuous read mode. Present tags to auto-open URLs.",
                QSystemTrayIcon.Information,
                3000,
            )
            self.log_message("Background mode active", "success")
            self._play_tts("background_mode")  # Voice announcement
        else:
            # Disable background read mode
            self.tray_icon.setToolTip("NFC Reader/Writer - Ready")
            self.tray_icon.showMessage(
                "Background Read Mode",
                "Background read mode disabled.",
                QSystemTrayIcon.Information,
                2000,
            )
            self.log_message("Background mode off")

    def quit_application(self):
        """Quit the application completely"""
        reply = QMessageBox.question(
            self,
            "Quit",
            "Do you want to quit the NFC Reader/Writer?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            self._play_tts("closing")  # Farewell announcement
            self.nfc_handler.stop_monitoring()
            self.tray_icon.hide()
            # Brief delay to let the TTS play
            from PyQt5.QtCore import QTimer

            QTimer.singleShot(1500, QApplication.quit)

    def closeEvent(self, event):
        """Handle window close event - minimize to tray instead of closing"""
        if self.tray_icon.isVisible():
            event.ignore()
            self.hide_to_tray()
        else:
            self.quit_application()
            event.accept()


def main():
    """Main entry point"""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # Modern cross-platform style
    window = NFCGui()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
