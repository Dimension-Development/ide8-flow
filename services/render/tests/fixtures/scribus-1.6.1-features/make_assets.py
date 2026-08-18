#!/usr/bin/env python3
"""Create the small RGBA source used by the Scribus 1.6.1 feature harvest.

Stdlib-only and deterministic: no image library or network input is required.
"""

import argparse
import struct
import zlib
from pathlib import Path


WIDTH = 400
HEIGHT = 200


def _chunk(kind, payload):
    body = kind + payload
    return (struct.pack(">I", len(payload)) + body
            + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))


def make_png():
    rows = []
    for y in range(HEIGHT):
        row = bytearray([0])  # PNG filter: none
        for x in range(WIDTH):
            nx = (x - WIDTH / 2) / (WIDTH * 0.44)
            ny = (y - HEIGHT / 2) / (HEIGHT * 0.42)
            inside = nx * nx + ny * ny <= 1
            if inside:
                # Uneven internal detail makes focal cropping visible.
                if (x - 285) ** 2 + (y - 72) ** 2 < 28 ** 2:
                    rgba = (255, 224, 40, 255)
                else:
                    rgba = (230, 25, 120, 255)
            else:
                rgba = (0, 0, 0, 0)
            row.extend(rgba)
        rows.append(bytes(row))

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 6, 0, 0, 0)
    # 100 ppi, matching Scribus' default missing-resolution assumption while
    # making that source-scale input explicit and repeatable.
    phys = struct.pack(">IIB", 3937, 3937, 1)
    return (signature + _chunk(b"IHDR", ihdr) + _chunk(b"pHYs", phys)
            + _chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
            + _chunk(b"IEND", b""))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out", nargs="?", default="transparent-source.png")
    args = parser.parse_args()
    Path(args.out).write_bytes(make_png())


if __name__ == "__main__":
    main()
