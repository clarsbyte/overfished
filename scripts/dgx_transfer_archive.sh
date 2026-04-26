#!/usr/bin/env bash
# Transfer archive.zip to the ASUS DGX and unzip into ~/datasets/ships-aerial-images/
#
# Usage (from your Mac, repo root or anywhere):
#   ./scripts/dgx_transfer_archive.sh
#   ./scripts/dgx_transfer_archive.sh /path/to/archive.zip
#
# Override SSH target or remote layout:
#   DGX_HOST=asus@10.30.215.46 ./scripts/dgx_transfer_archive.sh
#   DGX_DATASETS_DIR=/workspace/datasets ./scripts/dgx_transfer_archive.sh
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ZIP="${1:-$REPO_ROOT/archive.zip}"
HOST="${DGX_HOST:-asus@gx10-eb94}"

if [[ ! -f "$ZIP" ]]; then
  echo "error: zip not found: $ZIP" >&2
  exit 1
fi

echo "==> Uploading $(basename "$ZIP") to ${HOST}:~/archive.zip"
scp "$ZIP" "${HOST}:~/archive.zip"

echo "==> Unpacking on remote into datasets/ (creates ships-aerial-images/)"
# shellcheck disable=SC2029
ssh "$HOST" "mkdir -p ~/datasets && cd ~/datasets && unzip -qo ~/archive.zip && ls -la ships-aerial-images/data.yaml && du -sh ships-aerial-images"

echo "==> Done. On the DGX, pool root for assign script is typically:"
echo "    ~/datasets/ships-aerial-images"
echo ""
echo "After assign + build_all on the DGX, sync back to your Mac, e.g.:"
echo "  rsync -avz ${HOST}:~/overfished/data/local_pipeline/vessel_images/ ${REPO_ROOT}/data/local_pipeline/vessel_images/"
echo "  rsync -avz ${HOST}:~/overfished/data/local_pipeline/vessel_cards.json ${REPO_ROOT}/data/local_pipeline/vessel_cards.json"
