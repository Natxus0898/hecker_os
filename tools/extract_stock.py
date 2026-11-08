#!/usr/bin/env python3
"""Regenerate apps/ (readable copies of the stock files the fixes touch) from ROM APKs.

  extract_stock.py --settings Settings.apk --systemui SystemUI.apk \
                   --framework framework-res.apk --launcher NexusLauncherRelease.apk --out apps

The APKs come from the stock ROM: /system_ext/priv-app/Settings, /system_ext/priv-app/SystemUI,
/system/framework/framework-res.apk and /product/priv-app/NexusLauncherRelease (pull them with
`adb pull` from a phone running the ROM, or from the extracted images, see docs/BUILDING.md).
"""
import argparse, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import decode_res  # noqa: E402

SETTINGS_XML = [
    "res/layout/hecker_homepage_preference.xml",
    "res/layout/hecker_brand_preference.xml",
    "res/layout/hecker_maintainer_preference.xml",
    "res/drawable/hecker_card_background.xml",
    "res/drawable/hecker_button_background.xml",
    "res/drawable/hecker_icon_background.xml",
]
SETTINGS_COLORS = ["color/hecker_" + n for n in (
    "background", "card", "border", "foreground", "secondary", "accent", "on_accent", "button", "icon_background")]
SETTINGS_FACE = ["dimen/face_preview_scale", "dimen/face_preview_translate_x", "dimen/face_preview_translate_y"]
FRAMEWORK_XML = [
    ("res/color/shade_panel_bg_color.xml", "res/color/shade_panel_bg_color.xml"),
    ("res/color-night-v8/shade_panel_bg_color.xml", "res/color-night/shade_panel_bg_color.xml"),
    ("res/color/shade_panel_fg_color.xml", "res/color/shade_panel_fg_color.xml"),
    ("res/color-night-v8/shade_panel_fg_color.xml", "res/color-night/shade_panel_fg_color.xml"),
    ("res/color/shade_panel_scrim_color.xml", "res/color/shade_panel_scrim_color.xml"),
]
METHODS = [
    ("settings", "Lcom/android/settings/biometrics/face/FacePoseGridView;", "onDraw",
     "Settings/bytecode/FacePoseGridView.onDraw.txt"),
    ("settings", "Lcom/android/settings/biometrics/face/FaceEnrollPreviewFragment;", "chooseOptimalSize",
     "Settings/bytecode/FaceEnrollPreviewFragment.chooseOptimalSize.txt"),
    ("systemui", "Lcom/android/systemui/hecker/HeckerReferenceQuickSettingsKt$$ExternalSyntheticLambda34;", "invoke",
     "SystemUI/bytecode/HeckerReferenceQuickSettingsKt.Lambda34.invoke.txt"),
]


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def values(apk, names, out_res, fname, fw):
    for d, lines in decode_res.decode_values(apk, names, fw).items():
        write(os.path.join(out_res, d, fname),
              '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n' + "\n".join(lines) + "\n</resources>\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--settings", required=True)
    ap.add_argument("--systemui", required=True)
    ap.add_argument("--framework", required=True)
    ap.add_argument("--launcher", required=True)
    ap.add_argument("--out", default="apps")
    a = ap.parse_args()
    fw = a.framework

    res = os.path.join(a.out, "Settings", "res")
    for f in SETTINGS_XML:
        write(os.path.join(res, f[len("res/"):]), decode_res.decode_xml(a.settings, f, fw))
    values(a.settings, SETTINGS_COLORS, res, "hecker_colors.xml", fw)
    values(a.settings, SETTINGS_FACE, res, "face_preview.xml", fw)

    fres = os.path.join(a.out, "framework-res", "res")
    values(fw, ["dimen/taskbar_stashed_size"], fres, "dimens.xml", fw)
    values(fw, ["color/shade_panel_bg", "color/shade_panel_fg", "color/shade_panel_scrim"], fres, "colors.xml", fw)
    for src, dst in FRAMEWORK_XML:
        write(os.path.join(a.out, "framework-res", dst), decode_res.decode_xml(fw, src, fw))

    values(a.launcher, ["color/taskbar_stashed_handle_light_color", "color/taskbar_stashed_handle_dark_color"],
           os.path.join(a.out, "NexusLauncher", "res"), "colors.xml", fw)

    apks = {"settings": a.settings, "systemui": a.systemui}
    for which, cls, meth, dst in METHODS:
        out = subprocess.run([sys.executable, os.path.join(HERE, "dump_method.py"), apks[which], cls, meth],
                             capture_output=True, text=True, check=True).stdout
        write(os.path.join(a.out, dst), out)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
