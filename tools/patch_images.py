#!/usr/bin/env python3
"""Write the fixed files into copies of the stock product and system_ext images.

  patch_images.py --product work/images/product.img --system-ext work/images/system_ext.img

Run from the repository root. Uses debugfs (e2fsprogs) on the ext4 images in place:
each file is replaced or added as root:root 0644 with the SELinux label
u:object_r:system_file:s0, and file and directory mtimes are set to now so
PackageManager does not reuse its cached parse of the old APKs (the build
fingerprint stays the same). Lines in product/etc/build.prop.append are added to
/product/etc/build.prop (kept root:root 0600). The images keep their size; run
avb_update.py next.
"""
import argparse, os, shutil, subprocess, sys, time

PRODUCT = [
    ("/priv-app/EuiccGoogle/EuiccGoogle.apk", "prebuilts/EuiccGoogle.apk"),
    ("/app/FloralMotionSenseBridge/FloralMotionSenseBridge.apk", "prebuilts/FloralMotionSenseBridge.apk"),
    ("/etc/permissions/privapp-permissions-hecker-euicc.xml", "product/etc/permissions/privapp-permissions-hecker-euicc.xml"),
    ("/overlay/HeckerHidePill.apk", "out/overlays/HeckerHidePill.apk"),
    ("/overlay/HeckerGestureSpace.apk", "out/overlays/HeckerGestureSpace.apk"),
    ("/overlay/HeckerShadePanel.apk", "out/overlays/HeckerShadePanel.apk"),
    ("/overlay/HeckerSettingsTheme.apk", "out/overlays/HeckerSettingsTheme.apk"),
    ("/overlay/HeckerFacePreview.apk", "out/overlays/HeckerFacePreview.apk"),
]
SYSTEM_EXT = [
    ("/priv-app/Settings/Settings.apk", "out/apps/Settings.apk"),
    ("/priv-app/SystemUI/SystemUI.apk", "out/apps/SystemUI.apk"),
]
NEW_DIRS = {"product": [], "system_ext": []}
PROP_APPEND = {"product": ("/etc/build.prop", "product/etc/build.prop.append"), "system_ext": None}
LABEL = b"u:object_r:system_file:s0\0"


def commands(files, new_dirs, stage, stamp):
    out, dirs = [], set()
    for d in new_dirs:
        parent, name = d.rsplit("/", 1)
        out += ["cd %s" % (parent or "/"), "mkdir %s" % name,
                "sif %s mode 040755" % d, "sif %s uid 0" % d, "sif %s gid 0" % d,
                "ea_set -f %s/label %s security.selinux" % (stage, d)]
    for dest, _ in files:
        parent, name = dest.rsplit("/", 1)
        dirs.add(parent)
        out += ["cd %s" % parent, "rm %s" % name, "write %s/%s %s" % (stage, name, name),
                "sif %s mode 0100644" % dest, "sif %s uid 0" % dest, "sif %s gid 0" % dest,
                "ea_set -f %s/label %s security.selinux" % (stage, dest),
                "sif %s mtime %s" % (dest, stamp), "sif %s ctime %s" % (dest, stamp)]
    for d in sorted(dirs):
        out += ["sif %s mtime %s" % (d, stamp), "sif %s ctime %s" % (d, stamp)]
    return "\n".join(out) + "\n"


def append_prop(image, dest, src, work, stage, stamp, debugfs):
    """Append src to the build.prop at dest inside image, keeping mode 0600 and the label."""
    rel = lambda p: os.path.relpath(p, work).replace(os.sep, "/")
    local = os.path.join(stage, "build.prop")
    subprocess.run([debugfs, "-R", "dump %s %s" % (dest, rel(local)), rel(image)], cwd=work, capture_output=True)
    if not os.path.isfile(local) or not os.path.getsize(local):
        sys.exit("could not read %s from %s" % (dest, image))
    data = open(local, "rb").read()
    extra = open(src, "rb").read()
    if extra.strip() in data:
        return False
    open(local, "wb").write(data + extra)
    parent, name = dest.rsplit("/", 1)
    return ["cd %s" % parent, "rm %s" % name, "write %s/build.prop %s" % (os.path.basename(stage), name),
            "sif %s mode 0100600" % dest, "sif %s uid 0" % dest, "sif %s gid 0" % dest,
            "ea_set -f %s/label %s security.selinux" % (os.path.basename(stage), dest),
            "sif %s mtime %s" % (dest, stamp), "sif %s ctime %s" % (dest, stamp)]


def patch(image, files, new_dirs, debugfs, e2fsck, prop=None):
    work = os.path.dirname(image) or "."
    stage = os.path.join(work, "stage-" + os.path.splitext(os.path.basename(image))[0])
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage)
    with open(os.path.join(stage, "label"), "wb") as f:
        f.write(LABEL)
    for dest, src in files:
        if not os.path.isfile(src):
            sys.exit("missing input: %s" % src)
        shutil.copyfile(src, os.path.join(stage, dest.rsplit("/", 1)[1]))
    stamp = time.strftime("%Y%m%d%H%M%S", time.gmtime())
    cmd_file = stage + ".cmds"
    with open(cmd_file, "w", newline="\n") as f:
        f.write(commands(files, new_dirs, os.path.basename(stage), stamp))
    rel = lambda p: os.path.relpath(p, work).replace(os.sep, "/")
    r = subprocess.run([debugfs, "-w", "-f", rel(cmd_file), rel(image)], cwd=work, capture_output=True, text=True)
    # "rm" of a file that is being added for the first time is expected to fail; anything else is fatal
    errors = [l for l in (r.stdout + r.stderr).splitlines()
              if not l.startswith("rm:") and (" while " in l or "Could not" in l or "No free space" in l)]
    if r.returncode or errors:
        sys.exit("debugfs failed on %s:\n%s" % (image, "\n".join(errors) or r.stderr))
    r = subprocess.run([e2fsck, "-fn", rel(image)], cwd=work, capture_output=True, text=True)
    if r.returncode:
        sys.exit("e2fsck reports problems in %s:\n%s" % (image, r.stdout + r.stderr))
    shutil.rmtree(stage)
    os.remove(cmd_file)
    print("%s: %d files written, e2fsck clean" % (image, len(files)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--product", required=True)
    ap.add_argument("--system-ext", required=True)
    ap.add_argument("--debugfs", default=os.environ.get("DEBUGFS", "debugfs"))
    ap.add_argument("--e2fsck", default=os.environ.get("E2FSCK", "e2fsck"))
    a = ap.parse_args()
    patch(a.product, PRODUCT, NEW_DIRS["product"], a.debugfs, a.e2fsck, PROP_APPEND["product"])
    patch(a.system_ext, SYSTEM_EXT, NEW_DIRS["system_ext"], a.debugfs, a.e2fsck, PROP_APPEND["system_ext"])


if __name__ == "__main__":
    main()
