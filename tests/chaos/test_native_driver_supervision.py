"""Build-free probes; fresh temporary scripts/logs are explicitly authorized.

The state-mutating fixture runs in a disposable Python, never this suite process.
No fixture is native acceptance evidence.
"""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ADAPTERS = (
    (
        "test_episode_platforms.py",
        "EpisodePlatformTests",
        "test_explicit_source_platforms",
        "PLATFORM",
    ),
    (
        "test_episode_whistle.py",
        "EpisodeWhistleTests",
        "test_selected_ordinary_whistle",
        "WHISTLE",
    ),
)


class AdapterTests(unittest.TestCase):
    def test_adapter_isolates_real_caller_state(self):
        probe = r"""
import ctypes, importlib.util, json, os, resource, signal, sys
from pathlib import Path
from unittest import mock
sys.path.insert(0, sys.argv[1])
filename, classname, method, prefix = sys.argv[3:]
prefix = 'NYARLATHACK_' + prefix + '_'
spec = importlib.util.spec_from_file_location('adapter', Path(sys.argv[1]) / filename)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
root = Path(sys.argv[2])
script = root / 'fake.py'
script.write_text("import json,os,resource,signal,sys\nfrom pathlib import Path\nos.umask(0o077)\nresource.setrlimit(resource.RLIMIT_CORE,(0,0))\nsignal.signal(signal.SIGTERM,lambda *a: None)\nsignal.alarm(10)\nos.environ['child_only']='yes'\nprint(json.dumps({'args':sys.argv[1:],'cwd':os.getcwd(),'obs':os.getenv('NYARLATHACK_OBSERVATIONS'),'pythonpath':os.getenv('PYTHONPATH')}))\nprint('diagnostic',file=sys.stderr)\n")
os.umask(0o022)
os.environ['NYARLATHACK_OBSERVATIONS'] = 'leaked'
os.environ['PYTHONPATH'] = 'leaked'
values = {'ROOT':str(root), 'RECEIPT':str(root/'receipt'), 'REVISION':'a'*40, 'ARTIFACTS':str(root/'absent')}
if prefix == 'NYARLATHACK_PLATFORM_': values['OFF_TUPLE'] = str(root/'stock')
for key,value in values.items(): os.environ[prefix+key] = value
adapter = getattr(getattr(m, classname)(method), method)
libc = ctypes.CDLL(None)
def state():
    mask = os.umask(0o022); os.umask(mask)
    sub = ctypes.c_int(); assert libc.prctl(37,ctypes.byref(sub),0,0,0) == 0
    limits = {name:resource.getrlimit(value) for name,value in vars(resource).items() if name.startswith('RLIMIT_')}
    return (mask,limits,dict(os.environ),{sig:signal.getsignal(sig) for sig in signal.valid_signals()},signal.getitimer(signal.ITIMER_REAL),sub.value,os.getcwd())
def poison(args):
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    os.environ['poison'] = 'yes'
before = state()
with mock.patch.object(m,'main',side_effect=poison), mock.patch.object(m,'__file__',str(script)):
    adapter()
assert before == state(), 'inline adapter changed caller state'
assert not (root/'absent').exists()
logs = list(root.glob('absent.driver-*'))
assert len(logs) == 1
payload = json.loads((logs[0]/'driver.stdout').read_text())
expected = []
for key,value in values.items(): expected += ['--'+key.lower().replace('_','-'),value]
assert payload == {'args':expected,'cwd':str(root),'obs':None,'pythonpath':None}, payload
assert (logs[0]/'driver.stderr').read_text() == 'diagnostic\n'
assert logs[0].stat().st_mode & 0o777 == 0o700
assert (logs[0]/'driver.stdout').stat().st_mode & 0o777 == 0o600
script.write_text("import sys\nprint('failure diagnostic',file=sys.stderr)\nsys.exit(9)\n")
os.environ[prefix+'ARTIFACTS'] = str(root/'other-absent')
before = state()
with mock.patch.object(m,'__file__',str(script)):
    try: adapter()
    except AssertionError as exc:
        assert 'driver failed (9)' in str(exc)
        failure_logs = list(root.glob('other-absent.driver-*'))
        assert len(failure_logs) == 1
        assert str(failure_logs[0]) in str(exc), str(exc)
        assert (failure_logs[0]/'driver.stderr').read_text() == 'failure diagnostic\n'
    else: raise AssertionError('adapter swallowed nonzero exit')
assert before == state(), 'failed adapter changed caller state'
assert not (root/'other-absent').exists()
assert len(list(root.glob('other-absent.driver-*'))) == 1
"""
        for adapter in ADAPTERS:
            with (
                self.subTest(adapter=adapter[0]),
                tempfile.TemporaryDirectory() as root,
            ):
                result = subprocess.run(
                    [sys.executable, "-c", probe, str(HERE), root, *adapter],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_required_environment_still_asserts(self):
        probe = r"""
import importlib.util, os, sys
from pathlib import Path
filename, classname, method, prefix = sys.argv[2:]
prefix = 'NYARLATHACK_' + prefix + '_'
spec = importlib.util.spec_from_file_location('adapter', Path(sys.argv[1])/filename)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
keys = ['ROOT', 'RECEIPT', 'REVISION', 'ARTIFACTS']
if prefix == 'NYARLATHACK_PLATFORM_': keys.append('OFF_TUPLE')
adapter = getattr(getattr(m, classname)(method), method)
for missing in keys:
    for key in keys: os.environ[prefix+key] = 'unit-only-unused'
    del os.environ[prefix+missing]
    try: adapter()
    except AssertionError as e: assert prefix+missing in str(e), str(e)
    else: raise AssertionError('missing selection accepted: '+missing)
"""
        for adapter in ADAPTERS:
            with self.subTest(adapter=adapter[0]):
                p = subprocess.run(
                    [sys.executable, "-c", probe, str(HERE), *adapter],
                    capture_output=True,
                    timeout=5,
                )
                self.assertEqual(p.returncode, 0, p.stderr)


@unittest.skipUnless(
    sys.platform == "linux" and hasattr(os, "pidfd_open"), "Linux pidfds"
)
class DescendantTests(unittest.TestCase):
    def test_nested_pty_timeout(self):
        self.family("timeout")

    def test_driver_error_before_descendant_exit(self):
        self.family("exit")

    def test_repeated_supervisor_cancellation_cleans_nested_family(self):
        self.family("cancel")

    def test_stale_identity_never_signals(self):
        from unittest import mock
        import native_driver_supervision as supervisor

        with (
            mock.patch.object(supervisor.os, "waitid", side_effect=ChildProcessError),
            mock.patch.object(supervisor.os, "kill") as kill,
            mock.patch.object(supervisor.os, "killpg") as killpg,
        ):
            with self.assertRaises(ChildProcessError):
                supervisor.owned_signal(123456789, 15)
            kill.assert_not_called()
            killpg.assert_not_called()

    def family(self, mode):
        import signal
        import time

        helper = HERE / "native_driver_supervision.py"
        self.assertTrue(helper.exists(), "external subreaper supervisor missing")
        worker = r"""
import os, pty, signal, sys, time
from pathlib import Path
root = Path(sys.argv[1])
def publish_pid(name):
    # Existence is the readiness signal: publish only fully written content.
    pending = root / (name + '.pending')
    pending.write_text(str(os.getpid()))
    pending.replace(root / name)
signal.alarm(8)
if sys.argv[2] == 'timeout':
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
# Keep the original supervisor pipe across forkpty's stdio replacement.
pipe_holder = os.dup(1)
pid, fd = pty.fork()
if pid == 0:
    signal.alarm(8)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    child = os.fork()
    if child == 0:
        os.setsid()
        signal.alarm(8)
        publish_pid('grandchild')
        while True: time.sleep(.01)
    publish_pid('child')
    while True: time.sleep(.01)
while not (root/'go').exists(): time.sleep(.005)
if sys.argv[2] == 'exit': sys.exit(7)
while True: time.sleep(.01)
"""
        held = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            logs = root / "logs"
            logs.mkdir(mode=0o700)
            p = subprocess.Popen(
                [
                    sys.executable,
                    str(helper),
                    str(logs),
                    "1",
                    ".15",
                    "1024",
                    sys.executable,
                    "-c",
                    worker,
                    str(root),
                    mode,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            try:
                deadline = time.monotonic() + 3
                for name in ("child", "grandchild"):
                    while not (root / name).exists():
                        self.assertLess(time.monotonic(), deadline)
                        time.sleep(0.005)
                    held.append(os.pidfd_open(int((root / name).read_text())))
                (root / "go").touch()
                if mode == "cancel":
                    p.send_signal(signal.SIGTERM)
                    time.sleep(0.04)
                    p.send_signal(signal.SIGALRM)
                    p.send_signal(signal.SIGINT)
                _, err = p.communicate(timeout=5)
                expected = {"timeout": 124, "exit": 7, "cancel": 143}[mode]
                self.assertEqual(p.returncode, expected, err)
                import json

                status = json.loads((logs / "supervisor.status.json").read_text())
                self.assertEqual(status["family_cleanup"], "verified")
                import select

                for fd in held:
                    self.assertTrue(
                        select.select([fd], [], [], 1)[0], "owned descendant survived"
                    )
            finally:
                for fd in held:
                    try:
                        signal.pidfd_send_signal(fd, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    os.close(fd)
                if p.poll() is None:
                    p.terminate()
                    try:
                        p.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        p.kill()
                        p.wait(timeout=2)
                p.stderr.close()

    def test_cancellation_during_cleanup_is_not_success(self):
        probe = r"""
import os, signal, sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import native_driver_supervision as s
original = s.cleanup
def interrupted(*args):
    os.kill(os.getpid(),signal.SIGTERM)
    os.kill(os.getpid(),signal.SIGINT)
    return original(*args)
s.cleanup = interrupted
code = s.supervise(Path(sys.argv[2]),1,.05,1024,[sys.executable,'-c','pass'])
assert code == 143, code
"""
        with tempfile.TemporaryDirectory() as tmp:
            p = subprocess.run(
                [sys.executable, "-c", probe, str(HERE), tmp],
                capture_output=True,
                timeout=5,
            )
            self.assertEqual(p.returncode, 0, p.stderr)

    def test_cleanup_error_preserves_primary_and_closes_logs(self):
        probe = r"""
import json, os, signal, sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import native_driver_supervision as s
signal.alarm(8)
original = s.cleanup
opened = []
fdopen = os.fdopen
def track(*a,**kw):
    stream = fdopen(*a,**kw); opened.append(stream); return stream
def faulty(*a):
    original(*a)
    raise RuntimeError('injected cleanup diagnostic')
s.cleanup = faulty
s.os.fdopen = track
root = Path(sys.argv[2])
result = s.supervise(root,.1,.1,1024,[sys.executable,'-c',"import time; print('ready',flush=True); time.sleep(8)"])
assert result == 125
status = json.loads((root/'supervisor.status.json').read_text())
assert 'TimeoutError' in status['failure'], status
assert 'injected cleanup diagnostic' in status['cleanup'], status
assert status['family_cleanup'] == 'unverified', status
assert opened and all(stream.closed for stream in opened)
assert not s.owned_children()
"""
        with tempfile.TemporaryDirectory() as tmp:
            p = subprocess.run(
                [sys.executable, "-c", probe, str(HERE), tmp],
                capture_output=True,
                timeout=5,
            )
            self.assertEqual(p.returncode, 0, p.stderr)

    def test_logs_are_capped_and_nonzero_propagates(self):
        self.assertTrue(
            (HERE / "native_driver_supervision.py").exists(), "supervisor missing"
        )
        import native_driver_supervision as supervisor

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = root / "fake.py"
            script.write_text(
                "import sys\nprint('x'*100000)\nprint('y'*100000,file=sys.stderr)\nsys.exit(9)\n"
            )
            code, logs = supervisor.run_driver(
                script, [], root, root / "absent", timeout=2, term_grace=0.1, limit=1024
            )
            self.assertEqual(code, 9)
            for name in ("driver.stdout", "driver.stderr"):
                self.assertEqual((logs / name).stat().st_size, 1024)
            self.assertFalse((root / "absent").exists())


class CorrectionTests(unittest.TestCase):
    def probe(self, source, *args):
        with tempfile.TemporaryDirectory() as tmp:
            p = subprocess.run(
                [sys.executable, "-c", source, str(HERE), tmp, *args],
                capture_output=True,
                text=True,
                timeout=12,
            )
            self.assertEqual(p.returncode, 0, p.stderr)

    @unittest.skipUnless(
        sys.platform == "linux" and hasattr(os, "pidfd_open"), "Linux pidfds"
    )
    def test_parent_signal_at_acquisition_retains_identity_and_diagnostics(self):
        self.probe(r"""
import os, signal, subprocess, sys, select
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import native_driver_supervision as s
root = Path(sys.argv[2])
real = subprocess.Popen
held = []
processes = []
def acquire(*a, **kw):
    p = real([sys.executable, '-c', 'import signal,time; signal.alarm(5); time.sleep(4)'], **kw)
    processes.append(p); held.append(os.pidfd_open(p.pid))
    os.kill(os.getpid(), signal.SIGINT)
    return p
s.subprocess.Popen = acquire
before = signal.getsignal(signal.SIGINT)
try:
    try: s.run_driver(root/'fake.py', [], root, root/'absent', timeout=.1, term_grace=.01)
    except KeyboardInterrupt as exc:
        notes = '\n'.join(getattr(exc, '__notes__', []))
        assert 'diagnostic' in notes and str(root) in notes, notes
    else: raise AssertionError('parent SIGINT lost')
    assert select.select(held, [], [], 0)[0] == held, 'supervisor abandoned at acquisition'
    assert signal.getsignal(signal.SIGINT) is before
finally:
    for fd in held:
        try: signal.pidfd_send_signal(fd, signal.SIGKILL)
        except ProcessLookupError: pass
        os.close(fd)
    for p in processes: p.wait(timeout=2)
""")

    @unittest.skipUnless(
        sys.platform == "linux" and hasattr(os, "pidfd_open"), "Linux pidfds"
    )
    def test_parent_repeated_signals_and_escalation_errors_preserve_primary(self):
        self.probe(r"""
import ctypes, os, resource, select, signal, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import native_driver_supervision as s
root = Path(sys.argv[2]); real = subprocess.Popen
primary = RuntimeError('primary wait failure'); calls = []; held = []; processes = []
def alarm(*a): raise AssertionError('alarm handler escaped deferral')
signal.signal(signal.SIGALRM, alarm); signal.setitimer(signal.ITIMER_REAL, 9, 9)
def state():
    mask = os.umask(0o022); os.umask(mask)
    sub = ctypes.c_int(); assert ctypes.CDLL(None).prctl(37,ctypes.byref(sub),0,0,0) == 0
    return (mask,resource.getrlimit(resource.RLIMIT_CORE),dict(os.environ),sub.value,
            tuple(signal.getsignal(sig) for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGALRM)))
before = state(); timer = signal.getitimer(signal.ITIMER_REAL)
def interrupt():
    os.kill(os.getpid(),signal.SIGINT); os.kill(os.getpid(),signal.SIGALRM)
def acquire(*a, **kw):
    p = real([sys.executable,'-c','import signal,time; signal.alarm(5); time.sleep(4)'],**kw)
    processes.append(p); held.append(os.pidfd_open(p.pid))
    original_wait = p.wait; original_kill = p.kill
    def terminate():
        calls.append('TERM'); interrupt(); raise OSError('TERM error')
    def kill():
        calls.append('KILL'); interrupt(); original_kill(); raise OSError('KILL error')
    def wait(timeout=None):
        if not calls: calls.append('primary'); raise primary
        if calls[-1] == 'TERM':
            calls.append('grace'); interrupt(); raise OSError('grace error')
        calls.append('reap'); interrupt(); original_wait(timeout=timeout); raise OSError('reap error')
    p.terminate=terminate; p.kill=kill; p.wait=wait
    return p
s.subprocess.Popen=acquire
start=time.monotonic()
try:
    try: s.run_driver(root/'fake.py',[],root,root/'absent',timeout=.1,term_grace=.01)
    except BaseException as exc:
        assert exc is primary, repr(exc)
        notes='\n'.join(exc.__notes__)
        for word in ('diagnostics','unverified','TERM error','grace error','KILL error','reap error'):
            assert word in notes, notes
    else: raise AssertionError('primary lost')
    assert calls == ['primary','TERM','grace','KILL','reap'], calls
    assert state() == before
    after=signal.getitimer(signal.ITIMER_REAL)
    assert 0 < after[0] <= timer[0] and after[1] == timer[1]
    assert time.monotonic()-start < 2
    assert select.select(held,[],[],0)[0] == held
finally:
    signal.setitimer(signal.ITIMER_REAL,0)
    for fd in held:
        try: signal.pidfd_send_signal(fd,signal.SIGKILL)
        except ProcessLookupError: pass
        os.close(fd)
    for p in processes: real.wait(p,timeout=2)
""")

    def test_status_write_failure_has_private_bounded_fallback(self):
        self.probe(r"""
import json, os, sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import native_driver_supervision as s
root=Path(sys.argv[2]); real=os.fdopen
class BrokenStatus:
    def __init__(self, stream): self.stream=stream
    def __enter__(self): return self
    def __exit__(self,*a): self.close()
    def close(self): self.stream.close(); raise OSError('status close failure')
    def write(self,data): raise OSError('status write failure')
def fdopen(fd,*a,**kw):
    stream=real(fd,*a,**kw)
    return BrokenStatus(stream) if a and a[0]=='w' else stream
s.os.fdopen=fdopen
code=s.supervise(root,.05,.01,1024,[sys.executable,'-c','import time; time.sleep(3)'])
assert code == 125
fallback=root/'supervisor.fallback.log'
assert fallback.stat().st_mode & 0o777 == 0o600
assert 0 < fallback.stat().st_size <= 16384
status=json.loads(fallback.read_text())
assert 'TimeoutError' in status['failure'],status
assert 'status close failure' in str(status['publication_errors']),status
assert not s.owned_children()
""")

    def test_selector_and_total_persistence_failures_are_nonzero(self):
        for mode in ("selector", "all-writes"):
            with self.subTest(mode=mode):
                self.probe(
                    r"""
import json, os, sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import native_driver_supervision as s
root=Path(sys.argv[2]); mode=sys.argv[3]
if mode=='selector':
    real=s.selectors.DefaultSelector.close
    def close(self):
        real(self)
        raise OSError('selector close failure')
    s.selectors.DefaultSelector.close=close
else:
    def broken(*a,**kw): raise OSError('all writes fail')
    s.json.dump=broken; s.os.write=broken
code=s.supervise(root,1,.01,1024,[sys.executable,'-c','pass'])
assert code == 125,code
assert not s.owned_children()
if mode=='selector':
    status=json.loads((root/'supervisor.status.json').read_text())
    assert 'selector close failure' in str(status),status
else:
    assert (root/'supervisor.fallback.log').stat().st_size==0
""",
                    mode,
                )

    def test_non_main_thread_rejected_before_launch(self):
        import threading
        from unittest import mock
        import native_driver_supervision as s

        errors = []

        def call():
            try:
                s.run_driver("unused", [], ".", "unused")
            except RuntimeError as exc:
                errors.append(str(exc))

        with mock.patch.object(s.subprocess, "Popen") as launch:
            thread = threading.Thread(target=call)
            thread.start()
            thread.join(timeout=2)
            launch.assert_not_called()
        self.assertEqual(len(errors), 1)
        self.assertIn("main thread", errors[0])

    def test_buffered_close_failure_still_publishes_status(self):
        self.probe(r"""
import json, os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import native_driver_supervision as s
root = Path(sys.argv[2])
real = os.fdopen
opened = []
class BrokenClose:
    def __init__(self, stream): self.stream = stream
    def __getattr__(self, name): return getattr(self.stream, name)
    def __enter__(self): return self
    def __exit__(self, *a): self.close()
    def close(self): raise OSError('injected buffered flush/close failure')
def fdopen(fd, *a, **kw):
    stream = real(fd, *a, **kw)
    if a and a[0] == 'wb':
        opened.append((fd, stream)); return BrokenClose(stream)
    return stream
s.os.fdopen = fdopen
try:
    code = s.supervise(root,.1,.01,1024,[sys.executable,'-c',"import time; print('buffered',flush=True); time.sleep(3)"])
except OSError as exc: raise AssertionError('close prevented status publication') from exc
assert code != 0
status = json.loads((root/'supervisor.status.json').read_text())
assert 'TimeoutError' in status['failure'], status
assert 'injected buffered flush/close failure' in str(status), status
assert not s.owned_children()
for fd, stream in opened:
    try: os.fstat(fd)
    except OSError: pass
    else: raise AssertionError('descriptor leaked after flush failure')
""")


class FinalizationTests(unittest.TestCase):
    probe = CorrectionTests.probe

    @unittest.skipUnless(
        sys.platform == "linux" and hasattr(os, "pidfd_open"), "Linux pidfds"
    )
    def test_pending_signals_at_restoration_boundary(self):
        for mode in ("pending", "setter-error"):
            with self.subTest(mode=mode):
                self.probe(
                    r"""
import ctypes, os, resource, select, signal, subprocess, sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import native_driver_supervision as s
root=Path(sys.argv[2]); mode=sys.argv[3]
primary=RuntimeError('first wait failure'); boundary=RuntimeError('boundary handler')
seen=[]; held=[]; processes=[]
def interrupt(*a): seen.append('INT'); raise boundary
def alarm(*a): seen.append('ALRM')
signal.signal(signal.SIGINT,interrupt); signal.signal(signal.SIGALRM,alarm)
signal.signal(signal.SIGUSR1,lambda *a: None)
signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGUSR2})
signal.setitimer(signal.ITIMER_REAL,9,9)
real_mask=signal.pthread_sigmask; real_signal=signal.signal; real_popen=subprocess.Popen
blocks=[]; restores=[]
def state():
    umask=os.umask(0o022); os.umask(umask)
    sub=ctypes.c_int(); assert ctypes.CDLL(None).prctl(37,ctypes.byref(sub),0,0,0)==0
    limits={name:resource.getrlimit(value) for name,value in vars(resource).items() if name.startswith('RLIMIT_')}
    return (umask,limits,dict(os.environ),sub.value,
            {sig:signal.getsignal(sig) for sig in signal.valid_signals()},
            real_mask(signal.SIG_BLOCK,[]),signal.getitimer(signal.ITIMER_VIRTUAL),
            signal.getitimer(signal.ITIMER_PROF))
before=state(); timer=signal.getitimer(signal.ITIMER_REAL)
def mask(how,signals):
    result=real_mask(how,signals)
    if how==signal.SIG_BLOCK:
        blocks.append(1)
        if len(blocks)==2:
            os.kill(os.getpid(),signal.SIGINT); os.kill(os.getpid(),signal.SIGALRM)
            assert {signal.SIGINT,signal.SIGALRM} <= signal.sigpending()
    return result
def setter(sig,handler):
    if len(blocks)==2:
        restores.append(sig)
        if mode=='setter-error' and len(restores)==1:
            raise OSError('ordinary restoration error')
    return real_signal(sig,handler)
def launch(command,**kw):
    p=real_popen([sys.executable,'-c','import signal,time; signal.alarm(4); time.sleep(3)'],**kw)
    processes.append(p); held.append(os.pidfd_open(p.pid)); wait=p.wait; calls=[]
    def waiting(timeout=None):
        if not calls: calls.append(1); raise primary
        return wait(timeout=timeout)
    p.wait=waiting
    return p
s.signal.pthread_sigmask=mask; s.signal.signal=setter; s.subprocess.Popen=launch
try:
    try: s.run_driver(root/'unused',[],root,root/'absent',timeout=.1,term_grace=.01)
    except BaseException as exc:
        assert exc is primary, repr(exc)
        notes='\n'.join(exc.__notes__)
        assert 'diagnostics retained at' in notes and str(root) in notes, notes
        assert 'boundary handler' in notes, notes
        if mode=='setter-error': assert 'ordinary restoration error' in notes,notes
    else: raise AssertionError('primary lost')
    assert state()==before, 'caller state not restored'
    assert sorted(seen)==['ALRM','INT'],seen
    after=signal.getitimer(signal.ITIMER_REAL)
    assert 0<after[0]<=timer[0] and after[1]==timer[1]
    assert select.select(held,[],[],0)[0]==held,'owned child survived'
finally:
    real_mask(signal.SIG_SETMASK,[]); signal.setitimer(signal.ITIMER_REAL,0)
    for fd in held:
        try: signal.pidfd_send_signal(fd,signal.SIGKILL)
        except ProcessLookupError: pass
        os.close(fd)
    for p in processes: real_popen.wait(p,timeout=2)
""",
                    mode,
                )

    def test_grace_and_normal_exit_require_explicit_bounded_status(self):
        self.probe(r"""
import json, os, signal, subprocess, sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import native_driver_supervision as s
root=Path(sys.argv[2]); real=subprocess.Popen
signal.alarm(9)
valid={'family_cleanup':'verified','cleanup':None,'failure':None,'returncode':0,
       'close_errors':[],'publication_errors':[]}
cases={'missing':None,'invalid':'{','oversized':' '*65537,'nonobject':'[]',
       'nested':'['*1000+']'*1000,'bad-utf8':b'\xff',
       'incomplete':'{}','failed':json.dumps(dict(valid,family_cleanup='unverified',cleanup='failed')),
       'failed125':json.dumps(dict(valid,family_cleanup='unverified',cleanup='failed',returncode=125)),
       'mismatch':json.dumps(dict(valid,returncode=125)),
       'dirty':json.dumps(dict(valid,close_errors=['flush failure'])),
       'valid':json.dumps(valid)}
for cancellation in (True,False):
    for name,receipt in cases.items():
        primary=RuntimeError('original cancellation'); processes=[]
        def launch(command,**kw):
            if receipt is not None:
                (Path(command[2])/'supervisor.status.json').write_bytes(receipt if isinstance(receipt,bytes) else receipt.encode())
            p=real([sys.executable,'-c','raise SystemExit(125)' if name=='failed125' else 'pass'],**kw); processes.append(p)
            wait=p.wait; calls=[]
            def waiting(timeout=None):
                result=wait(timeout=timeout)
                if cancellation and not calls: calls.append(1); raise primary
                return result
            p.wait=waiting
            return p
        s.subprocess.Popen=launch
        try:
            result=s.run_driver(root/'unused',[],root,root/(str(cancellation)+name),timeout=.2,term_grace=.01)
        except BaseException as exc:
            assert cancellation and exc is primary,repr(exc)
            notes='\n'.join(exc.__notes__)
            assert 'diagnostics retained at' in notes
            assert ('containment unverified' in notes)==(name!='valid'),(name,notes)
        else:
            assert not cancellation
            assert result[0]==(0 if name=='valid' else 125),(name,result)
        finally:
            for p in processes: real.wait(p,timeout=2)
""")

    def test_maximum_fallback_is_valid_json_with_short_writes(self):
        self.probe(r"""
import json, os, sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import native_driver_supervision as s
root=Path(sys.argv[2]); write=os.write; calls=[]
def fake(logs,timeout,grace,limit,command,status):
    status['failure']='PRIMARY driver failure '+ '\U0001f409'*4096
    status['cleanup']='CLEANUP '+ '\U0001f409'*4096
    status['close_errors']=['CLOSE '+ '\U0001f409'*4096]*100
    status['publication_errors']=['PUBLICATION '+ '\U0001f409'*4096]*100
    return 125
def broken(*a,**kw): raise OSError('status publication failed '+ '\U0001f409'*4096)
def short(fd,data): calls.append(len(data)); return write(fd,data[:31])
s._supervise=fake; s.json.dump=broken; s.os.write=short
assert s.supervise(root,1,.01,1024,[])==125
path=root/'supervisor.fallback.log'
assert path.stat().st_mode & 0o777==0o600
raw=path.read_bytes(); assert 0<len(raw)<=16384
status=json.loads(raw)
assert status['failure'].startswith('PRIMARY driver failure'),status
assert status['diagnostics_truncated'] is True,status
assert 'CLOSE' in str(status['close_errors']) and 'PUBLICATION' in str(status['publication_errors'])
assert len(calls)>1 and calls[-1]<=31 and max(calls)<=16384,calls
""")

    def test_simultaneous_flush_and_publication_failure_cleans_family(self):
        self.probe(r"""
import json, os, signal, sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import native_driver_supervision as s
root=Path(sys.argv[2]); real=os.fdopen
signal.alarm(8)
class Broken:
    def __init__(self,stream): self.stream=stream
    def __getattr__(self,name): return getattr(self.stream,name)
    def write(self,data): return self.stream.write(data)
    def close(self): self.stream.close(); raise OSError('buffer flush failure')
def fdopen(fd,*a,**kw):
    stream=real(fd,*a,**kw)
    return Broken(stream) if a and a[0]=='wb' else stream
def broken(*a,**kw): raise OSError('status publication failure')
s.os.fdopen=fdopen; s.json.dump=broken
worker='import os,signal,time; os.fork(); signal.alarm(4); print("buffered",flush=True); time.sleep(3)'
assert s.supervise(root,.15,.01,1024,[sys.executable,'-c',worker])==125
status=json.loads((root/'supervisor.fallback.log').read_text())
assert 'TimeoutError' in status['failure'],status
assert 'buffer flush failure' in str(status['close_errors']),status
assert 'status publication failure' in str(status['publication_errors']),status
assert status['family_cleanup']=='verified',status
assert not s.owned_children()
""")


if __name__ == "__main__":
    unittest.main()
