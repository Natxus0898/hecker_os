#!/usr/bin/env python3
"""Decode compiled Android resources from an APK into readable XML.

Uses `aapt2 dump` from the Android SDK build-tools. Resource ids are resolved to
names through the APK's own resource table and, for android: references, the
framework-res.apk given with --framework.

  decode_res.py xml    APK res/layout/foo.xml  [--framework framework-res.apk] > foo.xml
  decode_res.py values APK color/hecker_accent dimen/face_preview_scale ... --out res/
"""
import argparse, os, re, shutil, subprocess, sys
from collections import defaultdict
from xml.sax.saxutils import escape, quoteattr

ANDROID_NS = "http://schemas.android.com/apk/res/android"


def aapt2():
    exe = os.environ.get("AAPT2") or shutil.which("aapt2")
    if not exe:
        sdk = os.environ.get("ANDROID_HOME") or os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk")
        bt = os.path.join(sdk, "build-tools")
        if os.path.isdir(bt):
            for v in sorted(os.listdir(bt), reverse=True):
                for n in ("aapt2.exe", "aapt2"):
                    if os.path.isfile(os.path.join(bt, v, n)):
                        return os.path.join(bt, v, n)
        sys.exit("aapt2 not found: set AAPT2 or ANDROID_HOME")
    return exe


def run(*args):
    return subprocess.run([aapt2(), *args], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout


_tables = {}
def table(apk):
    """id -> 'type/name' and 'type/name' -> [(config, value)]"""
    if apk not in _tables:
        names, values, cur = {}, defaultdict(list), None
        for line in run("dump", "resources", apk).splitlines():
            m = re.match(r"\s+resource (0x[0-9a-f]{8}) ([\w.]+/[\w.]+)", line)
            if m:
                cur = m.group(2); names[int(m.group(1), 16)] = cur; continue
            m = re.match(r"\s+\(([^)]*)\) (.*)$", line)
            if m and cur:
                values[cur].append((m.group(1), m.group(2)))
        _tables[apk] = (names, values)
    return _tables[apk]


ENUMS = {
    "orientation": {0: "horizontal", 1: "vertical"},
    "visibility": {0: "visible", 1: "invisible", 2: "gone"},
    "importantForAccessibility": {0: "auto", 1: "yes", 2: "no", 4: "noHideDescendants"},
    "scaleType": {0: "matrix", 1: "fitXY", 2: "fitStart", 3: "fitCenter", 4: "fitEnd", 5: "center", 6: "centerCrop", 7: "centerInside"},
    "shape": {0: "rectangle", 1: "oval", 2: "line", 3: "ring"},
}
SIZE_ATTRS = {"layout_width", "layout_height", "width", "height"}


def gravity(v):
    vert = {0x10: "center_vertical", 0x30: "top", 0x50: "bottom", 0x70: "fill_vertical"}.get(v & 0x70)
    hor = {0x01: "center_horizontal", 0x03: "left", 0x05: "right", 0x07: "fill_horizontal",
           0x800003: "start", 0x800005: "end"}.get(v & 0x800007)
    if vert == "center_vertical" and hor == "center_horizontal":
        return "center"
    parts = [p for p in (vert, hor) if p]
    return "|".join(parts) if parts else "0x%08x" % v


def num(s):
    f = float(s)
    return str(int(f)) if f == int(f) else ("%f" % f).rstrip("0")


def ref(rid, apk, framework, prefix="@", attr=None):
    if rid == 0:
        return "@null"
    if rid >> 24 == 0x01:
        if not framework:
            return "%sandroid:0x%08x" % (prefix, rid)
        name = table(framework)[0].get(rid, "0x%08x" % rid)
        return "%sandroid:%s" % (prefix, name)
    name = table(apk)[0].get(rid, "0x%08x" % rid)
    if prefix == "@" and attr == "id" and name.startswith("id/"):
        return "@+" + name
    return prefix + name


def value(attr, raw, apk, framework):
    m = re.match(r'^"(.*)" \(Raw: "(.*)"\)$', raw)
    if m:
        return m.group(2)
    m = re.match(r"^([@?])0x([0-9a-f]{8})$", raw)
    if m:
        return ref(int(m.group(2), 16), apk, framework, m.group(1), attr)
    m = re.match(r"^(-?[\d.]+)(dp|sp|px|dip|pt|mm|in)$", raw)
    if m:
        return num(m.group(1)) + m.group(2)
    if re.match(r"^0x[0-9a-f]{8}$", raw):
        v = int(raw, 16)
        if attr in ("gravity", "layout_gravity"):
            return gravity(v)
        if attr == "textStyle":
            return "|".join(n for b, n in ((1, "bold"), (2, "italic")) if v & b) or "normal"
        return raw
    if re.match(r"^-?\d+$", raw):
        v = int(raw)
        if attr in SIZE_ATTRS and v in (-1, -2):
            return "match_parent" if v == -1 else "wrap_content"
        if attr in ENUMS and v in ENUMS[attr]:
            return ENUMS[attr][v]
        return raw
    if re.match(r"^-?\d+\.\d+$", raw):
        return num(raw)
    return raw


def decode_xml(apk, path, framework=None):
    lines = run("dump", "xmltree", apk, "--file", path).splitlines()
    root, stack = None, []
    for line in lines:
        ind = len(line) - len(line.lstrip())
        s = line.strip()
        if s.startswith("E: "):
            node = {"tag": s[3:].split(" (line=")[0], "attrs": [], "kids": [], "ind": ind}
            while stack and stack[-1]["ind"] >= ind:
                stack.pop()
            (stack[-1]["kids"] if stack else []).append(node)
            if root is None:
                root = node
            stack.append(node)
        elif s.startswith("A: "):
            body = s[3:]
            m = re.match(r"^(?:(\S+?):)?([\w]+)(?:\(0x[0-9a-f]{8}\))?=(.*)$", body)
            if not m:
                continue
            ns, name, raw = m.groups()
            prefix = "android:" if ns == ANDROID_NS else ("app:" if ns else "")
            stack[-1]["attrs"].append((prefix + name, value(name, raw, apk, framework)))
    out = ['<?xml version="1.0" encoding="utf-8"?>']
    def emit(n, depth, first):
        pad = "    " * depth
        attrs = ([("xmlns:android", ANDROID_NS)] if first else []) + n["attrs"]
        if not attrs:
            head = "%s<%s" % (pad, n["tag"])
        else:
            head = "%s<%s\n" % (pad, n["tag"]) + "\n".join("%s    %s=%s" % (pad, k, quoteattr(v)) for k, v in attrs)
        if n["kids"]:
            out.append(head + ">")
            for k in n["kids"]:
                emit(k, depth + 1, False)
            out.append("%s</%s>" % (pad, n["tag"]))
        else:
            out.append(head + " />")
    emit(root, 0, True)
    return "\n".join(out) + "\n"


CONFIG_DIRS = {"": "values", "night": "values-night"}


def decode_values(apk, names, framework=None):
    """returns {values-dir: [xml lines]} for resources like 'color/foo' or 'dimen/bar'"""
    _, vals = table(apk)
    files = defaultdict(list)
    for n in names:
        typ, name = n.split("/", 1)
        if n not in vals:
            sys.exit("not found: " + n)
        for cfg, raw in vals[n]:
            d = CONFIG_DIRS.get(cfg, "values-" + cfg)
            if raw.startswith("(file)"):
                files[d].append('    <!-- %s: %s -->' % (n, raw))
                continue
            v = value(name, raw, apk, framework)
            if typ == "dimen" and re.match(r"^-?[\d.e+-]+$", raw):
                files[d].append('    <item name="%s" type="dimen" format="float">%s</item>' % (name, num(raw)))
            else:
                files[d].append("    <%s name=\"%s\">%s</%s>" % (typ, name, escape(v), typ))
    return files


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["xml", "values"])
    ap.add_argument("apk")
    ap.add_argument("items", nargs="+")
    ap.add_argument("--framework")
    ap.add_argument("--out", help="values mode: res directory to write into")
    ap.add_argument("--name", default="values.xml", help="values mode: file name inside each values dir")
    a = ap.parse_args()
    if a.mode == "xml":
        sys.stdout.write(decode_xml(a.apk, a.items[0], a.framework))
        return
    files = decode_values(a.apk, a.items, a.framework)
    for d, lines in files.items():
        body = '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n' + "\n".join(lines) + "\n</resources>\n"
        if a.out:
            os.makedirs(os.path.join(a.out, d), exist_ok=True)
            with open(os.path.join(a.out, d, a.name), "w", encoding="utf-8", newline="\n") as f:
                f.write(body)
        else:
            sys.stdout.write("<!-- %s -->\n%s" % (d, body))


if __name__ == "__main__":
    main()
