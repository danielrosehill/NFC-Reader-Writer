"""
Settings management for NFC GUI application.
Handles persistent configuration for URL rewriting rules.
"""

import json
import os
import re
from pathlib import Path
from typing import Tuple, Optional


class Settings:
    """Manages application settings with JSON persistence."""

    CONFIG_DIR = Path.home() / ".config" / "nfc-gui"
    CONFIG_FILE = CONFIG_DIR / "settings.json"

    # Default pattern matches http(s)://10.0.0.x(:port)/item/...
    DEFAULT_PATTERN = r"^https?://10\.0\.0\.\d+(?::\d+)?/+item/(.+)$"
    DEFAULT_TARGET = "https://your-domain.com/item/"

    def __init__(self):
        self.source_pattern: str = self.DEFAULT_PATTERN
        self.target_base_url: str = self.DEFAULT_TARGET
        self.tts_enabled: bool = True  # Voice announcements enabled by default
        self.auto_open_browser: bool = True  # Auto-open URLs in browser when reading tags
        self.open_locked_tag_url: bool = False  # Open URL and switch to read mode when locked tag detected in write mode
        self.verify_after_write: bool = True  # Verify writes by reading back and comparing
        self.use_password_protection: bool = False  # False = permanent lock, True = password protection
        self.tag_password: str = ""  # 4-character password for NTAG password protection
        self.load()

    def load(self) -> None:
        """Load settings from config file."""
        if self.CONFIG_FILE.exists():
            try:
                with open(self.CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    self.source_pattern = data.get('source_pattern', self.DEFAULT_PATTERN)
                    self.target_base_url = data.get('target_base_url', self.DEFAULT_TARGET)
                    self.tts_enabled = data.get('tts_enabled', True)
                    self.auto_open_browser = data.get('auto_open_browser', True)
                    self.open_locked_tag_url = data.get('open_locked_tag_url', False)
                    self.verify_after_write = data.get('verify_after_write', True)
                    self.use_password_protection = data.get('use_password_protection', False)
                    self.tag_password = data.get('tag_password', "")
            except (json.JSONDecodeError, IOError):
                # Use defaults if file is corrupted
                pass

    def save(self) -> bool:
        """Save settings to config file. Returns True on success."""
        try:
            self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(self.CONFIG_FILE, 'w') as f:
                json.dump({
                    'source_pattern': self.source_pattern,
                    'target_base_url': self.target_base_url,
                    'tts_enabled': self.tts_enabled,
                    'auto_open_browser': self.auto_open_browser,
                    'open_locked_tag_url': self.open_locked_tag_url,
                    'verify_after_write': self.verify_after_write,
                    'use_password_protection': self.use_password_protection,
                    'tag_password': self.tag_password
                }, f, indent=2)
            return True
        except IOError:
            return False

    def set_rewrite_rule(self, pattern: str, target: str) -> None:
        """Set the URL rewrite rule."""
        self.source_pattern = pattern
        self.target_base_url = target

    def is_configured(self) -> bool:
        """Check if settings have been configured (not using placeholder defaults)."""
        return self.target_base_url != self.DEFAULT_TARGET

    def rewrite_url(self, url: str) -> Tuple[str, bool]:
        """
        Rewrite URL using configured pattern and target.

        Args:
            url: The URL to potentially rewrite

        Returns:
            Tuple of (rewritten_url, was_rewritten)
        """
        if not self.source_pattern or not self.target_base_url:
            return url, False

        try:
            match = re.match(self.source_pattern, url)
            if match:
                # Extract the captured group (item ID)
                item_id = match.group(1)
                # Ensure target ends with / before appending
                target = self.target_base_url.rstrip('/') + '/'
                new_url = f"{target}{item_id}"
                return new_url, True
        except re.error:
            # Invalid regex pattern
            pass

        return url, False

    def test_rewrite(self, test_url: str) -> Optional[str]:
        """
        Test the rewrite rule with a sample URL.

        Args:
            test_url: URL to test

        Returns:
            Rewritten URL if pattern matches, None otherwise
        """
        new_url, was_rewritten = self.rewrite_url(test_url)
        return new_url if was_rewritten else None
