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
        self.allow_overwrite = False  # Safety: do not overwrite existing NDEF by default
        self.last_read_time = 0  # Timestamp of last successful read
        self.read_cooldown = 3.0  # Cooldown period in seconds
        self.settings = settings  # Settings object for URL rewriting

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
                self.log_callback(f"Error initializing reader: {e}")
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

    def start_monitoring(self, read_callback: Callable = None, write_callback: Callable = None,
                         update_callback: Callable = None, log_callback: Callable = None):
        """Start monitoring for NFC tags"""
        if self.is_monitoring:
            return

        self.read_callback = read_callback
        self.write_callback = write_callback
        self.update_callback = update_callback
        self.log_callback = log_callback

        if not self.initialize_reader():
            if self.log_callback:
                self.log_callback("Failed to initialize NFC reader")
            return

        self.observer = NFCObserver(self)
        self.monitor = CardMonitor()
        self.monitor.addObserver(self.observer)
        self.is_monitoring = True

        if self.log_callback:
            self.log_callback(f"Started monitoring with reader: {self.reader}")

    def stop_monitoring(self):
        """Stop monitoring for NFC tags"""
        if not self.is_monitoring:
            return

        if self.monitor and self.observer:
            self.monitor.deleteObserver(self.observer)

        self.monitor = None
        self.observer = None
        self.is_monitoring = False

        if self.log_callback:
            self.log_callback("Stopped NFC monitoring")

    def set_write_mode(self, url: str, lock_after_write: bool = False, allow_overwrite: bool = False):
        """Set write mode with URL and optional locking"""
        self.mode = "write"
        self.url_to_write = url
        self.lock_tags = lock_after_write
        self.allow_overwrite = allow_overwrite

    def set_read_mode(self):
        """Set read mode"""
        self.mode = "read"
        self.url_to_write = None
        self.lock_tags = False

    def set_update_mode(self):
        """Set update mode - reads tag, rewrites URL, writes back and locks"""
        self.mode = "update"
        self.url_to_write = None
        self.lock_tags = True  # Always lock after update
        self.allow_overwrite = True  # Must overwrite for update to work


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

            except Exception as e:
                if self.nfc_handler.log_callback:
                    self.nfc_handler.log_callback(f"Error: {e}", "error")

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
                self.nfc_handler.log_callback("No URL found on tag", "warning")

    def handle_write_mode(self, connection):
        """Handle writing to NFC tag"""
        if not self.nfc_handler.url_to_write:
            return

        # Safety: prevent overwriting existing NDEF unless explicitly allowed
        try:
            existing = self.nfc_handler.read_ndef_message(connection)
        except Exception:
            existing = None

        if existing and not self.nfc_handler.allow_overwrite:
            if self.nfc_handler.write_callback:
                self.nfc_handler.write_callback("Write blocked: tag already contains data")
            return

        if self.nfc_handler.log_callback:
            self.nfc_handler.log_callback("Writing...", "info")

        try:
            ndef_message = self.nfc_handler.create_ndef_record(self.nfc_handler.url_to_write)

            if self.nfc_handler.write_ndef_message(connection, ndef_message):
                success_msg = "Written"

                if self.nfc_handler.lock_tags:
                    if self.nfc_handler.lock_tag_permanently(connection):
                        success_msg += " & locked"
                    else:
                        success_msg += " (lock failed)"

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
                    self.nfc_handler.log_callback("Write failed - check tag position", "error")

        except Exception as e:
            if self.nfc_handler.log_callback:
                self.nfc_handler.log_callback(f"Write error: {e}", "error")

    def handle_update_mode(self, connection):
        """Handle update mode: read tag, rewrite URL, write back and lock"""
        # Step 1: Read the existing URL from the tag
        try:
            existing_url = self.nfc_handler.read_ndef_message(connection)
        except Exception as e:
            if self.nfc_handler.log_callback:
                self.nfc_handler.log_callback(f"Failed to read tag: {e}", "error")
            return

        if not existing_url:
            if self.nfc_handler.log_callback:
                self.nfc_handler.log_callback("No URL found on tag - nothing to update", "warning")
            return

        # Step 2: Apply URL rewriting using settings
        if not self.nfc_handler.settings:
            if self.nfc_handler.log_callback:
                self.nfc_handler.log_callback("No rewrite settings configured", "error")
            return

        new_url, was_rewritten = self.nfc_handler.settings.rewrite_url(existing_url)

        if not was_rewritten:
            if self.nfc_handler.log_callback:
                self.nfc_handler.log_callback(f"URL doesn't need rewriting: {existing_url}", "warning")
            if self.nfc_handler.update_callback:
                self.nfc_handler.update_callback(existing_url, existing_url, False)
            return

        if self.nfc_handler.log_callback:
            self.nfc_handler.log_callback(f"Rewriting: {existing_url}", "info")
            self.nfc_handler.log_callback(f"       To: {new_url}", "info")

        # Step 3: Write the new URL back to the tag
        try:
            ndef_message = self.nfc_handler.create_ndef_record(new_url)

            if self.nfc_handler.write_ndef_message(connection, ndef_message):
                success_msg = "Updated"

                # Step 4: Lock the tag
                if self.nfc_handler.lock_tag_permanently(connection):
                    success_msg += " & locked"
                else:
                    success_msg += " (lock failed)"

                if self.nfc_handler.log_callback:
                    self.nfc_handler.log_callback(success_msg, "success")

                if self.nfc_handler.update_callback:
                    self.nfc_handler.update_callback(existing_url, new_url, True)

                self.nfc_handler.cards_processed += 1

                # Handle batch updating
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
                    self.nfc_handler.log_callback("Update failed - write error", "error")
                if self.nfc_handler.update_callback:
                    self.nfc_handler.update_callback(existing_url, new_url, False)

        except Exception as e:
            if self.nfc_handler.log_callback:
                self.nfc_handler.log_callback(f"Update error: {e}", "error")
            if self.nfc_handler.update_callback:
                self.nfc_handler.update_callback(existing_url, new_url, False)
