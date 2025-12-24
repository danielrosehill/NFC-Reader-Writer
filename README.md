# NFC GUI - Reader/Writer for ACS ACR1252

A modern PyQt5-based GUI application for reading and writing NFC tags using the ACS ACR1252U USB NFC Reader on Linux systems.

![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![Reader](https://img.shields.io/badge/Reader-ACS%20ACR1252U-blue)
![Validated Tag](https://img.shields.io/badge/Validated%20Tag-NXP%20NTAG213-brightgreen)

## Features

- **Modern PyQt5 GUI**: Beautiful, responsive interface with material design styling
- **Read Mode**: Continuously scan NFC tags and automatically open URLs in browser
- **Write Mode**: Write URLs to NFC tags with optional permanent locking
- **Batch Writing**: Write the same URL to multiple tags sequentially
- **Safety Features**: Optional overwrite protection to prevent accidental data loss
- **Clipboard Integration**: Easy paste from clipboard and copy read URLs
- **Real-time Logging**: Activity log with timestamps for all operations
- **System Tray Integration**: Minimize to system tray for background operation
- **Background Read Mode**: Continuous tag reading while minimized - perfect for always-on inventory management

## Hardware Requirements

- ACS ACR1252U USB NFC Reader/Writer (tested)
- NTAG213/215/216 NFC tags (recommended)
- Linux system with USB support

### Validated Hardware

- **Reader**: ACS ACR1252U
- **Tags**: NXP NTAG213 (validated)

## Installation

### Quick Install (Recommended)

Run the install script which builds and installs the Debian package:
```bash
./install.sh
```

This will:
- Build the .deb package
- Optionally install it
- Set up all dependencies
- Configure system permissions

### Manual Installation

Build the package:
```bash
./build-deb.sh
```

Install the package:
```bash
sudo dpkg -i dist/nfc-gui_1.0.0_amd64.deb
sudo apt-get install -f
```

### Development Mode

For development without installing:
```bash
./run-gui.sh
```

Or manually:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m nfc_gui.gui
```

## Usage

### Read Mode

1. Click "Read Mode" button (green)
2. Present NFC tag to reader
3. URL will be automatically:
   - Displayed in the activity log
   - Copied to clipboard
   - Opened in your default browser

### Write Mode

1. Click "Write Mode" button (blue)
2. Enter or paste the URL to write
3. Configure options:
   - **Lock tag after writing**: Permanently locks the tag (irreversible)
   - **Allow overwrite**: Permits overwriting existing tag data
4. Set batch count (1 for single tag, >1 for multiple tags)
5. Click "Write Tag(s)" (orange button)
6. Present tag(s) to the reader

### GUI Controls

- **Read Mode** (Green): Switch to continuous tag reading
- **Write Mode** (Blue): Switch to tag writing mode
- **URL Entry**: Enter or paste URL to write to tags
- **Paste Button**: Paste URL from clipboard
- **Lock tag after writing**: Checkbox to enable permanent tag locking
- **Allow overwrite**: Checkbox to enable overwriting existing tags
- **Batch count**: Spinbox to set number of tags to write (1-100)
- **Write Tag(s)** (Orange): Execute write operation
- **Clear Log**: Clear the activity log
- **Copy Last URL**: Copy the last read URL to clipboard
- **Open Last URL**: Open the last read URL in browser
- **Background Read Mode**: Minimize to tray and enable continuous background reading

### Background Read Mode

The application can run minimized in the system tray with continuous NFC tag reading:

1. Click "Background Read Mode" button in the main window, OR
2. Right-click the system tray icon and select "Background Read Mode"

When enabled:
- Application minimizes to system tray (blue circle icon)
- NFC reader stays active in read mode
- Present any NFC tag and the URL will automatically open in your browser
- Desktop notifications confirm mode changes
- Perfect for always-on inventory scanning at your desk

To restore the window:
- Double-click the tray icon, OR
- Right-click tray icon → "Show Window"

To quit completely:
- Right-click tray icon → "Quit"

## Safety Features

### Overwrite Protection

By default, the application will **not** overwrite tags that already contain data. To intentionally replace existing content, enable the "Allow overwrite" checkbox.

### Tag Locking

When "Lock tag after writing" is enabled, tags will be **permanently locked** after writing. This is **irreversible** - locked tags cannot be rewritten.

## URL Rewriting

The application includes configurable URL rewriting for migrating NFC tags from local to public URLs. This is useful when:
- You run a local service (like Homebox) that you later expose publicly
- You have old tags pointing to internal IPs that need updating

**Settings Dialog:**
Click the "Settings" button to configure:
- **Source URL Pattern**: A regex pattern to match URLs that need rewriting (e.g., `^https?://10\.0\.0\.\d+(?::\d+)?/+item/(.+)$`)
- **Target Base URL**: The new base URL to use (e.g., `https://your-domain.com/item/`)

**Update Mode:**
Use "Update Mode" to automatically:
1. Read the existing URL from a tag
2. Apply the rewrite rule
3. Write the new URL back
4. Lock the tag

## Project Structure

```
NFC-GUI-1025/
├── nfc_gui/
│   ├── __init__.py
│   ├── gui.py           # PyQt5 GUI implementation
│   └── nfc_handler.py   # Core NFC operations
├── install.sh           # Build & install Debian package (recommended)
├── build-deb.sh         # Build Debian package only
├── run-gui.sh           # Launch in development mode
├── requirements.txt     # Python dependencies
├── CHANGELOG.md         # Version history
└── README.md            # This file
```

## Build Scripts

- **`install.sh`** - Interactive installer (builds and optionally installs)
- **`build-deb.sh`** - Build Debian package only (no installation)
- **`build.sh`** - Legacy build script (supports multiple formats, not recommended)
- **`run-gui.sh`** - Development mode launcher

## Troubleshooting

### Reader Not Found

- Ensure the ACS ACR1252 is connected via USB
- Check that pcscd daemon is running: `sudo systemctl status pcscd`
- Verify reader is detected: `pcsc_scan`

### Permission Issues

- Add your user to the `scard` group: `sudo usermod -a -G scard $USER`
- Log out and back in for group changes to take effect

### Tag Read/Write Failures

- Ensure tag is NDEF-compatible
- Try different tag positioning on the reader
- Check that the tag isn't locked or damaged
- Keep tag steady on reader during write operations

## Tested Tags

- **NXP NTAG213**: ~144 bytes usable NDEF capacity (recommended)

## Dependencies

- `PyQt5`: Modern GUI framework
- `pyscard`: PC/SC smartcard library interface
- `ndeflib`: NDEF message encoding/decoding
- `pyperclip`: Clipboard operations

## Credits

Core NFC functionality based on [VladoPortos's ACR1252 implementation](https://github.com/VladoPortos/python-nfc-read-write-acr1252)

## License

MIT License - see [LICENSE](LICENSE) for details.
