#!/bin/bash
set -e

# NFC GUI Build Script
# Builds .deb package, standalone executable, and AppImage for Ubuntu Linux

APP_NAME="nfc-gui"
APP_VERSION="1.4.2"
AUTHOR="Daniel Rosehill"
DESCRIPTION="NFC Reader/Writer GUI for ACS ACR1252"
BUILD_DIR="build"
DIST_DIR="dist"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

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

# Clean previous builds
clean_build() {
    print_header "Cleaning previous builds"
    rm -rf "$BUILD_DIR" "$DIST_DIR"
    mkdir -p "$BUILD_DIR" "$DIST_DIR"
    print_success "Build directories cleaned"
}

# Check dependencies
check_dependencies() {
    print_header "Checking dependencies"

    # Check for PyInstaller - use venv
    if ! python3 -c "import PyInstaller" 2>/dev/null; then
        echo "Installing PyInstaller in virtual environment..."
        if [ ! -d ".venv" ]; then
            python3 -m venv .venv
        fi
        source .venv/bin/activate
        pip install pyinstaller
    else
        # Activate existing venv if it exists
        if [ -d ".venv" ]; then
            source .venv/bin/activate
        fi
    fi
    print_success "PyInstaller available"

    # Check for dpkg-deb
    if ! command -v dpkg-deb &> /dev/null; then
        print_error "dpkg-deb not found. Install with: sudo apt install dpkg-dev"
        exit 1
    fi
    print_success "dpkg-deb available"

    # Check for appimagetool (optional)
    if ! command -v appimagetool &> /dev/null; then
        echo "appimagetool not found. Will download it..."
        wget -q https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage -O /tmp/appimagetool
        chmod +x /tmp/appimagetool
        APPIMAGETOOL="/tmp/appimagetool"
    else
        APPIMAGETOOL="appimagetool"
    fi
    print_success "AppImage tools ready"
}

# Build standalone executable with PyInstaller
build_executable() {
    print_header "Building standalone executable"

    # Create a wrapper script that can be packaged
    cat > build/run_nfc_gui.py << 'EOF'
#!/usr/bin/env python3
import sys
import os

# Add the directory containing nfc_gui to the path
if getattr(sys, 'frozen', False):
    # Running in PyInstaller bundle
    bundle_dir = sys._MEIPASS
else:
    # Running in normal Python environment
    bundle_dir = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, bundle_dir)

# Now import and run the GUI
from nfc_gui.gui import main

if __name__ == "__main__":
    main()
EOF

    pyinstaller --noconfirm \
        --onefile \
        --windowed \
        --name "$APP_NAME" \
        --add-data "nfc_gui:nfc_gui" \
        --hidden-import="PyQt5.QtWidgets" \
        --hidden-import="PyQt5.QtCore" \
        --hidden-import="PyQt5.QtGui" \
        --hidden-import="smartcard" \
        --hidden-import="smartcard.System" \
        --hidden-import="smartcard.CardMonitoring" \
        --hidden-import="smartcard.CardConnection" \
        --hidden-import="pyperclip" \
        build/run_nfc_gui.py

    print_success "Executable built: dist/$APP_NAME"
}

# Build .deb package
build_deb() {
    print_header "Building .deb package"

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
Depends: python3 (>= 3.8), python3-pip, python3-pyqt5, python3-pyscard, python3-pyperclip, pcscd, libpcsclite1
Maintainer: $AUTHOR
Description: $DESCRIPTION
 A modern PyQt5-based GUI application for reading and writing NFC tags
 using the ACS ACR1252U USB NFC Reader on Linux systems.
EOF

    # Create postinst script
    cat > "$DEB_DIR/DEBIAN/postinst" << 'EOF'
#!/bin/bash
set -e

# Determine target user for scard group membership
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
    echo "Could not determine desktop user; please ensure your account belongs to the 'scard' group." >&2
fi

# Ensure pcscd is enabled
systemctl enable pcscd 2>/dev/null || true
systemctl start pcscd 2>/dev/null || true

# Install Python dependencies (for ndeflib, etc.)
if command -v pip3 &>/dev/null; then
    cd /usr/share/nfc-gui
    pip3 install -q -r requirements.txt --break-system-packages 2>/dev/null || \
        pip3 install -q -r requirements.txt 2>/dev/null || true
else
    echo "pip3 not found; install python3-pip to ensure NFC GUI dependencies are available." >&2
fi

# Refresh desktop integration caches
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache &>/dev/null; then
    gtk-update-icon-cache -q /usr/share/icons/hicolor 2>/dev/null || true
fi

exit 0
EOF
    chmod 755 "$DEB_DIR/DEBIAN/postinst"

    # Copy application files
    cp -r nfc_gui "$DEB_DIR/usr/share/$APP_NAME/"
    cp requirements.txt "$DEB_DIR/usr/share/$APP_NAME/"

    # Create launcher script
    cat > "$DEB_DIR/usr/bin/$APP_NAME" << 'EOF'
#!/bin/bash
set -euo pipefail
APP_DIR="/usr/share/nfc-gui"
cd "$APP_DIR"
exec python3 -m nfc_gui.gui "$@"
EOF
    chmod 755 "$DEB_DIR/usr/bin/$APP_NAME"

    # Create desktop entry
    cat > "$DEB_DIR/usr/share/applications/$APP_NAME.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=NFC Reader/Writer
Comment=$DESCRIPTION
Exec=/usr/bin/$APP_NAME
TryExec=/usr/bin/$APP_NAME
Icon=$APP_NAME
StartupNotify=true
Terminal=false
Categories=Utility;
Keywords=nfc;reader;writer;tag;
EOF

    # Create simple icon (text-based placeholder)
    cat > "$DEB_DIR/usr/share/icons/hicolor/48x48/apps/$APP_NAME.png" << 'EOF_ICON'
iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==
EOF_ICON

    # Build the .deb package
    dpkg-deb --build "$DEB_DIR" "$DIST_DIR/${APP_NAME}_${APP_VERSION}_amd64.deb"

    print_success "Debian package built: $DIST_DIR/${APP_NAME}_${APP_VERSION}_amd64.deb"
}

# Build AppImage
build_appimage() {
    print_header "Building AppImage"

    APPDIR="$BUILD_DIR/${APP_NAME}.AppDir"

    # Create AppDir structure
    mkdir -p "$APPDIR/usr/bin"
    mkdir -p "$APPDIR/usr/lib"
    mkdir -p "$APPDIR/usr/share/applications"
    mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"

    # Copy the PyInstaller executable
    if [ ! -f "dist/$APP_NAME" ]; then
        build_executable
    fi
    cp "dist/$APP_NAME" "$APPDIR/usr/bin/"

    # Create AppRun
    cat > "$APPDIR/AppRun" << 'EOF'
#!/bin/bash
SELF=$(readlink -f "$0")
HERE=${SELF%/*}
export PATH="${HERE}/usr/bin:${PATH}"
export LD_LIBRARY_PATH="${HERE}/usr/lib:${LD_LIBRARY_PATH}"
exec "${HERE}/usr/bin/nfc-gui" "$@"
EOF
    chmod 755 "$APPDIR/AppRun"

    # Create desktop file
    cat > "$APPDIR/usr/share/applications/$APP_NAME.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=NFC Reader/Writer
Comment=$DESCRIPTION
Exec=$APP_NAME
Icon=$APP_NAME
Terminal=false
Categories=Utility;
EOF

    # Copy desktop file to AppDir root
    cp "$APPDIR/usr/share/applications/$APP_NAME.desktop" "$APPDIR/"

    # Create simple icon
    cp "$BUILD_DIR/${APP_NAME}_${APP_VERSION}/usr/share/icons/hicolor/48x48/apps/$APP_NAME.png" \
       "$APPDIR/usr/share/icons/hicolor/256x256/apps/" 2>/dev/null || \
       echo "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==" | base64 -d > "$APPDIR/$APP_NAME.png"

    cp "$APPDIR/usr/share/icons/hicolor/256x256/apps/$APP_NAME.png" "$APPDIR/" 2>/dev/null || \
       cp "$APPDIR/$APP_NAME.png" "$APPDIR/" || true

    # Build AppImage
    ARCH=x86_64 $APPIMAGETOOL "$APPDIR" "$DIST_DIR/${APP_NAME}-${APP_VERSION}-x86_64.AppImage"

    print_success "AppImage built: $DIST_DIR/${APP_NAME}-${APP_VERSION}-x86_64.AppImage"
}

# Main build process
main() {
    print_header "NFC GUI Build Script"
    echo "Building version $APP_VERSION"
    echo ""

    # Parse arguments
    BUILD_DEB=false
    BUILD_EXE=false
    BUILD_APPIMAGE=false

    if [ $# -eq 0 ]; then
        # Build all by default
        BUILD_DEB=true
        BUILD_EXE=true
        BUILD_APPIMAGE=true
    else
        for arg in "$@"; do
            case $arg in
                --deb)
                    BUILD_DEB=true
                    ;;
                --exe)
                    BUILD_EXE=true
                    ;;
                --appimage)
                    BUILD_APPIMAGE=true
                    ;;
                --all)
                    BUILD_DEB=true
                    BUILD_EXE=true
                    BUILD_APPIMAGE=true
                    ;;
                --help)
                    echo "Usage: $0 [OPTIONS]"
                    echo ""
                    echo "Options:"
                    echo "  --deb        Build .deb package only"
                    echo "  --exe        Build standalone executable only"
                    echo "  --appimage   Build AppImage only"
                    echo "  --all        Build all formats (default)"
                    echo "  --help       Show this help message"
                    exit 0
                    ;;
                *)
                    print_error "Unknown option: $arg"
                    echo "Use --help for usage information"
                    exit 1
                    ;;
            esac
        done
    fi

    clean_build
    check_dependencies

    if [ "$BUILD_EXE" = true ]; then
        build_executable
    fi

    if [ "$BUILD_DEB" = true ]; then
        build_deb
    fi

    if [ "$BUILD_APPIMAGE" = true ]; then
        build_appimage
    fi

    print_header "Build Complete!"
    echo ""
    echo "Build artifacts in $DIST_DIR:"
    ls -lh "$DIST_DIR"
    echo ""
    print_success "All builds completed successfully!"
}

# Run main
main "$@"
