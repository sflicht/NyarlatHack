from pathlib import Path
import sys,tempfile,subprocess,shutil,json
sys.path.insert(0,'/home/hermes/nyarlathack/tests/chaos')
from gameplay_support import Game
repo=Path('/home/hermes/nyarlathack');root=Path(tempfile.mkdtemp(prefix='nyarl-m2-extra-'));clock=root/'clock.so'
subprocess.run(['cc','-shared','-fPIC',str(repo/'tests/chaos/replay_clock.c'),'-o',str(clock),'-ldl'],check=True)
old=Path.home()/'.local/share/nyarlathack/baselines/28bf1b192'
current=repo/'dnethackdir';results={}
for name,first,second in [('old-new',old,current),('new-old',current,old)]:
 g=Game(first,clock,wizard=True,root=root/name)
 try:
  g.start();g.wait_turns(2);assert g.save()==0
  for file in ('dnethack','nhdat'):shutil.copy2(second/file,g.game/file)
  g.start();assert b'Configuration incompatibility' in g.raw
  assert not any(e['event']=='session' and e['detail']=='restore' for e in g.events())
  assert g.quit()==0;results[name]='configuration rejected'
 finally:g.close()
games=[]
for name,source,observe in [('stock',Path('/tmp/nyarlathack-m2-off'),False),('inactive',current,False),('empty',current,True)]:
 g=Game(source,clock,wizard=True,observe=observe,root=root/name)
 try:
  g.start()
  for key in 'lhlhjkjklhlh':g.more(g.send(key))
  assert g.quit()==0;games.append(g)
 finally:g.close()
for g in games[1:]:
 assert g.inputs==games[0].inputs
 assert g.raw==games[0].raw
 assert (g.game/'xlogfile').read_bytes()==(games[0].game/'xlogfile').read_bytes()
results['backtracking_stock_comparison']='inputs, terminal and score logs identical'
results['artifacts']=str(root)
(repo/'docs/evidence/milestone2-extra-checks.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
