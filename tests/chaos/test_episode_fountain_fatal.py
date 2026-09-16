#!/usr/bin/env python3
"""Native first-quaff fatal interruption, controlled linked test setup.

Original main/moveloop dispatch q to a setup-and-forward dodrink wrapper.
This is not ordinary-play preparation or the complete whole-turnloop matrix.
Invoke through native_driver_supervision.run_driver, no optimized Python.
"""
import argparse
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import sys
import time
import unittest
from unittest.mock import patch

from test_episode_fountain_fatal_oracle import compare_pair, validate_fatal, reject_mutated_death_evidence
from test_episode_platforms import Cancellation, bounded, digest, observe, owned_game_type, save

# Frozen after the first successful preparation run, before final acceptance.
# Endgame answers are disclosures only; this non-wizard run has no Die? prompt.
FROZEN_INPUTS = {
    'healthy': ['n', ' ', ' ', 'q', 'y', '#quit\n', 'y', 'n', 'n', 'n', ' '],
    'fatal': ['n', ' ', ' ', 'q', 'y', ' ', ' ', 'n', 'n', 'n', ' ', ' '],
}


def finish_native(game, text):
    """Only bounded native post-game disclosures; never refuse death."""
    deadline = time.monotonic() + 15
    for _ in range(35):
        assert time.monotonic() < deadline, 'native endgame deadline'
        if observe(game.pid) is not None:
            game.read(1)
            return
        assert b'Die?' not in text, 'non-wizard baseline must not offer resurrection'
        if b'--More--' in text:
            text = game.send(' ')
        elif b'[ynq]' in text:
            text = game.send('n')
        else:
            text = game.read(1)
    raise AssertionError('native endgame input cap')


def main(argv=None):
    if sys.flags.optimize:
        raise SystemExit('optimized Python unsupported')
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'receipt', 'revision', 'artifacts'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args(argv)
    root, receipt, out = map(Path, (args.root, args.receipt, args.artifacts))
    assert all(p.is_absolute() and p.resolve() == p for p in (root, receipt, out))
    assert Path.cwd() == root and not out.is_relative_to(root)
    os.umask(0o077)
    out.mkdir(mode=0o700)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    trusted = root / 'tests/chaos'
    # Import the immutable receipt-bound source helpers, not ambient copies.
    for name in ('gameplay_support', 'native_fixture_selection', 'native_build_identity', 'native_build_calibration'):
        assert name not in sys.modules
    sys.path.insert(0, str(trusted))
    import gameplay_support
    import native_fixture_selection
    env = dict(os.environ, NYARLATHACK_NATIVE_FIXTURE_MODE='source-build',
               NYARLATHACK_NATIVE_BUILD_RECEIPT=str(receipt),
               NYARLATHACK_NATIVE_EXPECTED_REVISION=args.revision)
    selection = native_fixture_selection.prepare(root, env)
    assert selection.environment is not None
    env = dict(selection.environment, HOME=str(out), TMPDIR=str(out), MAIL=str(out / 'MAIL'))
    (out / 'MAIL').write_bytes(b'')
    manifest = json.loads((receipt / '1-manifest.json').read_text())
    originals = {str(root / p): digest(root / p) for p in manifest['objects']}
    save(out / 'original-object-hashes.json', originals)
    cancel = Cancellation()
    handlers = {sig: signal.signal(sig, cancel.handler) for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGALRM)}
    signal.alarm(180)
    try:
        def run(command, name):
            return bounded(command, out, env, out / name, 45, cancel=cancel)[0]
        flags = ['-std=gnu17', '-g', '-Wall', '-Wextra', '-Werror', '-DCHAOS', '-DDLB', '-isystem' + str(root / 'include')]
        for path in native_fixture_selection.ORACLE_SOURCES:
            shutil.copyfile(root / path, out / Path(path).name)
        selection.verify_helper_copy(out)
        run([selection.compiler, *flags, out / 'curio_save_layout.c', '-o', out / 'layout'], 'layout-build')
        selection.validate_schema(json.loads(run([out / 'layout'], 'layout')))
        save(out / 'selection.json', selection.record())
        sources = [Path(__file__).resolve(), Path(__file__).with_name('episode_fountain_fatal.c'),
                   Path(__file__).with_name('test_episode_fountain_fatal_oracle.py'),
                   Path(__file__).with_name('test_episode_platforms.py'),
                   Path(__file__).with_name('native_driver_supervision.py')]
        save(out / 'external-source-hashes.json', {str(p): digest(p) for p in sources})
        for p in sources:
            shutil.copyfile(p, out / p.name)
        objects = sorted((root / 'src').glob('*.o')) + [root / p for p in (
            'sys/unix/unixres.o', 'sys/unix/unixunix.o', 'sys/unix/unixmain.o',
            'sys/share/ioctl.o', 'sys/share/unixtty.o')] + sorted((root / 'win/tty').glob('*.o')) + sorted((root / 'win/curses').glob('*.o'))
        original = root / 'src/rnd.o'
        controlled = out / 'rnd.o'
        run(['/usr/bin/objcopy', '--globalize-symbol=reseed_period', '--globalize-symbol=reseed_count', original, controlled], 'rng-copy')
        objects = [controlled if p == original else p for p in objects]
        run([selection.compiler, *flags, '-c', out / 'episode_fountain_fatal.c', '-o', out / 'fixture.o'], 'fixture-compile')
        libs = run(['/usr/bin/pkg-config', '--libs', 'lua5.4'], 'lua-libs').decode().split()
        exe = out / 'fatal-fountain'
        run([selection.compiler, out / 'fixture.o', *objects, '-Wl,--wrap=main', '-Wl,--wrap=dodrink', '-lncursesw', '-ltinfo', '-lm', '-ldl', *libs, '-o', exe], 'fixture-link')
        clock = out / 'clock.so'
        run([selection.compiler, '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror', out / 'replay_clock.c', '-ldl', '-o', clock], 'clock-build')
        chosen = json.loads(run([exe, '--calibrate'], 'seed-preflight'))
        assert chosen['fate'] == 21 and 1 <= chosen['seed'] == chosen['candidates'] <= 4096
        save(out / 'frozen-seed.json', dict(chosen, action_rerolls=0))
        save(out / 'executables.json', {str(p): digest(p) for p in (exe, clock)})
        sys.path.insert(0, str(root))
        from chaos.episodes import project_episodes
        OwnedGame = owned_game_type(gameplay_support.Game, cancel)

        class FrozenGame(OwnedGame):
            def send(self, value, *, deadline=None):
                encoded = value.encode() if isinstance(value, str) else value
                expected = self.frozen_inputs
                assert len(self.inputs) < len(expected), 'input cap'
                assert encoded.hex() == expected[len(self.inputs)], 'unplanned input'
                return super().send(value, deadline=deadline)

        save(out / 'frozen-inputs.json', FROZEN_INPUTS)
        all_results = []
        for case in ('healthy', 'fatal'):
            pair = []
            for enabled in (False, True):
                work = out / (case + ('-on' if enabled else '-off'))
                game = FrozenGame(selection.tuple_dir, clock, observe=True, wizard=False, root=work, echoes=False)
                game.frozen_inputs = [s.encode().hex() for s in FROZEN_INPUTS[case]]
                selection.verify_copy(game.game)
                shutil.copyfile(exe, game.game / 'dnethack')
                child_env = dict(env, FATAL_FOUNTAIN_SEED=str(chosen['seed']), FATAL_FOUNTAIN_CASE=case)
                child_env.pop('NYARLATHACK_OBSERVATIONS', None)
                if enabled:
                    child_env['NYARLATHACK_OBSERVATIONS'] = '1'
                try:
                    with patch.dict(os.environ, child_env, clear=True):
                        text = game.start()
                    assert b'Drink from' not in text
                    text = game.send('q')
                    assert b'Drink from the fountain?' in text, text
                    assert game._reader_pid == game.pid
                    text = game.send('y')
                    if case == 'healthy':
                        text = game.more(text)
                        assert b'The water is contaminated!' in bytes(game.raw)
                        text = game.send('#quit\n')
                        assert b'Really quit?' in text, text
                        text = game.send('y')
                    finish_native(game, text)
                finally:
                    game.cleanup()
                assert game.exitcode == 0
                assert game.inputs == game.frozen_inputs
                native = json.loads((game.game / 'native-exit.json').read_text())
                before = json.loads((game.game / 'native-before.json').read_text())
                records = game.events()
                journal = (game.run / 'events.jsonl').read_bytes()
                public = project_episodes(journal)
                xlog = (game.game / 'xlogfile').read_bytes()
                dump_files = sorted((game.game / 'dumplog').glob('*'))
                assert dump_files, 'native dump required'
                dump = b''.join(p.read_bytes() for p in dump_files)
                terminal = bytes(game.raw)
                if case == 'fatal':
                    validate_fatal(records, native, terminal, xlog, public, enabled=enabled)
                    if enabled:
                        save(work / 'oracle-mutations-rejected.json', reject_mutated_death_evidence(records, native, terminal, xlog, public))
                else:
                    assert native['gameover'] == 1 and native['returned'] == 1 and native['hp'] > 0
                    stages = [r['observation']['stage'] for r in records if r['v'] == 2]
                    assert stages == (['enabled', 'started', 'completed'] if enabled else [])
                    assert records[-1]['detail'] == 'quit'
                result = dict(terminal=terminal, inputs=game.inputs, xlog=xlog, dump=dump,
                              native=native, before=before, records=records)
                pair.append(result)
                save(work / 'public.json', public)
                all_results.append(dict(case=case, enabled=enabled, exitcode=game.exitcode, native=native, before=before))
            compare_pair(*pair)
        assert originals == {p: digest(Path(p)) for p in originals}
        save(out / 'result.json', dict(status='PASS', scope='original main/moveloop with test-only first-dodrink baseline; not ordinary-play setup or complete turnloop acceptance', results=all_results))
        print(json.dumps(all_results, indent=2))
    finally:
        signal.alarm(0)
        for sig, handler in handlers.items():
            signal.signal(sig, handler)


class FatalDriverTests(unittest.TestCase):
    def test_c_fixture_is_required(self):
        self.assertTrue(Path(__file__).with_name('episode_fountain_fatal.c').is_file())


if __name__ == '__main__':
    main()
