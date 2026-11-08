# Building

There are two ways to use this repository:

1. **Rebuild the fixed flashable zip** from the stock HeckerOS zip, without a ROM
   source tree (`tools/make_release.sh`).
2. **Apply the fixes in the ROM source**, using the readable diffs in `apps/` and the
   notes below.

## 1. Rebuilding the fixed zip

### Requirements

- Android SDK build-tools (`aapt2`, `zipalign`, `apksigner`, `dexdump`) and one
  `platforms/android-*/android.jar`. Set `ANDROID_HOME` if they are not on `PATH`.
- Python 3 with `cryptography` and `pyasn1-modules`
  (`pip install cryptography pyasn1-modules`).
- e2fsprogs (`debugfs`, `e2fsck`).
- The stock zip `HeckerOS_flame-17.0-20261026-2156.zip`.
- The two Google APKs in `prebuilts/`, see [`prebuilts/README.md`](../prebuilts/README.md).
- About 12 GB of free disk space.

### Build

```
tools/fetch_aosp_keys.sh      # public AOSP test keys, the same keys the stock zip uses
STOCK_ZIP=/path/to/HeckerOS_flame-17.0-20261026-2156.zip tools/make_release.sh out/HeckerOS_flame-17.0-fixed.zip
```

The script runs these steps; each tool can also be run on its own (`--help`):

| Step | Tool | What it does |
|---|---|---|
| 1 | `payload_extract.py` | Extracts `product`, `system_ext` and `vbmeta_system` from the stock zip, checking every hash. |
| 2 | `debugfs dump` | Copies the stock `Settings.apk` and `SystemUI.apk` out of `system_ext`. |
| 3 | `build_overlays.sh` | Builds the five overlays in `overlays/`, filling them from `apps/` (`sources.txt`), signed with the platform key. |
| 4 | `apply_dex_patches.py`, `sign_platform.sh` | Applies `patches/*.json` to Settings and SystemUI, checking the stock bytes first, then signs with the platform key. |
| 5-6 | `patch_images.py` | Writes the APKs, overlays, overlay config and permission file into copies of the images (owner, mode, SELinux label and timestamps set). |
| 7 | `avb_update.py` | Rebuilds the dm-verity hash trees of the changed images and re-signs `vbmeta_system`. |
| 8 | `build_ota.py`, `verify_ota.py` | Builds the new payload (unchanged operations copied, changed ones re-encoded), signs payload and zip, and checks the result. |

### Signing

The stock zip is signed with the public AOSP test keys, so the fixed zip is too:

| What | Key |
|---|---|
| Platform apps and overlays | `platform` |
| OTA zip (whole-file) and payload | `testkey` |
| `vbmeta_system` (AVB) | `external/avb/test/data/testkey_rsa2048.pem` |

Recovery therefore installs it without an "install anyway" prompt. The stock
`vbmeta` has verification disabled (flags 3) and is left as it is. The new
hash trees are written without FEC.

### Flashing

1. Boot the HeckerOS recovery.
2. *Apply update > Apply from ADB*, then `adb sideload <zip>`.
3. Over an existing HeckerOS 20261026 install the data is kept. Coming from
   another ROM, factory reset first.

## 2. Applying the fixes in the ROM source

| Fix | Where in the source tree | How |
|---|---|---|
| SIM Manager | GMS prebuilts for `EuiccGoogle` | Update the APK to D.2.1.989982212 or newer and add the five permissions from `product/etc/permissions/privapp-permissions-hecker-euicc.xml` to its privapp allow-list. |
| Motion Sense Bridge | the `FloralMotionSenseBridge` prebuilt module | Ship Google's signed stub and keep its signature (`certificate: "PRESIGNED"`) instead of re-signing a full APK with the platform key. |
| Settings colours and spacing | Settings app `res/` | Apply the diff of `apps/Settings/res` (layouts, drawables, `hecker_colors.xml`, new `hecker_card_surface`). |
| Gesture pill | Pixel Launcher is a prebuilt | Keep the `HeckerHidePill` overlay in `/product/overlay`. |
| Bottom space | `frameworks/base/core/res/res/values/dimens.xml` or a device overlay | `taskbar_stashed_size` 0dp. |
| Shade colour | `frameworks/base/core/res/res/values/colors.xml` or a device overlay | `shade_panel_bg`, `shade_panel_fg`, `shade_panel_scrim` transparent. |
| Dark theme tile | SystemUI, `HeckerReferenceQuickSettings.kt` | Read `UiModeManager.nightMode` in the click handler, see [FIXES.md](FIXES.md#6-quick-settings-dark-theme-tile-does-nothing). |
| Face enrollment | Settings, `FaceEnrollPreviewFragment`, `FacePoseGridView`, device overlay for `face_preview_*` | See [FIXES.md](FIXES.md#7-face-unlock-enrollment-off-centre-preview-and-faint-progress). |

When the fixes are in the source, the overlays and binary patches here are no
longer needed, apart from the Pixel Launcher overlay.
