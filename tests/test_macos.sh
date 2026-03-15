#!/bin/bash
# PSO Test Script for macOS
# Tests installation and basic functionality on macOS systems

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test tracking
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}PSO macOS Compatibility Test${NC}"
echo -e "${BLUE}================================${NC}"
echo ""

# Function to run a test
run_test() {
    local test_name="$1"
    local test_command="$2"

    TESTS_RUN=$((TESTS_RUN + 1))
    echo -n "Testing $test_name... "

    if eval "$test_command" &>/dev/null; then
        echo -e "${GREEN}✓ PASS${NC}"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    else
        echo -e "${RED}✗ FAIL${NC}"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    fi
}

# 1. System Information
echo -e "${YELLOW}1. System Information${NC}"
echo "   OS: $(sw_vers -productName) $(sw_vers -productVersion)"
echo "   Kernel: $(uname -r)"
echo "   Architecture: $(uname -m)"
echo "   Chip: $(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo 'Unknown')"
echo ""

# 2. Prerequisites Check
echo -e "${YELLOW}2. Prerequisites${NC}"
run_test "Python 3.10+" "python3 --version | grep -E 'Python 3\.(1[0-9]|[2-9][0-9])'"
run_test "pip installed" "python3 -m pip --version"

# Check for Docker Desktop
if command -v docker &> /dev/null; then
    run_test "Docker installed" "docker --version"
    run_test "Docker running" "docker ps"
else
    echo -e "${RED}   ✗ Docker Desktop not found${NC}"
    echo "     Install from: https://www.docker.com/products/docker-desktop"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

run_test "Git installed" "git --version"
echo ""

# 3. Homebrew (macOS package manager)
echo -e "${YELLOW}3. Package Manager${NC}"
if command -v brew &> /dev/null; then
    run_test "Homebrew installed" "brew --version"
    echo "   (Homebrew found - good for installing dependencies)"
else
    echo -e "${YELLOW}   ⚠ Homebrew not found (optional but recommended)${NC}"
    echo "     Install from: https://brew.sh"
fi
echo ""

# 4. Python Dependencies
echo -e "${YELLOW}4. Python Dependencies${NC}"
run_test "Flask available" "python3 -c 'import flask'" || echo "   Install: pip3 install flask"
run_test "Docker SDK available" "python3 -c 'import docker'" || echo "   Install: pip3 install docker"
run_test "JWT available" "python3 -c 'import jwt'" || echo "   Install: pip3 install pyjwt"
run_test "Cryptography available" "python3 -c 'import cryptography'" || echo "   Install: pip3 install cryptography"
echo ""

# 5. PSO Installation Test
echo -e "${YELLOW}5. PSO Installation${NC}"
if [ -f "./pso" ]; then
    run_test "PSO executable exists" "[ -x ./pso ]"
    run_test "PSO help command" "./pso --help | grep -q 'PSO'"
    run_test "Python modules loadable" "python3 -c 'import core.database, core.auth'"
else
    echo -e "${RED}   ✗ PSO not found - skipping installation tests${NC}"
fi
echo ""

# 6. Docker Functionality
echo -e "${YELLOW}6. Docker Functionality${NC}"
if command -v docker &> /dev/null && docker ps &>/dev/null; then
    run_test "Pull test image" "docker pull hello-world:latest"
    run_test "Run test container" "docker run --rm hello-world"
    run_test "Docker network create" "docker network create pso-test-net && docker network rm pso-test-net"
    run_test "Docker volume create" "docker volume create pso-test-vol && docker volume rm pso-test-vol"
else
    echo -e "${YELLOW}   ⚠ Skipping Docker tests (Docker not available)${NC}"
fi
echo ""

# 7. Port Availability
echo -e "${YELLOW}7. Port Availability${NC}"
run_test "Port 5000 available" "! lsof -i :5000"
run_test "Port 8080 available" "! lsof -i :8080"
run_test "Port 8096 available" "! lsof -i :8096"
echo ""

# 8. Filesystem Permissions
echo -e "${YELLOW}8. Filesystem Permissions${NC}"
run_test "Can create ~/.pso_dev" "mkdir -p ~/.pso_dev && rm -rf ~/.pso_dev"
run_test "Can write to /tmp" "echo 'test' > /tmp/pso-test && rm /tmp/pso-test"
run_test "Current dir writable" "touch .pso-test && rm .pso-test"
echo ""

# 9. Network Connectivity
echo -e "${YELLOW}9. Network Connectivity${NC}"
run_test "Can reach Docker Hub" "curl -s https://hub.docker.com > /dev/null"
run_test "Can reach GitHub" "curl -s https://github.com > /dev/null"
run_test "DNS resolution" "nslookup google.com > /dev/null"
echo ""

# 10. macOS Specific
echo -e "${YELLOW}10. macOS Specific${NC}"
run_test "Xcode Command Line Tools" "xcode-select -p" || echo "   Install: xcode-select --install"
run_test "Security permissions OK" "security find-identity -v -p codesigning" || echo "   (May need to allow in System Preferences)"
echo ""

# Summary
echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}Test Summary${NC}"
echo -e "${BLUE}================================${NC}"
echo ""
echo "Tests Run:    $TESTS_RUN"
echo -e "Tests Passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Tests Failed: ${RED}$TESTS_FAILED${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed! macOS system is compatible with PSO.${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Run: ./pso install"
    echo "2. Run: ./pso start"
    echo "3. Open: http://localhost:5000"
    echo ""
    echo "macOS Notes:"
    echo "- Docker Desktop must be running before starting PSO"
    echo "- Some services may require Rosetta 2 on Apple Silicon"
    echo "- Use launchd for auto-start (see docs/SETUP_GUIDES.md)"
    exit 0
else
    echo -e "${RED}✗ Some tests failed. Please fix the issues above.${NC}"
    echo ""
    echo "Common fixes for macOS:"
    echo "- Docker Desktop: Install from https://www.docker.com/products/docker-desktop"
    echo "- Python 3.10+: brew install python@3.10"
    echo "- Dependencies: pip3 install -r requirements.txt"
    echo "- Xcode tools: xcode-select --install"
    exit 1
fi
