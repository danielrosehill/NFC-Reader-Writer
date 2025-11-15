# NFC GUI - Quick Reference

## Installation

### Install (one command):
```bash
./install.sh
```

### Build only:
```bash
./build-deb.sh
```

### Development mode:
```bash
./run-gui.sh
```

## Usage

### Launch Application
```bash
nfc-gui
```

Or find "NFC Reader/Writer" in your application menu.

### Read Mode
1. Click "Read Mode" (green button)
2. Present NFC tag
3. URL opens automatically in Chrome

### Write Mode
1. Click "Write Mode" (blue button)
2. Paste/enter URL
3. Check "Lock tag after writing" (recommended)
4. Click "Write Tag(s)"
5. Present blank tag

### Batch Write
1. In Write Mode, set "Batch count" to number of tags
2. Click "Write Tag(s)"
3. Present tags one at a time

## Files

### Scripts
- `install.sh` - Build & install package
- `build-deb.sh` - Build package only
- `run-gui.sh` - Run in dev mode

### Documentation
- `README.md` - Full documentation
- `CHANGELOG.md` - Version history
- `INSTALLATION_SUMMARY.md` - Detailed install guide
- `UPDATING_VERSION.md` - Version update procedure
- `QUICK_REFERENCE.md` - This file

### Source Code
- `nfc_gui/gui.py` - PyQt5 GUI
- `nfc_gui/nfc_handler.py` - NFC operations
- `requirements.txt` - Python dependencies

## Troubleshooting

### Reader not found
```bash
sudo systemctl status pcscd
pcsc_scan
```

### Permission denied
```bash
sudo usermod -a -G scard $USER
# Log out and back in
```

### Chrome doesn't open
Install Chrome or Chromium:
```bash
sudo apt install google-chrome-stable
# or
sudo apt install chromium-browser
```

## Version Info

**Current**: 1.1.0
**Package**: `dist/nfc-gui_1.1.0_amd64.deb`

## Common Tasks

### Update to new version
```bash
sudo dpkg -r nfc-gui
./install.sh
```

### Rebuild package
```bash
rm -rf build dist
./build-deb.sh
```

### Check installed version
```bash
dpkg -l | grep nfc-gui
```

### Uninstall
```bash
sudo dpkg -r nfc-gui
```

## URL Redirection

Local URLs automatically redirect:
- `http://10.0.0.1:3100/item/X` → `https://homebox.residencejlm.com/item/X`
- Any 10.0.0.x IP supported
- Double slashes normalized
- Malformed ports corrected

## Hardware

**Reader**: ACS ACR1252U USB
**Tags**: NTAG213 (recommended), NTAG215, NTAG216

## Support

Check documentation files for detailed help:
- Installation issues → `INSTALLATION_SUMMARY.md`
- Version updates → `UPDATING_VERSION.md`
- Feature documentation → `README.md`
- Changes → `CHANGELOG.md`
