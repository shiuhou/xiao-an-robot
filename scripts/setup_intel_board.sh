#!/usr/bin/env bash
# setup_intel_board.sh — One-click setup for xiao-an emotion runtime on Intel DK2500 / Ubuntu 24
# Usage:  bash scripts/setup_intel_board.sh
#
# What it does:
#   1. Install system packages (Python 3.10, OpenCV deps, git-lfs, etc.)
#   2. Clone the repo (or use existing checkout)
#   3. Create a Python venv
#   4. Install Python dependencies (base_station + VLM + OpenFace runtime)
#   5. Pull git-lfs files (OpenFace OV IR models)
#   6. Download HuggingFace models (Qwen2.5-VL + base detection models)
#   7. Verify everything
#   8. Print a ready-to-run command
#
# Assumes: Ubuntu 24.04, internet access, sudo available.
# Re-runnable: skips steps that are already done.

set -euo pipefail

# ─── Config ───────────────────────────────────────────────────────────────────

REPO_URL="https://github.com/shiuhou/xiao-an-robot.git"
BRANCH="integration/perception-memory"
INSTALL_DIR="${XIAO_AN_DIR:-$HOME/xiao-an-robot}"
VENV_DIR="$INSTALL_DIR/.venv"
PYTHON="${PYTHON:-python3}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[setup]${NC} $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC} $*"; }
fail()  { echo -e "${RED}[error]${NC} $*"; exit 1; }

# ─── Step 1: System packages ─────────────────────────────────────────────────

info "Step 1/7: Installing system packages..."

sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3 python3-pip python3-venv python3-dev \
    git git-lfs \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    sqlite3 \
    portaudio19-dev \
    > /dev/null

git lfs install --skip-repo > /dev/null 2>&1 || true

info "System packages OK."

# ─── Step 2: Clone or update repo ────────────────────────────────────────────

info "Step 2/7: Setting up repository at $INSTALL_DIR ..."

if [ -d "$INSTALL_DIR/.git" ]; then
    info "Repo already exists, fetching latest..."
    cd "$INSTALL_DIR"
    git fetch origin
    git checkout "$BRANCH"
    git pull origin "$BRANCH" --ff-only || warn "Pull failed (local changes?). Continuing with current state."
else
    info "Cloning $REPO_URL ..."
    git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

info "Repository OK. Branch: $(git branch --show-current)"

# ─── Step 3: Python venv ─────────────────────────────────────────────────────

info "Step 3/7: Setting up Python venv..."

if [ ! -f "$VENV_DIR/bin/activate" ]; then
    $PYTHON -m venv "$VENV_DIR"
    info "Created venv at $VENV_DIR"
else
    info "Venv already exists."
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install --upgrade pip -q

info "Python: $(python --version), pip: $(pip --version | cut -d' ' -f2)"

# ─── Step 4: Python dependencies ─────────────────────────────────────────────

info "Step 4/7: Installing Python dependencies..."

pip install -r base_station/requirements.txt -q
pip install -r base_station/requirements-vlm.txt -q
pip install -r agent/requirements.txt -q

# OpenFace STAR runtime needs torch (CPU only on Intel board)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu -q

info "Python dependencies OK."

# ─── Step 5: Git LFS (OpenFace OV IR models) ─────────────────────────────────

info "Step 5/7: Pulling git-lfs files (OpenFace OV models)..."

git lfs pull

OPENFACE_OV_DIR="base_station/models/openface_ov"
EXPECTED_LFS_FILES=(
    "$OPENFACE_OV_DIR/retinaface/retinaface.bin"
    "$OPENFACE_OV_DIR/retinaface/retinaface.xml"
    "$OPENFACE_OV_DIR/star/star.bin"
    "$OPENFACE_OV_DIR/star/star.xml"
    "$OPENFACE_OV_DIR/mtl/mtl.bin"
    "$OPENFACE_OV_DIR/mtl/mtl.xml"
)

lfs_ok=true
for f in "${EXPECTED_LFS_FILES[@]}"; do
    if [ ! -f "$f" ] || [ "$(wc -c < "$f")" -lt 1000 ]; then
        warn "LFS file missing or is pointer: $f"
        lfs_ok=false
    fi
done
if $lfs_ok; then
    info "OpenFace OV models OK (6 IR files)."
else
    fail "Some OpenFace OV models are missing. Check git-lfs setup."
fi

# ─── Step 6: HuggingFace models ──────────────────────────────────────────────

info "Step 6/7: Downloading HuggingFace models (Qwen2.5-VL + base models)..."

python tools/setup_models.py

info "HuggingFace models OK."

# ─── Step 7: Verify ──────────────────────────────────────────────────────────

info "Step 7/7: Running verification..."

ERRORS=0

# Can import the runtime?
python -c "from base_station.monitor.emotion_runtime import create_runtime; print('[ok] emotion_runtime imports')" \
    || { warn "emotion_runtime import failed"; ERRORS=$((ERRORS+1)); }

# Can import OpenFace adapter?
python -c "from base_station.perception.openface_ov_adapter import build_ov_perceive_callable; print('[ok] openface_ov_adapter imports')" \
    || { warn "openface_ov_adapter import failed"; ERRORS=$((ERRORS+1)); }

# Can import VLM?
python -c "from base_station.perception.vlm_face_analyzer import VLMFaceAnalyzer; print('[ok] vlm_face_analyzer imports')" \
    || { warn "vlm_face_analyzer import failed"; ERRORS=$((ERRORS+1)); }

# Quick unit tests (gate delivery)
python -m pytest tests/unit/test_emotion_runtime_gate_delivery.py -q --tb=short 2>&1 \
    || { warn "gate delivery tests failed"; ERRORS=$((ERRORS+1)); }

if [ "$ERRORS" -gt 0 ]; then
    warn "$ERRORS verification step(s) failed. Review the output above."
else
    info "All verification passed."
fi

# ─── Done ─────────────────────────────────────────────────────────────────────

echo ""
echo "=========================================="
echo " Setup complete!"
echo "=========================================="
echo ""
echo "To activate the environment:"
echo "  source $VENV_DIR/bin/activate"
echo ""
echo "To verify the chain with fake data (no camera needed):"
echo "  python -m base_station.monitor.emotion_runtime \\"
echo "    --source fake_camera \\"
echo "    --model-backend mock \\"
echo "    --enable-vlm-gate \\"
echo "    --vlm-backend fake \\"
echo "    --force-vlm \\"
echo "    --no-agent --verbose --count 5"
echo ""
echo "To start all services:"
echo "  bash scripts/start_all.sh"
echo ""
echo "TODO: Real camera/ESP32 frame source is not finalized yet."
echo ""
