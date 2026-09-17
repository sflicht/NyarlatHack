#!/usr/bin/env python3
"""Official local/Actions native suite entry point, after trusted preparation.

No build, provider, inferred revision, log-status parser or retries. The unittest
process exit status is the result. Descriptors and diagnostics are never reused.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

if not __debug__ or sys.flags.optimize or os.environ.get("PYTHONOPTIMIZE"):
    raise RuntimeError("optimized Python is not supported")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests/chaos"))
import native_fixture_config as config  # noqa: E402
from native_fixture_selection import prepare  # noqa: E402


def suite_environment(path, data):
    out = Path(data["build_output"])
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(out / "home"),
        "LANG": "C.UTF-8",
        "TZ": "America/New_York",
        "PKG_CONFIG_LIBDIR": "/usr/lib/x86_64-linux-gnu/pkgconfig:/usr/share/pkgconfig",
        "MAIL": str(out / "MAIL"),
        "TMPDIR": str(out / "fixtures"),
        "PYTHONDONTWRITEBYTECODE": "1",
        config.KEY: str(path),
        # Compatibility bridge for frozen gameplay_support and legacy players.
        "NYARLATHACK_GAME_TESTS": "1",
        "NYARLATHACK_STOCK_DIR": str(out / "stock"),
        "NYARLATHACK_PRECURIO_DIR": str(out / "precurio"),
        "NYARLATHACK_NATIVE_FIXTURE_MODE": "source-build",
        "NYARLATHACK_NATIVE_BUILD_RECEIPT": data["receipt"],
        config.REVISION_KEY: data["revision"],
    }
    if data["profile"] == "selected-turnloop":
        env["NYARLATHACK_TURNLOOP_EVIDENCE"] = str(
            Path(data["artifact_parent"]) / "turnloop"
        )
        for key, value in data["historical_stock"].items():
            env["NYARLATHACK_TURNLOOP_STOCK_" + key.upper()] = value
    return env


def run_unittest(root, env, log, *, start="tests/chaos", pattern="test_*.py"):
    """Run unittest exactly once; output is opaque diagnostic bytes."""
    with os.fdopen(
        os.open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
    ) as stream:
        process = subprocess.run(
            [
                "/usr/bin/python3",
                "-B",
                "-m",
                "unittest",
                "discover",
                "-s",
                start,
                "-p",
                pattern,
                "-v",
            ],
            cwd=root,
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
            umask=0o022,
        )
    # Do not parse, decode or rewrite unittest's output. The retained file is the
    # authoritative diagnostic even if the console cannot display arbitrary bytes.
    print(f"unittest exit={process.returncode}; log={log}", flush=True)
    return process.returncode if process.returncode >= 0 else 128 - process.returncode


def create_descriptor(
    root, expected_revision, build_output, *, profile="core", historical_stock=None
):
    config.revision(expected_revision)
    config.require(
        config.canonical(str(root)) == ROOT, "runner must come from selected checkout"
    )
    out = config.private_directory(build_output)
    config.require(
        not out.is_relative_to(ROOT) and not ROOT.is_relative_to(out),
        "build output and checkout must be disjoint",
    )
    for name in ("fixtures", "home", "system-gcc13"):
        config.private_directory(out / name)
    env = {
        "NYARLATHACK_NATIVE_FIXTURE_MODE": "source-build",
        "NYARLATHACK_NATIVE_BUILD_RECEIPT": str(out / "system-gcc13"),
        config.REVISION_KEY: expected_revision,
    }
    # Existing verification binds actual checkout HEAD, source bytes, tuple,
    # headers/objects and reviewed driver. Drivers retain their own calibration.
    prepare(ROOT, env)
    if profile == "selected-turnloop":
        config.require(
            type(historical_stock) is dict
            and set(historical_stock) == {"tuple", "receipt", "revision"},
            "complete independently selected historical stock required",
        )
        from turnloop_header_bindings import historical_binding

        historical_binding(
            Path(historical_stock["receipt"]),
            Path(historical_stock["tuple"]),
            historical_stock["revision"],
        )
    parent = Path(tempfile.mkdtemp(prefix="full-suite.", dir=out / "fixtures"))
    data = dict(
        schema=1,
        root=str(ROOT),
        revision=expected_revision,
        receipt=str(out / "system-gcc13"),
        build_output=str(out),
        artifact_parent=str(parent),
        profile=profile,
        historical_stock=historical_stock,
    )
    path = parent / "descriptor.json"
    with os.fdopen(
        os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
    ) as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")
    config.load(path, ROOT, expected_revision)
    env = suite_environment(path, data)
    for name in config.FAMILIES:
        config.family(name, ROOT, env)
    return path, data, env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("--build-output", required=True)
    parser.add_argument(
        "--profile", choices=("core", "selected-turnloop"), default="core"
    )
    for key in ("tuple", "receipt", "revision"):
        parser.add_argument("--historical-stock-" + key)
    args = parser.parse_args()
    stock = {
        k: getattr(args, "historical_stock_" + k)
        for k in ("tuple", "receipt", "revision")
    }
    if not any(v is not None for v in stock.values()):
        stock = None
    config.require(
        (args.profile == "core" and stock is None)
        or (
            args.profile == "selected-turnloop"
            and stock is not None
            and all(stock.values())
        ),
        "profile and historical-stock selection must be complete",
    )
    path, data, env = create_descriptor(
        args.root,
        args.expected_revision,
        args.build_output,
        profile=args.profile,
        historical_stock=stock,
    )
    return run_unittest(ROOT, env, path.parent / "full-suite.log")


if __name__ == "__main__":
    sys.exit(main())
