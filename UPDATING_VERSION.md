# Version Update Guide

Quick reference for updating the version number when releasing new versions.

## Files to Update

When releasing a new version (e.g., 1.0.1 → 1.0.2), update the version number in these files:

### 1. `nfc_gui/__init__.py`
```python
__version__ = "1.0.2"  # Update this
```

### 2. `nfc_gui/gui.py`
```python
def init_ui(self):
    """Initialize the user interface"""
    self.setWindowTitle("NFC Reader/Writer - ACS ACR1252 - v1.0.2")  # Update version here
```

Line ~38

### 3. `build-deb.sh`
```bash
APP_VERSION="1.0.2"  # Update this
```

Line ~8

### 4. `install.sh`
```bash
APP_VERSION="1.0.2"  # Update this
```

Line ~8

### 5. `README.md`
Update installation instructions if version is referenced:
```bash
sudo dpkg -i dist/nfc-gui_1.0.2_amd64.deb  # Update version
```

Line ~54

### 6. `CHANGELOG.md`
Add new version entry at the top:
```markdown
## [1.0.2] - YYYY-MM-DD

### Added
- New feature description

### Fixed
- Bug fix description

### Changed
- Change description
```

## Version Numbering

Follow semantic versioning:
- **Major (X.0.0)**: Breaking changes, major rewrites
- **Minor (1.X.0)**: New features, backward compatible
- **Patch (1.0.X)**: Bug fixes, small improvements

## Quick Update Script

You can use this one-liner to update all version numbers:

```bash
# Set new version
NEW_VERSION="1.0.2"

# Update all files
sed -i "s/__version__ = \"[0-9.]*\"/__version__ = \"$NEW_VERSION\"/" nfc_gui/__init__.py
sed -i "s/v[0-9.]*\"/v$NEW_VERSION\"/" nfc_gui/gui.py
sed -i "s/APP_VERSION=\"[0-9.]*\"/APP_VERSION=\"$NEW_VERSION\"/" build-deb.sh
sed -i "s/APP_VERSION=\"[0-9.]*\"/APP_VERSION=\"$NEW_VERSION\"/" install.sh
sed -i "s/nfc-gui_[0-9.]*/nfc-gui_$NEW_VERSION/" README.md

echo "✓ Version updated to $NEW_VERSION in all files"
echo "⚠ Don't forget to update CHANGELOG.md manually!"
```

## Build and Release Workflow

After updating version numbers:

```bash
# 1. Test the application
./run-gui.sh

# 2. Build the new package
./build-deb.sh

# 3. Test the package (optional)
sudo dpkg -i dist/nfc-gui_<VERSION>_amd64.deb

# 4. Commit changes
git add .
git commit -m "Release version <VERSION>"

# 5. Tag the release
git tag -a v<VERSION> -m "Version <VERSION>"

# 6. Push to GitHub
git push origin main
git push origin v<VERSION>
```

## Verification Checklist

Before releasing:

- [ ] All version numbers updated consistently
- [ ] CHANGELOG.md updated with changes
- [ ] Application tested in development mode
- [ ] Package builds successfully
- [ ] Package installs correctly
- [ ] NFC reader functions work as expected
- [ ] Chrome auto-open works
- [ ] URL redirection works
- [ ] Git committed and tagged
