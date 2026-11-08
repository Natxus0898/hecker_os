# Prebuilts (not committed)

Google APKs needed by `tools/make_release.sh`. Put them here with these names:

| File | Package / version | Where to get it |
|---|---|---|
| `EuiccGoogle.apk` | `com.google.android.euicc` 306110 (D.2.1.989982212) or newer | `adb pull` from a phone after updating SIM Manager from the Play Store (`adb shell pm path com.google.android.euicc`) |
| `FloralMotionSenseBridge.apk` | `com.google.android.apps.motionsense.bridge` 3 (stub) | stock Pixel 4 factory image `flame-tp1a.221005.002.b2`, `product.img`: `/app/MotionSenseBridgePrebuilt/MotionSenseBridgePrebuilt.apk` |

A newer EuiccGoogle may request more privileged permissions; compare with
`product/etc/permissions/privapp-permissions-hecker-euicc.xml` before using it,
because the ROM enforces the privapp allow-list at boot.
