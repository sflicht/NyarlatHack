import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class HauntInstallTests(unittest.TestCase):
    def test_install_preserves_exact_source_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            cmd = [
                "python3",
                "-m",
                "chaos",
                "haunt",
                "--run-dir",
                tmp,
                "--source",
                str(ROOT / "chaos/packs/footsteps.lua"),
            ]
            p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=5)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(
                (Path(tmp) / "haunting.lua").read_bytes(),
                (ROOT / "chaos/packs/footsteps.lua").read_bytes(),
            )
            self.assertEqual((Path(tmp) / "haunting.lua").stat().st_mode & 0o777, 0o600)
            p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=5)
            self.assertEqual(p.returncode, 2)
