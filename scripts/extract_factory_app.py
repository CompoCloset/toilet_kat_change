#!/usr/bin/env python3
"""Extract factory app, bootloader, and partition table from a merged flash image."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from ota_partition_report import detect_software_version  # noqa: E402

FACTORY_OFFSET = 0x10000
FACTORY_SIZE = 0x480000
BOOTLOADER_OFFSET = 0x0
BOOTLOADER_SIZE = 19984
PARTITION_OFFSET = 0x8000
PARTITION_SIZE = 0xC00
ESP_IMAGE_MAGIC = 0xE9


def extract_region(data: bytes, offset: int, size: int) -> bytes:
    end = offset + size
    if len(data) < end:
        raise ValueError(f"Image too small for region @0x{offset:X} size 0x{size:X}")
    return data[offset:end]


_VERSION_RE = re.compile(r"\d+\.\d+\.\d+(?:\.\d+)?(?:-[A-Za-z0-9]+)?")


def detect_factory_version(app_data: bytes) -> str | None:
    """Read the software version embedded in a factory app image.

    esp_app_desc on SARAH is a git hash. The readable version is the
    three-part SOFTWARE_VERSION_NUMBER literal, for example 3.0.0.
    """
    detected = detect_software_version(app_data)
    if _VERSION_RE.fullmatch(detected or ""):
        return detected
    return None


def validate_app_image(app_data: bytes) -> None:
    if not app_data or app_data[0] != ESP_IMAGE_MAGIC:
        raise ValueError("Factory app region does not look like a valid ESP image (missing 0xE9 magic)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract SARAH/factory regions from merged flash image")
    parser.add_argument("merged_image", type=Path, help="Path to *.merged.bin")
    parser.add_argument("--out-dir", type=Path, required=True, help="Output directory for extracted bins")
    parser.add_argument("--label", default="sarah", help="Output filename prefix")
    args = parser.parse_args()

    if not args.merged_image.exists():
        raise SystemExit(f"Merged image not found: {args.merged_image}")

    data = args.merged_image.read_bytes()
    app_data = extract_region(data, FACTORY_OFFSET, FACTORY_SIZE)
    validate_app_image(app_data)

    bootloader = extract_region(data, BOOTLOADER_OFFSET, BOOTLOADER_SIZE)
    partitions = extract_region(data, PARTITION_OFFSET, PARTITION_SIZE)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    app_path = args.out_dir / f"{args.label}_factory_app.bin"
    boot_path = args.out_dir / f"{args.label}_bootloader.bin"
    part_path = args.out_dir / f"{args.label}_partitions.bin"
    app_path.write_bytes(app_data)
    boot_path.write_bytes(bootloader)
    part_path.write_bytes(partitions)

    detected_version = detect_factory_version(app_data)

    print(f"Wrote factory app ({len(app_data)} bytes) -> {app_path}")
    print(f"Wrote bootloader ({len(bootloader)} bytes) -> {boot_path}")
    print(f"Wrote partitions ({len(partitions)} bytes) -> {part_path}")
    if detected_version:
        print(f"Detected version string: {detected_version}")
    else:
        print("WARN: Could not detect version string in factory app image")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
