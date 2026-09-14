"""Sidecar contract tests; all fixtures are synthetic unless named C integration."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
REQ = dict(v=1, id=1, mutation='ambient', value=1, duration=0, telegraph=1, at=1)

def event(seq=1, **kw):
    return dict(dict(v=1, seq=seq, turn=10, safe=1, event='safe_point', phase='result',
                    detail='pray', sanity=100, insight=0, budget=2, spent=0,
                    reserved=0, last_id=0), **kw)

def ack(seq=2, request=None, **kw):
    return event(seq, **dict(dict(event='ack', detail='ok', status='accepted',
        cost=1, expires=10, last_id=1, spent=1, budget=1,
        **{k:v for k,v in (request or REQ).items() if k != 'v'}), **kw))

def append(path, *records):
    with open(path, 'ab') as f:
        for r in records: f.write(json.dumps(r).encode()+b'\n')
    os.chmod(path, 0o600)

class DirectorTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('chaos'), 'director package missing')
        from chaos import protocol, director
        self.p, self.d = protocol, director
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)

    def test_schema_strict(self):
        self.assertEqual(self.p.parse_request(json.dumps(REQ).encode()), REQ)
        for key in REQ:
            r = dict(REQ); del r[key]
            with self.assertRaises(ValueError): self.p.parse_request(json.dumps(r).encode())
        bad = [dict(REQ, id=True), dict(REQ, id=0), dict(REQ, at=0), dict(REQ, id=2147483648),
               dict(REQ, value=4), dict(REQ, duration=1), dict(REQ, telegraph=0),
               dict(REQ, cost=0), dict(REQ, mutation='shell'), dict(REQ, value=1.0)]
        raw = json.dumps(REQ).encode()
        for r in bad:
            with self.subTest(r=r), self.assertRaises(ValueError): self.p.parse_request(json.dumps(r).encode())
        for r in [raw[:-1]+b',"id":1}', raw+b' '*512, raw.replace(b'"id": 1', b'"id": -0'),
                  raw.replace(b'ambient', b'ambi\\u0065nt'), b'[]', raw+b'{}']:
            with self.subTest(r=r), self.assertRaises(ValueError): self.p.parse_request(r)

    def test_reader_partial_tail_retains_bytes(self):
        path = self.path/'events.jsonl'; raw=json.dumps(event()).encode()+b'\n'
        path.write_bytes(raw[:35]); path.chmod(0o600)
        reader=self.d.EventReader(path)
        self.assertEqual(reader.read(), [])
        with path.open('ab') as f: f.write(raw[35:])
        self.assertEqual(reader.read(), [event()]); self.assertEqual(reader.read(), [])

    def test_reader_rejects_invalid_and_overlong(self):
        for raw in [b'[]\n', b'{"seq":true}\n', b'x'*4097, json.dumps(event(seq=True)).encode()+b'\n',
                    json.dumps(event()).encode()[:-1]+b',"v":1}\n']:
            path=self.path/'events.jsonl'; path.write_bytes(raw); path.chmod(0o600)
            with self.subTest(raw=raw[:50]), self.assertRaises(ValueError): self.d.EventReader(path).read()

    def test_reader_rewrite_truncation_and_caps(self):
        path=self.path/'events.jsonl'; append(path,event())
        r=self.d.EventReader(path); r.read()
        path.write_bytes(b'')
        with self.assertRaises(ValueError): r.read()
        append(path,event()); r=self.d.EventReader(path); r.read()
        path.write_text(json.dumps(event(turn=11))+'\n')
        with self.assertRaises(ValueError): r.read()
        with self.assertRaises(ValueError): self.d.EventReader(path,max_bytes=10).read()
        append(path,event(2))
        with self.assertRaises(ValueError): self.d.EventReader(path,max_events=1).read()

    def test_summary_redaction_and_rollback(self):
        s=self.d.State(); s.ingest(event(hidden_map='SECRET', detail='SECRET\u001b[31m'))
        self.assertNotIn('SECRET', s.summary()); self.assertNotIn('hidden_map',s.summary())
        with self.assertRaises(ValueError): s.ingest(event())
        with self.assertRaises(ValueError): s.ingest(event(2, safe=0))
        for i in range(2,102): s.ingest(event(i))
        self.assertLess(len(s.summary()), 4096)
        s.ingest(event(102,event='death',detail='quit')); self.assertTrue(s.ended)

    def test_budgets_and_seeded_eligibility(self):
        s=self.d.State(); s.ingest(event())
        a=self.d.RandomBackend(42); b=self.d.RandomBackend(42)
        self.assertEqual(a.choose(s,1,2), b.choose(s,1,2))
        self.assertEqual(a.choose(s,1,2)['mutation'],'ambient')
        s.ingest(event(2,budget=0,spent=2)); self.assertIsNone(a.choose(s,2,2))
        s=self.d.State(); s.ingest(event(sanity=80,budget=4))
        self.assertEqual(set(self.d.eligible(s,ordinary_food=True)),{'ambient','ward_efficacy','hunger_rate'})
        s.ingest(ack(request=dict(REQ,mutation='ward_efficacy',value=50,duration=5,telegraph=2),
                         sanity=80,budget=0,spent=4,reserved=4,cost=4,expires=15))
        s.ingest(event(3,sanity=0,budget=8,spent=4,reserved=4,last_id=1))
        self.assertNotIn('ward_efficacy', self.d.eligible(s,True))
        s.ingest(event(4,turn=15,sanity=0,budget=8,spent=4,reserved=0,last_id=1))
        self.assertIn('ward_efficacy',self.d.eligible(s,True))

    def test_atomic_mailbox_resume_no_clobber(self):
        box=self.d.Mailbox(self.path); self.addCleanup(box.close)
        s=self.d.State(); box.submit(REQ,s)
        target=self.path/'whisper.json'
        self.assertEqual(target.stat().st_mode & 0o777,0o600)
        with self.assertRaises(ValueError): box.submit(dict(REQ,id=2,at=2),s)
        s.ingest(event()); s.ingest(ack())
        box.submit(dict(REQ,id=2,at=2),s)
        self.assertEqual(json.loads(target.read_text())['id'],2)
        box.close()
        with self.d.Mailbox(self.path) as resumed:
            self.assertEqual(resumed.pending(s)['id'],2)
        target.unlink(); target.symlink_to(self.path/'victim')
        with self.d.Mailbox(self.path) as resumed:
            with self.assertRaises((ValueError,OSError)): resumed.pending(s)

    def test_run_resume_stale_and_finite_no_events(self):
        append(self.path/'events.jsonl',event(),ack(detail='schedule',status='rejected'))
        self.assertEqual(self.d.run(self.path,self.d.RandomBackend(2),max_runtime=.08,poll=.02)['submitted'],1)
        request=json.loads((self.path/'whisper.json').read_text())
        self.assertEqual((request['id'],request['at']),(2,2))
        self.assertEqual(self.d.run(self.path,self.d.RandomBackend(2),max_runtime=.08,poll=.02)['submitted'],0)
        append(self.path/'events.jsonl',event(3,event='death',detail='quit',last_id=1,spent=1,budget=1))
        self.assertEqual(self.d.run(self.path,self.d.RandomBackend(2),max_runtime=.08,poll=.02)['reason'],'death')

    def test_replay_requires_ack_and_projects_fields(self):
        journal=self.path/'whispers.jsonl'; evidence=self.path/'events.jsonl'
        append(journal,dict(REQ,status='admitted',turn=10,safe=1,secret='PRIVATE'))
        append(evidence,event())
        with self.assertRaises(ValueError): self.d.load_replay(journal,evidence)
        append(evidence,ack())
        self.assertEqual(self.d.load_replay(journal,evidence),[REQ])
        # IDs need not be contiguous: rejected IDs are consumed, never renumber.
        r=dict(REQ,id=3,at=4); append(journal,dict(r,status='admitted',turn=11,safe=4))
        append(evidence,event(3,last_id=2,safe=3,spent=1,budget=1),
               ack(4,r,last_id=3,safe=4,turn=11,spent=2,budget=0))
        self.assertEqual(self.d.load_replay(journal,evidence),[REQ,r])

    def test_cli_pack_real_c_admission(self):
        help_=subprocess.run(['python3','-m','chaos','--help'],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(help_.returncode,0,help_.stderr)
        subprocess.run(['python3','-m','chaos','pack','ambient','--run-dir',str(self.path),'--install-only'],cwd=ROOT,check=True,capture_output=True)
        exe=self.path/'io'
        subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror','-pedantic','-I'+str(ROOT/'include'),
            str(ROOT/'src/chaos_protocol.c'),str(ROOT/'src/chaos_io.c'),str(ROOT/'tests/chaos/io_harness.c'),'-o',str(exe)],check=True)
        result=json.loads(subprocess.check_output([str(exe),str(self.path),'normal']))
        self.assertEqual((result['spent'],result['telegraphs']),(1,1))
        evidence=[json.loads(x) for x in (self.path/'events.jsonl').read_text().splitlines()]
        self.assertTrue(any(e['event']=='ack' and e['status']=='accepted' for e in evidence))

if __name__=='__main__': unittest.main()
