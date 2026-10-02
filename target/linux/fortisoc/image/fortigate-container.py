#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build the TFTP image the FortiGate boot loader runs from RAM.

On a TFTP boot to RAM (boot menu option [R]), the boot loader of the
FortiSOC based FortiGate appliances does not take a bare kernel: it wants a
gzip-compressed firmware container,

    image = gzip(header + ext2 partition 0)

whose ext2 holds the "flatkc" file it runs. The header is LBA x 512 bytes
long, LBA being the start of partition 0 (256 on the 60C, 1 on the 60D).

Default mode (--model): the container is written from scratch and holds no
vendor bytes. Header, all zero but for:

    0x06   model byte (60C 0x0d, 60D 0x0f)
    0x0c   tag, u32 LE 0x55aae517
    0x10   ASCII label ("FGT" + model + "-fortiwrt", model in capitals)
    0x1be  partition table: entry 0 = active (0x80), type 0x83, LBA, sectors
    0x1fe  55 aa

Partition 0: a new ext2 (revision 1, 1 KiB blocks, 128-byte inodes,
ext_attr resize_inode dir_index filetype sparse_super) of the size of the
stock one (60C 80128 sectors, 60D 524288 sectors), holding the layout the
boot loader expects: "flatkc" -> "./flatkc.nosmp" (our kernel), an empty
gzip stream as "rootfs.gz" (loaded, then ignored by a kernel built with
CONFIG_INITRAMFS_FORCE), and "flatkc.chk", "rootfs.gz.chk" of 256 zero
bytes (not checked by the boot loader). This layout has been booted on a
FortiGate 60D; with "flatkc" alone, the boot loader fails to open the root
file system. The output is reproducible (fixed dates, UUID, hash seed).

Fallback mode (--base FILE): start from a base container the user extracts
himself from a firmware image of his own appliance, and replace its kernel
file in place with debugfs. Such an image holds vendor bytes: it must stay
on the machine that built it.

Usage:
    fortigate-container.py --model 60d --flatkc FLATKC --output IMAGE
    fortigate-container.py --base FILE --flatkc FLATKC --output IMAGE
"""

import argparse
import gzip
import io
import os
import shutil
import struct
import subprocess
import sys
import tempfile

TABLE = 0x1BE
TAG = 0x55AAE517
CHK_LEN = 256
EPOCH = 1735689600
HASH_SEED = "66727469-7772-7400-0000-000000000309"
MODELS = {
    "60c": dict(lba=256, nsect=80128, model_byte=0x0D),
    "60d": dict(lba=1, nsect=524288, model_byte=0x0F),
}


def model_name(model: str) -> str:
    """Name of the model in the container: "FGT" + model in capitals."""
    return "FGT" + model.upper()


def tool(name: str) -> str:
    path = os.environ.get("PATH", "") + os.pathsep + "/usr/sbin" + os.pathsep + "/sbin"
    found = shutil.which(name, path=path)
    if found is None:
        sys.exit("%s not found (e2fsprogs)" % name)
    return found


def run(cmd, env=None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


# --- synthetic container ---------------------------------------------------

def synth_header(model: dict, label: str) -> bytes:
    hdr = bytearray(model["lba"] * 512)
    hdr[0x06] = model["model_byte"]
    struct.pack_into("<I", hdr, 0x0C, TAG)
    lab = label.encode("ascii")
    if len(lab) >= 0x40:
        sys.exit("label too long (%d bytes, 63 at most)" % len(lab))
    hdr[0x10:0x10 + len(lab)] = lab
    hdr[TABLE] = 0x80
    hdr[TABLE + 4] = 0x83
    struct.pack_into("<II", hdr, TABLE + 8, model["lba"], model["nsect"])
    hdr[0x1FE:0x200] = b"\x55\xaa"
    return bytes(hdr)


def synth_ext2(workdir: str, size: int, flatkc: str) -> bytes:
    root = os.path.join(workdir, "root")
    os.mkdir(root)
    shutil.copyfile(flatkc, os.path.join(root, "flatkc.nosmp"))
    os.symlink("./flatkc.nosmp", os.path.join(root, "flatkc"))
    with open(os.path.join(root, "rootfs.gz"), "wb") as f:
        f.write(gzip.compress(b"", mtime=0))
    for name in ("flatkc.chk", "rootfs.gz.chk"):
        with open(os.path.join(root, name), "wb") as f:
            f.write(bytes(CHK_LEN))
    names = ["flatkc.nosmp", "flatkc", "rootfs.gz", "flatkc.chk", "rootfs.gz.chk"]
    for name in names:
        os.utime(os.path.join(root, name), (EPOCH, EPOCH), follow_symlinks=False)
    os.utime(root, (EPOCH, EPOCH))

    part = os.path.join(workdir, "part.img")
    with open(part, "wb") as f:
        f.truncate(size)
    env = dict(os.environ, E2FSPROGS_FAKE_TIME=str(EPOCH))
    r = run([tool("mke2fs"), "-q", "-F", "-t", "ext2", "-r", "1", "-b", "1024",
             "-I", "128", "-i", "4096", "-m", "5",
             "-O", "none,ext_attr,resize_inode,dir_index,filetype,sparse_super",
             "-U", "clear", "-E", "root_owner=0:0,hash_seed=" + HASH_SEED,
             "-d", root, part], env)
    if r.returncode != 0:
        sys.exit("mke2fs failed:\n" + r.stdout + r.stderr)

    # root:root (mke2fs -d copies the uid of the caller) and fixed dates
    cmds = os.path.join(workdir, "cmds")
    with open(cmds, "w") as f:
        for name in names:
            f.write("sif /%s uid 0\nsif /%s gid 0\n" % (name, name))
            for field in ("atime", "mtime", "ctime"):
                f.write("sif /%s %s @%d\n" % (name, field, EPOCH))
    r = run([tool("debugfs"), "-w", "-f", cmds, part], env)
    if r.returncode != 0:
        sys.exit("debugfs failed:\n" + r.stdout + r.stderr)
    r = run([tool("e2fsck"), "-fn", part])
    if r.returncode != 0:
        sys.exit("e2fsck reports a broken ext2:\n" + r.stdout + r.stderr)

    # Read the kernel back
    back = os.path.join(workdir, "flatkc.back")
    r = run([tool("debugfs"), "-R", "dump /flatkc.nosmp %s" % back, part])
    with open(back, "rb") as a, open(flatkc, "rb") as b:
        if a.read() != b.read():
            sys.exit("read back: the kernel in the ext2 differs from %s" % flatkc)

    with open(part, "rb") as f:
        return f.read()


def build_synthetic(args, workdir: str) -> tuple:
    model = MODELS[args.model]
    name = model_name(args.model)
    label = args.label or name + "-fortiwrt"
    part = synth_ext2(workdir, model["nsect"] * 512, args.flatkc)
    return synth_header(model, label) + part, args.name or name


# --- base container (fallback) ---------------------------------------------

def part0_offset(raw: bytes) -> int:
    if raw[0x1FE:0x200] != b"\x55\xaa":
        sys.exit("base container: no partition table (no 55aa at 0x1fe)")
    lba, nsect = struct.unpack_from("<II", raw, TABLE + 8)
    if raw[TABLE + 4] != 0x83 or lba == 0 or nsect == 0:
        sys.exit("base container: bad partition 0 (type %#x, LBA %d, %d sectors)"
                 % (raw[TABLE + 4], lba, nsect))
    return lba * 512


def build_from_base(args, workdir: str) -> tuple:
    with open(args.base, "rb") as f:
        raw = f.read()
    offset = part0_offset(raw)
    if raw[offset + 0x438:offset + 0x43A] != b"\x53\xef":
        sys.exit("base container: no ext2 at %#x" % offset)
    name = args.name
    if name is None:
        label = raw[0x10:0x50].split(b"\0")[0].decode("ascii", "replace")
        if not label.startswith("FGT"):
            sys.exit("base container: unexpected label, give --name")
        name = label.split("-")[0]

    part = os.path.join(workdir, "part.img")
    with open(part, "wb") as f:
        f.write(raw[offset:])
    cmds = os.path.join(workdir, "cmds")
    with open(cmds, "w") as f:
        f.write("rm /flatkc.nosmp\n")
        f.write("write %s flatkc.nosmp\n" % os.path.abspath(args.flatkc))
    r = run([tool("debugfs"), "-w", "-f", cmds, part])
    if r.returncode != 0 or "Allocated inode" not in r.stdout:
        sys.exit("debugfs failed:\n" + r.stdout + r.stderr)
    r = run([tool("e2fsck"), "-fn", part])
    if r.returncode not in (0, 1):
        sys.exit("e2fsck reports a broken ext2:\n" + r.stdout + r.stderr)
    with open(part, "rb") as f:
        new_part = f.read()
    if len(new_part) != len(raw) - offset:
        sys.exit("partition size changed: the kernel does not fit in the ext2")
    return raw[:offset] + new_part, name


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--model", choices=sorted(MODELS),
                      help="write a synthetic container for this appliance")
    mode.add_argument("--base", help="fallback: base container (local file, "
                      "never distributed)")
    ap.add_argument("--flatkc", required=True, help="flatkc to put in the container")
    ap.add_argument("--output", required=True, help="TFTP image to write")
    ap.add_argument("--label", help="label at 0x10 (default FGT<model>-fortiwrt)")
    ap.add_argument("--name", help="name of the gzip member (default FGT<model>)")
    ap.add_argument("--level", type=int, default=6, help="gzip level (default 6)")
    args = ap.parse_args()

    outdir = os.path.dirname(os.path.abspath(args.output))
    with tempfile.TemporaryDirectory(dir=outdir) as td:
        if args.model:
            body, name = build_synthetic(args, td)
        else:
            body, name = build_from_base(args, td)

    buf = io.BytesIO()
    with gzip.GzipFile(filename=name, mode="wb", fileobj=buf,
                       compresslevel=args.level, mtime=0) as gz:
        gz.write(body)
    with open(args.output, "wb") as f:
        f.write(buf.getvalue())
    print("%s: %d bytes (%s container %d bytes, flatkc %d bytes)"
          % (args.output, buf.tell(), "synthetic" if args.model else "base",
             len(body), os.path.getsize(args.flatkc)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
