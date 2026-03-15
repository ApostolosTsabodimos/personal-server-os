#!/bin/bash
# PSO GitHub Preparation Script
# Run this before making repository public
#
# Usage:
#   ./prepare_for_github.sh              # Output to terminal only
#   ./prepare_for_github.sh -o report.txt  # Output to both terminal and file

set -e

# Parse command line arguments
OUTPUT_FILE=""
while [[ $# -gt 0 ]]; do
    case $1 in
        -o|--output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [-o|--output FILE]"
            echo "  -o, --output FILE    Save output to FILE (without color codes)"
            echo "  -h, --help           Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use -h for help"
            exit 1
            ;;
    esac
done

# If output file specified, set up output redirection
if [ -n "$OUTPUT_FILE" ]; then
    # Create a temporary file for colored output
    TEMP_OUTPUT=$(mktemp)
    # Redirect stdout and stderr to tee, which writes to both terminal and temp file
    exec > >(tee "$TEMP_OUTPUT") 2>&1
    # Set up trap to strip colors and save to final file on exit
    trap "sed 's/\x1b\[[0-9;]*m//g' '$TEMP_OUTPUT' > '$OUTPUT_FILE'; rm -f '$TEMP_OUTPUT'; echo ''; echo '📄 Report saved to: $OUTPUT_FILE'" EXIT
fi

echo "🔍 PSO GitHub Readiness Check"
echo "=============================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track issues
ISSUES=0

# 1. Check for personal information
echo "1️⃣  Checking for personal information..."
echo ""

echo "   Searching for personal paths..."
PERSONAL_PATHS=$(grep -r "/home/apostolos" --exclude-dir=.git --exclude-dir=__pycache__ --exclude-dir=.venv --exclude-dir=venv --exclude="*.db" --exclude="prepare_for_github.sh" . 2>/dev/null || true)
if [ -n "$PERSONAL_PATHS" ]; then
    echo -e "${RED}   ❌ Found hardcoded personal paths:${NC}"
    echo "$PERSONAL_PATHS" | head -10
    ISSUES=$((ISSUES+1))
else
    echo -e "${GREEN}   ✅ No personal paths found${NC}"
fi
echo ""

echo "   Searching for email addresses..."
EMAILS=$(grep -rE "[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}" --exclude-dir=.git --exclude-dir=__pycache__ --exclude="prepare_for_github.sh" . 2>/dev/null || true)
if [ -n "$EMAILS" ]; then
    echo -e "${YELLOW}   ⚠️  Found email addresses (review manually):${NC}"
    echo "$EMAILS" | head -5
    echo "   (These might be OK if they're in documentation)"
fi
echo ""

echo "   Searching for personal GitHub usernames..."
GITHUB_USERNAMES=$(grep -rE "github\.com/[A-Za-z0-9_-]+" --exclude-dir=.git --exclude-dir=__pycache__ --exclude-dir=.venv --exclude-dir=venv --exclude="prepare_for_github.sh" --exclude-dir=services . 2>/dev/null | grep -v "api.github.com" | grep -v "raw.github" | grep -v "github.com/your-" | grep -v "github.com/YOUR_" | grep -v "nginx/nginx" | grep -v "portainer/portainer" | grep -v "bastienwirtz/homer" | grep -v "firefly-iii" | grep -v "home-assistant" | grep -v "dperson/openvpn" | grep -v "nextcloud" | grep -v "docmost" | grep -v "filebrowser" | grep -v "zadam/trilium" | grep -v "dani-garcia" | grep -v "jellyfin" | grep -v "immich-app" | grep -v "Prowlarr" | grep -v "Tautulli" | grep -v "grafana" | grep -v "louislam" | grep -v "influxdata" | grep -v "pi-hole" | grep -v "Koenkk" | grep -v "eclipse/mosquitto" | grep -v "pypa/pip" || true)
if [ -n "$GITHUB_USERNAMES" ]; then
    echo -e "${RED}   ❌ Found personal GitHub username(s):${NC}"
    echo "$GITHUB_USERNAMES" | head -5
    ISSUES=$((ISSUES+1))
else
    echo -e "${GREEN}   ✅ No personal GitHub usernames found${NC}"
fi
echo ""

# 2. Check for secrets
echo "2️⃣  Checking for potential secrets..."
echo ""

echo "   Searching for passwords/keys/tokens..."
SECRETS=$(grep -riE "(password|secret|key|token).*=.*['\"]" --exclude-dir=.git --exclude-dir=__pycache__ --exclude="*.db" --exclude="prepare_for_github.sh" . 2>/dev/null | grep -v "default" || true)
if [ -n "$SECRETS" ]; then
    echo -e "${YELLOW}   ⚠️  Found potential secrets (review manually):${NC}"
    echo "$SECRETS" | head -10
    echo "   (Default credentials and API field names are OK)"
fi
echo ""

# 3. Check .gitignore exists
echo "3️⃣  Checking .gitignore..."
echo ""

if [ -f ".gitignore" ]; then
    echo -e "${GREEN}   ✅ .gitignore exists${NC}"

    # Check if important items are in .gitignore
    REQUIRED_IGNORES=("*.db" "*.env" "__pycache__" ".pso_dev")
    for item in "${REQUIRED_IGNORES[@]}"; do
        if grep -q "$item" .gitignore; then
            echo -e "${GREEN}   ✅ .gitignore includes $item${NC}"
        else
            echo -e "${RED}   ❌ .gitignore missing: $item${NC}"
            ISSUES=$((ISSUES+1))
        fi
    done
else
    echo -e "${RED}   ❌ .gitignore does not exist!${NC}"
    ISSUES=$((ISSUES+1))
fi
echo ""

# 4. Check for database files
echo "4️⃣  Checking for database files in git..."
echo ""

DB_FILES=$(git ls-files | grep -E "\.db$|\.sqlite" || true)
if [ -n "$DB_FILES" ]; then
    echo -e "${RED}   ❌ Database files are tracked in git:${NC}"
    echo "$DB_FILES"
    echo "   Run: git rm --cached $DB_FILES"
    ISSUES=$((ISSUES+1))
else
    echo -e "${GREEN}   ✅ No database files in git${NC}"
fi
echo ""

# 5. Check for documentation
echo "5️⃣  Checking for essential documentation..."
echo ""

DOCS=("README.md" "LICENSE" "docs/INSTALL.md" "docs/USER_GUIDE.md")
for doc in "${DOCS[@]}"; do
    if [ -f "$doc" ]; then
        echo -e "${GREEN}   ✅ $doc exists${NC}"
    else
        echo -e "${RED}   ❌ $doc missing${NC}"
        ISSUES=$((ISSUES+1))
    fi
done
echo ""

# 6. Run code quality checks (if tools available)
echo "6️⃣  Running code quality checks..."
echo ""

if command -v black &> /dev/null; then
    echo "   Running black formatter check..."
    if black --check --line-length=120 core/ web/ 2>/dev/null; then
        echo -e "${GREEN}   ✅ Code is formatted${NC}"
    else
        echo -e "${YELLOW}   ⚠️  Code needs formatting. Run: black --line-length=120 .${NC}"
    fi
else
    echo -e "${YELLOW}   ⚠️  black not installed (pip install black)${NC}"
fi
echo ""

if command -v flake8 &> /dev/null; then
    echo "   Running flake8 linter..."
    if flake8 core/ web/ --max-line-length=120 --count 2>/dev/null; then
        echo -e "${GREEN}   ✅ No linting issues${NC}"
    else
        echo -e "${YELLOW}   ⚠️  Linting issues found (non-critical)${NC}"
    fi
else
    echo -e "${YELLOW}   ⚠️  flake8 not installed (pip install flake8)${NC}"
fi
echo ""

# 7. Check for TODOs
echo "7️⃣  Checking for TODO comments..."
echo ""

TODOS=$(grep -r "TODO\|FIXME\|XXX\|HACK" --exclude-dir=.git --exclude-dir=__pycache__ --exclude="prepare_for_github.sh" core/ web/ 2>/dev/null || true)
if [ -n "$TODOS" ]; then
    TODO_COUNT=$(echo "$TODOS" | wc -l)
    echo -e "${YELLOW}   ⚠️  Found $TODO_COUNT TODO/FIXME comments${NC}"
    echo "   (These should be completed or removed before release)"
    echo "$TODOS" | head -5
else
    echo -e "${GREEN}   ✅ No TODO comments found${NC}"
fi
echo ""

# 8. Summary
echo "📊 Summary"
echo "=========="
echo ""

if [ $ISSUES -eq 0 ]; then
    echo -e "${GREEN}✅ No critical issues found!${NC}"
    echo ""
    echo "Recommended next steps:"
    echo "1. Review warnings above (yellow items)"
    echo "2. Write essential documentation (README, etc.)"
    echo "3. Test on another platform (Ubuntu VM, macOS)"
    echo "4. Run: git add . && git commit -m 'Prepare for public release'"
    echo "5. Push to GitHub"
else
    echo -e "${RED}❌ Found $ISSUES critical issue(s) that MUST be fixed${NC}"
    echo ""
    echo "Fix these before making repository public!"
fi
echo ""

echo "📖 Full checklist: See GITHUB_READINESS.md"
echo ""
