"""Explicit launcher-fixture selection, not a builder or native acceptance.

Run source mode from gameplay_support.ROOT itself, with a job-selected full
revision and a known trusted local builder receipt directory. Neither receipt
JSON nor a copied working tree chooses the checkout/revision. Stable cooperating
files only: this is not malicious same-UID attestation or a portable ABI claim.
"""

from dataclasses import asdict, dataclass, field
import hashlib
import os
from pathlib import Path
import re
import subprocess

from native_build_calibration import NativeProfile, validate_native_profile
from native_build_identity import SourceBuildInputs, verify_source_build


# Exact historical launcher tuple, including the older bones implementation.
# Never refresh these from current files/receipts or fall back to source mode.
ARCHIVED_HASHES = {
    "dnethack": "2d032ebc8f9773a18927f553a4cc7932e407953735980586a4349536ae55fbc0",
    "nhdat": "b69e9b107ac4aa1a28ac50ab7ea47a5d35a4ed14fb298d0d71859e3519cffc25",
    "license": "93a3ae2cb8dee482daddfaebe53bcffe5b114b603def19b4dca21621cbc5a747",
}
DRIVER_HASH = "9d341b28a4ab3f4453b09e4f49a2e8701a7c78345184f487e2f0b32d70db7270"
# Source mode alone pins the explicitly reviewed EOF/reaping + send-deadline
# helper correction. DRIVER_HASH above remains the frozen historical identity;
# this is not an archive refresh or a substitute for exact-source calibration.
SOURCE_DRIVER_HASH = "4011aaeadd2bb1bab938ccba44b9f1a3e8098db8664b533d3a9277da71620f75"
ORACLE_SOURCES = (
    "tests/chaos/gameplay_support.py",
    "tests/chaos/replay_clock.c",
    "tests/chaos/curio_save_layout.c",
)


class SelectionError(ValueError):
    """Invalid explicit selection or pre-launch identity binding."""


def _require(condition, message):
    if not condition:
        raise SelectionError(message)


def _hash(path):
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise SelectionError(f"unreadable fixture input: {path}") from exc


def _verify_hashes(directory, hashes, label):
    measured = {}
    for name, expected in hashes.items():
        measured[name] = _hash(directory / name)
        _require(measured[name] == expected, f"{label} hash mismatch: {name}")
    return measured


def _committed_sources(root, revision):
    # Fixed paths and full independently validated revision. No receipt commands,
    # shell, text conversion, ambient Git variables or replacement objects.
    env = {
        "PATH": "/usr/bin:/bin",
        "LANG": "C",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_NO_REPLACE_OBJECTS": "1",
    }
    hashes = {}
    for name in ORACLE_SOURCES:
        try:
            result = subprocess.run(
                ["/usr/bin/git", "-C", str(root), "show", revision + ":" + name],
                env=env,
                capture_output=True,
                check=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise SelectionError(
                f"committed oracle source unavailable: {name}"
            ) from exc
        hashes[name] = hashlib.sha256(result.stdout).hexdigest()
        _require(_hash(root / name) == hashes[name], f"oracle source mismatch: {name}")
    _require(
        hashes[ORACLE_SOURCES[0]] == SOURCE_DRIVER_HASH, "reviewed driver pin mismatch"
    )
    return hashes


@dataclass
class FixtureSelection:
    mode: str
    tuple_dir: Path
    artifact_hashes: dict
    compiler: str
    environment: dict | None
    source_inputs: SourceBuildInputs | None = None
    source_hashes: dict = field(default_factory=dict)
    native_profile: NativeProfile | None = None

    def verify_helper_copy(self, directory):
        """Bind copied oracle bytes before compilation; archive only records."""
        directory = Path(directory)
        if self.source_inputs is not None:
            expected = {Path(n).name: h for n, h in self.source_hashes.items()}
            return _verify_hashes(directory, expected, "helper copy")
        return {Path(n).name: _hash(directory / Path(n).name) for n in ORACLE_SOURCES}

    def validate_schema(self, schema):
        """After helper compilation, before publication/Game construction.

        The reporter's active compression macros must independently agree with
        the calibrator's supported uncompressed profile. Never edit the schema
        to match that assumption or derive semantic expectations from a save.
        """
        if self.source_inputs is None:
            return None  # Archived ELF predates the source-profile bones checks.
        self.native_profile = None
        _verify_hashes(
            self.source_inputs.build_root, self.source_hashes, "oracle source"
        )
        profile = validate_native_profile(self.source_inputs, schema)
        self.native_profile = profile
        return profile

    def verify_copy(self, directory):
        """Check all copied tuple bytes immediately before fresh/restore start."""
        _require(
            self.source_inputs is None or self.native_profile is not None,
            "source calibration required before copy/launch guard",
        )
        return _verify_hashes(Path(directory), self.artifact_hashes, "copy")

    def record(self):
        """JSON-ready observed selection, not a claim of gameplay success."""
        source = None
        if self.source_inputs is not None:
            source = asdict(self.source_inputs)
            for key in ("build_root", "tuple_dir"):
                source[key] = str(source[key])
        return {
            "mode": self.mode,
            "tuple_dir": str(self.tuple_dir),
            "expected_artifact_hashes": self.artifact_hashes.copy(),
            "compiler": self.compiler,
            "environment": self.environment,
            "source_build": source,
            "source_hashes": self.source_hashes,
            "native_profile": asdict(self.native_profile)
            if self.native_profile
            else None,
            "limits": (
                "stable cooperating inputs; no native acceptance implied; "
                "archived pins retain older bones; source profile is bounded static calibration"
            ),
        }


def prepare(build_root, environment=None):
    """Read-only preflight; call before copying, compiler or artifact publication.

    build_root MUST be actual gameplay_support.ROOT, never a root from JSON.
    Expected revision MUST be independent reviewed job input, not receipt-derived.
    The receipt directory must be selected from the trusted builder job context;
    ownership/private permissions alone do not authenticate arbitrary JSON.
    """
    env = os.environ if environment is None else environment
    mode = env.get("NYARLATHACK_NATIVE_FIXTURE_MODE", "archived")
    receipt_key = "NYARLATHACK_NATIVE_BUILD_RECEIPT"
    revision_key = "NYARLATHACK_NATIVE_EXPECTED_REVISION"
    _require(mode in ("archived", "source-build"), "unknown native fixture mode")
    if mode == "archived":
        _require(
            receipt_key not in env and revision_key not in env,
            "archived mode forbids orphan receipt/revision context",
        )
        root = Path(build_root)
        hashes = _verify_hashes(root / "dnethackdir", ARCHIVED_HASHES, "archived")
        return FixtureSelection(mode, root / "dnethackdir", hashes, "cc", None)

    revision, receipt = env.get(revision_key), env.get(receipt_key)
    _require(
        type(revision) is str and re.fullmatch(r"[0-9a-f]{40}", revision),
        "independent expected revision must be full lowercase 40hex",
    )
    if type(receipt) is not str:
        raise SelectionError("trusted receipt directory must be explicitly selected")
    _require(
        bool(receipt.strip())
        and "\x00" not in receipt
        and Path(receipt).is_absolute()
        and ".." not in Path(receipt).parts
        and str(Path(receipt)) == receipt,
        "trusted receipt directory must be an explicit canonical absolute path",
    )
    root, receipts = Path(build_root), Path(receipt)
    inputs = verify_source_build(receipts, root, revision, mode=1)
    _require(
        type(inputs) is SourceBuildInputs
        and inputs.build_root == root
        and inputs.tuple_dir == root / "dnethackdir"
        and inputs.revision == revision
        and type(inputs.mode) is int
        and inputs.mode == 1
        and inputs.metadata["receipt_dir"] == str(receipts),
        "verified source-build context differs from independently selected context",
    )
    hashes = _committed_sources(root, revision)
    return FixtureSelection(
        mode,
        inputs.tuple_dir,
        inputs.artifact_hashes.copy(),
        "/usr/bin/cc",
        inputs.metadata["environment"].copy(),
        inputs,
        hashes,
    )
