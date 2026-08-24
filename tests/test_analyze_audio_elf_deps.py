#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "analyze-audio-elf-deps.py"
SPEC = importlib.util.spec_from_file_location("analyze_audio_elf_deps", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ResolveLibraryTests(unittest.TestCase):
    def test_normalizes_system_absolute_and_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library = root / "lib" / "soundfx" / "libeffect.so"
            library.parent.mkdir(parents=True)
            library.write_bytes(b"\x7fELF\x01")

            for target in (
                "system/lib/soundfx/libeffect.so",
                "/system/lib/soundfx/libeffect.so",
                "lib/soundfx/libeffect.so",
            ):
                self.assertEqual(
                    MODULE.resolve_library(root, "lib/hw/audio.primary.so", target, "elf32"),
                    "lib/soundfx/libeffect.so",
                )

    def test_normalizes_system_vendor_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library = root / "vendor" / "lib" / "libadm.so"
            library.parent.mkdir(parents=True)
            library.write_bytes(b"\x7fELF\x01")

            self.assertEqual(
                MODULE.resolve_library(
                    root,
                    "lib/hw/audio.primary.so",
                    "system/vendor/lib/libadm.so",
                    "elf32",
                ),
                "vendor/lib/libadm.so",
            )

    def test_rejects_wrong_architecture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library = root / "lib" / "libwrong.so"
            library.parent.mkdir(parents=True)
            library.write_bytes(b"\x7fELF\x02")

            self.assertIsNone(
                MODULE.resolve_library(root, "lib/hw/audio.primary.so", "lib/libwrong.so", "elf32")
            )


if __name__ == "__main__":
    unittest.main()
