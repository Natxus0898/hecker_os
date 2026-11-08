#!/usr/bin/env python3
"""Build a new signed A/B OTA zip from a stock one, replacing some partition images.

  build_ota.py --stock-zip HeckerOS_flame-17.0-20261026-2156.zip --stock-images work/stock \
               --images work/images --key keys/testkey.pk8 --out out/HeckerOS_fixed.zip

--images holds the new <partition>.img files (same sizes as stock). --stock-images holds
the same partitions extracted from the stock zip (tools/payload_extract.py).

Install operations whose target blocks did not change are copied byte for byte from
the stock payload; the others are re-encoded as REPLACE_XZ (CRC none, like the stock
payload). The payload metadata and payload are signed with --key, and the whole zip
is signed the way `signapk -w` does it, so recovery verifies it like the stock zip.
"""
import argparse, base64, hashlib, lzma, os, struct, sys, zlib
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, utils
from pyasn1.codec.der import decoder, encoder
from pyasn1_modules import rfc2315

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from otalib import encode, entry_data_offset, fields, open_payload, signatures_blob  # noqa: E402

BS = 4096


def read_extents(f, exts):
    out = bytearray()
    for start, count in exts:
        f.seek(start * BS); out += f.read(count * BS)
    return bytes(out)


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 24), b""):
            h.update(c)
    return h.digest()


def plan_partitions(p, images, stock_images):
    plan = []
    for part in p["partitions"]:
        name, entries, info = part["name"], [], None
        new = os.path.join(images, name + ".img")
        if os.path.exists(new):
            if os.path.getsize(new) != part["size"]:
                sys.exit("%s: size %d differs from stock %d" % (name, os.path.getsize(new), part["size"]))
            fn, fo = open(new, "rb"), open(os.path.join(stock_images, name + ".img"), "rb")
            copied = changed = 0
            for opb in part["ops"]:
                op = fields(opb)
                exts = [(dict(fields(v)).get(1, 0), dict(fields(v)).get(2, 0)) for k, v in op if k == 6]
                data = read_extents(fn, exts)
                if data == read_extents(fo, exts):
                    d = dict(op); entries.append(("copy", op, d[2], d[3])); copied += 1
                    continue
                blob, typ = lzma.compress(data, format=lzma.FORMAT_XZ, check=lzma.CHECK_NONE, preset=6), 8
                if len(blob) >= len(data):
                    blob, typ = data, 0
                op = [(1, typ), (2, 0), (3, 0)] + [(6, v) for k, v in op if k == 6] + \
                     [(8, hashlib.sha256(blob).digest())]
                entries.append(("new", op, blob)); changed += 1
            info = encode([(1, part["size"]), (2, file_sha256(new))])
            print("%-14s %5d operations copied, %4d re-encoded" % (name, copied, changed), flush=True)
        else:
            for opb in part["ops"]:
                op = fields(opb); d = dict(op); entries.append(("copy", op, d[2], d[3]))
        plan.append((part, info, entries))
    return plan


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stock-zip", required=True)
    ap.add_argument("--stock-images", required=True)
    ap.add_argument("--images", required=True)
    ap.add_argument("--key", required=True, help="OTA signing key, PKCS#8 DER (testkey.pk8)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    key = serialization.load_der_private_key(open(a.key, "rb").read(), None)
    sign256 = lambda d: key.sign(d, padding.PKCS1v15(), utils.Prehashed(hashes.SHA256()))
    p = open_payload(a.stock_zip)
    sf = p["file"]
    plan = plan_partitions(p, a.images, a.stock_images)

    # assign data offsets in operation order and rebuild the manifest
    off, parts = 0, []
    for part, info, entries in plan:
        it = iter(entries); pf = []
        for k, v in part["fields"]:
            if k == 7 and info is not None:
                pf.append((7, info))
            elif k == 8:
                e = next(it)
                length = e[3] if e[0] == "copy" else len(e[2])
                op = [(kk, off if kk == 2 else length if (kk == 3 and e[0] == "new") else vv) for kk, vv in e[1]]
                off += length
                pf.append((8, encode(op)))
            else:
                pf.append((k, v))
        parts.append(encode(pf))
    data_len = off
    sig_size = len(signatures_blob(bytes(256)))
    it = iter(parts)
    man = encode([(13, next(it)) if k == 13 else (4, data_len) if k == 4 else (5, sig_size) if k == 5 else (k, v)
                  for k, v in p["manifest_fields"]])
    hdr = b"CrAU" + struct.pack(">QQ", 2, len(man)) + struct.pack(">I", sig_size)
    meta_digest = hashlib.sha256(hdr + man).digest()

    out_dir = os.path.dirname(os.path.abspath(a.out))
    os.makedirs(out_dir, exist_ok=True)
    payload_path = a.out + ".payload.tmp"
    file_hash, signed_hash = hashlib.sha256(), hashlib.sha256()
    with open(payload_path, "wb") as pfh:
        def w(b, signed=True):
            pfh.write(b); file_hash.update(b)
            if signed:
                signed_hash.update(b)
        w(hdr); w(man); w(signatures_blob(sign256(meta_digest)), signed=False)
        for part, info, entries in plan:
            for e in entries:
                if e[0] == "copy":
                    sf.seek(p["data_offset"] + e[2]); left = e[3]
                    while left:
                        c = sf.read(min(left, 1 << 24)); w(c); left -= len(c)
                else:
                    w(e[2])
        w(signatures_blob(sign256(signed_hash.digest())), signed=False)
    payload_size = os.path.getsize(payload_path)
    props = ("FILE_HASH=%s\nFILE_SIZE=%d\nMETADATA_HASH=%s\nMETADATA_SIZE=%d\n" % (
        base64.b64encode(file_hash.digest()).decode(), payload_size,
        base64.b64encode(meta_digest).decode(), len(hdr) + len(man))).encode()
    write_zip(p, a.out, payload_path, payload_size, props, len(hdr) + len(man) + sig_size, key)
    os.remove(payload_path)
    print("wrote", a.out, os.path.getsize(a.out), "bytes")


def write_zip(p, out, payload_path, payload_size, props, payload_meta_len, key):
    z = p["zip"]
    entries = z.infolist()
    content = {zi.filename: z.read(zi.filename) for zi in entries if zi.filename != "payload.bin"}
    content["payload_properties.txt"] = props
    deflated = {}
    for zi in entries:
        if zi.compress_type == 8:
            co = zlib.compressobj(9, zlib.DEFLATED, -15)
            deflated[zi.filename] = co.compress(content[zi.filename]) + co.flush()
    size = lambda n: payload_size if n == "payload.bin" else len(deflated.get(n, content.get(n, b"")))
    layout, pos = {}, 0
    for zi in entries:
        layout[zi.filename] = (pos, pos + 30 + len(zi.filename.encode()))
        pos = layout[zi.filename][1] + size(zi.filename)

    # ota-property-files: byte ranges of entries, padded to the stock length so offsets stay fixed
    short = {"META-INF/com/android/metadata": "metadata", "META-INF/com/android/metadata.pb": "metadata.pb"}
    order = ["payload.bin", "payload_properties.txt", "apex_info.pb", "care_map.pb",
             "META-INF/com/android/metadata", "META-INF/com/android/metadata.pb"]
    rng = lambda n: "%s:%d:%d" % (short.get(n, n), layout[n][1], size(n))
    streaming = ",".join(rng(n) for n in order if n in layout)
    full = "payload_metadata.bin:%d:%d," % (layout["payload.bin"][1], payload_meta_len) + streaming

    def padded(new, old):
        if len(new) > len(old):
            sys.exit("property-files string grew; cannot keep zip offsets")
        return new + " " * (len(old) - len(new))
    lines = content["META-INF/com/android/metadata"].decode().split("\n")
    for i, l in enumerate(lines):
        for k, v in (("ota-property-files=", full), ("ota-streaming-property-files=", streaming)):
            if l.startswith(k):
                lines[i] = k + padded(v, l[len(k):])
    content["META-INF/com/android/metadata"] = "\n".join(lines).encode()
    pb = []
    for k, v in fields(content["META-INF/com/android/metadata.pb"]):
        if k == 4:
            e = dict(fields(v)); name = e[1].decode(); old = e[2].decode()
            new = {"ota-property-files": full, "ota-streaming-property-files": streaming}.get(name, old)
            v = encode([(1, e[1]), (2, padded(new, old).encode())])
        pb.append((k, v))
    old_len = len(z.read("META-INF/com/android/metadata.pb"))
    content["META-INF/com/android/metadata.pb"] = encode(pb)
    assert len(content["META-INF/com/android/metadata.pb"]) == old_len

    central, sha1 = bytearray(), hashlib.sha1()
    with open(out, "wb") as o:
        def zw(b):
            o.write(b); sha1.update(b)
        for zi in entries:
            name = zi.filename.encode()
            y, mo, d, hh, mi, ss = zi.date_time
            t, dt = (hh << 11) | (mi << 5) | (ss // 2), ((y - 1980) << 9) | (mo << 5) | d
            hoff = o.tell(); assert hoff == layout[zi.filename][0], zi.filename
            if zi.filename == "payload.bin":
                crc = 0
                with open(payload_path, "rb") as r:
                    for c in iter(lambda: r.read(1 << 24), b""):
                        crc = zlib.crc32(c, crc)
                csize = usize = payload_size; method = 0
            else:
                raw = content[zi.filename]; crc = zlib.crc32(raw); usize = len(raw)
                method = 8 if zi.filename in deflated else 0
                data = deflated.get(zi.filename, raw); csize = len(data)
            ver = 20 if method == 8 else 10
            zw(struct.pack("<IHHHHHIIIHH", 0x04034b50, ver, 0, method, t, dt, crc, csize, usize, len(name), 0) + name)
            if zi.filename == "payload.bin":
                with open(payload_path, "rb") as r:
                    for c in iter(lambda: r.read(1 << 24), b""):
                        zw(c)
            else:
                zw(data)
            central += struct.pack("<IHHHHHHIIIHHHHHII", 0x02014b50, 20, ver, 0, method, t, dt, crc, csize, usize,
                                   len(name), 0, 0, 0, 0, 0, hoff) + name
        cd = o.tell()
        zw(bytes(central))
        zw(struct.pack("<IHHHHII", 0x06054b50, 0, 0, len(entries), len(entries), len(central), cd))
        # whole-file signature: SHA-1 over everything but the comment length and comment,
        # PKCS#7 SignedData without signed attributes, reusing the stock zip's structure.
        sig = key.sign(sha1.digest(), padding.PKCS1v15(), utils.Prehashed(hashes.SHA1()))
        f = p["file"]; L = f.seek(0, 2); f.seek(L - 6)
        sig_start, mark, _ = struct.unpack("<HHH", f.read(6))
        if mark != 0xFFFF:
            sys.exit("stock zip is not whole-file signed")
        f.seek(L - sig_start); der = f.read(sig_start - 6)
        ci, _ = decoder.decode(der, asn1Spec=rfc2315.ContentInfo())
        sd, _ = decoder.decode(ci["content"], asn1Spec=rfc2315.SignedData())
        sd["signerInfos"][0]["encryptedDigest"] = sig
        ci["content"] = encoder.encode(sd)
        new_der = encoder.encode(ci)
        assert len(new_der) == len(der)
        msg = b"signed by SignApk\0"
        comment = msg + new_der + struct.pack("<HHH", len(new_der) + 6, 0xFFFF, len(msg) + len(new_der) + 6)
        if b"PK\x05\x06" in comment:
            sys.exit("signature contains an EOCD marker; rebuild")
        o.write(struct.pack("<H", len(comment)) + comment)


if __name__ == "__main__":
    main()
