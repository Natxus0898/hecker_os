# HeckerOS fixes (Pixel 4 / flame)

Fixes for **HeckerOS 17.0** on the Pixel 4 (`flame`), worked out on a real device
and packaged as a flashable zip.

Base build: `HeckerOS_flame-17.0-20261026-2156.zip` (build `1793051590`).

## Fixes

| # | Problem | Fix |
|---|---|---|
| 1 | Setup wizard loops/crashes after "Accounts added" | Newer SIM Manager (EuiccGoogle) + privapp allow-list |
| 2 | Motion Sense Bridge update always fails in the Play Store | Google-signed stub instead of a platform-re-signed APK |
| 3 | Settings home page ignores Material You; cramped cards | Material You colours, submenu spacing |
| 4 | Gesture pill cannot be hidden; empty strip at the bottom | Transparent stashed handle, `taskbar_stashed_size` 0dp |
| 5 | Darker band under notifications in the shade | Transparent `shade_panel_*` colours |
| 6 | Quick Settings dark theme tile does nothing | Read the real night mode when tapped |
| 7 | Face enrollment preview off-centre, progress hard to see | 4:3 preview centred in the circle, visible progress cells |
| 8 | Preinstalled overlays start disabled | `/product/overlay/config/config.xml` |

Details (symptom, cause, change, testing) for each: [docs/FIXES.md](docs/FIXES.md).
The commit history follows the same order, one commit per fix, starting from the
stock files.

## Layout

| Path | What it is |
|---|---|
| `apps/` | Readable copies of the files each fix changes, decoded from the ROM's APKs: layouts, colours, dimensions, and the bytecode of the patched methods. The first commit is stock; later commits show each change as a diff. |
| `overlays/` | Runtime resource overlays used in the prebuilt zip. Each one is filled from `apps/` at build time (`sources.txt`). |
| `patches/` | Byte patches for Settings and SystemUI, with the stock bytes they expect. |
| `product/` | Files added to `/product`, and the list of prebuilt apps. |
| `prebuilts/` | Where the two Google APKs go for a build (not committed). |
| `tools/` | Decode, build, patch, sign and verify scripts. |
| `docs/` | [FIXES.md](docs/FIXES.md), [BUILDING.md](docs/BUILDING.md). |

## Quick start

```
tools/fetch_aosp_keys.sh
STOCK_ZIP=/path/to/HeckerOS_flame-17.0-20261026-2156.zip tools/make_release.sh out/HeckerOS_flame-17.0-fixed.zip
```

Requirements, the individual steps, flashing, and how to move each fix into the
ROM source tree are in [docs/BUILDING.md](docs/BUILDING.md).

## Regenerating the stock files in `apps/`

```
python3 tools/extract_stock.py --settings Settings.apk --systemui SystemUI.apk \
    --framework framework-res.apk --launcher NexusLauncherRelease.apk --out apps
```

Google's APKs and the signing keys are not stored here; the AOSP test keys are
downloaded by `tools/fetch_aosp_keys.sh`.
