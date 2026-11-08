#!/usr/bin/env python3
"""Check an A/B OTA zip the way recovery and update_engine do, plus structural checks.

  verify_ota.py ROM.zip --cert keys/testkey.x509.pem

  1. whole-file signature (recovery's verify_file: SHA-1, PKCS#7 in the zip comment)
  2. payload metadata signature and payload signature (update_engine)
  3. payload_properties.txt hashes and sizes
  4. ota-property-files byte ranges and zip CRCs
Use tools/payload_extract.py to also check every partition hash.
"""
import argparse, base64, hashlib, os, struct, sys, zipfile
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, utils
from pyasn1.codec.der import decoder
from pyasn1_modules import rfc2315

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from otalib import entry_data_offset, fields, open_payload, signature_from_blob  # noqa: E402

failures = 0


def check(ok, what):
    global failures
    print(("  OK    " if ok else "  FAIL  ") + what)
    failures += 0 if ok else 1


def hash_range(f, start, length, algo):
    h = hashlib.new(algo); f.seek(start)
    while length:
        c = f.read(min(length, 1 << 24)); h.update(c); length -= len(c)
    return h.digest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("zip")
    ap.add_argument("--cert", required=True)
    a = ap.parse_args()
    pub = x509.load_pem_x509_certificate(open(a.cert, "rb").read()).public_key()
    f = open(a.zip, "rb")
    z = zipfile.ZipFile(a.zip)

    print("whole-file signature")
    L = f.seek(0, 2); f.seek(L - 6)
    sig_start, mark, csz = struct.unpack("<HHH", f.read(6))
    check(mark == 0xFFFF, "signature footer present")
    f.seek(L - sig_start)
    ci, _ = decoder.decode(f.read(sig_start - 6), asn1Spec=rfc2315.ContentInfo())
    si = decoder.decode(ci["content"], asn1Spec=rfc2315.SignedData())[0]["signerInfos"][0]
    try:
        pub.verify(bytes(si["encryptedDigest"]), hash_range(f, 0, L - csz - 2, "sha1"),
                   padding.PKCS1v15(), utils.Prehashed(hashes.SHA1()))
        check(True, "signature verifies with %s" % os.path.basename(a.cert))
    except Exception:
        check(False, "signature verifies with %s" % os.path.basename(a.cert))

    print("payload signatures")
    p = open_payload(a.zip)
    try:
        pub.verify(signature_from_blob(p["metadata_signature"]), hashlib.sha256(p["header"] + p["manifest"]).digest(),
                   padding.PKCS1v15(), utils.Prehashed(hashes.SHA256()))
        check(True, "metadata signature")
    except Exception:
        check(False, "metadata signature")
    mf = dict(p["manifest_fields"])
    # the payload signature covers header + manifest + data, not the metadata signature
    hh = hashlib.sha256(); hh.update(p["header"] + p["manifest"]); f.seek(p["data_offset"]); left = mf[4]
    while left:
        c = f.read(min(left, 1 << 24)); hh.update(c); left -= len(c)
    f.seek(p["data_offset"] + mf[4]); blob = f.read(mf[5])
    check(p["data_offset"] + mf[4] + mf[5] == p["base"] + p["size"], "signature blob ends the payload")
    try:
        pub.verify(signature_from_blob(blob), hh.digest(), padding.PKCS1v15(), utils.Prehashed(hashes.SHA256()))
        check(True, "payload signature")
    except Exception:
        check(False, "payload signature")

    print("payload_properties.txt")
    props = dict(l.split("=", 1) for l in z.read("payload_properties.txt").decode().split())
    check(int(props["FILE_SIZE"]) == p["size"], "FILE_SIZE")
    check(base64.b64decode(props["FILE_HASH"]) == hash_range(f, p["base"], p["size"], "sha256"), "FILE_HASH")
    check(int(props["METADATA_SIZE"]) == 24 + len(p["manifest"]), "METADATA_SIZE")
    check(base64.b64decode(props["METADATA_HASH"]) == hashlib.sha256(p["header"] + p["manifest"]).digest(), "METADATA_HASH")

    print("zip structure")
    check(z.testzip() is None, "CRC of every entry")
    names = {"metadata": "META-INF/com/android/metadata", "metadata.pb": "META-INF/com/android/metadata.pb"}
    meta = z.read("META-INF/com/android/metadata").decode()
    for line in meta.splitlines():
        if not line.startswith(("ota-property-files=", "ota-streaming-property-files=")):
            continue
        for ent in line.split("=", 1)[1].strip().split(","):
            name, o, s = ent.rsplit(":", 2); o, s = int(o), int(s)
            if name == "payload_metadata.bin":
                ok = o == p["base"] and s == 24 + len(p["manifest"]) + len(p["metadata_signature"])
            else:
                zi = z.getinfo(names.get(name, name))
                ok = o == entry_data_offset(f, zi) and s == zi.compress_size
                if ok and zi.filename != "payload.bin":
                    f.seek(o); ok = f.read(s) == z.read(zi.filename)
            check(ok, "%s %s" % (line.split("=")[0], ent))
    print("RESULT:", "all checks passed" if not failures else "%d check(s) failed" % failures)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
