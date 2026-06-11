#!/usr/bin/env python3
"""RND-3 acceptance check: a PDF must contain a NAMED /Separation colourspace
per spot swatch. Presence of any /Separation is a false pass — crop marks
always contribute /Separation /All (registration).

    python3 check_separation.py out.pdf CutContour [MoreSpots...]

Exit 0 if every named separation is present; 1 otherwise (prints what WAS found).
"""

import re
import sys
import zlib
from pathlib import Path

SEP_RE = re.compile(rb"/Separation\s*/((?:[^\s/\[\]<>()#]|#[0-9A-Fa-f]{2})+)")


def pdf_name(raw: bytes) -> str:
    """Decode #xx escapes in a PDF name."""
    return re.sub(rb"#([0-9A-Fa-f]{2})",
                  lambda m: bytes([int(m.group(1), 16)]),
                  raw).decode("latin-1")


def separations(pdf_path):
    data = Path(pdf_path).read_bytes()
    names = {pdf_name(m) for m in SEP_RE.findall(data)}
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        try:
            inflated = zlib.decompress(m.group(1))
        except zlib.error:
            continue
        names |= {pdf_name(n) for n in SEP_RE.findall(inflated)}
    return names


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    pdf, wanted = argv[1], set(argv[2:])
    found = separations(pdf)
    missing = wanted - found
    print(f"separations found: {sorted(found) or 'none'}")
    if missing:
        print(f"MISSING named separations: {sorted(missing)}")
        return 1
    print("ok: all required named separations present")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
