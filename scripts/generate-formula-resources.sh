#!/bin/bash
#
# Generate Homebrew Formula Resource Stanzas
#
# This script generates the resource blocks needed for the Homebrew formula
# using homebrew-pypi-poet.
#
# Usage: ./scripts/generate-formula-resources.sh [output_file]
#
# If output_file is not specified, outputs to stdout.
#

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== Generating Homebrew Formula Resources ===${NC}"

# Ensure we're in the project root
if [ ! -f "pyproject.toml" ]; then
    echo "Error: Must run from project root directory"
    exit 1
fi

# Install poet if not present
if ! poetry run pip show homebrew-pypi-poet > /dev/null 2>&1; then
    echo -e "${YELLOW}Installing homebrew-pypi-poet...${NC}"
    poetry run pip install homebrew-pypi-poet
fi

# Get all direct dependencies from pyproject.toml
DEPS=$(grep -A 100 '\[tool.poetry.dependencies\]' pyproject.toml | \
       grep -B 100 '\[tool.poetry' | \
       grep -E '^\w+' | \
       grep -v 'python' | \
       grep -v '\[tool' | \
       cut -d'=' -f1 | \
       tr -d ' ')

echo -e "${YELLOW}Generating resources for dependencies...${NC}"
echo "This may take a few minutes as it fetches from PyPI."
echo ""

OUTPUT_FILE="${1:-/dev/stdout}"

# Generate resources for each dependency
for dep in $DEPS; do
    echo "Processing: $dep" >&2
    poetry run poet -r "$dep" 2>/dev/null || true
done | sort -u > "$OUTPUT_FILE"

if [ "$OUTPUT_FILE" != "/dev/stdout" ]; then
    echo ""
    echo -e "${GREEN}Resources written to: ${OUTPUT_FILE}${NC}"
    echo ""
    echo "Copy the contents into your Formula/solenoid.rb file"
    echo "between the 'depends_on' lines and the 'def install' block."
fi
