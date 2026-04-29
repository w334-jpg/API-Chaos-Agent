#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DIST_DIR="${PROJECT_DIR}/dist"
PACKAGE_NAME="api-chaos-agent"
OFFLINE_DIR="${DIST_DIR}/${PACKAGE_NAME}-offline"

echo "=== Building offline installation package ==="

rm -rf "${DIST_DIR}"
mkdir -p "${OFFLINE_DIR}"

echo "[1/4] Building wheel..."
cd "${PROJECT_DIR}"
pip wheel --no-deps -w "${OFFLINE_DIR}/packages" .

echo "[2/4] Downloading dependencies..."
pip download -d "${OFFLINE_DIR}/packages" -e ".[dev]" 2>/dev/null || \
    pip download -d "${OFFLINE_DIR}/packages" -r <(pip show api-chaos-agent 2>/dev/null | grep Requires | sed 's/Requires: //' | tr ',' '\n' | while read -r pkg; do echo "$pkg"; done) 2>/dev/null || \
    echo "Warning: Some dependencies may need network during install"

echo "[3/4] Copying project files..."
cp -r "${PROJECT_DIR}/src" "${OFFLINE_DIR}/"
cp "${PROJECT_DIR}/pyproject.toml" "${OFFLINE_DIR}/"
cp "${PROJECT_DIR}/.env.example" "${OFFLINE_DIR}/"
cp "${PROJECT_DIR}/Dockerfile" "${OFFLINE_DIR}/" 2>/dev/null || true
cp "${PROJECT_DIR}/docker-compose.yml" "${OFFLINE_DIR}/" 2>/dev/null || true
cp -r "${PROJECT_DIR}/tests" "${OFFLINE_DIR}/" 2>/dev/null || true

cat > "${OFFLINE_DIR}/install.sh" << 'INSTALL_EOF'
#!/usr/bin/env bash
set -euo pipefail
echo "=== Offline Installation ==="
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
pip install --no-index --find-links="${SCRIPT_DIR}/packages" ${SCRIPT_DIR}/packages/*.whl 2>/dev/null || \
    pip install --no-index --find-links="${SCRIPT_DIR}/packages" -e .
echo "Installation complete. Run: uvicorn api_chaos_agent.main:app --reload"
INSTALL_EOF
chmod +x "${OFFLINE_DIR}/install.sh"

echo "[4/4] Creating archive..."
cd "${DIST_DIR}"
tar -czf "${PACKAGE_NAME}-offline.tar.gz" "${PACKAGE_NAME}-offline"

SIZE=$(du -sh "${PACKAGE_NAME}-offline.tar.gz" | cut -f1)
echo ""
echo "=== Build complete ==="
echo "Archive: ${DIST_DIR}/${PACKAGE_NAME}-offline.tar.gz (${SIZE})"
echo ""
echo "To install offline:"
echo "  tar -xzf ${PACKAGE_NAME}-offline.tar.gz"
echo "  cd ${PACKAGE_NAME}-offline"
echo "  ./install.sh"
