"""Native curio validation through the engine's own Lua sandbox (NGPL).

CurioValidator calls the exact C entry points the engine's admission uses
(src/chaos_curio.c: chaos_lua_curio_load, then inspect and apply with the
player's Sanity and Insight, three charges and state 0), from a shared library
built from the unmodified src/chaos_lua.c. It then runs the same hooks across a
fixed validation grid of contexts a placed curio can meet later, and collects
every name and text the hooks can return, for the prose truthfulness check.

The caller supplies the library (an explicit absolute path) and owns its
provenance; the library's SHA-256 is recorded, not certified. Passing here is
not admission: the engine re-validates the exact bytes at its safe point.
"""

import ctypes
import hashlib
from pathlib import Path

# The grid: Sanity 0..100, Insight 0..1000000, charges 3..1, state 0..255 are
# the hook bounds (include/chaos_lua.h). The admission context is added.
GRID_SANITY = (100, 80, 50, 20, 0)
GRID_INSIGHT = (0, 3, 30, 300)
GRID_CHARGES = (3, 2, 1)
GRID_STATES = (0, 1, 2, 5, 255)
MAX_SOURCE_BYTES = 4096


class _Context(ctypes.Structure):
    _fields_ = [(k, ctypes.c_int) for k in ("sanity", "insight", "charges", "state")]


class _Intent(ctypes.Structure):
    _fields_ = [
        ("text", ctypes.c_char * 161),
        ("state", ctypes.c_int),
        ("sanity_delta", ctypes.c_int),
    ]


class CurioValidator:
    def __init__(self, library):
        path = Path(library)
        if not path.is_absolute():
            raise ValueError("explicit absolute trusted native library required")
        self.library = path
        self.library_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        lib = ctypes.CDLL(str(path))
        self._load = lib.chaos_lua_curio_load
        self._load.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p]
        self._load.restype = ctypes.c_int
        self._inspect = lib.chaos_lua_curio_inspect
        self._inspect.argtypes = [
            ctypes.c_char_p,
            ctypes.c_size_t,
            ctypes.POINTER(_Context),
            ctypes.c_char_p,
        ]
        self._inspect.restype = ctypes.c_int
        self._apply = lib.chaos_lua_curio_apply
        self._apply.argtypes = [
            ctypes.c_char_p,
            ctypes.c_size_t,
            ctypes.POINTER(_Context),
            ctypes.POINTER(_Intent),
        ]
        self._apply.restype = ctypes.c_int

    def validate(self, source, sanity, insight):
        """Admission checks, then the grid. Returns a JSON-ready dict.

        ``admitted`` is true only when the admission calls and every grid call
        succeed; ``failure`` names the first stage that failed.
        """
        if type(source) is not bytes or not 1 <= len(source) <= MAX_SOURCE_BYTES:
            raise ValueError("source must be 1..4096 bytes")
        for value, top in ((sanity, 100), (insight, 1000000)):
            if type(value) is not int or not 0 <= value <= top:
                raise ValueError("sanity/insight outside hook bounds")
        n = len(source)
        name = ctypes.create_string_buffer(49)
        text = ctypes.create_string_buffer(161)
        intent = _Intent()
        if self._load(source, n, name):
            return dict(admitted=False, failure="native_load")
        first = _Context(sanity, insight, 3, 0)
        if self._inspect(source, n, ctypes.byref(first), text):
            return dict(admitted=False, failure="native_inspect")
        admission_inspect = text.value.decode("ascii")
        if self._apply(source, n, ctypes.byref(first), ctypes.byref(intent)):
            return dict(admitted=False, failure="native_apply")
        admission_apply = dict(
            text=intent.text.decode("ascii"),
            state=intent.state,
            sanity_delta=intent.sanity_delta,
        )
        failures, inspects, applies, calls = 0, set(), set(), 0
        for s in sorted(set(GRID_SANITY) | {sanity}, reverse=True):
            for i in sorted(set(GRID_INSIGHT) | {insight}):
                for charges in GRID_CHARGES:
                    for state in GRID_STATES:
                        c = _Context(s, i, charges, state)
                        calls += 2
                        if self._inspect(source, n, ctypes.byref(c), text):
                            failures += 1
                        else:
                            inspects.add(text.value.decode("ascii"))
                        if self._apply(
                            source, n, ctypes.byref(c), ctypes.byref(intent)
                        ):
                            failures += 1
                        else:
                            applies.add(intent.text.decode("ascii"))
        # Admission passed above; a grid failure is still rejected before
        # install (proposal 3.8): a hook that fails later would show nothing.
        result = dict(
            admitted=failures == 0,
            failure=None if failures == 0 else "native_grid",
            name=name.value.decode("ascii"),
            admission_inspect=admission_inspect,
            admission_apply=admission_apply,
            grid_calls=calls,
            grid_failures=failures,
            inspect_texts=sorted(inspects),
            apply_texts=sorted(applies),
        )
        return result
