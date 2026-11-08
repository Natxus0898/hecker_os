# Locate Android SDK tools. Sourced by the other scripts; every tool can be overridden by env.
_sdk="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}"
if [ -z "$_sdk" ] && [ -n "${LOCALAPPDATA:-}" ]; then _sdk="$(cygpath -u "$LOCALAPPDATA" 2>/dev/null || echo "$LOCALAPPDATA")/Android/Sdk"; fi
[ -z "$_sdk" ] && _sdk="$HOME/Android/Sdk"
_bt="$(ls -d "$_sdk"/build-tools/* 2>/dev/null | sort -V | tail -1)"
_find() { for n in "$@"; do if command -v "$n" >/dev/null 2>&1; then command -v "$n"; return; fi; for s in "" .exe .bat; do [ -f "$_bt/$n$s" ] && { echo "$_bt/$n$s"; return; }; done; done; }
AAPT2="${AAPT2:-$(_find aapt2)}"
ZIPALIGN="${ZIPALIGN:-$(_find zipalign)}"
APKSIGNER="${APKSIGNER:-$(_find apksigner)}"
DEXDUMP="${DEXDUMP:-$(_find dexdump)}"
ANDROID_JAR="${ANDROID_JAR:-$(ls -d "$_sdk"/platforms/android-*/android.jar 2>/dev/null | sort -V | tail -1)}"
for _t in AAPT2 ZIPALIGN APKSIGNER ANDROID_JAR; do
  [ -n "${!_t}" ] || { echo "error: $_t not found; set ANDROID_HOME or $_t" >&2; exit 1; }
done
