#!/usr/bin/env bash
# Download the public AOSP test keys HeckerOS is signed with into keys/.
#   platform.*        platform certificate (system apps and overlays)
#   testkey.*         OTA package and payload signing key
#   testkey_rsa2048   AVB key for vbmeta_system
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEYS="${KEYS:-$ROOT/keys}"
mkdir -p "$KEYS"
get() { curl -sSfL "https://android.googlesource.com/$1?format=TEXT" | base64 -d > "$KEYS/$2"; echo "fetched $2"; }
SEC=platform/build/+/refs/heads/main/target/product/security
get "$SEC/platform.pk8"      platform.pk8
get "$SEC/platform.x509.pem" platform.x509.pem
get "$SEC/testkey.pk8"       testkey.pk8
get "$SEC/testkey.x509.pem"  testkey.x509.pem
get platform/external/avb/+/refs/heads/main/test/data/testkey_rsa2048.pem testkey_rsa2048.pem
