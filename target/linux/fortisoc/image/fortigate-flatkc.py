#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Wrap a kernel into the "flatkc" format of the FortiGate boot loader.

The boot loader of the FortiSOC based FortiGate appliances (60C, 60D) runs
a file named "flatkc" made of a 512-byte header followed by a gzip stream,
which it inflates and jumps to. Header layout (little endian):

    0x000  55 AA AA 55   magic
    0x004  0x000000ce    constant
    0x008  0x00000200    offset of the payload
    0x00c  tag           read by the boot menu on a TFTP boot (0x55aa____);
                         its third byte (0xaa) is the OS code
    0x030  0x00100000    load address
    0x058  length        of the command line, terminator included
    0x05c  command line  ASCII, terminated by "\\n\\0"
    0x200  payload       gzip stream (FNAME "fortikernel.out", XFL 4, OS 3)

The payload here is a zImage with its device tree appended: it relocates
and inflates itself. The command line of the header is ignored by a kernel
built with CONFIG_CMDLINE_FORCE, which these images are.

Usage: fortigate-flatkc.py [--cmdline STR] [--tag N] input output
"""

import argparse
import gzip
import io
import struct
import sys

HDR_LEN = 0x200
MAGIC = bytes.fromhex("55aaaa55")
GZIP_NAME = "fortikernel.out"
DEFAULT_TAG = 0x55AAE517
DEFAULT_CMDLINE = "console=ttyS0,9600n8"


def build_header(cmdline: str, tag: int) -> bytes:
    hdr = bytearray(HDR_LEN)
    hdr[0x00:0x04] = MAGIC
    struct.pack_into("<I", hdr, 0x04, 0xCE)
    struct.pack_into("<I", hdr, 0x08, HDR_LEN)
    struct.pack_into("<I", hdr, 0x0C, tag)
    struct.pack_into("<I", hdr, 0x30, 0x00100000)
    line = cmdline.encode("ascii") + b"\n\0"
    if len(line) > HDR_LEN - 0x5C:
        sys.exit("command line too long (%d bytes)" % len(line))
    struct.pack_into("<I", hdr, 0x58, len(line))
    hdr[0x5C:0x5C + len(line)] = line
    return bytes(hdr)


def gzip_payload(data: bytes) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(filename=GZIP_NAME, mode="wb", fileobj=buf,
                       compresslevel=9, mtime=0) as gz:
        gz.write(data)
    out = bytearray(buf.getvalue())
    out[8] = 0x04   # XFL: maximum compression
    out[9] = 0x03   # OS: Unix
    return bytes(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="kernel to wrap (zImage with appended DTB)")
    ap.add_argument("output", help="flatkc file to write")
    ap.add_argument("--cmdline", default=DEFAULT_CMDLINE,
                    help="command line stored in the header")
    ap.add_argument("--tag", type=lambda x: int(x, 0), default=DEFAULT_TAG,
                    help="32-bit tag at 0x0c (default %#x)" % DEFAULT_TAG)
    args = ap.parse_args()

    with open(args.input, "rb") as f:
        raw = f.read()
    body = gzip_payload(raw)
    with open(args.output, "wb") as f:
        f.write(build_header(args.cmdline, args.tag))
        f.write(body)
    print("%s: %d bytes (header %d + gzip %d, kernel %d)"
          % (args.output, HDR_LEN + len(body), HDR_LEN, len(body), len(raw)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
