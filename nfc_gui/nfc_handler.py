"""
NFC Handler for ACS ACR1252 USB NFC Reader/Writer
Handles reading and writing URLs to NTAG213/215/216 tags
Based on VladoPortos's ACR1252 implementation: https://github.com/VladoPortos/python-nfc-read-write-acr1252
"""

import ndef
import time
import re
from typing import Optional, Callable, Tuple
from smartcard.CardMonitoring import CardMonitor, CardObserver
from smartcard.CardConnection import CardConnection
from smartcard.System import readers


class NFCHandler:
    def __init__(self, debug_mode=False, settings=None):
        self.reader = None
        self.monitor = None
        self.observer = None
        self.is_monitoring = False
        self.read_callback = None
        self.write_callback = None
        self.update_callback = None  # Callback for update mode (old_url, new_url, success)
        self.log_callback = None
        self.mode = "read"  # "read", "write", or "update"
        self.url_to_write = None
        self.batch_count = 0
        self.batch_total = 0
        self.debug_mode = debug_mode
        self.cards_processed = 0
        self.lock_tags = False  # Whether to permanently lock tags after writing
        self.use_password = False  # Whether to use password protection instead of permanent lock
        self.tag_password = ""  # Password for NTAG password protection
        self.allow_overwrite = False  # Safety: do not overwrite existing NDEF by default
        self.last_read_time = 0  # Timestamp of last successful read
        self.read_cooldown = 3.0  # Cooldown period in seconds
        self.settings = settings  # Settings object for URL rewriting
        # Update mode state (two-step workflow)
        self.update_step = "scan_old"  # "scan_old" or "write_new"
        self.pending_rewrite_url = None  # URL to write after scanning old tag
        self.pending_original_url = None  # Original URL from old tag
        self.outdated_callback = None  # Callback for outdated tag detected (legacy)
        self.update_scan_callback = None  # Callback for interactive update mode scan
        self.locked_tag_callback = None  # Callback for locked tag with URL detected in write mode

    def initialize_reader(self) -> bool:
        """Initialize the NFC reader connection"""
        try:
            available_readers = readers()
            if not available_readers:
                return False

            # Look for ACS ACR1252 or any available reader
            for reader in available_readers:
                if "ACR1252" in str(reader) or len(available_readers) == 1:
                    self.reader = reader
                    break

            if not self.reader:
                self.reader = available_readers[0]  # Use first available reader

            return True
        except Exception as e:
            if self.log_callback:
                self.log_callback("Reader initialization failed", "error")
            return False

    def create_ndef_record(self, url: str) -> bytes:
        """Create NDEF record (TLV-wrapped) for NTAG21x pages"""
        uri_record = ndef.UriRecord(url)
        encoded_message = b''.join(ndef.message_encoder([uri_record]))
        message_length = len(encoded_message)

        # NDEF TLV format: Type(0x03) + Length + Value + Terminator(0xFE)
        ndef_tlv = b'\x03' + message_length.to_bytes(1, 'big') + encoded_message + b'\xFE'

        # Pad to 4-byte boundary for NTAG213 page alignment
        padding_length = (4 - (len(ndef_tlv) % 4)) % 4
        return ndef_tlv + (b'\x00' * padding_length)

    def _pcsc_write_page(self, connection: CardConnection, page: int, data4: bytes, retries: int = 4) -> bool:
        """Write exactly 4 bytes to a page with retry on NACK."""
        apdu = [0xFF, 0xD6, 0x00, page, 0x04] + list(data4)
        attempts = 0
        did_reconnect = False

        while True:
            try:
                response, sw1, sw2 = connection.transmit(apdu)
                if sw1 == 0x90 and sw2 == 0x00:
                    return True
                if sw1 == 0x63 and attempts < retries:
                    attempts += 1
                    time.sleep(0.05)
                    continue
                return False
            except Exception as e:
                err_txt = str(e)
                if not did_reconnect and ("T=1" in err_txt or "transport" in err_txt.lower()):
                    try:
                        try:
                            connection.disconnect()
                        except Exception:
                            pass
                        connection.connect(CardConnection.T1_protocol)
                        did_reconnect = True
                        time.sleep(0.05)
                        response, sw1, sw2 = connection.transmit(apdu)
                        if sw1 == 0x90 and sw2 == 0x00:
                            return True
                    except Exception:
                        pass
                return False

    def _pcsc_read_page(self, connection: CardConnection, page: int) -> Optional[bytes]:
        """Read exactly 4 bytes from a page."""
        read_command = [0xFF, 0xB0, 0x00, page, 0x04]
        response, sw1, sw2 = connection.transmit(read_command)
        if sw1 == 0x90 and sw2 == 0x00:
            return bytes(response)
        return None

    def is_tag_locked(self, connection: CardConnection) -> bool:
        """Check if tag has lock bits set (pages 3-15 locked)"""
        try:
            page2 = self._pcsc_read_page(connection, 2)
            if page2 and len(page2) == 4:
                # Bytes 2 and 3 of page 2 are the static lock bytes
                # If they're 0xFF, pages 3-15 are locked
                if page2[2] == 0xFF and page2[3] == 0xFF:
                    return True
            return False
        except Exception:
            return False

    def _verify_write(self, connection: CardConnection, page: int, expected: bytes) -> bool:
        """Verify a page was written correctly by reading it back"""
        try:
            actual = self._pcsc_read_page(connection, page)
            if actual is None:
                return False
            return actual[:len(expected)] == expected[:len(actual)]
        except Exception:
            return False

    def _format_cc_if_needed(self, connection: CardConnection) -> bool:
        """Ensure Capability Container (CC) bytes are present on page 3 for NTAG213."""
        try:
            cc = self._pcsc_read_page(connection, 3)
            if cc and len(cc) == 4 and cc[0] == 0xE1 and cc[1] == 0x10:
                return True
            return self._pcsc_write_page(connection, 3, bytes([0xE1, 0x10, 0x12, 0x00]))
        except Exception:
            return False

    def write_ndef_message(self, connection: CardConnection, ndef_message: bytes) -> bool:
        """Write NDEF message to NTAG213."""
        try:
            self._format_cc_if_needed(connection)

            if len(ndef_message) < 4:
                padded = ndef_message + b"\x00" * (4 - len(ndef_message))
                return self._pcsc_write_page(connection, 4, padded[:4])

            original_p4 = bytes(ndef_message[0:4])
            if not self._pcsc_write_page(connection, 4, bytes([0x03, 0x00, 0x00, 0x00])):
                return False
            time.sleep(0.05)

            remaining = ndef_message[4:]
            page = 5
            while remaining and page <= 39:
                chunk = remaining[:4]
                if len(chunk) < 4:
                    chunk = chunk + b"\x00" * (4 - len(chunk))
                if not self._pcsc_write_page(connection, page, chunk):
                    return False
                remaining = remaining[4:]
                page += 1
                time.sleep(0.02)

            return self._pcsc_write_page(connection, 4, original_p4)

        except Exception:
            return False

    def read_ndef_message(self, connection: CardConnection) -> str:
        """Read NDEF message from tag"""
        try:
            ndef_data = b''
            max_page = 40  # Safe for both NTAG213 and NTAG215

            for page in range(4, max_page):
                read_command = [0xFF, 0xB0, 0x00, page, 0x04]
                response, sw1, sw2 = connection.transmit(read_command)

                if sw1 != 0x90 or sw2 != 0x00:
                    break

                ndef_data += bytes(response)

                # Check for NDEF terminator
                if 0xFE in response:
                    break

            # Find NDEF TLV (Type-Length-Value)
            for i in range(len(ndef_data) - 2):
                if ndef_data[i] == 0x03:  # NDEF Message TLV
                    length = ndef_data[i + 1]
                    if length > 0 and i + 2 + length <= len(ndef_data):
                        ndef_payload = ndef_data[i + 2:i + 2 + length]

                        try:
                            records = list(ndef.message_decoder(ndef_payload))
                            for record in records:
                                if hasattr(record, 'uri') and record.uri:
                                    return record.uri
                                elif hasattr(record, 'text') and record.text:
                                    return record.text
                        except Exception:
                            continue

            return None

        except Exception:
            return None

    def lock_tag_permanently(self, connection: CardConnection) -> bool:
        """Permanently lock NTAG213 tag by setting lock bits"""
        try:
            read_command = [0xFF, 0xB0, 0x00, 0x02, 0x04]
            response, sw1, sw2 = connection.transmit(read_command)

            if sw1 != 0x90 or sw2 != 0x00:
                return False

            current_lock = list(response)
            current_lock[2] = 0xFF  # Lock pages 3-10
            current_lock[3] = 0xFF  # Lock pages 11-15 and lock bytes

            return self._pcsc_write_page(connection, 0x02, bytes(current_lock))

        except Exception:
            return False

    def set_password_protection(self, connection: CardConnection, password: str) -> bool:
        """Set password protection on NTAG213 tag (write-protected, readable by all)

        NTAG213 config pages:
        - Page 41 (0x29): CFG0 - MIRROR, AUTH0 (byte 3)
        - Page 42 (0x2A): CFG1 - ACCESS config (byte 0), AUTHLIM
        - Page 43 (0x2B): PWD - 4-byte password
        - Page 44 (0x2C): PACK - 2-byte password acknowledgment

        Args:
            connection: Active card connection
            password: 4-character password (will be padded/truncated to 4 bytes)

        Returns:
            True if password protection was set successfully
        """
        try:
            # Ensure password is exactly 4 bytes
            pwd_bytes = password.encode('utf-8')[:4].ljust(4, b'\x00')

            # Step 1: Write password to page 43 (0x2B)
            if not self._pcsc_write_page(connection, 0x2B, pwd_bytes):
                return False
            time.sleep(0.05)

            # Step 2: Write PACK (password acknowledgment) to page 44 (0x2C)
            # Using simple PACK value - first 2 bytes of password hash
            pack_bytes = bytes([pwd_bytes[0] ^ 0xAA, pwd_bytes[1] ^ 0x55, 0x00, 0x00])
            if not self._pcsc_write_page(connection, 0x2C, pack_bytes):
                return False
            time.sleep(0.05)

            # Step 3: Read current CFG0 (page 41) to preserve MIRROR settings
            cfg0 = self._pcsc_read_page(connection, 0x29)
            if not cfg0:
                cfg0 = bytes([0x04, 0x00, 0x00, 0xFF])  # Default values

            # Set AUTH0 to page 4 (0x04) - protect from page 4 onwards (NDEF data area)
            cfg0_new = bytes([cfg0[0], cfg0[1], cfg0[2], 0x04])
            if not self._pcsc_write_page(connection, 0x29, cfg0_new):
                return False
            time.sleep(0.05)

            # Step 4: Read current CFG1 (page 42) and set ACCESS bits
            cfg1 = self._pcsc_read_page(connection, 0x2A)
            if not cfg1:
                cfg1 = bytes([0x00, 0x05, 0x00, 0x00])  # Default values

            # Set PROT=0 (write protection only), keep CFGLCK=0 (config not locked)
            # ACCESS byte: bit 7 = PROT, bits 2-0 = AUTHLIM
            # PROT=0 means write-only protection (anyone can read)
            # AUTHLIM=0 means unlimited auth attempts
            access_byte = cfg1[0] & 0x7F  # Clear PROT bit (write-only protection)
            cfg1_new = bytes([access_byte, cfg1[1], cfg1[2], cfg1[3]])
            if not self._pcsc_write_page(connection, 0x2A, cfg1_new):
                return False

            return True

        except Exception:
            return False

    def is_password_protected(self, connection: CardConnection) -> bool:
        """Check if tag has password protection enabled"""
        try:
            # Read CFG0 (page 41) and check AUTH0 value
            cfg0 = self._pcsc_read_page(connection, 0x29)
            if cfg0 and len(cfg0) >= 4:
                auth0 = cfg0[3]
                # If AUTH0 < 0xFF, password protection is enabled from that page
                return auth0 < 0xFF
            return False
        except Exception:
            return False

    def start_monitoring(self, read_callback: Callable = None, write_callback: Callable = None,
                         update_callback: Callable = None, log_callback: Callable = None,
                         outdated_callback: Callable = None, update_scan_callback: Callable = None,
                         locked_tag_callback: Callable = None):
        """Start monitoring for NFC tags"""
        if self.is_monitoring:
            return

        self.read_callback = read_callback
        self.write_callback = write_callback
        self.update_callback = update_callback
        self.log_callback = log_callback
        self.outdated_callback = outdated_callback
        self.update_scan_callback = update_scan_callback
        self.locked_tag_callback = locked_tag_callback

        if not self.initialize_reader():
            if self.log_callback:
                self.log_callback("Failed to connect to reader", "error")
            return

        self.observer = NFCObserver(self)
        self.monitor = CardMonitor()
        self.monitor.addObserver(self.observer)
        self.is_monitoring = True

    def stop_monitoring(self):
        """Stop monitoring for NFC tags"""
        if not self.is_monitoring:
            return

        if self.monitor and self.observer:
            self.monitor.deleteObserver(self.observer)

        self.monitor = None
        self.observer = None
        self.is_monitoring = False

    def set_write_mode(self, url: str, lock_after_write: bool = False, allow_overwrite: bool = False,
                       use_password: bool = False, password: str = ""):
        """Set write mode with URL and protection options

        Args:
            url: URL to write to tag
            lock_after_write: Permanently lock tag (mutually exclusive with use_password)
            allow_overwrite: Allow overwriting existing data
            use_password: Use password protection instead of permanent lock
            password: Password for NTAG password protection (4 chars)
        """
        self.mode = "write"
        self.url_to_write = url
        self.lock_tags = lock_after_write and not use_password
        self.use_password = use_password
        self.tag_password = password
        self.allow_overwrite = allow_overwrite

    def set_read_mode(self):
        """Set read mode"""
        self.mode = "read"
        self.url_to_write = None
        self.lock_tags = False

    def set_update_mode(self):
        """Set update mode - two-step workflow: scan old tag, then write to new tag"""
        self.mode = "update"
        self.url_to_write = None
        self.lock_tags = True  # Always lock after update
        self.allow_overwrite = False  # Don't overwrite - we want to write to blank tags
        # Reset update workflow state
        self.update_step = "scan_old"
        self.pending_rewrite_url = None
        self.pending_original_url = None

    def cancel_pending_update(self):
        """Cancel pending update and reset to scan_old step"""
        self.update_step = "scan_old"
        self.pending_rewrite_url = None
        self.pending_original_url = None

    def _is_valid_url(self, data: str) -> bool:
        """Check if the data is a valid URL (starts with http:// or https://)

        This prevents false positives from garbage data on tags being
        interpreted as "existing data" by the NDEF library.
        """
        if not data or not isinstance(data, str):
            return False
        data = data.strip()
        # Only consider it valid data if it looks like a real URL
        return data.startswith(('http://', 'https://'))

    def _has_ndef_content(self, connection: CardConnection) -> Tuple[bool, Optional[str]]:
        """Check if tag has meaningful NDEF content

        Returns (has_content, url_or_none)
        - has_content: True if tag has valid NDEF URL/text data
        - url_or_none: The URL if found and valid, None otherwise

        This is more strict than read_ndef_message - it validates that
        any found data is actually a valid URL to prevent false positives
        from garbage/residual data on tags.
        """
        try:
            url = self.read_ndef_message(connection)
            if url and self._is_valid_url(url):
                return (True, url)
            return (False, None)
        except Exception:
            return (False, None)


class NFCObserver(CardObserver):
    def __init__(self, nfc_handler):
        self.nfc_handler = nfc_handler

    def update(self, observable, actions):
        (addedcards, removedcards) = actions

        for card in addedcards:
            try:
                connection = card.createConnection()
                try:
                    connection.connect(CardConnection.T1_protocol)
                except Exception:
                    connection.connect()

                if self.nfc_handler.mode == "read":
                    self.handle_read_mode(connection)
                elif self.nfc_handler.mode == "write":
                    self.handle_write_mode(connection)
                elif self.nfc_handler.mode == "update":
                    self.handle_update_mode(connection)

                connection.disconnect()

            except Exception:
                if self.nfc_handler.log_callback:
                    self.nfc_handler.log_callback("Tag communication error", "error")

    def handle_read_mode(self, connection):
        """Handle reading from NFC tag with debouncing"""
        current_time = time.time()

        if current_time - self.nfc_handler.last_read_time < self.nfc_handler.read_cooldown:
            return

        url = self.nfc_handler.read_ndef_message(connection)

        if url:
            self.nfc_handler.last_read_time = current_time
            if self.nfc_handler.read_callback:
                self.nfc_handler.read_callback(url)
        else:
            if self.nfc_handler.log_callback:
                self.nfc_handler.log_callback("Invalid URL", "warning")

    def handle_write_mode(self, connection):
        """Handle writing to NFC tag"""
        if not self.nfc_handler.url_to_write:
            return

        # Check if tag is locked first
        if self.nfc_handler.is_tag_locked(connection):
            # Try to read the URL from the locked tag
            has_url, existing_url = self.nfc_handler._has_ndef_content(connection)
            if has_url and existing_url:
                if self.nfc_handler.locked_tag_callback:
                    self.nfc_handler.locked_tag_callback(existing_url)
            else:
                # Locked tag without valid URL
                if self.nfc_handler.write_callback:
                    self.nfc_handler.write_callback("Locked tag detected")
            return

        # Safety: prevent overwriting existing NDEF unless explicitly allowed
        # Use stricter check that validates URL format to prevent false positives
        # from garbage/residual data on tags
        has_existing, existing_url = self.nfc_handler._has_ndef_content(connection)

        if has_existing and not self.nfc_handler.allow_overwrite:
            if self.nfc_handler.write_callback:
                self.nfc_handler.write_callback("Write blocked: tag has existing data")
            return

        try:
            ndef_message = self.nfc_handler.create_ndef_record(self.nfc_handler.url_to_write)

            if self.nfc_handler.write_ndef_message(connection, ndef_message):
                # Quick verify to catch locked tags that appear to write successfully
                quick_verify_url = self.nfc_handler.read_ndef_message(connection)
                if quick_verify_url != self.nfc_handler.url_to_write:
                    # Write appeared to succeed but verification failed (likely locked)
                    if self.nfc_handler.write_callback:
                        self.nfc_handler.write_callback("Locked tag - writing prevented")
                    return

                success_msg = "Written"

                # Apply protection: either permanent lock or password
                if self.nfc_handler.use_password and self.nfc_handler.tag_password:
                    if self.nfc_handler.set_password_protection(connection, self.nfc_handler.tag_password):
                        success_msg += " & password protected"
                    else:
                        success_msg += " (password protection failed)"
                elif self.nfc_handler.lock_tags:
                    if self.nfc_handler.lock_tag_permanently(connection):
                        success_msg += " & locked"
                    else:
                        success_msg += " (lock failed)"

                # Perform delayed verification if enabled
                if self.nfc_handler.settings and self.nfc_handler.settings.verify_after_write:
                    time.sleep(1.0)  # Wait for tag to settle
                    verified_url = self.nfc_handler.read_ndef_message(connection)
                    if verified_url == self.nfc_handler.url_to_write:
                        success_msg += " & verified"
                    else:
                        success_msg += " (verification failed)"

                if self.nfc_handler.write_callback:
                    self.nfc_handler.write_callback(success_msg)

                self.nfc_handler.cards_processed += 1

                # Handle batch writing
                if self.nfc_handler.batch_total > 1:
                    self.nfc_handler.batch_count += 1
                    if self.nfc_handler.batch_count < self.nfc_handler.batch_total:
                        if self.nfc_handler.log_callback:
                            self.nfc_handler.log_callback(
                                f"Present next tag ({self.nfc_handler.batch_count + 1}/{self.nfc_handler.batch_total})",
                                "info"
                            )
            else:
                if self.nfc_handler.log_callback:
                    self.nfc_handler.log_callback("Write failed", "error")

        except Exception:
            if self.nfc_handler.log_callback:
                self.nfc_handler.log_callback("Write error", "error")

    def handle_update_mode(self, connection):
        """Handle update mode: interactive workflow - scan tag, user confirms, write to new tag"""
        handler = self.nfc_handler

        if handler.update_step == "scan_old":
            # STEP 1: Scan tag and send to GUI for user interaction
            try:
                existing_url = handler.read_ndef_message(connection)
            except Exception:
                if handler.log_callback:
                    handler.log_callback("Failed to read tag", "error")
                return

            if not existing_url:
                if handler.log_callback:
                    handler.log_callback("Empty tag - scan a tag with URL", "warning")
                return

            # Try to apply URL rewriting for suggestion
            suggested_url = ""
            if handler.settings:
                new_url, was_rewritten = handler.settings.rewrite_url(existing_url)
                if was_rewritten:
                    suggested_url = new_url

            # Send to GUI for interactive confirmation
            if handler.update_scan_callback:
                handler.update_scan_callback(existing_url, suggested_url)
            # GUI will set update_step to "write_new" and pending_rewrite_url when user confirms

        elif handler.update_step == "write_new":
            # STEP 2: Write rewritten URL to new blank tag
            if not handler.pending_rewrite_url:
                if handler.log_callback:
                    handler.log_callback("No pending URL - scan old tag first", "error")
                handler.update_step = "scan_old"
                return

            # Check if tag is locked first
            if handler.is_tag_locked(connection):
                if handler.log_callback:
                    handler.log_callback("Locked tag - writing prevented", "error")
                return

            # Check if tag already has valid URL data (we want a blank tag)
            # Use stricter check to prevent false positives from garbage data
            has_existing, _ = handler._has_ndef_content(connection)

            if has_existing:
                if handler.log_callback:
                    handler.log_callback("Tag has data - use blank tag", "warning")
                return

            # Write the rewritten URL to the new tag
            try:
                ndef_message = handler.create_ndef_record(handler.pending_rewrite_url)

                if handler.write_ndef_message(connection, ndef_message):
                    # Verify the write by reading back
                    written_url = handler.read_ndef_message(connection)
                    if written_url != handler.pending_rewrite_url:
                        # Write appeared to succeed but verification failed
                        if handler.log_callback:
                            handler.log_callback("Locked tag - writing prevented", "error")
                        if handler.update_callback:
                            handler.update_callback(
                                handler.pending_original_url,
                                handler.pending_rewrite_url,
                                False
                            )
                        return

                    # Lock the tag
                    handler.lock_tag_permanently(connection)

                    if handler.update_callback:
                        handler.update_callback(
                            handler.pending_original_url,
                            handler.pending_rewrite_url,
                            True
                        )

                    handler.cards_processed += 1

                    # Reset for next update
                    handler.update_step = "scan_old"
                    handler.pending_rewrite_url = None
                    handler.pending_original_url = None

                else:
                    if handler.log_callback:
                        handler.log_callback("Write failed", "error")
                    if handler.update_callback:
                        handler.update_callback(
                            handler.pending_original_url,
                            handler.pending_rewrite_url,
                            False
                        )

            except Exception:
                if handler.log_callback:
                    handler.log_callback("Write error", "error")
                if handler.update_callback:
                    handler.update_callback(
                        handler.pending_original_url,
                        handler.pending_rewrite_url,
                        False
                    )
