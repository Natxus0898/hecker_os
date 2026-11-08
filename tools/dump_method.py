#!/usr/bin/env python3
"""Print the bytecode of one method from an APK in a stable, diff-friendly form.

  dump_method.py APK 'Lcom/android/settings/biometrics/face/FacePoseGridView;' onDraw

Uses `dexdump -d` from the Android SDK build-tools. Raw bytes and file offsets
are dropped; the dex file name and code_item offset are printed in the header
so the listing can be matched with a binary patch.
"""
import os, re, shutil, subprocess, sys, tempfile, zipfile


def dexdump():
    exe = os.environ.get("DEXDUMP") or shutil.which("dexdump")
    if exe:
        return exe
    sdk = os.environ.get("ANDROID_HOME") or os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk")
    bt = os.path.join(sdk, "build-tools")
    for v in sorted(os.listdir(bt), reverse=True) if os.path.isdir(bt) else []:
        for n in ("dexdump.exe", "dexdump"):
            if os.path.isfile(os.path.join(bt, v, n)):
                return os.path.join(bt, v, n)
    sys.exit("dexdump not found: set DEXDUMP or ANDROID_HOME")


def main():
    apk, cls, method = sys.argv[1:4]
    z = zipfile.ZipFile(apk)
    for dex in sorted(n for n in z.namelist() if re.match(r"classes\d*\.dex$", n)):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, dex)
            open(p, "wb").write(z.read(dex))
            out = subprocess.run([dexdump(), "-d", p], capture_output=True, text=True, errors="replace").stdout
        blocks = re.split(r"(?m)^(?=Class #\d+)", out)
        for b in blocks:
            if "Class descriptor  : '%s'" % cls not in b:
                continue
            for mb in re.split(r"(?m)^(?=    #\d+\s+: \(in )", b):
                if not re.search(r"name\s+: '%s'" % re.escape(method), mb):
                    continue
                typ = re.search(r"type\s+: '([^']+)'", mb).group(1)
                regs = re.search(r"registers\s+: (\d+)", mb)
                code = re.search(r"^([0-9a-f]{6}):\s+\|\[[0-9a-f]+\]", mb, re.M)
                print("# %s->%s%s" % (cls, method, typ))
                print("# dex: %s" % dex)
                if code:
                    print("# code_item at dex offset 0x%s (instructions start 16 bytes later)" % code.group(1))
                if regs:
                    print("# registers: %s" % regs.group(1))
                for line in mb.splitlines():
                    m = re.match(r"^[0-9a-f]{6}: [0-9a-f ]+\|([0-9a-f]{4}: .*)$", line)
                    if m:
                        print(re.sub(r" // (method|field|type|string)@[0-9a-f]+", "", m.group(1)).rstrip())
                    elif re.match(r"\s+catches\s+:", line) or re.match(r"\s+L[\w/$]+; -> 0x", line) or re.match(r"\s+0x[0-9a-f]+ - 0x[0-9a-f]+$", line):
                        print("# " + line.strip())
                return
    sys.exit("method not found")


if __name__ == "__main__":
    main()
