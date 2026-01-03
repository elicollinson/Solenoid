#!/bin/bash
#
# Solenoid Release Script
#
# Usage: ./scripts/release.sh <version>
# Example: ./scripts/release.sh 1.2.0
#
# This script:
# 1. Updates version numbers in pyproject.toml and main_bundled.py
# 2. Commits the version bump
# 3. Creates and pushes a git tag
# 4. Generates the SHA256 for the formula
# 5. Outputs instructions for updating the Homebrew formula
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check for version argument
if [ -z "$1" ]; then
    echo -e "${RED}Error: Version argument required${NC}"
    echo "Usage: $0 <version>"
    echo "Example: $0 1.2.0"
    exit 1
fi

VERSION="$1"
TAG="v${VERSION}"

echo -e "${GREEN}=== Solenoid Release Script ===${NC}"
echo "Releasing version: ${VERSION}"
echo ""

# Validate we're in the right directory
if [ ! -f "pyproject.toml" ]; then
    echo -e "${RED}Error: Must run from project root directory${NC}"
    exit 1
fi

# Check for clean git state
if [ -n "$(git status --porcelain)" ]; then
    echo -e "${RED}Error: Working directory not clean. Commit or stash changes first.${NC}"
    git status --short
    exit 1
fi

# Update version in pyproject.toml
echo -e "${YELLOW}Updating pyproject.toml...${NC}"
sed -i '' "s/^version = \".*\"/version = \"${VERSION}\"/" pyproject.toml

# Update version in main_bundled.py
echo -e "${YELLOW}Updating main_bundled.py...${NC}"
sed -i '' "s/^VERSION = \".*\"/VERSION = \"${VERSION}\"/" main_bundled.py

# Commit version bump
echo -e "${YELLOW}Committing version bump...${NC}"
git add pyproject.toml main_bundled.py
git commit -m "chore: bump version to ${VERSION}"

# Create and push tag
echo -e "${YELLOW}Creating tag ${TAG}...${NC}"
git tag -a "${TAG}" -m "Release ${VERSION}"

echo -e "${YELLOW}Pushing changes and tag...${NC}"
git push origin main
git push origin "${TAG}"

# Wait for GitHub to process the tag
echo -e "${YELLOW}Waiting for GitHub to process tag...${NC}"
sleep 3

# Get SHA256 of the source archive
ARCHIVE_URL="https://github.com/elicollinson/Solenoid/archive/refs/tags/${TAG}.tar.gz"
echo -e "${YELLOW}Fetching source archive SHA256...${NC}"
SHA256=$(curl -sL "${ARCHIVE_URL}" | shasum -a 256 | cut -d' ' -f1)

echo ""
echo -e "${GREEN}=== Release Complete ===${NC}"
echo ""
echo -e "${GREEN}Next steps:${NC}"
echo ""
echo "1. Update the Homebrew formula in homebrew-solenoid/Formula/solenoid.rb:"
echo ""
echo "   url \"${ARCHIVE_URL}\""
echo "   sha256 \"${SHA256}\""
echo "   version \"${VERSION}\""
echo ""
echo "2. Generate resource stanzas (from the Solenoid project directory):"
echo ""
echo "   brew update-python-resources /path/to/homebrew-solenoid/Formula/solenoid.rb"
echo ""
echo "   Or manually with poet:"
echo "   poetry run pip install homebrew-pypi-poet"
echo "   poetry run poet -r solenoid > resources.txt"
echo ""
echo "3. Commit and push the formula update:"
echo "   cd ../homebrew-solenoid"
echo "   git add Formula/solenoid.rb"
echo "   git commit -m \"chore: update solenoid to ${VERSION}\""
echo "   git push origin main"
echo ""
echo "4. Test the installation:"
echo "   brew update"
echo "   brew upgrade solenoid"
echo ""
