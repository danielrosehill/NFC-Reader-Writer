#!/usr/bin/env python3
"""
NFC GUI Application - PyQt5-based GUI for NFC tag reading/writing
Based on ACS ACR1252 USB NFC Reader/Writer
"""

import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QPushButton, QTextEdit,
                             QLineEdit, QCheckBox, QSpinBox, QGroupBox,
                             QMessageBox, QFrame, QProgressBar, QSystemTrayIcon,
                             QMenu, QAction)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject, pyqtSlot
from PyQt5.QtGui import QFont, QIcon, QPixmap
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

        self.tts_checkbox = QCheckBox("Enable voice announcements (British accent)")
        self.tts_checkbox.setChecked(self.settings.tts_enabled)
        self.tts_checkbox.setToolTip("Announce events like 'Tag opened', 'Batch finished' etc.")
        voice_layout.addWidget(self.tts_checkbox)

        # Test button
        test_voice_btn = QPushButton("Test Voice")
        test_voice_btn.setMaximumWidth(120)
        test_voice_btn.clicked.connect(self.test_voice)
        voice_layout.addWidget(test_voice_btn)

        voice_group.setLayout(voice_layout)
        layout.addWidget(voice_group)

        # Source pattern section
        pattern_group = QGroupBox("Source URL Pattern (regex)")
        pattern_layout = QVBoxLayout()

        self.pattern_input = QLineEdit()
        self.pattern_input.setText(self.settings.source_pattern)
        self.pattern_input.setPlaceholderText(r"^https?://10\.0\.0\.\d+(?::\d+)?/+item/(.+)$")
        self.pattern_input.textChanged.connect(self.update_test_result)
        pattern_layout.addWidget(self.pattern_input)

        pattern_help = QLabel("Use (.+) to capture the item ID that will be appended to the target URL")
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

        target_help = QLabel("Item ID will be appended automatically (e.g., https://domain.com/item/{id})")
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
        save_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
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
                target_base = target.rstrip('/') + '/'
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
            QMessageBox.warning(self, "Warning", "Please fill in both pattern and target URL")
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
        self.signals.log_message.connect(self.log_message)

        # NFC Handler with settings
        self.nfc_handler = NFCHandler(debug_mode=False, settings=self.settings)
        self.current_mode = "read"
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
        self.setWindowTitle("NFC Reader/Writer - ACS ACR1252 - v1.3.0")
        self.setGeometry(100, 100, 800, 500)

        # Set modern stylesheet
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #ddd;
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 10px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QPushButton {
                padding: 10px 20px;
                border-radius: 4px;
                font-weight: bold;
                min-width: 120px;
                font-size: 13px;
            }
            QPushButton#readBtn {
                background-color: #4CAF50;
                color: white;
                border: none;
                min-width: 140px;
            }
            QPushButton#readBtn:hover {
                background-color: #45a049;
            }
            QPushButton#writeBtn {
                background-color: #2196F3;
                color: white;
                border: none;
                min-width: 140px;
            }
            QPushButton#writeBtn:hover {
                background-color: #0b7dda;
            }
            QPushButton#updateBtn {
                background-color: #9C27B0;
                color: white;
                border: none;
                min-width: 140px;
            }
            QPushButton#updateBtn:hover {
                background-color: #7B1FA2;
            }
            QPushButton#actionBtn {
                background-color: #ff9800;
                color: white;
                border: none;
                padding: 14px 28px;
                font-size: 15px;
                min-width: 150px;
            }
            QPushButton#actionBtn:hover {
                background-color: #e68900;
            }
            QPushButton#secondaryBtn {
                background-color: #607D8B;
                color: white;
                border: none;
            }
            QPushButton#secondaryBtn:hover {
                background-color: #546E7A;
            }
            QLineEdit {
                padding: 8px;
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: white;
            }
            QTextEdit {
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: white;
                font-family: monospace;
            }
            QCheckBox {
                spacing: 8px;
            }
            QLabel#statusLabel {
                padding: 8px;
                border-radius: 4px;
                font-weight: bold;
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

        # Settings button
        settings_btn = QPushButton("Settings")
        settings_btn.setObjectName("secondaryBtn")
        settings_btn.setToolTip("Configure URL rewrite settings")
        settings_btn.clicked.connect(self.open_settings)
        header_layout.addWidget(settings_btn)

        self.status_label = QLabel("Status: Initializing...")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setStyleSheet("background-color: #FFC107; color: white;")
        header_layout.addWidget(self.status_label)

        main_layout.addLayout(header_layout)

        # Control panel
        control_group = QGroupBox("Controls")
        control_layout = QVBoxLayout()

        # Mode selection
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Mode:"))

        self.read_btn = QPushButton("Read Mode")
        self.read_btn.setObjectName("readBtn")
        self.read_btn.setToolTip("Switch to read mode - automatically opens scanned URLs")
        self.read_btn.clicked.connect(self.set_read_mode)
        mode_layout.addWidget(self.read_btn)

        self.write_btn = QPushButton("Write Mode")
        self.write_btn.setObjectName("writeBtn")
        self.write_btn.setToolTip("Switch to write mode - write URLs to NFC tags")
        self.write_btn.clicked.connect(self.set_write_mode)
        mode_layout.addWidget(self.write_btn)

        self.update_btn = QPushButton("Update Mode")
        self.update_btn.setObjectName("updateBtn")
        self.update_btn.setToolTip("Switch to update mode - rewrites old local URLs to new public format")
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
        self.url_input.returnPressed.connect(self.write_tags)  # Enter key to write
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
        self.lock_checkbox.setToolTip("Lock tag to prevent further writes (recommended for single-use tags)")
        self.options_layout.addWidget(self.lock_checkbox)

        self.overwrite_checkbox = QCheckBox("Allow overwrite")
        self.overwrite_checkbox.setChecked(False)
        self.overwrite_checkbox.setToolTip("Allow writing to tags that already contain data")
        self.options_layout.addWidget(self.overwrite_checkbox)

        self.options_layout.addStretch()
        control_layout.addLayout(self.options_layout)

        # Batch write - Write mode only
        self.batch_layout = QHBoxLayout()
        self.batch_label = QLabel("Batch count:")
        self.batch_layout.addWidget(self.batch_label)

        self.batch_spinbox = QSpinBox()
        self.batch_spinbox.setMinimum(1)
        self.batch_spinbox.setMaximum(100)
        self.batch_spinbox.setValue(1)
        self.batch_spinbox.setToolTip("Number of tags to write with the same URL")
        self.batch_layout.addWidget(self.batch_spinbox)

        self.write_tags_btn = QPushButton("Write Tag(s)")
        self.write_tags_btn.setObjectName("actionBtn")
        self.write_tags_btn.setToolTip("Start writing - present tag(s) to reader (Press Enter)")
        self.write_tags_btn.clicked.connect(self.write_tags)
        self.batch_layout.addWidget(self.write_tags_btn)

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
                padding: 20px;
                font-size: 16px;
                color: #333;
                background-color: #f0f0f0;
                border-radius: 8px;
                border: 1px solid #ddd;
            }
        """)
        self.status_message.setMinimumHeight(80)
        main_layout.addWidget(self.status_message)

        # Bottom buttons
        bottom_layout = QHBoxLayout()

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
        background_btn.setToolTip("Minimize to tray and continuously read tags in background")
        background_btn.clicked.connect(self.enable_background_mode)
        bottom_layout.addWidget(background_btn)

        bottom_layout.addStretch()
        main_layout.addLayout(bottom_layout)

    def log_message(self, message, level="info"):
        """Update status message with color coding

        Args:
            message: The message to display
            level: One of 'success', 'error', 'warning', 'info'
        """
        # Color and background mapping
        styles = {
            'success': ('color: #2e7d32; background-color: #e8f5e9;', '#4CAF50'),
            'error': ('color: #c62828; background-color: #ffebee;', '#f44336'),
            'warning': ('color: #ef6c00; background-color: #fff3e0;', '#ff9800'),
            'info': ('color: #1565c0; background-color: #e3f2fd;', '#2196F3')
        }

        style, border_color = styles.get(level, styles['info'])

        self.status_message.setStyleSheet(f"""
            QLabel {{
                padding: 20px;
                font-size: 16px;
                {style}
                border-radius: 8px;
                border: 2px solid {border_color};
            }}
        """)
        self.status_message.setText(message)

    def initialize_nfc(self):
        """Initialize NFC reader"""
        try:
            if self.nfc_handler.initialize_reader():
                self.status_label.setText(f"Status: Connected - {self.nfc_handler.reader}")
                self.status_label.setStyleSheet("background-color: #4CAF50; color: white;")
                self.log_message("Reader connected", "success")

                # Start monitoring with signal emitters as callbacks (thread-safe)
                self.nfc_handler.start_monitoring(
                    read_callback=lambda url: self.signals.tag_read.emit(url),
                    write_callback=lambda msg: self.signals.tag_written.emit(msg),
                    update_callback=lambda old, new, success: self.signals.tag_updated.emit(old, new, success),
                    log_callback=lambda msg, level="info": self.signals.log_message.emit(msg, level)
                )

                # Start in read mode
                self.set_read_mode()
            else:
                self.status_label.setText("Status: No reader found")
                self.status_label.setStyleSheet("background-color: #f44336; color: white;")
                self.log_message("No NFC reader found", "error")
                QMessageBox.critical(self, "Error", "No NFC reader found.\nPlease connect ACS ACR1252 USB reader.")
        except Exception as e:
            self.status_label.setText("Status: Error")
            self.status_label.setStyleSheet("background-color: #f44336; color: white;")
            self.log_message("Failed to connect to reader", "error")
            QMessageBox.critical(self, "Error", f"Failed to initialize reader:\n{e}")

    def set_read_mode(self):
        """Switch to read mode"""
        self.current_mode = "read"
        self.nfc_handler.set_read_mode()
        self.log_message("Ready to read - present NFC tag")
        self.status_label.setText("Status: Connected - READ MODE")
        self.status_label.setStyleSheet("background-color: #4CAF50; color: white;")

        # Hide write-mode controls
        self._toggle_write_controls(False)

    def set_write_mode(self):
        """Switch to write mode"""
        self.current_mode = "write"
        self.log_message("Ready to write - enter URL and present tag")
        self.status_label.setText("Status: Connected - WRITE MODE")
        self.status_label.setStyleSheet("background-color: #2196F3; color: white;")

        # Show write-mode controls
        self._toggle_write_controls(True)

        # Auto-focus URL input for quick workflow
        self.url_input.setFocus()
        self.url_input.selectAll()  # Select any existing text

    def set_update_mode(self):
        """Switch to update mode - rewrites old local URLs to new public format"""
        self.current_mode = "update"
        self.nfc_handler.set_update_mode()

        # Check if settings are configured
        if not self.settings.is_configured():
            self.log_message("Configure rewrite settings first", "warning")
        else:
            self.log_message("Ready to update - present tags to migrate URLs")

        self.status_label.setText("Status: Connected - UPDATE MODE")
        self.status_label.setStyleSheet("background-color: #9C27B0; color: white;")

        # Hide write-mode controls (update mode doesn't need URL input)
        self._toggle_write_controls(False)

    def open_settings(self):
        """Open the settings dialog"""
        if self.settings_dialog is None or not self.settings_dialog.isVisible():
            # Get reader info
            reader_info = str(self.nfc_handler.reader) if self.nfc_handler.reader else "No reader connected"
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
        self.batch_spinbox.setVisible(visible)
        self.write_tags_btn.setVisible(visible)

    def paste_url(self):
        """Paste URL from clipboard"""
        try:
            clipboard_content = pyperclip.paste().strip()
            if clipboard_content:
                self.url_input.setText(clipboard_content)
                self.log_message("URL pasted from clipboard", "info")
            else:
                self.log_message("Clipboard is empty", "warning")
                QMessageBox.warning(self, "Warning", "Clipboard is empty")
        except Exception as e:
            self.log_message("Failed to paste from clipboard", "error")
            QMessageBox.critical(self, "Error", f"Failed to paste from clipboard:\n{e}")

    def write_tags(self):
        """Write URL to tag(s)"""
        url = self.url_input.text().strip()

        if not url:
            QMessageBox.warning(self, "Warning", "Please enter a URL")
            return

        # Add https:// if not present
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        batch_count = self.batch_spinbox.value()

        # Set write mode
        self.nfc_handler.set_write_mode(
            url,
            lock_after_write=self.lock_checkbox.isChecked(),
            allow_overwrite=self.overwrite_checkbox.isChecked()
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
            self._play_tts("batch_started")  # Voice announcement for batch start
        else:
            self.progress_group.setVisible(False)
            self.log_message("Present tag to write")

    @pyqtSlot(str)
    def on_tag_read(self, url):
        """Handle tag read event (thread-safe slot)"""
        self.last_url = url
        self.log_message("Tag read - opened in browser", "success")
        self._play_beep("read")  # Short beep for successful read
        self._play_tts("tag_opened")  # Voice announcement

        # Copy to clipboard
        try:
            pyperclip.copy(url)
        except Exception:
            pass

        # Open in browser
        self._open_in_browser(url)

    @pyqtSlot(str)
    def on_tag_written(self, message):
        """Handle tag write event (thread-safe slot)"""
        is_success = "Written" in message or "locked" in message.lower()

        if is_success:
            if "locked" in message.lower():
                self.log_message("Tag written and locked", "success")
            else:
                self.log_message("Tag written", "success")
            self._play_tts("tag_written")  # Voice announcement
        else:
            self.log_message("Write failed", "error")

        self._play_beep("write" if is_success else "error")

        # Update batch progress
        if self.nfc_handler.batch_total > 1:
            # Update progress bar and label
            progress_percentage = int((self.nfc_handler.batch_count / self.nfc_handler.batch_total) * 100)
            self.progress_bar.setValue(progress_percentage)
            self.progress_label.setText(f"Tag {self.nfc_handler.batch_count} of {self.nfc_handler.batch_total}")

            if self.nfc_handler.batch_count < self.nfc_handler.batch_total:
                self.log_message(f"Present tag {self.nfc_handler.batch_count + 1} of {self.nfc_handler.batch_total}")
            else:
                self.log_message("All tags written", "success")
                self.progress_group.setVisible(False)  # Hide progress after completion
                self._play_tts("batch_finished")  # Voice announcement for batch complete
                QMessageBox.information(self, "Success", f"Successfully wrote {self.nfc_handler.batch_total} tags")

    @pyqtSlot(str, str, bool)
    def on_tag_updated(self, old_url, new_url, success):
        """Handle tag update event (thread-safe slot)"""
        if success:
            self.last_url = new_url
            self.log_message("Tag updated and locked", "success")
            self._play_beep("write")  # Two-tone beep for update success
            self._play_tts("tag_updated")  # Voice announcement
        else:
            if old_url == new_url:
                # URL didn't need rewriting
                self.log_message("Tag already up to date", "warning")
            else:
                self.log_message("Update failed", "error")
                self._play_beep("error")

    def copy_last_url(self):
        """Copy last URL to clipboard"""
        if self.last_url:
            try:
                pyperclip.copy(self.last_url)
                self.log_message("URL copied to clipboard", "success")
            except Exception as e:
                self.log_message("Failed to copy to clipboard", "error")
                QMessageBox.critical(self, "Error", f"Failed to copy to clipboard:\n{e}")
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
            subprocess.Popen(['google-chrome', url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            try:
                subprocess.Popen(['chromium-browser', url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except FileNotFoundError:
                try:
                    subprocess.Popen(['xdg-open', url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
                    subprocess.Popen(['paplay', sound], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif beep_type == "write":
                # Two-tone success beep for write & lock
                sound1 = "/usr/share/sounds/freedesktop/stereo/message.oga"
                sound2 = "/usr/share/sounds/freedesktop/stereo/complete.oga"
                if os.path.exists(sound1) and os.path.exists(sound2):
                    subprocess.Popen(['paplay', sound1], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    subprocess.Popen(
                        ['bash', '-c', f'sleep 0.15 && paplay {sound2}'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
            elif beep_type == "error":
                sound = "/usr/share/sounds/freedesktop/stereo/dialog-error.oga"
                if os.path.exists(sound):
                    subprocess.Popen(['paplay', sound], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
            sounds_dir = os.path.join(os.path.dirname(__file__), 'sounds')
            sound_file = os.path.join(sounds_dir, f"{announcement}.ogg")

            if os.path.exists(sound_file):
                subprocess.Popen(['paplay', sound_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
        if reason == QSystemTrayIcon.DoubleClick:
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
            2000
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
                3000
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
                2000
            )
            self.log_message("Background mode off")

    def quit_application(self):
        """Quit the application completely"""
        reply = QMessageBox.question(self, 'Quit',
                                     'Do you want to quit the NFC Reader/Writer?',
                                     QMessageBox.Yes | QMessageBox.No,
                                     QMessageBox.No)

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
    app.setStyle('Fusion')  # Modern cross-platform style
    window = NFCGui()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
