#!/usr/bin/env python3
"""
NFC GUI Application - PyQt5-based GUI for NFC tag reading/writing
Based on ACS ACR1252 USB NFC Reader/Writer
"""

import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QPushButton, QTextEdit,
                             QLineEdit, QCheckBox, QSpinBox, QGroupBox,
                             QMessageBox, QFrame, QProgressBar)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QIcon
import pyperclip
import subprocess
import webbrowser
from datetime import datetime
from .nfc_handler import NFCHandler, redirect_homebox_url


class NFCGui(QMainWindow):
    def __init__(self):
        super().__init__()

        # NFC Handler
        self.nfc_handler = NFCHandler(debug_mode=False)
        self.current_mode = "read"
        self.last_url = None

        # Setup UI
        self.init_ui()

        # Initialize NFC
        self.initialize_nfc()

    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("NFC Reader/Writer - ACS ACR1252 - v2.0.0")
        self.setGeometry(100, 100, 900, 700)

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
        self.read_btn.clicked.connect(self.set_read_mode)
        mode_layout.addWidget(self.read_btn)

        self.write_btn = QPushButton("Write Mode")
        self.write_btn.setObjectName("writeBtn")
        self.write_btn.clicked.connect(self.set_write_mode)
        mode_layout.addWidget(self.write_btn)

        mode_layout.addStretch()
        control_layout.addLayout(mode_layout)

        # URL input - Write mode only
        self.url_label = QLabel("URL:")
        self.url_layout = QHBoxLayout()
        self.url_layout.addWidget(self.url_label)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter URL to write to tag...")
        self.url_layout.addWidget(self.url_input, 1)

        self.paste_btn = QPushButton("Paste")
        self.paste_btn.setObjectName("secondaryBtn")
        self.paste_btn.clicked.connect(self.paste_url)
        self.url_layout.addWidget(self.paste_btn)

        control_layout.addLayout(self.url_layout)

        # Options - Write mode only
        self.options_layout = QHBoxLayout()

        self.lock_checkbox = QCheckBox("Lock tag after writing")
        self.lock_checkbox.setChecked(True)
        self.options_layout.addWidget(self.lock_checkbox)

        self.overwrite_checkbox = QCheckBox("Allow overwrite")
        self.overwrite_checkbox.setChecked(False)
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
        self.batch_layout.addWidget(self.batch_spinbox)

        self.write_tags_btn = QPushButton("Write Tag(s)")
        self.write_tags_btn.setObjectName("actionBtn")
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

        # Log area
        log_group = QGroupBox("Activity Log")
        log_layout = QVBoxLayout()

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)

        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group, 1)

        # Bottom buttons
        bottom_layout = QHBoxLayout()

        clear_btn = QPushButton("Clear Log")
        clear_btn.setObjectName("secondaryBtn")
        clear_btn.clicked.connect(self.clear_log)
        bottom_layout.addWidget(clear_btn)

        copy_btn = QPushButton("Copy Last URL")
        copy_btn.setObjectName("secondaryBtn")
        copy_btn.clicked.connect(self.copy_last_url)
        bottom_layout.addWidget(copy_btn)

        open_btn = QPushButton("Open Last URL")
        open_btn.setObjectName("secondaryBtn")
        open_btn.clicked.connect(self.open_last_url)
        bottom_layout.addWidget(open_btn)

        bottom_layout.addStretch()
        main_layout.addLayout(bottom_layout)

    def log_message(self, message, level="info"):
        """Log a message with timestamp and color coding

        Args:
            message: The message to log
            level: One of 'success', 'error', 'warning', 'info'
        """
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Color mapping
        colors = {
            'success': '#4CAF50',  # Green
            'error': '#f44336',    # Red
            'warning': '#ff9800',  # Orange
            'info': '#2196F3'      # Blue
        }

        color = colors.get(level, colors['info'])

        # Insert colored log entry
        self.log_text.append(f'<span style="color: {color};">[{timestamp}] {message}</span>')

    def initialize_nfc(self):
        """Initialize NFC reader"""
        try:
            if self.nfc_handler.initialize_reader():
                self.status_label.setText(f"Status: Connected - {self.nfc_handler.reader}")
                self.status_label.setStyleSheet("background-color: #4CAF50; color: white;")
                self.log_message(f"NFC Reader initialized: {self.nfc_handler.reader}", "success")

                # Start monitoring
                self.nfc_handler.start_monitoring(
                    read_callback=self.on_tag_read,
                    write_callback=self.on_tag_written,
                    log_callback=self.log_message
                )

                # Start in read mode
                self.set_read_mode()
            else:
                self.status_label.setText("Status: No reader found")
                self.status_label.setStyleSheet("background-color: #f44336; color: white;")
                self.log_message("No NFC reader found. Please connect ACS ACR1252.", "error")
                QMessageBox.critical(self, "Error", "No NFC reader found.\nPlease connect ACS ACR1252 USB reader.")
        except Exception as e:
            self.status_label.setText("Status: Error")
            self.status_label.setStyleSheet("background-color: #f44336; color: white;")
            self.log_message(f"Error initializing reader: {e}", "error")
            QMessageBox.critical(self, "Error", f"Failed to initialize reader:\n{e}")

    def set_read_mode(self):
        """Switch to read mode"""
        self.current_mode = "read"
        self.nfc_handler.set_read_mode()
        self.log_message("Switched to READ mode - Present NFC tag to read")
        self.status_label.setText("Status: Connected - READ MODE")
        self.status_label.setStyleSheet("background-color: #4CAF50; color: white;")

        # Hide write-mode controls
        self._toggle_write_controls(False)

    def set_write_mode(self):
        """Switch to write mode"""
        self.current_mode = "write"
        self.log_message("Switched to WRITE mode - Enter URL and click 'Write Tag(s)'")
        self.status_label.setText("Status: Connected - WRITE MODE")
        self.status_label.setStyleSheet("background-color: #2196F3; color: white;")

        # Show write-mode controls
        self._toggle_write_controls(True)

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
                self.log_message(f"Pasted URL from clipboard: {clipboard_content}", "info")
            else:
                self.log_message("Clipboard is empty", "warning")
                QMessageBox.warning(self, "Warning", "Clipboard is empty")
        except Exception as e:
            self.log_message(f"Failed to paste from clipboard: {e}", "error")
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
            self.log_message(f"Batch write mode: {batch_count} tags", "info")
            self.log_message(f"Writing URL: {url}", "info")
            self.log_message(f"Present first NFC tag (1/{batch_count})...", "info")
        else:
            self.progress_group.setVisible(False)
            self.log_message(f"Writing URL: {url}", "info")
            self.log_message("Present NFC tag to write...", "info")

    def on_tag_read(self, url):
        """Handle tag read event"""
        self.last_url = url
        self.log_message(f"Tag read: {url}", "success")

        # Copy to clipboard
        try:
            pyperclip.copy(url)
            self.log_message("URL copied to clipboard", "success")
        except Exception as e:
            self.log_message(f"Failed to copy to clipboard: {e}", "error")

        # Apply URL redirect
        redirected_url = redirect_homebox_url(url)
        if redirected_url != url:
            self.log_message(f"Redirected: {url} → {redirected_url}", "info")

        # Open in browser
        try:
            self.log_message(f"Opening browser: {redirected_url}", "info")
            result = subprocess.run(['xdg-open', redirected_url], check=True, capture_output=True)
        except Exception as e:
            self.log_message(f"Failed to open browser with xdg-open: {e}", "error")
            try:
                webbrowser.open(redirected_url)
                self.log_message(f"Opened with webbrowser fallback", "info")
            except Exception as e2:
                self.log_message(f"Failed to open with webbrowser: {e2}", "error")

    def on_tag_written(self, message):
        """Handle tag write event"""
        self.log_message(f"Write complete: {message}", "success")

        # Update batch progress
        if self.nfc_handler.batch_total > 1:
            # Update progress bar and label
            progress_percentage = int((self.nfc_handler.batch_count / self.nfc_handler.batch_total) * 100)
            self.progress_bar.setValue(progress_percentage)
            self.progress_label.setText(f"Tag {self.nfc_handler.batch_count} of {self.nfc_handler.batch_total}")

            if self.nfc_handler.batch_count < self.nfc_handler.batch_total:
                self.log_message(f"Present next tag ({self.nfc_handler.batch_count + 1}/{self.nfc_handler.batch_total})...", "info")
            else:
                self.log_message("Batch writing completed!", "success")
                self.progress_group.setVisible(False)  # Hide progress after completion
                QMessageBox.information(self, "Success", f"Successfully wrote {self.nfc_handler.batch_total} tags")

    def copy_last_url(self):
        """Copy last URL to clipboard"""
        if self.last_url:
            try:
                pyperclip.copy(self.last_url)
                self.log_message(f"Copied to clipboard: {self.last_url}", "success")
            except Exception as e:
                self.log_message(f"Failed to copy to clipboard: {e}", "error")
                QMessageBox.critical(self, "Error", f"Failed to copy to clipboard:\n{e}")
        else:
            self.log_message("No URL to copy - read a tag first", "warning")
            QMessageBox.warning(self, "Warning", "No URL to copy - read a tag first")

    def open_last_url(self):
        """Open last URL in browser"""
        if self.last_url:
            try:
                redirected_url = redirect_homebox_url(self.last_url)
                self.log_message(f"Opening browser: {redirected_url}", "info")
                subprocess.run(['xdg-open', redirected_url], check=True, capture_output=True)
            except Exception as e:
                self.log_message(f"Failed to open browser with xdg-open: {e}", "error")
                try:
                    webbrowser.open(redirected_url)
                    self.log_message(f"Opened with webbrowser fallback", "info")
                except Exception as e2:
                    self.log_message(f"Failed to open with webbrowser: {e2}", "error")
                    QMessageBox.critical(self, "Error", f"Failed to open browser:\n{e2}")
        else:
            self.log_message("No URL to open - read a tag first", "warning")
            QMessageBox.warning(self, "Warning", "No URL to open - read a tag first")

    def clear_log(self):
        """Clear the log area"""
        self.log_text.clear()
        self.log_message("Log cleared")

    def closeEvent(self, event):
        """Handle window close event"""
        reply = QMessageBox.question(self, 'Quit',
                                     'Do you want to quit?',
                                     QMessageBox.Yes | QMessageBox.No,
                                     QMessageBox.No)

        if reply == QMessageBox.Yes:
            self.nfc_handler.stop_monitoring()
            event.accept()
        else:
            event.ignore()


def main():
    """Main entry point"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Modern cross-platform style
    window = NFCGui()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
