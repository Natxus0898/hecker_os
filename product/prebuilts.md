# Prebuilt apps in `/product` that the fixes touch

| Path | Package | Version | Signing certificate (SHA-256) |
|---|---|---|---|
| `/product/priv-app/EuiccGoogle/EuiccGoogle.apk` | `com.google.android.euicc` | 306110 (D.2.1.989982212) | `7e26b6d5802a16799448ad635868f0345d6730310634684c0ae44e7e9f7ea764` (Google) |
| `/product/app/FloralMotionSenseBridge/FloralMotionSenseBridge.apk` | `com.google.android.apps.motionsense.bridge` | 3 (1.0.254391180.stub) | `4fa71b2d890e657bbe02ed7511eb7bf35dd78b27aa9ecd28666156f524fee6f3` (Google) |

The APKs themselves are Google's and are not stored in this repository. The
Motion Sense Bridge stub is the one from the stock Pixel 4 factory image
(`flame-tp1a.221005.002.b2`, `/product/app/MotionSenseBridgePrebuilt`).
