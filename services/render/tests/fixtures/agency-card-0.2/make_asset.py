#!/usr/bin/env python3
"""Create the small transparent synthetic model cut-out used by this fixture.

No person, product, logo or supplied brand material is encoded here. The PNG is
purely a deterministic RGBA silhouette with coloured geometric clothing.
"""

import struct
import zlib
from pathlib import Path

WIDTH, HEIGHT = 400, 600
OUT = Path(__file__).with_name("synthetic-model-cutout.png")


def chunk(kind, data):
    return (struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))


def pixel(x, y):
    # Transparent canvas; simple head, torso and legs are intentionally
    # abstract to exercise alpha preservation and focal cropping only.
    if ((x - 202) / 56) ** 2 + ((y - 118) / 68) ** 2 <= 1:
        return (246, 210, 174, 255)
    if 122 <= y < 160 and 178 <= x <= 226:
        return (46, 38, 84, 255)
    if 168 <= y < 400 and 118 + (y - 168) // 7 <= x <= 282 - (y - 168) // 7:
        return (76, 206, 178, 255)
    if 400 <= y < 560 and (145 <= x <= 188 or 216 <= x <= 259):
        return (46, 38, 84, 255)
    if 535 <= y < 570 and (126 <= x <= 195 or 209 <= x <= 278):
        return (246, 210, 174, 255)
    return (0, 0, 0, 0)


def main():
    rows = []
    for y in range(HEIGHT):
        row = bytearray([0])
        for x in range(WIDTH):
            row.extend(pixel(x, y))
        rows.append(bytes(row))
    raw = b"".join(rows)
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    OUT.write_bytes(png)
    print(f"wrote {OUT.name}: {WIDTH}x{HEIGHT}px RGBA")


if __name__ == "__main__":
    main()
