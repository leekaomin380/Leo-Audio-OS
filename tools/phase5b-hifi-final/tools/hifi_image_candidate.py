#!/usr/bin/env python3
import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import struct
import importlib.util
from pathlib import Path

TARGET_HAL = "/system/vendor/lib/hw/audio.primary.msm8994.so"
EXPECTED_SOURCE_HASH = "7238ee916246f6ac4564d7386639494323bae01b67eb8bed6b0168b2d47689c3"

def fail(msg):
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()

def extract_inode_fields(fs, inode_num):
    inode_bytes = fs.read_inode(inode_num)
    if len(inode_bytes) < 256:
        fail(f"Inode {inode_num} size < 256")
    fields = {
        "mode": struct.unpack_from("<H", inode_bytes, 0)[0],
        "uid_lo": struct.unpack_from("<H", inode_bytes, 2)[0],
        "size_lo": struct.unpack_from("<I", inode_bytes, 4)[0],
        "atime": struct.unpack_from("<I", inode_bytes, 8)[0],
        "ctime": struct.unpack_from("<I", inode_bytes, 12)[0],
        "mtime": struct.unpack_from("<I", inode_bytes, 16)[0],
        "dtime": struct.unpack_from("<I", inode_bytes, 20)[0],
        "gid_lo": struct.unpack_from("<H", inode_bytes, 24)[0],
        "links_count": struct.unpack_from("<H", inode_bytes, 26)[0],
        "flags": struct.unpack_from("<I", inode_bytes, 32)[0],
        "generation": struct.unpack_from("<I", inode_bytes, 100)[0],
        "size_hi": struct.unpack_from("<I", inode_bytes, 108)[0],
        "uid_hi": struct.unpack_from("<H", inode_bytes, 120)[0],
        "gid_hi": struct.unpack_from("<H", inode_bytes, 122)[0],
        "extra_isize": struct.unpack_from("<H", inode_bytes, 128)[0],
        "ctime_extra": struct.unpack_from("<I", inode_bytes, 132)[0],
        "mtime_extra": struct.unpack_from("<I", inode_bytes, 136)[0],
        "atime_extra": struct.unpack_from("<I", inode_bytes, 140)[0],
        "crtime": struct.unpack_from("<I", inode_bytes, 144)[0],
        "crtime_extra": struct.unpack_from("<I", inode_bytes, 148)[0],
    }
    xattrs = fs.xattrs(inode_bytes)
    return fields, xattrs

def filesystem_identity(path):
    with open(path, "rb") as f:
        f.seek(1024); sb = f.read(1024)
    return {"raw_size": path.stat().st_size,
            "inode_count": struct.unpack_from("<I", sb, 0)[0],
            "block_count": struct.unpack_from("<I", sb, 4)[0],
            "block_size": 1024 << struct.unpack_from("<I", sb, 24)[0],
            "inode_size": struct.unpack_from("<H", sb, 88)[0],
            "features": sb[92:104].hex(), "uuid": sb[104:120].hex(),
            "label": sb[120:136].hex(), "hash_seed": sb[236:252].hex()}

def require_plain_file(path):
    if str(path.absolute()).startswith("/dev/"):
        fail("source/input cannot be a device path")
    if not path.is_file() or any(p.is_symlink() for p in [path, *path.parents]):
        fail(f"{path} must be a regular file without symlink ancestors")

def compare_entries(before, after):
    old = {e["path_utf8"]: e for e in before}
    new = {e["path_utf8"]: e for e in after}
    if len(old) != len(before) or len(new) != len(after) or old.keys() != new.keys():
        fail("Filesystem paths differ or duplicate paths")
    for path, entry in old.items():
        a, b = dict(entry), dict(new[path])
        if path == TARGET_HAL:
            for k in ("inode", "size", "content_sha256"):
                a.pop(k, None); b.pop(k, None)
        if a != b:
            fail(f"Filesystem semantic/content difference outside allowlist: {path}")

def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--collector", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--payload", type=Path)
    parser.add_argument("--payload-sha256")
    parser.add_argument("--builder-image", required=True)
    args = parser.parse_args(argv)

    if args.source_sha256 != EXPECTED_SOURCE_HASH:
        fail(f"source-sha256 must be exactly {EXPECTED_SOURCE_HASH}")

    for p in [args.source, args.collector]:
        require_plain_file(p)
    if args.payload:
        require_plain_file(args.payload)
        if not args.payload_sha256 or sha256_file(args.payload) != args.payload_sha256:
            fail("Payload hash missing or mismatch")
    elif args.payload_sha256:
        fail("payload-sha256 requires payload")
    if not args.builder_image.startswith("sha256:") or len(args.builder_image) != 71:
        fail("builder-image must be a frozen local sha256 image ID")
    if args.output.exists() or args.output.is_symlink():
        fail(f"output directory {args.output} already exists")
    if any(p.is_symlink() for p in args.output.parents):
        fail("output has symlink ancestor")
    if sha256_file(args.source) != EXPECTED_SOURCE_HASH:
        fail("Source hash mismatch")
    original_identity = filesystem_identity(args.source)

    output_img = args.output / "image.img"
    if args.source.resolve() == output_img.resolve():
        fail("output alias of source")

    existing_parent = args.output.parent
    while not existing_parent.exists():
        existing_parent = existing_parent.parent
    st = os.statvfs(existing_parent)
    src_size = args.source.stat().st_size
    req_space = src_size + 10 * 1024**3
    if (st.f_bavail * st.f_frsize) < req_space:
        fail("Insufficient disk space, need 10GiB headroom + full copy size")
        
    args.output.mkdir(parents=True, exist_ok=False)
    report_dir = args.output / "report"
    report_dir.mkdir()
    
    try:
        subprocess.run(["cp", "-c", str(args.source), str(output_img)], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        with open(args.source, "rb") as fsrc, open(output_img, "wb") as fdst:
            while chunk := fsrc.read(4 * 1024 * 1024):
                fdst.write(chunk)

    if sha256_file(output_img) != EXPECTED_SOURCE_HASH:
        fail("Copied image hash mismatch")

    spec = importlib.util.spec_from_file_location("collector", args.collector)
    collector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(collector)
    
    fs_orig = collector.Ext4(args.source)
    orig_collector_out = report_dir / "orig"
    subprocess.run([sys.executable, str(args.collector), "--raw", str(args.source), "--output", str(orig_collector_out)], check=True)
    
    with open(orig_collector_out / "entries.jsonl") as f:
        orig_entries = [json.loads(line) for line in f]
    with open(orig_collector_out / "audit-summary.json") as f:
        orig_summary = json.load(f)

    hal_orig_entry = None
    orig_inode_map = {}
    for entry in orig_entries:
        if entry["path_utf8"] == TARGET_HAL:
            hal_orig_entry = entry
        orig_inode_map[entry["path_utf8"]] = entry["inode"]
        
    if not hal_orig_entry:
        fail("Target HAL not found in source image")
    if hal_orig_entry["type"] != "regular" or hal_orig_entry["nlink"] != 1:
        fail("Target HAL is not a regular file or nlink != 1")

    hal_inode_num = hal_orig_entry["inode"]
    hal_orig_fields, hal_orig_xattrs = extract_inode_fields(fs_orig, hal_inode_num)
    
    orig_full_metadata = {}
    for path, ino in orig_inode_map.items():
        fields, xattrs = extract_inode_fields(fs_orig, ino)
        orig_full_metadata[path] = {"fields": fields, "xattrs": xattrs}
    fs_orig.close()
    
    block_size = orig_summary["filesystem"]["block_size"]
    
    if args.payload:
        payload_size = args.payload.stat().st_size
        with open(args.source, "rb") as f:
            f.seek(1024 + 12)
            free_blocks = struct.unpack("<I", f.read(4))[0]
        if payload_size > free_blocks * block_size:
            fail("Payload too large for free blocks")
        
        payload_hash = sha256_file(args.payload)
        if args.payload_sha256 and payload_hash != args.payload_sha256:
            fail("Payload hash mismatch")
            
        if payload_hash != hal_orig_entry["content_sha256"]:
            input_mount = report_dir / "input"
            input_mount.mkdir()
            shutil.copy(args.payload, input_mount / "payload.so")
            
            script_lines = [
                f"rm {TARGET_HAL}",
                f"write /input/payload.so {TARGET_HAL}"
            ]
            
            for idx, (key, val_bytes) in enumerate(sorted(hal_orig_xattrs.items())):
                if any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for c in key):
                    fail("Unexpected xattr name")
                xattr_bin = input_mount / f"xattr-{idx}.bin"
                xattr_bin.write_bytes(val_bytes)
                script_lines.append(f"ea_set -f /input/xattr-{idx}.bin {TARGET_HAL} {key}")
                
            for k in ["mode", "uid_lo", "gid_lo", "uid_hi", "gid_hi", "atime_extra", "ctime_extra", "mtime_extra", "crtime_extra", "links_count", "generation", "extra_isize", "flags"]:
                script_lines.append(f"sif {TARGET_HAL} {k} {hal_orig_fields[k]}")
            for k in ["atime", "ctime", "mtime", "crtime"]:
                script_lines.append(f"sif {TARGET_HAL} {k} @{hal_orig_fields[k]}")

            script_path = input_mount / "debugfs_script.txt"
            script_path.write_text("\n".join(script_lines) + "\n")
            
            docker_cmd = [
                "docker", "run", "--rm", "--entrypoint", "/bin/sh",
                "--pull", "never",
                "--network", "none",
                "--read-only",
                "--cap-drop", "ALL",
                "--memory", "512m",
                "--tmpfs", "/tmp:rw,size=64m",
                "-v", f"{input_mount.resolve()}:/input:ro",
                "-v", f"{args.output.resolve()}:/output:rw",
                "-e", "E2FSPROGS_FAKE_TIME=1230768000",
                args.builder_image,
                "-c",
                "/opt/e2fsprogs/sbin/debugfs -w -f /input/debugfs_script.txt /output/image.img"
            ]
            (report_dir / "debugfs-command.json").write_text(json.dumps(docker_cmd, indent=2))
            res = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=180)
            (report_dir / "debugfs.log").write_text(res.stdout + res.stderr)
            if res.returncode != 0 or "fail" in res.stderr.lower() or "error" in res.stderr.lower() or "not found" in res.stderr.lower():
                fail(f"debugfs failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}")

    docker_fsck = [
        "docker", "run", "--rm", "--entrypoint", "/bin/sh",
        "--pull", "never",
        "--network", "none",
        "--read-only",
        "--cap-drop", "ALL",
        "--memory", "512m",
        "--tmpfs", "/tmp:rw,size=64m",
        "-v", f"{args.output.resolve()}:/output:rw",
        args.builder_image,
        "-c",
        "/opt/e2fsprogs/sbin/e2fsck -f -n /output/image.img"
    ]
    docker_fsck = [v.replace(":/output:rw", ":/output:ro") for v in docker_fsck]
    (report_dir / "fsck-command.json").write_text(json.dumps(docker_fsck, indent=2))
    res_fsck = subprocess.run(docker_fsck, capture_output=True, text=True, timeout=180)
    (report_dir / "e2fsck.log").write_text(res_fsck.stdout + res_fsck.stderr)
    (report_dir / "e2fsck.exit").write_text(str(res_fsck.returncode))
    if res_fsck.returncode != 0:
        fail(f"e2fsck failed:\nSTDOUT:\n{res_fsck.stdout}\nSTDERR:\n{res_fsck.stderr}")
        
    new_collector_out = report_dir / "new"
    subprocess.run([sys.executable, str(args.collector), "--raw", str(output_img), "--output", str(new_collector_out)], check=True)
    
    with open(new_collector_out / "entries.jsonl") as f:
        new_entries = [json.loads(line) for line in f]
    with open(new_collector_out / "audit-summary.json") as f:
        new_summary = json.load(f)
        
    if filesystem_identity(output_img) != original_identity:
        fail("Filesystem identity changed")
    compare_entries(orig_entries, new_entries)
    for k in ["block_size", "inode_count", "uuid"]:
        if orig_summary["filesystem"][k] != new_summary["filesystem"][k]:
            fail(f"Filesystem {k} changed")
    
    new_inode_map = {e["path_utf8"]: e["inode"] for e in new_entries}
    if set(orig_inode_map.keys()) != set(new_inode_map.keys()):
        fail("Filesystem tree structure changed (paths added/removed)")
        
    fs_new = collector.Ext4(output_img)
    try:
        for path in orig_inode_map:
            orig_e = orig_full_metadata[path]
            new_ino = new_inode_map[path]
            new_f, new_x = extract_inode_fields(fs_new, new_ino)
            
            if path == TARGET_HAL:
                if orig_e["xattrs"] != new_x:
                    fail("Target HAL xattrs mismatch")
                for k in orig_e["fields"]:
                    if k in ("size_lo", "size_hi"): continue
                    if orig_e["fields"][k] != new_f[k]:
                        fail(f"Target HAL field {k} mismatch: {orig_e['fields'][k]} vs {new_f[k]}")
            else:
                if orig_inode_map[path] != new_ino:
                    fail(f"Inode number changed for non-target path {path}")
                if orig_e["fields"] != new_f:
                    fail(f"Metadata changed for non-target path {path}")
                if orig_e["xattrs"] != new_x:
                    fail(f"Xattrs changed for non-target path {path}")
    finally:
        fs_new.close()
        
    if sha256_file(args.source) != EXPECTED_SOURCE_HASH:
        fail("Original source changed during execution")
    candidate_hash = sha256_file(output_img)
    changed_payload = bool(args.payload and payload_hash != hal_orig_entry["content_sha256"])
    if not changed_payload and candidate_hash != EXPECTED_SOURCE_HASH:
        fail("No-op copy is not byte identical")
    final = {"status": "ARTIFACT_VALIDATED_NOT_DEPLOYED" if changed_payload else "NO_OP_ONLY",
             "source_sha256": EXPECTED_SOURCE_HASH, "candidate_sha256": candidate_hash,
             "payload_sha256": payload_hash if args.payload else None,
             "collector_sha256": sha256_file(args.collector), "builder_image": args.builder_image,
             "filesystem": original_identity, "verified_paths": len(orig_entries),
             "allowlist": [TARGET_HAL], "e2fsck_exit": 0, "source_unchanged": True,
             "device_authorized": False}
    if args.payload and payload_hash != hal_orig_entry["content_sha256"]:
        hal_new_entry = next(e for e in new_entries if e["path_utf8"] == TARGET_HAL)
        if hal_new_entry["content_sha256"] != payload_hash:
            fail("Payload hash mismatch after write")
        print("ARTIFACT_VALIDATED_NOT_DEPLOYED")
        print("SystemUI/Settings/boot unchanged, no device operations granted.")
    else:
        print("NO_OP_ONLY")
        print("SystemUI/Settings/boot unchanged, no device operations granted.")
    (report_dir / "result.json").write_text(json.dumps(final, indent=2) + "\n")

if __name__ == "__main__":
    main()
