# Fixes

Each section lists the symptom, the cause found on the device, and what was changed.

## 1. Setup wizard crashes after "Accounts added"

**Symptom.** During setup, pressing *Next* on "Accounts added" immediately goes
back to the same screen, with a crash in the background.

**Cause.** The ROM ships SIM Manager (`com.google.android.euicc`) version
D.2.1.452606436 from 2022. Its eSIM activation screen uses an old setup-design
library that passes partner colour names such as `@sud_system_primary_dark`
straight to `Color.parseColor()`, which throws
`IllegalArgumentException: Unknown color`. The wizard treats the crashed step
as *Back*, so it loops.

**Change.**
- `/product/priv-app/EuiccGoogle/EuiccGoogle.apk` updated to D.2.1.989982212
  (same Google signature, so it is a normal upgrade path).
- The new version requests five more privileged permissions. They are added in
  [`product/etc/permissions/privapp-permissions-hecker-euicc.xml`](../product/etc/permissions/privapp-permissions-hecker-euicc.xml).
  The ROM enforces the allow-list (`ro.control_privapp_permissions=enforce`),
  so without this file the system server stops at boot.
- Native libraries in the new APK are stored uncompressed
  (`extractNativeLibs=false`), so it runs from `/product` as is.
