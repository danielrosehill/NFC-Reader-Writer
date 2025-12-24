#!/bin/bash
# NFC GUI - Update Script
# Builds new package and installs it on the system

set -euo pipefail

# Colors for output
BLUE='\033[0;34m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}NFC GUI - Update Script${NC}"
echo -e "${BLUE}========================================${NC}"

# Check if running as root
if [ "$EUID" -eq 0 ]; then
   echo -e "${RED}Error: Do not run this script as root/sudo${NC}"
   echo -e "${YELLOW}The script will prompt for sudo when needed${NC}"
   exit 1
fi

echo ""
echo -e "${BLUE}Step 1: Building new package...${NC}"
echo ""

# Run the install script to build the package
./install.sh

if [ ! -f "dist/nfc-gui_1.1.0_amd64.deb" ]; then
    echo -e "${RED}Error: Package build failed${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}✓ Package built successfully${NC}"
echo ""
echo -e "${BLUE}Step 2: Installing package...${NC}"
echo ""

# Install the package
sudo dpkg -i dist/nfc-gui_1.1.0_amd64.deb

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}✓ Update completed successfully!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "${YELLOW}You can now run 'nfc-gui' to start the application${NC}"
else
    echo ""
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}✗ Installation failed${NC}"
    echo -e "${RED}========================================${NC}"
    exit 1
fi
