# Platform Testing Guide

Test PSO compatibility on different operating systems before installation.

---

## Quick Test

### Ubuntu/Debian
```bash
chmod +x tests/test_ubuntu.sh
./tests/test_ubuntu.sh
```

### macOS
```bash
chmod +x tests/test_macos.sh
./tests/test_macos.sh
```

### Arch/Manjaro
```bash
# Use Ubuntu script (mostly compatible)
chmod +x tests/test_ubuntu.sh
./tests/test_ubuntu.sh
```

---

## What These Tests Check

### System Requirements
- ✓ Operating system version
- ✓ CPU architecture (x86_64, ARM64)
- ✓ Kernel version

### Prerequisites
- ✓ Python 3.10+ installed
- ✓ pip package manager
- ✓ Docker installed and running
- ✓ Docker accessible without sudo (Linux)
- ✓ Git installed

### Python Dependencies
- ✓ Flask (web framework)
- ✓ Docker SDK (container management)
- ✓ PyJWT (authentication)
- ✓ Cryptography (secrets encryption)

### Docker Functionality
- ✓ Can pull images
- ✓ Can run containers
- ✓ Can create networks
- ✓ Can create volumes

### System Configuration
- ✓ Required ports available (5000, 8080, 8096)
- ✓ Filesystem permissions correct
- ✓ Can write to user directories

### Network
- ✓ Internet connectivity
- ✓ Can reach Docker Hub
- ✓ Can reach GitHub
- ✓ DNS resolution working

---

## Test Output Example

```
================================
PSO Ubuntu Compatibility Test
================================

1. System Information
   OS: Ubuntu 22.04.4 LTS
   Kernel: 5.15.0-91-generic
   Architecture: x86_64

2. Prerequisites
Testing Python 3.10+... ✓ PASS
Testing pip installed... ✓ PASS
Testing Docker installed... ✓ PASS
Testing Docker running... ✓ PASS
Testing Docker without sudo... ✓ PASS
Testing Git installed... ✓ PASS

...

================================
Test Summary
================================

Tests Run:    28
Tests Passed: 28
Tests Failed: 0

✓ All tests passed! Ubuntu system is compatible with PSO.
```

---

## Common Issues & Fixes

### Ubuntu/Debian

**Issue**: Docker permission denied
```bash
# Fix: Add user to docker group
sudo usermod -aG docker $USER
# Then log out and back in
```

**Issue**: Python 3.10+ not found
```bash
# Ubuntu 20.04 - add PPA
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.10 python3.10-venv python3-pip
```

**Issue**: Docker not running
```bash
sudo systemctl start docker
sudo systemctl enable docker
```

### macOS

**Issue**: Docker Desktop not installed
```
Download from: https://www.docker.com/products/docker-desktop
```

**Issue**: Xcode Command Line Tools missing
```bash
xcode-select --install
```

**Issue**: Python version too old
```bash
brew install python@3.10
```

**Issue**: Docker Desktop not running
```
Launch Docker Desktop from Applications
Wait for "Docker is running" in menu bar
```

### Arch/Manjaro

**Issue**: Docker permission denied
```bash
sudo usermod -aG docker $USER
# Then log out and back in
```

**Issue**: Python dependencies missing
```bash
pip install -r requirements.txt
```

---

## Requesting Test Results

If you test PSO on a new platform, please report your results!

### How to Report

1. Run the test script for your platform
2. Save the output to a file:
   ```bash
   ./tests/test_ubuntu.sh > test_results.txt 2>&1
   # or
   ./tests/test_macos.sh > test_results.txt 2>&1
   ```

3. Create a GitHub issue with:
   - Title: `[Platform Test] Ubuntu 22.04 / macOS 14.2 / etc.`
   - Include system info (OS, version, architecture)
   - Attach test_results.txt
   - Note any issues encountered

### Test Report Template

```markdown
**Platform**: Ubuntu 22.04.4 LTS
**Architecture**: x86_64
**Docker Version**: 24.0.7
**Python Version**: 3.10.12

**Test Results**: 28/28 passed ✓

**Notes**:
- All tests passed on first run
- No issues encountered
- Installation completed successfully

**Installation Time**: ~5 minutes
**First Service (Jellyfin)**: Installed and running successfully
```

---

## Platform Support Status

### Tested & Working
- Arch Linux / Manjaro

### Should Work (Needs Testing)
- Ubuntu 20.04 LTS
- Ubuntu 22.04 LTS
- Ubuntu 24.04 LTS
- Debian 11 (Bullseye)
- Debian 12 (Bookworm)
- Fedora 38+
- macOS 12+ (Monterey or later)

### ❓ Untested
- Pop!_OS
- Linux Mint
- openSUSE
- CentOS Stream 9
- Raspberry Pi OS 64-bit

### Not Supported
- Windows (use WSL2)
- 32-bit systems
- ARM32 (Raspberry Pi OS 32-bit)

---

## Creating Tests for Other Distros

Want to add a test for your distro? Copy `test_ubuntu.sh` and modify:

```bash
# Create new test
cp tests/test_ubuntu.sh tests/test_fedora.sh

# Modify:
# 1. Update system info detection
# 2. Adjust package manager commands
# 3. Update common fixes section
# 4. Test on your system
# 5. Submit a PR!
```

---

## Continuous Testing

For maintainers - run tests in VMs:

```bash
# Create Ubuntu VM
multipass launch 22.04 --name pso-test-ubuntu

# Run test in VM
multipass exec pso-test-ubuntu -- bash -c "
  git clone https://github.com/ApostolosTsampodimos/personal-server-os
  cd personal-server-os
  ./tests/test_ubuntu.sh
"

# Cleanup
multipass delete pso-test-ubuntu
multipass purge
```

---

**Help us expand platform support!**
Test PSO on your system and report results.
