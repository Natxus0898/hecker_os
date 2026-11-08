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

## 2. Motion Sense Bridge update always fails in the Play Store

**Symptom.** Play offers an update for Motion Sense Bridge, and it fails every time.

**Cause.** The ROM ships a full Motion Sense Bridge (v10010) re-signed with the
platform key. Play's update is signed by Google, so the install is rejected with
`INSTALL_FAILED_UPDATE_INCOMPATIBLE` (Play error 6004).

**Change.** Ship Google's original signed stub (v3), the same file stock Pixel 4
firmware uses. Play then updates it normally (tested up to v10016).

## 3. Settings home page colours and spacing

**Symptom.** The Settings home page used its own fixed blue palette, so it did
not follow the wallpaper colours like the rest of the system. The cards ran
edge to edge, and inside the cards and rows the content sat too close to the
borders: icons started 33 px from the screen edge, against 88 px in every
submenu.

**Change** ([`apps/Settings/res`](../apps/Settings/res)):
- `hecker_*` colours now point at the Material You system tokens
  (`system_surface_container_*`, `system_on_surface_*`, `system_primary_*`, ...)
  for light and dark.
- `hecker_card` and `hecker_border` are transparent, which hides the old
  decoration drawn behind the rows. A new `hecker_card_surface` colour is used
  for the card backgrounds.
- Home rows use 32dp side padding and a 12dp gap between icon and text, the
  same spacing as the submenus (icons at 88 px, titles at 231 px).
- The brand and maintainer cards get 16dp outer and 16dp inner padding, so their
  content lines up with the rows; the button keeps its own background colour.

Shipped as the overlay [`overlays/HeckerSettingsTheme`](../overlays/HeckerSettingsTheme),
built from the files above by `tools/build_overlays.sh`.

## 4. Hide the gesture pill and remove the space it leaves

**Symptom.** With gesture navigation, the pill at the bottom could not be hidden.
Once hidden, a 24dp (66 px) empty strip stayed at the bottom of every app.

**Cause.** On this ROM there is no separate navigation bar window in gesture
mode: Pixel Launcher's taskbar draws the pill (the "stashed handle") and
reports the bottom inset. The inset comes from the framework dimension
`taskbar_stashed_size`, not `navigation_bar_height` (setting that to 0 changes
nothing in gesture mode).

**Change.**
- Pixel Launcher: `taskbar_stashed_handle_light_color` and `..._dark_color`
  set to transparent ([`apps/NexusLauncher`](../apps/NexusLauncher/res/values/colors.xml)).
  Pixel Launcher is a Google prebuilt, so this can only be done with an overlay:
  [`overlays/HeckerHidePill`](../overlays/HeckerHidePill). It is signed with a
  different key from the launcher, so it has to be preinstalled in `/product`.
- Framework: `taskbar_stashed_size` set to 0dp
  ([`apps/framework-res`](../apps/framework-res/res/values/dimens.xml)), shipped as
  [`overlays/HeckerGestureSpace`](../overlays/HeckerGestureSpace).

The gesture area (`navigation_bar_gesture_height`) is unchanged, so swipe up for
Home, edge swipe for Back and swipe-and-hold for Recents keep working.
`navigation_bar_height` is unchanged too, so 3-button navigation still shows its
buttons with its normal 48dp bar (tested).

## 5. Notification shade: dark band under the notifications

**Symptom.** Pulling down the shade, the top (quick settings) was see-through
but the notification area below had a darker hue, so the panel looked like two
different surfaces.

**Cause.** SystemUI's shade colours (`ShadeColors.shadePanel()`) come from the
framework colours `shade_panel_bg`, `shade_panel_fg` and `shade_panel_scrim`.
Their stock colour state lists ([`apps/framework-res/res/color`](../apps/framework-res/res/color))
add tinted layers on top of the blur. SystemUI's own `notification_scrim_*`
colours are not used for this.

**Change.** The three framework colours are transparent
([`apps/framework-res/res/values/colors.xml`](../apps/framework-res/res/values/colors.xml)),
shipped as [`overlays/HeckerShadePanel`](../overlays/HeckerShadePanel). The panel
is now one even colour from top to bottom; the background blur is unchanged.

## 6. Quick Settings dark theme tile does nothing

**Symptom.** In the expanded quick settings panel, the dark theme tile often
does nothing when tapped, or only works in one direction.

**Cause.** The tile's click lambda
(`HeckerReferenceQuickSettingsKt$$ExternalSyntheticLambda34`) captures an
`isDark` flag when the panel is composed and calls
`UiModeManager.setNightModeActivated(!isDark)`. That flag comes from the
composition's configuration, which is not refreshed when the theme changes, so
after the first toggle every tap asks for the state the phone is already in.

**Change.** Decide at tap time from the real night mode:

```kotlin
// before (reconstructed from bytecode)
uiModeManager.setNightModeActivated(!isDark)

// after
val activate = uiModeManager.nightMode != UiModeManager.MODE_NIGHT_YES
uiModeManager.setNightModeActivated(activate)
```

In the prebuilt this is a same-size bytecode patch
([`patches/systemui-dark-tile.json`](../patches/systemui-dark-tile.json); bytecode
before and after in
[`apps/SystemUI/bytecode`](../apps/SystemUI/bytecode/HeckerReferenceQuickSettingsKt.Lambda34.invoke.txt)).
There was no room to keep the "open Display settings if
`setNightModeActivated` returns false" fallback, so it is dropped; in source it
can stay. Tested by toggling four times in a row in both directions.

## 7. Face unlock enrollment: off-centre preview and faint progress

**Symptoms.**
- The camera preview in the enrollment circle was zoomed in and off-centre:
  with the face in the middle of the camera's view, it appeared at the bottom
  edge of the circle or outside it.
- Captured areas of the progress grid were very hard to see.
- Enrollment could finish while the face was not visible in the circle.

**Causes.**
- The preview is drawn by `FaceEnrollPreviewFragment.configureTransform()` from
  the `face_preview_scale` / `face_preview_translate_x/y` values, which were
  1 / 0 / 0. That pins the camera image to the top of the square view, so the
  middle of the camera frame lands near the bottom of the circle.
- `chooseOptimalSize()` asks the front camera for 1920x1080. That is a 16:9 crop
  of the 4:3 sensor, which cuts the sides and makes the preview look zoomed in
  compared with the camera app.
- `FacePoseGridView.onDraw()` fills captured cells with the accent colour at
  alpha 30/255 (12%), and the accent is close to the neutral outline colour.
- The third symptom is a consequence of the first. Enrollment is done by the
  real Pixel 4 face HAL with the IR cameras; the circle only shows the RGB
  selfie camera. The IR cameras could see the face while the misplaced preview
  did not. Enrollment only completes when the HAL reports all poses captured,
  and the HAL rejects frames with no face (checked in the logs).

**Change.**

```java
// FaceEnrollPreviewFragment.chooseOptimalSize()
if (size.getHeight() == 1080 && size.getWidth() == 1440)   // was 1920: use the full 4:3 frame

// FacePoseGridView.onDraw(), captured cells
fill alpha:    inFrame ? 115 : 60     // was 30 : 15
glow alpha:    max(reveal, guide) * 90f    // was 14f
outline width: dp(1.15f + 1.85f * max(reveal, guide))    // was 0.55f
```

```xml
<!-- apps/Settings/res/values/face_preview.xml -->
face_preview_scale        1.05   (was 1)
face_preview_translate_x  -24    (was 0)
face_preview_translate_y  -189   (was 0)
```

With a 1440x1080 stream, the square preview view on the Pixel 4 (946 px, circle
radius 453 px) shows the camera image 993x1324 px, with the centre of the camera
frame on the centre of the circle. These pixel values only suit this screen.
Stock Pixel 4 firmware uses 1.2 / -100 / -400 with a 16:9 stream; tried first,
it left the face too large and low.

Prebuilt: [`patches/settings-face-enroll.json`](../patches/settings-face-enroll.json)
plus [`overlays/HeckerFacePreview`](../overlays/HeckerFacePreview). Bytecode before
and after is in [`apps/Settings/bytecode`](../apps/Settings/bytecode). Tested by
enrolling twice and comparing with the camera app.
