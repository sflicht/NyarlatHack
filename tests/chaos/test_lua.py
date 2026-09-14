"""Executable Lua sandbox tests; no C/game stubs stand in for the interpreter."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]

class LuaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='nyarl-lua-')
        cls.exe=Path(cls.tmp.name)/'lua-test'
        if (ROOT/'src/chaos_lua.c').exists():
            flags=subprocess.check_output(['pkg-config','--cflags','--libs','lua5.4'],text=True).split()
            subprocess.run(['cc','-Wall','-Wextra','-Werror','-std=c99','-I'+str(ROOT/'include'),str(ROOT/'src/chaos_lua.c'),str(ROOT/'tests/chaos/lua_harness.c'),*flags,'-o',str(cls.exe)],check=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def run_script(self,source):
        self.assertTrue(self.exe.exists(),'Lua runtime is missing')
        p=subprocess.run([str(self.exe)],input=source.encode(),capture_output=True,timeout=3)
        self.assertEqual(p.returncode,0,p.stderr)
        return json.loads(p.stdout)
    def test_pure_movement_and_state(self):
        r=self.run_script('return function(c) return {dx=c.history[1].x-c.mx,dy=0,state=c.state+1} end')
        self.assertEqual(r,{'status':0,'dx':1,'dy':0,'state':8})
    def test_bounds_errors_and_no_capabilities(self):
        for source in ['return function(c) while true do end end','while true do end',
                       'return function(c) local t={} for i=1,1000000 do t[i]={i} end return t end',
                       'return function(c) return io.open("/etc/passwd") end',
                       'return function(c) return os.execute("true") end',
                       'return function(c) return load("return 1")() end',
                       'return function(c) return {dx=2,dy=0,state=0} end',
                       'return function(c) return {dx=true,dy=0,state=0} end',
                       'return function(c) return {dx=0.5,dy=0,state=0} end',
                       'return function(c) return {dx=0,dy=0,state=-1} end',
                       'return function(c) return {dx=0,dy=0,state=0,damage=99} end',
                       'return 4','syntax ???','\x1bLua', ' '*4097]:
            with self.subTest(source=source[:40]):self.assertNotEqual(self.run_script(source)['status'],0)
    def test_fresh_vm_no_hidden_persistent_globals(self):
        source='hidden=(hidden or 0)+1; return function(c) return {dx=0,dy=0,state=hidden} end'
        self.assertEqual(self.run_script(source)['state'],1)
        self.assertEqual(self.run_script(source)['state'],1)
