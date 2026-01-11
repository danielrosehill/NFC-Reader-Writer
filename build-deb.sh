#!/bin/bash
set -e

# NFC GUI - Debian Package Builder (Debian-only, no install)
# Use this for building packages without installing

APP_NAME="nfc-gui"
APP_VERSION="1.4.16"
BUILD_DIR="build"
DIST_DIR="dist"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_header "NFC GUI - Debian Package Builder v${APP_VERSION}"

# Check dependencies
if ! command -v dpkg-deb &> /dev/null; then
    print_error "dpkg-deb not found. Install with: sudo apt install dpkg-dev"
    exit 1
fi
print_success "dpkg-deb available"

# Clean previous builds
print_header "Cleaning previous builds"
rm -rf "$BUILD_DIR" "$DIST_DIR"
mkdir -p "$BUILD_DIR" "$DIST_DIR"
print_success "Build directories cleaned"

# Build the package
print_header "Building Debian package"

DEB_DIR="$BUILD_DIR/${APP_NAME}_${APP_VERSION}"

# Create directory structure
mkdir -p "$DEB_DIR/DEBIAN"
mkdir -p "$DEB_DIR/usr/bin"
mkdir -p "$DEB_DIR/usr/share/applications"
mkdir -p "$DEB_DIR/usr/share/$APP_NAME"
mkdir -p "$DEB_DIR/usr/share/icons/hicolor/48x48/apps"
mkdir -p "$DEB_DIR/usr/share/icons/hicolor/128x128/apps"
mkdir -p "$DEB_DIR/usr/share/icons/hicolor/256x256/apps"

# Create control file
cat > "$DEB_DIR/DEBIAN/control" << EOF
Package: $APP_NAME
Version: $APP_VERSION
Section: utils
Priority: optional
Architecture: amd64
Depends: python3 (>= 3.8), python3-pip, python3-pyqt5, python3-pyscard, python3-pyperclip, pcscd, libpcsclite1
Maintainer: Daniel Rosehill
Description: NFC Reader/Writer GUI for ACS ACR1252
 A modern PyQt5-based GUI application for reading and writing NFC tags
 using the ACS ACR1252U USB NFC Reader on Linux systems.
 .
 Features:
  - Read NFC tags and auto-open URLs in Chrome
  - Write URLs to NFC tags with optional locking
  - Batch write operations
  - URL redirection for local Homebox instances
  - Clipboard integration
EOF

# Create postinst script
cat > "$DEB_DIR/DEBIAN/postinst" << 'POSTINST'
#!/bin/bash
set -e

# Determine desktop user to manage scard membership
TARGET_USER="${SUDO_USER:-}"
if [ -z "$TARGET_USER" ]; then
    TARGET_USER="$(logname 2>/dev/null || true)"
fi

# Ensure scard group exists
if ! getent group scard >/dev/null; then
    groupadd --system scard || true
fi

if [ -n "$TARGET_USER" ] && id "$TARGET_USER" &>/dev/null; then
    if id -nG "$TARGET_USER" | grep -q '\bscard\b'; then
        echo "User $TARGET_USER already in scard group"
    else
        usermod -a -G scard "$TARGET_USER" || true
        echo "Added $TARGET_USER to scard group. Log out/in for permissions to take effect."
    fi
else
    echo "Could not determine desktop user; please manually ensure your account is in the 'scard' group." >&2
fi

# Ensure pcscd is enabled
systemctl enable pcscd 2>/dev/null || true
systemctl start pcscd 2>/dev/null || true

# Install Python dependencies (needed for ndeflib)
if command -v pip3 &>/dev/null; then
    cd /usr/share/nfc-gui
    pip3 install -q -r requirements.txt --break-system-packages 2>/dev/null || \
        pip3 install -q -r requirements.txt 2>/dev/null || true
else
    echo "pip3 not found; install python3-pip to ensure NFC GUI dependencies are available." >&2
fi

# Refresh desktop caches
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache &>/dev/null; then
    gtk-update-icon-cache -q /usr/share/icons/hicolor 2>/dev/null || true
fi

exit 0
POSTINST
chmod 755 "$DEB_DIR/DEBIAN/postinst"

# Copy application files
cp -r nfc_gui "$DEB_DIR/usr/share/$APP_NAME/"
cp requirements.txt "$DEB_DIR/usr/share/$APP_NAME/"

# Create launcher script
cat > "$DEB_DIR/usr/bin/$APP_NAME" << 'LAUNCHER'
#!/bin/bash
set -euo pipefail
APP_DIR="/usr/share/nfc-gui"
cd "$APP_DIR"
exec /usr/bin/python3 -m nfc_gui.gui "$@"
LAUNCHER
chmod 755 "$DEB_DIR/usr/bin/$APP_NAME"

# Create desktop entry
cat > "$DEB_DIR/usr/share/applications/$APP_NAME.desktop" << DESKTOP
[Desktop Entry]
Version=1.0
Type=Application
Name=NFC Reader/Writer
Comment=NFC Reader/Writer GUI for ACS ACR1252
Exec=/usr/bin/$APP_NAME
TryExec=/usr/bin/$APP_NAME
Icon=$APP_NAME
StartupNotify=true
Terminal=false
Categories=Utility;
Keywords=nfc;reader;writer;tag;
DESKTOP

# Copy application icons (multiple sizes for better display quality)
cp assets/nfc-icon-48.png "$DEB_DIR/usr/share/icons/hicolor/48x48/apps/$APP_NAME.png"
cp assets/nfc-icon-128.png "$DEB_DIR/usr/share/icons/hicolor/128x128/apps/$APP_NAME.png"
cp assets/nfc-icon-256.png "$DEB_DIR/usr/share/icons/hicolor/256x256/apps/$APP_NAME.png"

# Build the .deb package
DEB_FILE="${DIST_DIR}/${APP_NAME}_${APP_VERSION}_amd64.deb"
dpkg-deb --build "$DEB_DIR" "$DEB_FILE"

print_success "Debian package built: $DEB_FILE"

# Show package info
print_header "Package Information"
dpkg-deb --info "$DEB_FILE"
echo ""
ls -lh "$DEB_FILE"

print_header "Build Complete!"
echo ""
echo "Package: $DEB_FILE"
echo ""
echo "To install:"
echo "  sudo dpkg -i $DEB_FILE"
echo "  sudo apt-get install -f"
echo ""
echo "Or use the install script:"
echo "  ./install.sh"
