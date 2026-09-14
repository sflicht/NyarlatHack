"""Task 4: actual native inspection with a controlled window port."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from gameplay_support import ROOT
from native_rng import controlled_rng_objects, verify_native_fixture


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class CurioInspectionTests(unittest.TestCase):
    def test_linked_inspection(self):
        artifacts = Path(tempfile.mkdtemp(prefix="nyarl-curio-inspection-"))
        print("CURIO_INSPECTION_ARTIFACTS=" + str(artifacts), flush=True)
        subprocess.run(
            [
                "objcopy",
                "--redefine-sym",
                "main=original_game_main",
                str(ROOT / "sys/unix/unixmain.o"),
                str(artifacts / "unixmain.o"),
            ],
            check=True,
        )
        objects = (
            sorted((ROOT / "src").glob("*.o"))
            + [
                ROOT / "sys/unix/unixres.o",
                ROOT / "sys/unix/unixunix.o",
                artifacts / "unixmain.o",
                ROOT / "sys/share/ioctl.o",
                ROOT / "sys/share/unixtty.o",
            ]
            + sorted((ROOT / "win/tty").glob("*.o"))
            + sorted((ROOT / "win/curses").glob("*.o"))
        )
        objects = controlled_rng_objects(objects, artifacts)
        # Expose native callers only in private copies, not production objects.
        for filename, symbol in (("shk.o", "dopayobj"), ("pickup.o", "lift_object")):
            original = ROOT / "src" / filename
            exposed = artifacts / filename
            subprocess.run(
                [
                    "objcopy",
                    "--globalize-symbol=" + symbol,
                    str(original),
                    str(exposed),
                ],
                check=True,
            )
            objects = [exposed if obj == original else obj for obj in objects]
        exe = artifacts / "curio-inspection"
        command = [
            "cc",
            "-g",
            "-DCHAOS",
            "-I" + str(ROOT / "include"),
            str(ROOT / "tests/chaos/curio_inspection.c"),
            *map(str, objects),
            "-Wl,--wrap=checkfile",
            "-lncursesw",
            "-ltinfo",
            "-lm",
            *subprocess.check_output(
                ["pkg-config", "--libs", "lua5.4"], text=True
            ).split(),
            "-o",
            str(exe),
        ]
        (artifacts / "build-command.txt").write_text(repr(command))
        subprocess.run(command, check=True, timeout=45)
        verify_native_fixture(
            self,
            exe,
            artifacts,
            naming_cases=(
                "corpse-direct",
                "corpse-direct-singular",
                "corpse-cxname",
                "corpse-cxname2",
                "corpse-menu",
                "singular-xname",
                "singular-doname",
                "singular-corpse",
                "singular-corpse-doname",
                "quantity-wrappers",
                "xprname",
                "xprname-text",
                "xprname-controls",
                "shop-quote",
                "shop-decline",
                "shop-refuse-used",
                "shop-poor",
                "shop-paid",
                "lift-prompt",
                "xprname-coin-tag1",
                "xprname-coin-tag2",
                "xprname-coin-tag255",
                "xprname-coin-ordinary",
                "descname-percent",
                "descname-eyes",
                "descname-controls",
                "descname-ordinary",
                "inspect-inventory-where",
                "inspect-context-copy",
                "encyc-percent",
                "encyc-eyes",
                "encyc-controls",
                "encyc-ordinary",
                "finalnames-simple-percent",
                "finalnames-simple-eyes",
                "finalnames-simple-controls",
                "finalnames-simple-ordinary",
                "finalnames-cloak-percent",
                "finalnames-cloak-eyes",
                "finalnames-cloak-controls",
                "finalnames-cloak-ordinary",
                "finalnames-wrappers",
            ),
        )
