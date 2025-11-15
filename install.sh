#!/bin/bash
set -e

# NFC GUI Installation Script
# Builds and optionally installs the Debian package

APP_NAME="nfc-gui"
APP_VERSION="1.0.1"
BUILD_DIR="build"
DIST_DIR="dist"
DEB_FILE="${DIST_DIR}/${APP_NAME}_${APP_VERSION}_amd64.deb"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
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

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Check if running as root (we need sudo later)
if [ "$EUID" -eq 0 ]; then
    print_error "Please do not run this script as root"
    echo "The script will ask for sudo password when needed for installation"
    exit 1
fi

print_header "NFC GUI - Installation Script v${APP_VERSION}"

# Check dependencies
print_header "Checking build dependencies"

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 not found. Install with: sudo apt install python3"
    exit 1
fi
print_success "Python 3 available"

# Check for dpkg-deb
if ! command -v dpkg-deb &> /dev/null; then
    print_error "dpkg-deb not found. Install with: sudo apt install dpkg-dev"
    exit 1
fi
print_success "dpkg-deb available"

# Check for pcscd (runtime dependency)
if ! command -v pcscd &> /dev/null; then
    print_warning "pcscd not found - this is required at runtime"
    echo "Install with: sudo apt install pcscd"
fi

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

# Create control file
cat > "$DEB_DIR/DEBIAN/control" << EOF
Package: $APP_NAME
Version: $APP_VERSION
Section: utils
Priority: optional
Architecture: amd64
Depends: python3 (>= 3.8), python3-pyqt5, pcscd, libpcsclite1
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

# Add user to scard group if not already
if [ -n "$SUDO_USER" ]; then
    if groups $SUDO_USER | grep -q '\bscard\b'; then
        echo "User already in scard group"
    else
        usermod -a -G scard $SUDO_USER || true
        echo "Added user to scard group. Please log out and back in for changes to take effect."
    fi
fi

# Ensure pcscd is enabled
systemctl enable pcscd 2>/dev/null || true
systemctl start pcscd 2>/dev/null || true

# Install Python dependencies
cd /usr/share/nfc-gui
pip3 install -q -r requirements.txt --break-system-packages 2>/dev/null || \
    pip3 install -q -r requirements.txt 2>/dev/null || true

exit 0
POSTINST
chmod 755 "$DEB_DIR/DEBIAN/postinst"

# Copy application files
cp -r nfc_gui "$DEB_DIR/usr/share/$APP_NAME/"
cp requirements.txt "$DEB_DIR/usr/share/$APP_NAME/"

# Create launcher script
cat > "$DEB_DIR/usr/bin/$APP_NAME" << 'LAUNCHER'
#!/bin/bash
cd /usr/share/nfc-gui
python3 -m nfc_gui.gui "$@"
LAUNCHER
chmod 755 "$DEB_DIR/usr/bin/$APP_NAME"

# Create desktop entry
cat > "$DEB_DIR/usr/share/applications/$APP_NAME.desktop" << DESKTOP
[Desktop Entry]
Version=1.0
Type=Application
Name=NFC Reader/Writer
Comment=NFC Reader/Writer GUI for ACS ACR1252
Exec=$APP_NAME
Icon=$APP_NAME
Terminal=false
Categories=Utility;
Keywords=nfc;reader;writer;tag;
DESKTOP

# Create simple icon placeholder (1x1 transparent PNG)
echo "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==" | base64 -d > "$DEB_DIR/usr/share/icons/hicolor/48x48/apps/$APP_NAME.png"

# Build the .deb package
dpkg-deb --build "$DEB_DIR" "$DEB_FILE"

print_success "Debian package built: $DEB_FILE"

# Show package info
print_header "Package Information"
dpkg-deb --info "$DEB_FILE"

# Ask if user wants to install
echo ""
print_header "Installation"
echo "Package built successfully: $DEB_FILE"
echo ""
read -p "Do you want to install the package now? [y/N]: " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_header "Installing package"

    # Remove old version if exists
    if dpkg -l | grep -q "^ii.*$APP_NAME"; then
        echo "Removing old version..."
        sudo dpkg -r $APP_NAME 2>/dev/null || true
    fi

    # Install package
    sudo dpkg -i "$DEB_FILE"

    # Fix any dependency issues
    sudo apt-get install -f -y

    print_success "Installation complete!"
    echo ""
    echo "You can now run the application with: $APP_NAME"
    echo "Or find it in your application menu as 'NFC Reader/Writer'"
    echo ""
    print_warning "If this is your first installation, you may need to:"
    echo "  1. Log out and back in (for group permissions)"
    echo "  2. Connect your ACS ACR1252 NFC reader"
    echo "  3. Ensure pcscd service is running: sudo systemctl status pcscd"
else
    echo ""
    print_success "Build complete! Package saved to: $DEB_FILE"
    echo ""
    echo "To install later, run:"
    echo "  sudo dpkg -i $DEB_FILE"
    echo "  sudo apt-get install -f"
fi

echo ""
print_header "Build Complete!"
