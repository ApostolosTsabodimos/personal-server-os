#!/bin/bash
# PSO Test Script for Ubuntu
# Tests installation and basic functionality on Ubuntu systems

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
echo -e "${BLUE}PSO Ubuntu Compatibility Test${NC}"
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
echo "   OS: $(lsb_release -d | cut -f2)"
echo "   Kernel: $(uname -r)"
echo "   Architecture: $(uname -m)"
echo ""

# 2. Prerequisites Check
echo -e "${YELLOW}2. Prerequisites${NC}"
run_test "Python 3.10+" "python3 --version | grep -E 'Python 3\.(1[0-9]|[2-9][0-9])'"
run_test "pip installed" "python3 -m pip --version"
run_test "Docker installed" "docker --version"
run_test "Docker running" "docker ps"
run_test "Docker without sudo" "docker ps"
run_test "Git installed" "git --version"
echo ""

# 3. Python Dependencies
echo -e "${YELLOW}3. Python Dependencies${NC}"
run_test "Flask available" "python3 -c 'import flask'"
run_test "Docker SDK available" "python3 -c 'import docker'"
run_test "JWT available" "python3 -c 'import jwt'"
run_test "Cryptography available" "python3 -c 'import cryptography'"
echo ""

# 4. PSO Installation Test
echo -e "${YELLOW}4. PSO Installation${NC}"
if [ -f "./pso" ]; then
    run_test "PSO executable exists" "[ -x ./pso ]"
    run_test "PSO help command" "./pso --help | grep -q 'PSO'"
    run_test "Python modules loadable" "python3 -c 'import core.database, core.auth'"
else
    echo -e "${RED}   ✗ PSO not found - skipping installation tests${NC}"
fi
echo ""

# 5. Docker Functionality
echo -e "${YELLOW}5. Docker Functionality${NC}"
run_test "Pull test image" "docker pull hello-world:latest"
run_test "Run test container" "docker run --rm hello-world"
run_test "Docker network create" "docker network create pso-test-net && docker network rm pso-test-net"
run_test "Docker volume create" "docker volume create pso-test-vol && docker volume rm pso-test-vol"
echo ""

# 6. Port Availability
echo -e "${YELLOW}6. Port Availability${NC}"
run_test "Port 5000 available" "! sudo lsof -i :5000"
run_test "Port 8080 available" "! sudo lsof -i :8080"
run_test "Port 8096 available" "! sudo lsof -i :8096"
echo ""

# 7. Filesystem Permissions
echo -e "${YELLOW}7. Filesystem Permissions${NC}"
run_test "Can create ~/.pso_dev" "mkdir -p ~/.pso_dev && rm -rf ~/.pso_dev"
run_test "Can write to /tmp" "echo 'test' > /tmp/pso-test && rm /tmp/pso-test"
run_test "Current dir writable" "touch .pso-test && rm .pso-test"
echo ""

# 8. Network Connectivity
echo -e "${YELLOW}8. Network Connectivity${NC}"
run_test "Can reach Docker Hub" "curl -s https://hub.docker.com > /dev/null"
run_test "Can reach GitHub" "curl -s https://github.com > /dev/null"
run_test "DNS resolution" "nslookup google.com > /dev/null"
echo ""

# 9. Optional Tools
echo -e "${YELLOW}9. Optional Tools (Nice to Have)${NC}"
run_test "systemd available" "command -v systemctl" || echo "   (OK - systemd not required)"
run_test "curl available" "command -v curl" || echo "   (OK - wget can be used)"
run_test "jq available" "command -v jq" || echo "   (OK - not required)"
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
    echo -e "${GREEN}✓ All tests passed! Ubuntu system is compatible with PSO.${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Run: ./pso install"
    echo "2. Run: ./pso start"
    echo "3. Open: http://localhost:5000"
    exit 0
else
    echo -e "${RED}✗ Some tests failed. Please fix the issues above.${NC}"
    echo ""
    echo "Common fixes:"
    echo "- Docker permission: sudo usermod -aG docker \$USER (then log out and back in)"
    echo "- Python 3.10+: sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt install python3.10"
    echo "- Dependencies: pip install -r requirements.txt"
    exit 1
fi
