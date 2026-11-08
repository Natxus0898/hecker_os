#!/usr/bin/env bash
# Build the overlays in overlays/ into signed APKs.
#
#   tools/build_overlays.sh [OverlayName ...]     (default: all overlays)
#
# Each overlay directory holds an AndroidManifest.xml, overlay-only resources, and an
# optional sources.txt listing files copied in from apps/. Overlays are signed with the
# platform key (KEYS=keys/ by default, see tools/fetch_aosp_keys.sh). Output: out/overlays/
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
. "$ROOT/tools/sdk.sh"
KEYS="${KEYS:-$ROOT/keys}"
OUT="${OUT:-$ROOT/out/overlays}"
[ -f "$KEYS/platform.pk8" ] || { echo "error: $KEYS/platform.pk8 missing (run tools/fetch_aosp_keys.sh)" >&2; exit 1; }

names=("$@")
[ ${#names[@]} -eq 0 ] && names=($(ls "$ROOT/overlays"))
mkdir -p "$OUT"
for name in "${names[@]}"; do
  src="$ROOT/overlays/$name"
  work="$OUT/$name.build"
  rm -rf "$work"; mkdir -p "$work"
  cp -r "$src/res" "$work/res"
  if [ -f "$src/sources.txt" ]; then
    grep -v '^\s*\(#\|$\)' "$src/sources.txt" | while read -r from to; do
      mkdir -p "$(dirname "$work/$to")"; cp "$ROOT/$from" "$work/$to"
    done
  fi
  "$AAPT2" compile --dir "$work/res" -o "$work/compiled.zip"
  "$AAPT2" link -o "$work/unaligned.apk" -I "$ANDROID_JAR" --manifest "$src/AndroidManifest.xml" \
      --min-sdk-version 34 --target-sdk-version 36 --no-auto-version --no-resource-deduping "$work/compiled.zip"
  "$ZIPALIGN" -f -p 4 "$work/unaligned.apk" "$work/aligned.apk"
  "$APKSIGNER" sign --key "$KEYS/platform.pk8" --cert "$KEYS/platform.x509.pem" \
      --v1-signing-enabled false --v2-signing-enabled true --out "$OUT/$name.apk" "$work/aligned.apk"
  rm -f "$OUT/$name.apk.idsig"
  echo "built $OUT/$name.apk"
done
