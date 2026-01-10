#!/bin/bash
set -e

# NFC GUI - Local Update Script
# Rebuilds Debian package and updates installed version

APP_NAME="nfc-gui"
APP_VERSION="1.4.11"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
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

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_header "NFC GUI - Local Update v${APP_VERSION}"

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    print_error "Do not run this script as root/sudo"
    echo "This script will prompt for sudo when needed"
    exit 1
fi

# Check if package is currently installed
if dpkg -l | grep -q "^ii  $APP_NAME"; then
    CURRENT_VERSION=$(dpkg -l | grep "^ii  $APP_NAME" | awk '{print $3}')
    print_success "Currently installed version: $CURRENT_VERSION"
else
    print_warning "Package not currently installed"
    CURRENT_VERSION="1.4.1"
fi

# Step 1: Build the new package
print_header "Step 1: Building Debian package"
if [ -f "build-deb.sh" ]; then
    # Update version in build-deb.sh first
    sed -i "s/APP_VERSION=\".*\"/APP_VERSION=\"${APP_VERSION}\"/" build-deb.sh
    print_success "Updated build-deb.sh version to ${APP_VERSION}"

    ./build-deb.sh
    print_success "Package built successfully"
else
    print_error "build-deb.sh not found"
    exit 1
fi

# Step 2: Stop running instances
print_header "Step 2: Stopping running instances"
if pgrep -f "nfc_gui.gui" > /dev/null; then
    print_warning "Stopping running NFC GUI instances..."
    pkill -f "nfc_gui.gui" || true
    sleep 1
    print_success "Stopped running instances"
else
    print_success "No running instances found"
fi

# Step 3: Install/upgrade the package
print_header "Step 3: Installing package"
DEB_FILE="dist/${APP_NAME}_${APP_VERSION}_amd64.deb"

if [ ! -f "$DEB_FILE" ]; then
    print_error "Package file not found: $DEB_FILE"
    exit 1
fi

echo "Installing $DEB_FILE..."
sudo dpkg -i "$DEB_FILE"

# Fix any dependency issues
print_success "Fixing dependencies..."
sudo apt-get install -f -y

# Verify installation
print_header "Step 4: Verifying installation"
if dpkg -l | grep -q "^ii  $APP_NAME"; then
    NEW_VERSION=$(dpkg -l | grep "^ii  $APP_NAME" | awk '{print $3}')
    print_success "Package installed successfully!"
    echo ""
    echo -e "${GREEN}Version: $NEW_VERSION${NC}"

    if [ "$CURRENT_VERSION" != "none" ] && [ "$CURRENT_VERSION" != "$NEW_VERSION" ]; then
        echo -e "${GREEN}Upgraded from: $CURRENT_VERSION → $NEW_VERSION${NC}"
    fi
else
    print_error "Installation verification failed"
    exit 1
fi

# Step 5: Test launch
print_header "Update Complete!"
echo ""
echo "Package updated successfully to version ${APP_VERSION}"
echo ""
echo "To launch the application:"
echo "  - From command line: nfc-gui"
echo "  - From application menu: Search for 'NFC Reader/Writer'"
echo ""
echo "New features in v1.2.0:"
echo "  • System tray integration"
echo "  • Background read mode for always-on scanning"
echo "  • Minimize to tray instead of closing"
echo ""
print_warning "Note: If you were in the 'scard' group, you may need to log out/in"
print_warning "for permissions to take effect (first install only)"
echo ""
