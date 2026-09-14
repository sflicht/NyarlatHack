"""Control reseeding only in linked test binaries; preserve native RNG code."""

import hashlib
import signal
import subprocess


def controlled_rng_objects(objects, artifacts):
    originals = [obj for obj in objects if obj.name == "rnd.o"]
    assert len(originals) == 1, originals
    original = originals[0]
    digest = hashlib.sha256(original.read_bytes()).digest()
    controlled = artifacts / "rnd-controlled.o"
    subprocess.run(
        [
            "objcopy",
            "--globalize-symbol=reseed_period",
            "--globalize-symbol=reseed_count",
            str(original),
            str(controlled),
        ],
        check=True,
    )
    assert hashlib.sha256(original.read_bytes()).digest() == digest
    symbols = subprocess.check_output(["nm", str(controlled)], text=True)
    for name in ("reseed_period", "reseed_count"):
        assert any(line.split()[1:] == ["B", name] for line in symbols.splitlines())
    (artifacts / "rng-symbols.txt").write_text(symbols)
    return [controlled if obj == original else obj for obj in objects]


def verify_native_fixture(test, exe, artifacts, naming_cases=()):
    def run(args, log):
        result = subprocess.run(
            [str(exe), *args], capture_output=True, text=True, timeout=15
        )
        (artifacts / log).write_text(result.stdout + result.stderr)
        return result

    # Deliberate actual draws must fail the same oracle used by the positive tests.
    for mode, assertion in (
        ("--rng-negative-control", "reseed_count == 0"),
        ("--raw-rng-negative-control", "rn2(100000) == expected"),
    ):
        result = run([mode], mode[2:] + ".txt")
        test.assertEqual(result.returncode, -signal.SIGABRT, result.stderr)
        test.assertIn(assertion, result.stderr)
    for case in naming_cases:
        with test.subTest(naming=case):
            result = run([case], case + ".txt")
            test.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    # Bounded repetition after the controls, never retry-until-green.
    for repetition in range(10):
        result = run([], f"native-{repetition:02d}.txt")
        test.assertEqual(result.returncode, 0, result.stdout + result.stderr)
