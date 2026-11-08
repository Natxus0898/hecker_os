#!/usr/bin/env python3
"""Extract partition images from an A/B OTA zip (payload.bin), checking every hash.

  payload_extract.py ROM.zip OUTDIR [PARTITION ...]      (default: all partitions)
  payload_extract.py ROM.zip --list

Supports full payloads (REPLACE, REPLACE_BZ, REPLACE_XZ, ZERO, DISCARD; REPLACE_ZSTD
needs the `zstandard` module).
"""
import bz2, hashlib, lzma, os, struct, sys, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from otalib import fields, open_payload  # noqa: E402


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    zpath = sys.argv[1]
    p = open_payload(zpath)
    f, bs = p["file"], p["block_size"]
    if sys.argv[2] == "--list":
        for part in p["partitions"]:
            print("%-16s %12d bytes  %5d ops" % (part["name"], part["size"], len(part["ops"])))
        return
    out, want = sys.argv[2], set(sys.argv[3:])
    os.makedirs(out, exist_ok=True)
    for part in p["partitions"]:
        if want and part["name"] not in want:
            continue
        path = os.path.join(out, part["name"] + ".img")
        with open(path, "wb") as o:
            o.truncate(part["size"])
            for opb in part["ops"]:
                op = fields(opb)
                d = dict(op)
                ext = [dict(fields(v)) for k, v in op if k == 6]
                t = d.get(1, 0)
                if t in (0, 1, 8, 14):
                    f.seek(p["data_offset"] + d.get(2, 0))
                    raw = f.read(d.get(3, 0))
                    if 8 in d and hashlib.sha256(raw).digest() != d[8]:
                        sys.exit("%s: operation data hash mismatch" % part["name"])
                    if t == 1:
                        raw = bz2.decompress(raw)
                    elif t == 8:
                        raw = lzma.decompress(raw)
                    elif t == 14:
                        import zstandard
                        raw = zstandard.ZstdDecompressor().decompress(raw, max_output_size=1 << 31)
                    q = 0
                    for e in ext:
                        n = e.get(2, 0) * bs
                        o.seek(e.get(1, 0) * bs); o.write(raw[q:q + n]); q += n
                elif t in (6, 7):
                    for e in ext:
                        o.seek(e.get(1, 0) * bs); o.write(bytes(e.get(2, 0) * bs))
                else:
                    sys.exit("%s: unsupported operation type %d" % (part["name"], t))
        h = hashlib.sha256()
        with open(path, "rb") as r:
            for c in iter(lambda: r.read(1 << 24), b""):
                h.update(c)
        ok = h.digest() == part["hash"]
        print("%-16s %s %s" % (part["name"], "OK " if ok else "HASH MISMATCH", h.hexdigest()))
        if not ok:
            sys.exit(1)


if __name__ == "__main__":
    main()
