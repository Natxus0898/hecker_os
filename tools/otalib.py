"""Shared helpers for reading and writing A/B OTA payloads (update_engine major version 2)."""
import struct, zipfile


# ---- minimal protobuf wire format ----

def _varint(b, i):
    r = s = 0
    while True:
        c = b[i]; i += 1; r |= (c & 127) << s; s += 7
        if c < 128:
            return r, i


def fields(b):
    """Decode a protobuf message into an ordered list of (field_number, value).
    Varints become int, length-delimited fields bytes, fixed64/fixed32 ('f64'|'f32', raw)."""
    i, out = 0, []
    while i < len(b):
        k, i = _varint(b, i)
        t, k = k & 7, k >> 3
        if t == 0:
            v, i = _varint(b, i)
        elif t == 2:
            n, i = _varint(b, i); v = bytes(b[i:i + n]); i += n
        elif t == 1:
            v = ("f64", bytes(b[i:i + 8])); i += 8
        elif t == 5:
            v = ("f32", bytes(b[i:i + 4])); i += 4
        else:
            raise ValueError("unsupported wire type %d" % t)
        out.append((k, v))
    return out


def varint(n):
    out = bytearray()
    while True:
        x, n = n & 127, n >> 7
        if n:
            out.append(x | 128)
        else:
            out.append(x)
            return bytes(out)


def encode(flist):
    out = bytearray()
    for k, v in flist:
        if isinstance(v, int):
            out += varint(k << 3) + varint(v)
        elif isinstance(v, tuple):
            out += varint((k << 3) | (1 if v[0] == "f64" else 5)) + v[1]
        else:
            out += varint((k << 3) | 2) + varint(len(v)) + v
    return bytes(out)


def signatures_blob(sig):
    """update_engine Signatures message holding one RSA signature."""
    inner = encode([(2, sig), (3, ("f32", struct.pack("<I", len(sig))))])
    return encode([(1, inner)])


def signature_from_blob(blob):
    return dict(fields(dict(fields(blob))[1]))[2]


# ---- payload.bin inside a zip ----

def entry_data_offset(f, zi):
    f.seek(zi.header_offset)
    h = f.read(30)
    n, m = struct.unpack("<HH", h[26:30])
    return zi.header_offset + 30 + n + m


def open_payload(zpath):
    z = zipfile.ZipFile(zpath)
    zi = z.getinfo("payload.bin")
    if zi.compress_type != 0:
        raise ValueError("payload.bin must be stored")
    f = open(zpath, "rb")
    base = entry_data_offset(f, zi)
    f.seek(base)
    hdr = f.read(24)
    if hdr[:4] != b"CrAU":
        raise ValueError("not an update_engine payload")
    version, msz = struct.unpack(">QQ", hdr[4:20])
    if version != 2:
        raise ValueError("payload major version %d not supported" % version)
    ssz = struct.unpack(">I", hdr[20:24])[0]
    manifest = f.read(msz)
    metadata_sig = f.read(ssz)
    mf = fields(manifest)
    parts = []
    for k, v in mf:
        if k != 13:
            continue
        pf = fields(v)
        info = dict(fields([b for a, b in pf if a == 7][0]))
        parts.append({"name": [b for a, b in pf if a == 1][0].decode(), "size": info.get(1, 0),
                      "hash": info.get(2, b""), "ops": [b for a, b in pf if a == 8], "fields": pf})
    return {"zip": z, "file": f, "base": base, "size": zi.file_size, "header": hdr, "manifest": manifest,
            "manifest_fields": mf, "metadata_signature": metadata_sig,
            "data_offset": base + 24 + msz + ssz, "block_size": dict(mf).get(3, 4096), "partitions": parts}
