#!/usr/bin/env bash
# Zipalign an APK and sign it with the platform key (APK Signature Scheme v2 + v3).
#   tools/sign_platform.sh unsigned.apk signed.apk
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
. "$ROOT/tools/sdk.sh"
KEYS="${KEYS:-$ROOT/keys}"
in="$1"; out="$2"
tmp="$out.aligned"
"$ZIPALIGN" -f -p 4 "$in" "$tmp"
"$APKSIGNER" sign --key "$KEYS/platform.pk8" --cert "$KEYS/platform.x509.pem" \
    --v1-signing-enabled false --v2-signing-enabled true --v3-signing-enabled true --out "$out" "$tmp"
rm -f "$tmp" "$out.idsig"
echo "signed $out"
