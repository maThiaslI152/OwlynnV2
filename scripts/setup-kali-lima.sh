#!/bin/bash
# setup-kali-lima.sh — Set up Kali Linux VM via Lima for Owlynn pentest mode
#
# Usage:
#   ./scripts/setup-kali-lima.sh          # Full setup
#   ./scripts/setup-kali-lima.sh --start   # Just start existing VM
#   ./scripts/setup-kali-lima.sh --stop    # Stop the VM
#   ./scripts/setup-kali-lima.sh --status  # Check VM status
#
# Requirements:
#   - macOS on Apple Silicon (M1/M2/M3/M4)
#   - Homebrew installed
#   - ~4GB free RAM, ~30GB free disk
#
# After setup, Owlynn's pentest mode will automatically connect to this VM
# via SSH for tool execution and tmux capture.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LIMA_CONFIG="$PROJECT_ROOT/lima/kali.yaml"
VM_NAME="owlynn-kali"
SSH_PORT=60022

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*"; exit 1; }

# ── Argument handling ─────────────────────────────────────────────────

case "${1:-}" in
  --start)
    limactl start "$VM_NAME" 2>/dev/null || error "VM not found. Run full setup first."
    info "Kali VM started."
    exit 0
    ;;
  --stop)
    limactl stop "$VM_NAME" 2>/dev/null || true
    info "Kali VM stopped."
    exit 0
    ;;
  --status)
    if limactl list 2>/dev/null | grep -q "$VM_NAME"; then
      limactl list "$VM_NAME"
    else
      warn "Kali VM not found. Run setup first."
    fi
    exit 0
    ;;
  --delete)
    limactl stop "$VM_NAME" 2>/dev/null || true
    limactl delete "$VM_NAME" 2>/dev/null || true
    info "Kali VM deleted."
    exit 0
    ;;
  --help|-h)
    head -15 "$0" | tail -12
    exit 0
    ;;
esac

# ── Pre-flight checks ────────────────────────────────────────────────

echo ""
echo "══════════════════════════════════════════════════"
echo "  Owlynn Kali VM Setup (Lima)"
echo "══════════════════════════════════════════════════"
echo ""

# Check macOS
if [[ "$(uname)" != "Darwin" ]]; then
  error "This script is for macOS only."
fi

# Check Apple Silicon
if [[ "$(uname -m)" != "arm64" ]]; then
  warn "Not Apple Silicon — performance may be reduced."
fi

# Check RAM
TOTAL_RAM_GB=$(( $(sysctl -n hw.memsize) / 1073741824 ))
if (( TOTAL_RAM_GB < 16 )); then
  error "Need at least 16GB RAM. Detected: ${TOTAL_RAM_GB}GB"
fi
info "RAM: ${TOTAL_RAM_GB}GB"

# Check disk
AVAIL_GB=$(df -g "$HOME" | tail -1 | awk '{print $4}')
if (( AVAIL_GB < 30 )); then
  error "Need at least 30GB free disk. Available: ${AVAIL_GB}GB"
fi
info "Disk: ${AVAIL_GB}GB available"

# ── Install Lima ──────────────────────────────────────────────────────

if ! command -v limactl &>/dev/null; then
  info "Installing Lima via Homebrew..."
  brew install lima
else
  LIMA_VER=$(limactl --version 2>/dev/null | head -1)
  info "Lima already installed: $LIMA_VER"
fi

# ── Start Kali VM ────────────────────────────────────────────────────

if limactl list 2>/dev/null | grep -q "$VM_NAME"; then
  STATUS=$(limactl list "$VM_NAME" --format '{{.Status}}' 2>/dev/null)
  if [[ "$STATUS" == "Running" ]]; then
    info "Kali VM already running."
  else
    info "Starting existing Kali VM..."
    limactl start "$VM_NAME"
  fi
else
  info "Creating Kali VM (first boot installs Kali tools — takes ~10-15 minutes)..."
  echo ""
  echo "  The VM will:"
  echo "  - Boot Debian 12 on Apple Virtualization"
  echo "  - Install kali-linux-headless + pentest tool suites"
  echo "  - Set up SSH key auth (user: kali)"
  echo "  - Create tmux session 'main' for Owlynn integration"
  echo ""
  echo "  Provisioning log: ~/.lima/$VM_NAME/ha.stderr.log"
  echo ""

  limactl start --name="$VM_NAME" "$LIMA_CONFIG"
fi

# ── Verify connectivity ───────────────────────────────────────────────

info "Testing SSH connection..."
SSH_CONFIG="$HOME/.lima/$VM_NAME/ssh.config"

if [[ ! -f "$SSH_CONFIG" ]]; then
  error "SSH config not found at $SSH_CONFIG"
fi

# Wait for SSH to be ready
for i in $(seq 1 30); do
  if ssh -F "$SSH_CONFIG" "$VM_NAME" "echo ok" &>/dev/null; then
    break
  fi
  sleep 2
done

if ssh -F "$SSH_CONFIG" "$VM_NAME" "echo ok" &>/dev/null; then
  info "SSH connection OK"
else
  error "Cannot connect to Kali VM via SSH"
fi

# Verify tmux session
if ssh -F "$SSH_CONFIG" "$VM_NAME" "tmux has-session -t main" &>/dev/null; then
  info "tmux session 'main' running"
else
  warn "tmux session 'main' not found — creating..."
  ssh -F "$SSH_CONFIG" "$VM_NAME" "tmux new-session -d -s main -n shell" 2>/dev/null || true
fi

# Verify Kali tools
TOOLS_FOUND=$(ssh -F "$SSH_CONFIG" "$VM_NAME" "which nmap sqlmap msfconsole 2>/dev/null | wc -l" 2>/dev/null || echo "0")
if (( TOOLS_FOUND >= 2 )); then
  info "Kali tools installed (nmap, sqlmap, metasploit)"
else
  warn "Some Kali tools may not be installed yet — provisioning may still be running"
fi

# ── Print config for Owlynn ──────────────────────────────────────────

echo ""
echo "══════════════════════════════════════════════════"
echo "  Kali VM Ready"
echo "══════════════════════════════════════════════════"
echo ""
echo "  VM Name:    $VM_NAME"
echo "  SSH:        localhost:$SSH_PORT"
echo "  User:       kali"
echo "  tmux:       main"
echo ""
echo "  Add to ~/.owlynn/defaults.yaml or .env.local:"
echo ""
echo "    KALI_SSH_HOST=127.0.0.1"
echo "    KALI_SSH_PORT=$SSH_PORT"
echo "    KALI_SSH_USER=kali"
echo ""
echo "  Or update defaults.yaml:"
echo ""
echo "    screen_assist:"
echo "      kali:"
echo "        host: '127.0.0.1'"
echo "        port: $SSH_PORT"
echo "        user: kali"
echo "        tmux_session: main"
echo ""
echo "  Quick test:"
echo "    ssh -F $SSH_CONFIG $VM_NAME 'nmap --version'"
echo ""
echo "  Manage:"
echo "    ./scripts/setup-kali-lima.sh --status"
echo "    ./scripts/setup-kali-lima.sh --stop"
echo "    ./scripts/setup-kali-lima.sh --start"
echo ""
