#!/usr/bin/env python3
"""Refresh AVB metadata after partition images were modified.

  avb_update.py --vbmeta-system stock/vbmeta_system.img --key keys/testkey_rsa2048.pem \
                --out work/vbmeta_system.img work/product.img work/system_ext.img

For each image (which must keep its size and AVB footer):
  * rebuild the dm-verity hash tree over the filesystem area and write it in place,
  * clear the stale FEC area and set the hashtree descriptor to "no FEC",
  * store the new root digest in the image's footer vbmeta.
Then copy the stock vbmeta_system, update the same descriptors, and re-sign it.
vbmeta itself only chains to vbmeta_system's public key, so it does not change.
"""
import argparse, hashlib, os, struct
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

BS = 4096
HDR = ">4sLLQQLQQQQQQQQQQQLL"
HDR_LEN = struct.calcsize(HDR)


def header(blob):
    v = struct.unpack(HDR, blob[:HDR_LEN])
    keys = ("magic maj min auth aux alg hash_off hash_size sig_off sig_size pub_off pub_size "
            "meta_off meta_size desc_off desc_size rollback flags rollback_loc").split()
    return dict(zip(keys, v))


def hashtree_descriptors(blob):
    """Yield (offset of descriptor body in blob, partition name, fields) for hashtree descriptors."""
    h = header(blob)
    i = 256 + h["auth"] + h["desc_off"]
    end = i + h["desc_size"]
    while i < end:
        tag, n = struct.unpack(">QQ", blob[i:i + 16])
        b = i + 16
        if tag == 1:   # AvbHashtreeDescriptor
            ver, isz, toff, tsz, dbs, hbs, fecr, fo, fs = struct.unpack(">LQQQLLLQQ", blob[b:b + 56])
            pnl, sl, rdl, fl = struct.unpack(">LLLL", blob[b + 88:b + 104])
            o = b + 164
            name = blob[o:o + pnl].decode()
            yield b, name, dict(image_size=isz, tree_offset=toff, tree_size=tsz, data_block=dbs, hash_block=hbs,
                                fec_roots=fecr, fec_offset=fo, fec_size=fs, salt=bytes(blob[o + pnl:o + pnl + sl]),
                                root_offset=o + pnl + sl, root_len=rdl)
        i = b + n


def set_descriptor(blob, body, d, root):
    blob[body + 36:body + 40] = struct.pack(">L", 0)          # fec_num_roots
    blob[body + 40:body + 56] = struct.pack(">QQ", 0, 0)      # fec_offset, fec_size
    assert d["root_len"] == len(root)
    blob[d["root_offset"]:d["root_offset"] + len(root)] = root


def hash_tree(f, image_size, salt):
    """dm-verity hash tree as AVB lays it out: SHA-256 with salt prefix, top level first."""
    levels, level = [], bytearray()
    base = hashlib.sha256(salt)
    f.seek(0)
    left = image_size
    while left:
        chunk = f.read(min(left, BS * 2048))
        left -= len(chunk)
        for i in range(0, len(chunk), BS):
            h = base.copy(); h.update(chunk[i:i + BS]); level += h.digest()
    pad = lambda b: b + bytes(-len(b) % BS)
    level = pad(level); levels.append(bytes(level))
    while len(level) > BS:
        nxt = bytearray()
        for i in range(0, len(level), BS):
            h = base.copy(); h.update(level[i:i + BS]); nxt += h.digest()
        level = pad(nxt); levels.append(bytes(level))
    h = base.copy(); h.update(level)
    return h.digest(), b"".join(reversed(levels))


def update_image(path):
    name = os.path.splitext(os.path.basename(path))[0]
    with open(path, "r+b") as f:
        size = f.seek(0, 2)
        f.seek(size - 64)
        footer = f.read(64)
        if footer[:4] != b"AVBf":
            raise SystemExit("%s: no AVB footer" % path)
        _, vb_off, vb_size = struct.unpack(">QQQ", footer[12:36])
        f.seek(vb_off)
        blob = bytearray(f.read(vb_size))
        matches = [x for x in hashtree_descriptors(bytes(blob)) if x[1] == name]
        if len(matches) != 1:
            raise SystemExit("%s: hashtree descriptor for '%s' not found" % (path, name))
        body, _, d = matches[0]
        root, tree = hash_tree(f, d["image_size"], d["salt"])
        if len(tree) != d["tree_size"]:
            raise SystemExit("%s: tree size %d != descriptor %d" % (path, len(tree), d["tree_size"]))
        f.seek(d["tree_offset"]); f.write(tree)
        if d["fec_size"]:
            f.seek(d["fec_offset"]); f.write(bytes(d["fec_size"]))
        set_descriptor(blob, body, d, root)
        f.seek(vb_off); f.write(blob)
    print("%-12s root %s" % (name, root.hex()))
    return name, root


def resign(blob, key):
    h = header(blob)
    signed = bytes(blob[:256]) + bytes(blob[256 + h["auth"]:256 + h["auth"] + h["aux"]])
    a = 256
    blob[a + h["hash_off"]:a + h["hash_off"] + h["hash_size"]] = hashlib.sha256(signed).digest()
    sig = key.sign(signed, padding.PKCS1v15(), hashes.SHA256())
    assert len(sig) == h["sig_size"]
    blob[a + h["sig_off"]:a + h["sig_off"] + h["sig_size"]] = sig
    key.public_key().verify(sig, signed, padding.PKCS1v15(), hashes.SHA256())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vbmeta-system", required=True, help="stock vbmeta_system.img")
    ap.add_argument("--key", required=True, help="AVB key for vbmeta_system (PEM)")
    ap.add_argument("--out", required=True, help="where to write the new vbmeta_system.img")
    ap.add_argument("images", nargs="+")
    a = ap.parse_args()
    roots = dict(update_image(p) for p in a.images)
    vs = bytearray(open(a.vbmeta_system, "rb").read())
    done = set()
    for body, name, d in list(hashtree_descriptors(bytes(vs))):
        if name in roots:
            set_descriptor(vs, body, d, roots[name]); done.add(name)
    missing = set(roots) - done
    if missing:
        raise SystemExit("vbmeta_system has no descriptor for: %s" % ", ".join(sorted(missing)))
    key = serialization.load_pem_private_key(open(a.key, "rb").read(), None)
    resign(vs, key)
    open(a.out, "wb").write(vs)
    print("vbmeta_system updated and re-signed:", a.out)


if __name__ == "__main__":
    main()
