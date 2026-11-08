# HeckerOS fixes (Pixel 4 / flame)

Fixes for **HeckerOS 17.0** on the Pixel 4 (`flame`), worked out on a real device
and packaged as a flashable zip.

Base build: `HeckerOS_flame-17.0-20261026-2156.zip` (build `1793051590`).

## Layout

| Path | What it is |
|---|---|
| `apps/` | Readable copies of the stock files the fixes touch, decoded from the ROM's APKs (layouts, colours, dimensions, and the bytecode of the methods that are patched). |
| `product/` | Notes on the prebuilt apps in `/product`. |
| `tools/` | Scripts used to decode the stock files. |

`apps/` mirrors the resource layout of each app, so the history of a file shows
exactly what changed relative to the stock ROM.

## Regenerating `apps/`

```
python3 tools/extract_stock.py --settings Settings.apk --systemui SystemUI.apk \
    --framework framework-res.apk --launcher NexusLauncherRelease.apk --out apps
```

Requires Android SDK build-tools (`aapt2`, `dexdump`) on `PATH` or `ANDROID_HOME` set.
