#!/usr/bin/env python3
"""Apply byte patches from a JSON spec to the dex files inside an APK.

  apply_dex_patches.py patches/systemui-dark-tile.json SystemUI.apk SystemUI-unsigned.apk

Every patch names the dex file, the byte offset, the stock bytes expected there
and the replacement. Nothing is written unless every expected byte sequence
matches, so a spec cannot be applied to a different build by accident. The dex
header checksum and signature are recomputed. The output is unsigned: run
tools/sign_platform.sh on it.
"""
import hashlib, json, struct, sys, zipfile, zlib


def main():
    spec_path, src, dst = sys.argv[1:4]
    spec = json.load(open(spec_path, encoding="utf-8"))
    z = zipfile.ZipFile(src)
    dexes = {}
    for p in spec["patches"]:
        name = p["dex"]
        if name not in dexes:
            dexes[name] = bytearray(z.read(name))
        b = dexes[name]
        off = int(p["offset"], 16)
        old, new = bytes.fromhex(p["old"]), bytes.fromhex(p["new"])
        assert len(old) == len(new), "patch changes length at %s" % p["offset"]
        cur = bytes(b[off:off + len(old)])
        if cur == new:
            sys.exit("%s %s is already patched" % (name, p["offset"]))
        if cur != old:
            sys.exit("%s %s: expected %s, found %s (different build?)" % (name, p["offset"], old.hex(), cur.hex()))
        b[off:off + len(new)] = new
    for b in dexes.values():
        b[12:32] = hashlib.sha1(bytes(b[32:])).digest()
        b[8:12] = struct.pack("<I", zlib.adler32(bytes(b[12:])) & 0xFFFFFFFF)
    with zipfile.ZipFile(dst, "w") as o:
        for i in z.infolist():
            if i.filename.startswith("META-INF/") and i.filename.upper().endswith((".SF", ".RSA", ".DSA", ".EC", "MANIFEST.MF")):
                continue
            data = bytes(dexes[i.filename]) if i.filename in dexes else z.read(i.filename)
            zi = zipfile.ZipInfo(i.filename, date_time=i.date_time)
            zi.compress_type = i.compress_type
            zi.external_attr = i.external_attr
            o.writestr(zi, data, compresslevel=9 if i.compress_type == zipfile.ZIP_DEFLATED else None)
    for name, b in dexes.items():
        print("patched %s: %d change(s), sha256 %s" % (name, sum(p["dex"] == name for p in spec["patches"]),
                                                     hashlib.sha256(b).hexdigest()))


if __name__ == "__main__":
    main()
