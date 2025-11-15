# NFC GUI v1.0.1 - Installation Summary

## Quick Start

The simplest way to install NFC GUI is to run the install script:

```bash
./install.sh
```

This will build the Debian package and guide you through installation.

## What You Get

- **Executable**: `nfc-gui` command available system-wide
- **Desktop Entry**: "NFC Reader/Writer" in your application menu
- **Dependencies**: Automatically installed (PyQt5, pyscard, etc.)
- **Permissions**: User added to `scard` group
- **Service**: `pcscd` daemon enabled and started

## Installation Methods

### Method 1: Interactive Install (Recommended)

```bash
./install.sh
```

**What it does:**
1. Checks dependencies (dpkg-deb, python3)
2. Builds `nfc-gui_1.0.1_amd64.deb`
3. Shows package info
4. Asks if you want to install
5. Installs package with `dpkg`
6. Fixes dependencies with `apt-get`

### Method 2: Manual Build + Install

Build the package:
```bash
./build-deb.sh
```

Install it:
```bash
sudo dpkg -i dist/nfc-gui_1.0.1_amd64.deb
sudo apt-get install -f
```

### Method 3: Development Mode (No Installation)

For development/testing without installing system-wide:

```bash
./run-gui.sh
```

This runs the app from the source directory using a virtual environment.

## System Requirements

### Required Packages
- `python3` (>= 3.8)
- `python3-pyqt5`
- `pcscd` (PC/SC daemon for smartcard readers)
- `libpcsclite1`

The install script and package postinst will handle these automatically.

### Hardware
- ACS ACR1252U USB NFC Reader
- NTAG213/215/216 NFC tags

## Post-Installation

### 1. Connect Your NFC Reader

Plug in your ACS ACR1252U USB NFC reader.

### 2. Verify Service

Check that pcscd is running:
```bash
sudo systemctl status pcscd
```

Should show "active (running)".

### 3. Check Reader Detection

```bash
pcsc_scan
```

Should detect your ACR1252 reader.

### 4. Check Permissions

Your user should be in the `scard` group:
```bash
groups
```

If not listed, **log out and back in** for group changes to take effect.

### 5. Launch the Application

From command line:
```bash
nfc-gui
```

From application menu:
- Search for "NFC Reader/Writer"
- Or look in Utilities category

## First Use

1. **Launch** the application
2. **Read Mode**: Present an NFC tag to test reading
3. **Write Mode**: Enter a URL and write to a blank tag

## Troubleshooting

### "No NFC reader found"
- Ensure ACR1252 is connected via USB
- Check `sudo systemctl status pcscd`
- Run `pcsc_scan` to verify reader detection

### "Permission denied" errors
- Add user to scard group: `sudo usermod -a -G scard $USER`
- Log out and back in
- Verify with `groups` command

### Chrome doesn't open URLs
- Install Google Chrome: `sudo apt install google-chrome-stable`
- Or Chromium as alternative: `sudo apt install chromium-browser`
- Fallback uses default browser via `xdg-open`

## Upgrading

### From Previous Version

```bash
# Remove old version
sudo dpkg -r nfc-gui

# Install new version
./install.sh
```

Or:
```bash
sudo dpkg -i dist/nfc-gui_1.0.1_amd64.deb
```

dpkg will automatically replace the old version.

## Uninstalling

```bash
sudo dpkg -r nfc-gui
```

This removes the package but keeps your configuration.

To completely remove including config:
```bash
sudo dpkg --purge nfc-gui
```

## Package Contents

```
/usr/bin/nfc-gui                           # Launcher script
/usr/share/nfc-gui/                        # Application files
/usr/share/nfc-gui/nfc_gui/                # Python package
/usr/share/nfc-gui/requirements.txt        # Dependencies
/usr/share/applications/nfc-gui.desktop    # Desktop entry
/usr/share/icons/hicolor/48x48/apps/       # Icon
```

## Support

- **Issues**: Check CHANGELOG.md and README.md
- **Hardware**: Tested with ACS ACR1252U and NTAG213 tags
- **OS**: Ubuntu/Debian-based Linux distributions

## Version Information

- **Current Version**: 1.0.1
- **Release Date**: 2025-11-15
- **Package Size**: ~30 KB
- **Python Version**: 3.8+
