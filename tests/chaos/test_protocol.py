"""Executable tests of the real bounded C parser and state machine."""
import json
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
REQUEST = dict(v=1, id=1, mutation="ambient", value=1, duration=0, telegraph=1, at=1)

class ProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="chaos-protocol-")
        cls.exe = pathlib.Path(cls.tmp.name) / "protocol"
        cls.sources = [ROOT / "src/chaos_protocol.c", ROOT / "tests/chaos/protocol_harness.c"]
        if all(p.exists() for p in cls.sources):
            subprocess.run(["cc", "-std=c99", "-Wall", "-Wextra", "-Werror", "-pedantic",
                            "-I" + str(ROOT / "include"), *map(str, cls.sources), "-o", str(cls.exe)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_c(self, payload, mode="parse"):
        self.assertTrue(self.exe.exists(), "bounded C protocol implementation is missing")
        return subprocess.check_output([str(self.exe), mode], input=payload).decode().strip()

    def check_request(self, obj, expected="ok"):
        self.assertEqual(self.run_c(json.dumps(obj).encode()), expected)

    def test_valid_registry(self):
        for name, value, duration, telegraph in [("ambient", 3, 0, 1), ("ward_efficacy",50,50,2), ("hunger_rate",2,1,3)]:
            with self.subTest(name=name):
                self.check_request(dict(REQUEST, mutation=name, value=value, duration=duration, telegraph=telegraph))

    def test_missing_every_field(self):
        for key in REQUEST:
            obj = REQUEST.copy(); del obj[key]
            with self.subTest(key=key): self.check_request(obj,"schema")

    def test_unknown_duplicate_fields(self):
        for key in ["cost", "cruelty", "params", "unknown"]:
            self.check_request(dict(REQUEST, **{key:0}), "schema")
        for key, value in REQUEST.items():
            raw=json.dumps(REQUEST)[:-1]+", "+json.dumps(key)+":"+json.dumps(value)+"}"
            self.assertEqual(self.run_c(raw.encode()),"schema")

    def test_integer_grammar(self):
        for key in ["v","id","value","duration","telegraph","at"]:
            for value in [True,False,1.0,1e100,-1,2147483648,"1",None,[],{}]:
                with self.subTest(key=key,value=value): self.check_request(dict(REQUEST,**{key:value}),"schema")
        for token in ["01","+1","1e0","-0"]:
            self.assertEqual(self.run_c(json.dumps(REQUEST).replace('"id": 1','"id": '+token).encode()),"schema")

    def test_schema_bounds(self):
        for fields in [dict(v=2),dict(id=0),dict(at=0),dict(mutation="spawn_bias"),dict(value=4),dict(duration=1),dict(telegraph=2),
                       dict(mutation="ward_efficacy",value=49,duration=1,telegraph=2),
                       dict(mutation="hunger_rate",value=2,duration=51,telegraph=3),
                       dict(mutation="hunger_rate",value=2,duration=0,telegraph=3)]:
            self.check_request(dict(REQUEST,**fields),"schema")

    def test_malformed_and_size(self):
        valid=json.dumps(REQUEST).encode()
        for raw in [b"",b"[]",valid+b"{}",valid+b"x",valid+b"\x00",valid.replace(b"ambient",b"ambi\nent"),
                    valid.replace(b"ambient",b"ambi\x00ent"),valid.replace(b"ambient",b"ambi\\u0065nt"),
                    valid.replace(b"ambient",b"ambi\x7fent"), valid[:-1]+b",}",valid[:-1],b"{"*100]:
            with self.subTest(raw=raw): self.assertEqual(self.run_c(raw),"schema")
        self.assertEqual(self.run_c(valid+b" "*512),"oversize")
        self.assertEqual(self.run_c(b" "+valid+b"\r\n\t"),"ok")

    def test_state_budget_dedup_expiry_persistence(self):
        self.assertEqual(self.run_c(b"","state"),"state ok")

    def test_event_escaping(self):
        raw=b'quote" slash\\ newline\n tab\t ctrl\x01 utf8\xc3\xa9'
        self.assertEqual(json.loads(self.run_c(raw,"escape")),raw.decode())

if __name__ == "__main__": unittest.main()
