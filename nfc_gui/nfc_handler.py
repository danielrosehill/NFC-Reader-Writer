"""
NFC Handler for ACS ACR1252 USB NFC Reader/Writer
Handles reading and writing URLs to NTAG213/215/216 tags
Based on VladoPortos's ACR1252 implementation: https://github.com/VladoPortos/python-nfc-read-write-acr1252
"""

import hashlib
import ndef
import time
import re
from typing import Optional, Callable
from smartcard.CardMonitoring import CardMonitor, CardObserver
from smartcard.CardConnection import CardConnection
from smartcard.System import readers


def redirect_homebox_url(url: str) -> str:
    """
    Redirect local homebox URLs to the external domain.
    Handles various local formats:
    - http://10.0.0.1:3100/item/X
    - http://10.0.0.1:3100//item/X (double slash)
    - https://10.0.0.3:3100/item/X (any IP in 10.0.0.x subnet)
    - https://10.0.0.3100/item/X (malformed - port attached to IP)

    All converted to: https://homebox.residencejlm.com/item/X
    """
    if not url:
        return url

    # Pattern 1: Match 10.0.0.x subnet with proper port (e.g., 10.0.0.1:3100)
    # Handles both single and multiple slashes before /item/
    pattern1 = r'^https?://10\.0\.0\.(\d{1,3})(?::\d+)?(/+item/.*)$'
    match1 = re.match(pattern1, url)

    if match1:
        path = match1.group(2)  # Extract the /item/X or //item/X part
        # Normalize to single slash
        path = re.sub(r'^/+', '/', path)
        redirected_url = f"https://homebox.residencejlm.com{path}"
        return redirected_url

    # Pattern 2: Handle malformed URLs where port is attached to IP (e.g., 10.0.0.3100)
    # This catches cases like https://10.0.0.3100/item/X
    pattern2 = r'^https?://10\.0\.0\.(\d+)(/+item/.*)$'
    match2 = re.match(pattern2, url)

    if match2:
        path = match2.group(2)  # Extract the /item/X or //item/X part
        # Normalize to single slash
        path = re.sub(r'^/+', '/', path)
        redirected_url = f"https://homebox.residencejlm.com{path}"
        return redirected_url

    return url


class NFCHandler:
    def __init__(self, debug_mode=False):
        self.reader = None
        self.monitor = None
        self.observer = None
        self.is_monitoring = False
        self.read_callback = None
        self.write_callback = None
        self.log_callback = None
        self.mode = "read"  # "read" or "write"
        self.url_to_write = None
        self.batch_count = 0
        self.batch_total = 0
        self.debug_mode = debug_mode
        self.cards_processed = 0
        self.lock_tags = False  # Whether to permanently lock tags after writing
        self.allow_overwrite = False  # Safety: do not overwrite existing NDEF by default
        self.last_read_time = 0  # Timestamp of last successful read
        self.read_cooldown = 3.0  # Cooldown period in seconds

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
        # Create NDEF URI record manually for ACR1252 compatibility
        uri_record = ndef.UriRecord(url)
        encoded_message = b''.join(ndef.message_encoder([uri_record]))
        message_length = len(encoded_message)

        # NDEF TLV format: Type(0x03) + Length + Value + Terminator(0xFE)
        ndef_tlv = b'\x03' + message_length.to_bytes(1, 'big') + encoded_message + b'\xFE'

        # Pad to 4-byte boundary for NTAG213 page alignment
        padding_length = (4 - (len(ndef_tlv) % 4)) % 4
        complete_message = ndef_tlv + (b'\x00' * padding_length)

        if self.log_callback:
            self.log_callback(f"Created NDEF record for URL: {url}")
            self.log_callback(f"Message length: {message_length}, Total bytes: {len(complete_message)}")
            self.log_callback(f"Message content (hex): {complete_message.hex()}")

        return complete_message

    def _ensure_debug_dir(self):
        """Ensure debug directory exists for logs."""
        try:
            import os
            os.makedirs("debug", exist_ok=True)
        except Exception:
            pass

    def _pcsc_write_page(self, connection: CardConnection, page: int, data4: bytes, retries: int = 4) -> bool:
        """Write exactly 4 bytes to a page with small retry on SW1=0x63 (NACK) and one reconnect on transport error."""
        block_data = list(data4)
        apdu = [0xFF, 0xD6, 0x00, page, 0x04] + block_data
        attempts = 0
        did_reconnect = False
        while True:
            if self.log_callback:
                self.log_callback(f"Writing to page {page}: {block_data}")

            try:
                response, sw1, sw2 = connection.transmit(apdu)
                if sw1 == 0x90 and sw2 == 0x00:
                    if self.log_callback:
                        self.log_callback(f"Successfully wrote to page {page}")
                    return True
                # Retry transient NACKs a couple times
                if sw1 == 0x63 and attempts < retries:
                    attempts += 1
                    time.sleep(0.05)
                    continue
                error_msg = f"Write failed at page {page}: SW1={sw1:02X} SW2={sw2:02X}"
                if self.log_callback:
                    self.log_callback(error_msg)
            except Exception as e:
                # Handle T1 protocol errors and other communication issues
                err_txt = str(e)
                error_msg = f"Communication error at page {page}: {err_txt}"
                if "T=1" in err_txt or "transport" in err_txt.lower() or "protocol" in err_txt.lower():
                    error_msg += " (T1 transport/protocol error)"
                    # One attempt to reconnect and retry this APDU
                    if not did_reconnect:
                        try:
                            if self.log_callback:
                                self.log_callback("Reconnecting card after transport error…")
                            try:
                                connection.disconnect()
                            except Exception:
                                pass
                            # Prefer T=1 protocol on reconnect
                            connection.connect(CardConnection.T1_protocol)
                            did_reconnect = True
                            # brief settle
                            time.sleep(0.05)
                            # retry once immediately
                            response, sw1, sw2 = connection.transmit(apdu)
                            if sw1 == 0x90 and sw2 == 0x00:
                                if self.log_callback:
                                    self.log_callback(f"Successfully wrote to page {page} after reconnect")
                                return True
                        except Exception as e2:
                            # fall through to logging below
                            error_msg += f" | Reconnect retry failed: {e2}"
                if self.log_callback:
                    self.log_callback(error_msg)

            # Log detailed error information
            try:
                self._ensure_debug_dir()
                with open("debug/write_errors.log", "a") as f:
                    import datetime
                    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    f.write(f"[{ts}] Write Error: {error_msg}\n")
                    f.write(f"[{ts}] APDU: {apdu}\n")
                    f.write(f"[{ts}] Attempt: {attempts + 1}/{retries + 1}\n---\n")
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
        """Ensure Capability Container (CC) bytes are present on page 3 for NTAG213.
        CC format for NTAG213: E1 10 12 00 (NDEF mapping v1.0, 0x12=144 bytes/8)
        """
        try:
            cc = self._pcsc_read_page(connection, 3)
            if cc and len(cc) == 4 and cc[0] == 0xE1 and cc[1] == 0x10:
                return True
            desired = bytes([0xE1, 0x10, 0x12, 0x00])
            if self.log_callback:
                self.log_callback(f"CC not set or unknown ({cc}); writing CC bytes: {list(desired)}")
            return self._pcsc_write_page(connection, 3, desired)
        except Exception as e:
            if self.log_callback:
                self.log_callback(f"Failed to verify/write CC: {e}")
            return False

    def write_ndef_message(self, connection: CardConnection, ndef_message: bytes) -> bool:
        """Write NDEF message to NTAG213 with safe NLEN update and basic retries."""
        try:
            if self.log_callback:
                self.log_callback(f"Starting write operation, message length: {len(ndef_message)} bytes")
            # Ensure CC bytes exist for NDEF (best effort)
            self._format_cc_if_needed(connection)

            # Two-phase write:
            # 1) Temporarily set NLEN=0 on page 4 to avoid inconsistent reads
            # 2) Write remaining TLV bytes from page 5 onward
            # 3) Rewrite page 4 with the real NLEN and first two payload bytes

            if len(ndef_message) < 4:
                # Shouldn't happen (TLV header itself is 2+ bytes), but guard anyway
                padded = ndef_message + b"\x00" * (4 - len(ndef_message))
                if not self._pcsc_write_page(connection, 4, padded[:4]):
                    return False
                if self.log_callback:
                    self.log_callback("Write operation completed successfully")
                return True

            original_p4 = bytes(ndef_message[0:4])
            zero_p4 = bytes([0x03, 0x00, 0x00, 0x00])
            if not self._pcsc_write_page(connection, 4, zero_p4):
                return False
            time.sleep(0.05)

            # Write the rest starting from page 5
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

            # Restore real TLV header with actual NLEN
            if not self._pcsc_write_page(connection, 4, original_p4):
                return False

            if self.log_callback:
                self.log_callback("Write operation completed successfully")
            return True

        except Exception as e:
            if self.log_callback:
                self.log_callback(f"Write operation error: {e}")
                import traceback
                self.log_callback(f"Traceback: {traceback.format_exc()}")
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
            if self.log_callback:
                self.log_callback("Attempting to permanently lock tag...")

            # Read current lock status
            read_command = [0xFF, 0xB0, 0x00, 0x02, 0x04]
            response, sw1, sw2 = connection.transmit(read_command)

            if self.log_callback:
                self.log_callback(f"Read lock status - SW1: {sw1:02X}, SW2: {sw2:02X}, Response: {response}")

            if sw1 != 0x90 or sw2 != 0x00:
                if self.log_callback:
                    self.log_callback(f"Failed to read lock status: SW1={sw1:02X} SW2={sw2:02X}")
                return False

            current_lock = list(response)

            if self.log_callback:
                self.log_callback(f"Current lock bytes: {current_lock}")

            # Set lock bits - permanently lock pages 3-15
            current_lock[2] = 0xFF  # Lock pages 3-10
            current_lock[3] = 0xFF  # Lock pages 11-15 and lock bytes

            if self.log_callback:
                self.log_callback(f"Setting lock bytes to: {current_lock}")

            # Write lock bytes via robust page writer - WARNING: IRREVERSIBLE!
            success = self._pcsc_write_page(connection, 0x02, bytes(current_lock))
            if success:
                self.log_callback("Tag locked successfully")
            else:
                self.log_callback("Failed to lock tag: write did not succeed")

            return success

        except Exception as e:
            if self.log_callback:
                self.log_callback(f"Lock operation error: {e}")
                import traceback
                self.log_callback(f"Traceback: {traceback.format_exc()}")
            return False

    def start_monitoring(self, read_callback: Callable = None, write_callback: Callable = None, log_callback: Callable = None):
        """Start monitoring for NFC tags"""
        if self.is_monitoring:
            return

        self.read_callback = read_callback
        self.write_callback = write_callback
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
        if self.log_callback:
            self.log_callback(f"Set write mode: URL={url}, lock={lock_after_write}, overwrite={allow_overwrite}")

    def set_read_mode(self):
        """Set read mode"""
        self.mode = "read"
        self.url_to_write = None
        self.lock_tags = False
        if self.log_callback:
            self.log_callback("Set read mode")


class NFCObserver(CardObserver):
    def __init__(self, nfc_handler):
        self.nfc_handler = nfc_handler

    def update(self, observable, actions):
        (addedcards, removedcards) = actions

        for card in addedcards:
            try:
                connection = card.createConnection()
                # Prefer T=1 protocol for stability on contactless
                try:
                    connection.connect(CardConnection.T1_protocol)
                except Exception:
                    # Fallback to default negotiation if explicit T=1 fails
                    connection.connect()

                # Debug: log current mode
                if self.nfc_handler.log_callback:
                    self.nfc_handler.log_callback(f"Card detected, current mode: {self.nfc_handler.mode}")
                    self.nfc_handler.log_callback(f"URL to write: {self.nfc_handler.url_to_write}")
                    self.nfc_handler.log_callback(f"Lock tags: {self.nfc_handler.lock_tags}")

                if self.nfc_handler.mode == "read":
                    self.handle_read_mode(connection)
                elif self.nfc_handler.mode == "write":
                    self.handle_write_mode(connection)
                else:
                    if self.nfc_handler.log_callback:
                        self.nfc_handler.log_callback(f"Unknown mode: {self.nfc_handler.mode}")

                connection.disconnect()

            except Exception as e:
                if self.nfc_handler.log_callback:
                    self.nfc_handler.log_callback(f"Error: {e}")
                    import traceback
                    self.nfc_handler.log_callback(f"Traceback: {traceback.format_exc()}")

        for card in removedcards:
            if self.nfc_handler.log_callback:
                self.nfc_handler.log_callback("Card removed")

    def handle_read_mode(self, connection):
        """Handle reading from NFC tag with debouncing"""
        current_time = time.time()

        # Check if we're in cooldown period
        if current_time - self.nfc_handler.last_read_time < self.nfc_handler.read_cooldown:
            if self.nfc_handler.log_callback:
                self.nfc_handler.log_callback("Tag read ignored (cooldown period)")
            return

        if self.nfc_handler.log_callback:
            self.nfc_handler.log_callback("Reading NFC tag...")

        url = self.nfc_handler.read_ndef_message(connection)

        if url:
            # Update last read time to start cooldown BEFORE callback
            self.nfc_handler.last_read_time = current_time

            if self.nfc_handler.log_callback:
                self.nfc_handler.log_callback(f"DEBUG: Calling read_callback for: {url}")

            if self.nfc_handler.read_callback:
                self.nfc_handler.read_callback(url)
        else:
            if self.nfc_handler.log_callback:
                self.nfc_handler.log_callback("No URL found on tag")

    def handle_write_mode(self, connection):
        """Handle writing to NFC tag"""
        if self.nfc_handler.log_callback:
            self.nfc_handler.log_callback(f"handle_write_mode called with URL: {self.nfc_handler.url_to_write}")

        if not self.nfc_handler.url_to_write:
            if self.nfc_handler.log_callback:
                self.nfc_handler.log_callback("No URL to write")
            return

        # Safety: prevent overwriting existing NDEF unless explicitly allowed
        try:
            existing = self.nfc_handler.read_ndef_message(connection)
        except Exception:
            existing = None

        if existing:
            if self.nfc_handler.log_callback:
                self.nfc_handler.log_callback(f"Existing NDEF detected on tag: {existing}")
            if not self.nfc_handler.allow_overwrite:
                if self.nfc_handler.log_callback:
                    self.nfc_handler.log_callback("Write blocked: tag already contains NDEF. Re-run with overwrite enabled to proceed.")
                if self.nfc_handler.write_callback:
                    self.nfc_handler.write_callback("Write blocked: tag already contains data. Use overwrite option to replace.")
                return

        if self.nfc_handler.log_callback:
            self.nfc_handler.log_callback(f"Writing URL: {self.nfc_handler.url_to_write}")

        try:
            # Write NDEF message
            ndef_message = self.nfc_handler.create_ndef_record(self.nfc_handler.url_to_write)
            if self.nfc_handler.log_callback:
                self.nfc_handler.log_callback(f"Created NDEF message, length: {len(ndef_message)} bytes")

            if self.nfc_handler.write_ndef_message(connection, ndef_message):
                success_msg = "URL written successfully"

                # Lock tag if requested
                if self.nfc_handler.lock_tags:
                    if self.nfc_handler.log_callback:
                        self.nfc_handler.log_callback("Attempting to lock tag...")
                    if self.nfc_handler.lock_tag_permanently(connection):
                        success_msg += " and locked permanently"
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
                            self.nfc_handler.log_callback(f"Present next NFC tag ({self.nfc_handler.batch_count + 1}/{self.nfc_handler.batch_total})...")
                    else:
                        if self.nfc_handler.log_callback:
                            self.nfc_handler.log_callback("Batch writing completed")
            else:
                if self.nfc_handler.log_callback:
                    self.nfc_handler.log_callback("Failed to write URL - check if tag is writable and properly positioned")

        except Exception as e:
            # Enhanced error handling for T1 protocol and other communication errors
            error_str = str(e)
            if "T=1" in error_str or "protocol" in error_str.lower():
                error_msg = "Communication error: Tag may have been removed during write operation or reader communication interrupted"
                if self.nfc_handler.log_callback:
                    self.nfc_handler.log_callback(error_msg)
                    self.nfc_handler.log_callback("Try: Keep tag steady on reader, ensure good contact, try again")
            elif "locked" in error_str.lower() or "read-only" in error_str.lower():
                error_msg = "Tag appears to be locked or read-only"
                if self.nfc_handler.log_callback:
                    self.nfc_handler.log_callback(error_msg)
            else:
                error_msg = f"Write operation failed: {error_str}"
                if self.nfc_handler.log_callback:
                    self.nfc_handler.log_callback(f"Write error: {error_str}")

            # Log to file for debugging
            try:
                self.nfc_handler._ensure_debug_dir()
                with open("debug/write_errors.log", "a") as f:
                    import datetime
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    f.write(f"[{timestamp}] {error_msg}\n")
                    f.write(f"[{timestamp}] URL: {self.nfc_handler.url_to_write}\n")
                    f.write(f"[{timestamp}] Exception type: {type(e).__name__}\n")
                    f.write(f"[{timestamp}] Full exception: {error_str}\n")
                    f.write("---\n")
            except:
                pass
