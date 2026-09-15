"""Linked native financial exclusion and non-vacuous ordinary controls."""

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
class CurioShopTests(unittest.TestCase):
    def test_native_shop(self):
        artifacts = Path(
            os.environ.get("CURIO_SHOP_ARTIFACTS")
            or tempfile.mkdtemp(prefix="nyarl-curio-shop-")
        )
        artifacts.mkdir(parents=True, exist_ok=True)
        print("CURIO_SHOP_ARTIFACTS=" + str(artifacts), flush=True)
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
        original = ROOT / "src/shk.o"
        exposed = artifacts / "shk.o"
        subprocess.run(
            [
                "objcopy",
                "--globalize-symbol=dopayobj",
                "--globalize-symbol=get_cost",
                "--globalize-symbol=set_cost",
                "--globalize-symbol=addupbill",
                "--globalize-symbol=add_to_billobjs",
                "--globalize-symbol=shop_debt",
                "--globalize-symbol=rob_shop",
                "--globalize-symbol=cheapest_item",
                "--globalize-symbol=inherits",
                "--globalize-symbol=sub_one_frombill",
                str(original),
                str(exposed),
            ],
            check=True,
        )
        objects = [exposed if obj == original else obj for obj in objects]
        original = ROOT / "src/save.o"
        exposed = artifacts / "save.o"
        subprocess.run(
            [
                "objcopy",
                "--globalize-symbol=saveobjchn",
                "--globalize-symbol=savemonchn",
                str(original),
                str(exposed),
            ],
            check=True,
        )
        objects = [exposed if obj == original else obj for obj in objects]
        exe = artifacts / "curio-shop"
        command = [
            "cc",
            "-g",
            "-rdynamic",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wl,--wrap=alloc",
            "-DCHAOS",
            "-isystem",
            str(ROOT / "include"),
            str(ROOT / "tests/chaos/curio_shop.c"),
            *map(str, objects),
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
                "buy",
                "sell",
                "mixed-buy",
                "mixed-sell",
                "tagged-box-buy",
                "tagged-box-sell",
                "theft",
                "use",
                "stale",
                "price",
                "ordinary",
                "mixed-theft",
                "tagged-box-theft",
                "dummy",
                "split",
                "totals",
                "robbery",
                "used-view",
                "destroy",
                "useup",
                "dealloc",
                "pickup-full",
                "pickup-partial",
                "cash",
                "nested-buy",
                "nested-sell",
                "nested-theft",
                "surcharge",
                "pay-command",
                "inheritance",
                "local-retirement",
                "save-release",
                "save-monsters",
                "destroy-container",
                "unpaid-floor-theft",
                "unpaid-nested-theft",
                "coin-shell-theft",
                "aggregate-zero",
                "aggregate-short",
                "aggregate-ample",
                "aggregate-decline",
                "aggregate-credit-decline",
                "aggregate-dontsell",
            ),
        )
