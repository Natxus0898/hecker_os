#!/usr/bin/env bash
# Build the fixed HeckerOS OTA zip from the stock one, end to end.
#
#   STOCK_ZIP=/path/to/HeckerOS_flame-17.0-20261026-2156.zip tools/make_release.sh [out.zip]
#
# Needs: Android SDK build-tools (aapt2, zipalign, apksigner), Python 3 with
# `cryptography` and `pyasn1-modules`, e2fsprogs (debugfs, e2fsck), the two Google
# APKs in prebuilts/ (see prebuilts/README.md) and about 12 GB of free space.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
. tools/sdk.sh
: "${STOCK_ZIP:?set STOCK_ZIP to the stock HeckerOS zip}"
OUT_ZIP="${1:-out/HeckerOS_flame-17.0-fixed.zip}"
PY="${PYTHON:-python3}"
DEBUGFS="${DEBUGFS:-debugfs}"
W=work

for f in EuiccGoogle.apk FloralMotionSenseBridge.apk; do
  [ -f "prebuilts/$f" ] || { echo "error: prebuilts/$f missing (see prebuilts/README.md)" >&2; exit 1; }
done
[ -f keys/platform.pk8 ] && [ -f keys/testkey.pk8 ] && [ -f keys/testkey_rsa2048.pem ] || tools/fetch_aosp_keys.sh

echo "== 1/8 extract stock partitions"
"$PY" tools/payload_extract.py "$STOCK_ZIP" "$W/stock" product system_ext vbmeta_system

echo "== 2/8 copy stock Settings and SystemUI out of system_ext"
mkdir -p "$W/stock-apps"
"$DEBUGFS" -R "dump /priv-app/Settings/Settings.apk $W/stock-apps/Settings.apk" "$W/stock/system_ext.img"
"$DEBUGFS" -R "dump /priv-app/SystemUI/SystemUI.apk $W/stock-apps/SystemUI.apk" "$W/stock/system_ext.img"

echo "== 3/8 build overlays"
tools/build_overlays.sh

echo "== 4/8 patch Settings and SystemUI"
mkdir -p out/apps
"$PY" tools/apply_dex_patches.py patches/settings-face-enroll.json "$W/stock-apps/Settings.apk" out/apps/Settings-unsigned.apk
tools/sign_platform.sh out/apps/Settings-unsigned.apk out/apps/Settings.apk
"$PY" tools/apply_dex_patches.py patches/systemui-dark-tile.json "$W/stock-apps/SystemUI.apk" out/apps/SystemUI-unsigned.apk
tools/sign_platform.sh out/apps/SystemUI-unsigned.apk out/apps/SystemUI.apk

echo "== 5/8 copy stock images"
mkdir -p "$W/images"
cp "$W/stock/product.img" "$W/stock/system_ext.img" "$W/images/"

echo "== 6/8 write files into the images"
"$PY" tools/patch_images.py --product "$W/images/product.img" --system-ext "$W/images/system_ext.img" --debugfs "$DEBUGFS"

echo "== 7/8 hash trees and vbmeta_system"
"$PY" tools/avb_update.py --vbmeta-system "$W/stock/vbmeta_system.img" --key keys/testkey_rsa2048.pem \
    --out "$W/images/vbmeta_system.img" "$W/images/product.img" "$W/images/system_ext.img"

echo "== 8/8 build and verify the OTA zip"
"$PY" tools/build_ota.py --stock-zip "$STOCK_ZIP" --stock-images "$W/stock" --images "$W/images" \
    --key keys/testkey.pk8 --out "$OUT_ZIP"
"$PY" tools/verify_ota.py "$OUT_ZIP" --cert keys/testkey.x509.pem
