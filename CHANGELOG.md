# Changelog

All notable changes to NFC GUI will be documented in this file.

## [1.1.0] - 2025-11-15

### Added
- Desktop launcher now installs with `TryExec`, `StartupNotify`, and icon cache refresh to improve menu reliability

### Fixed
- Debian packaging now installs Python runtime deps from apt and automatically runs `pip3 install -r requirements.txt` (restoring `ndeflib`)
- Launcher script uses `exec` and a deterministic working directory so `.desktop` entries open the GUI consistently
- Post-install script gracefully handles environments where `SUDO_USER` is unavailable and still ensures `pcscd` is enabled


## [1.0.1] - 2025-11-15

### Fixed
- **Chrome Auto-Open**: URLs now open in Google Chrome instead of default browser
  - Primary: `google-chrome` command
  - Fallback 1: `chromium-browser` command
  - Fallback 2: `xdg-open` (default browser)

- **URL Redirect Logic**: Expanded to handle all local Homebox URL formats
  - Now supports any IP in 10.0.0.x subnet (not just 10.0.0.1)
  - Handles malformed URLs like `https://10.0.0.3100/item/X` (port attached to IP)
  - Normalizes double slashes: `//item/` → `/item/`
  - Supports URLs with or without port numbers

- **Version Consistency**: Synchronized version numbers across all files
  - `__init__.py`: 1.0.1
  - `gui.py` window title: v1.0.1
  - `build.sh`: 1.0.1

### Changed
- Updated README with comprehensive URL redirection documentation
- Enhanced error messaging for browser opening failures

## [1.0.0] - 2024-10-04

### Added
- Initial release with PyQt5 GUI
- Read mode with automatic URL opening
- Write mode with batch support
- Tag locking capability
- URL redirection for local Homebox instances
- Clipboard integration
- Real-time activity logging
