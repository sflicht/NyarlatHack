#!/usr/bin/env python3
"""Structural source contract for N-W-ACTIVATION; not runtime proof."""
import argparse, hashlib, json, re, stat, sys
from pathlib import Path

BASE={
 "include/chaos.h":"6f88c919c2785ecb830b0aa69bd87d47ef1a430cce3f23ed48761dc0bdaa07e9",
 "include/wintty.h":"a85a3157ba4dc48878a496e549b0574c3073437e9f606552b0f1a882c2e811f3",
 "src/apply.c":"99751a11e888776f8ea9b849ceb8a8035247a133e072e8598a52db40a9ac3aeb",
 "src/chaos_engine.c":"0f14d4709a0027b670e62aad5f0100fc7d4e44cc75e790614e0733850737c151",
 "win/tty/wintty.c":"a1fa65e487766aab29841ae738f56848dac00a9ef17be6c7ddb081f3267e6d7f"}
HOOK="chaos_next_use_whistle_completed"; TTY="tty_snapshot_projectable"
PREFLIGHT="chaos_next_use_action_preflight"
FALSE_RETURN=r"\breturn\s+(?:0|FALSE)\s*;"
SOURCE_ROOTS=("src","include","win","util","sys")


def emit(status,code,missing=()):
 print(json.dumps({"checker":"N-W-ACTIVATION","code":code,"missing":list(missing),
  "scope":"source_completeness_only_not_semantic_acceptance","status":status},sort_keys=True,separators=(",",":")))


def scrub(s):
 """Blank C comments and literals while preserving offsets and newlines."""
 out=list(s); i=0; state="code"; quote=""
 while i<len(s):
  c=s[i]; n=s[i+1] if i+1<len(s) else ""
  if state=="code" and c=="/" and n=="*": out[i]=out[i+1]=" ";i+=2;state="block";continue
  if state=="code" and c=="/" and n=="/": out[i]=out[i+1]=" ";i+=2;state="line";continue
  if state=="code" and c in "\"'": quote=c;out[i]=" ";i+=1;state="string";continue
  if state=="block":
   if c=="*" and n=="/": out[i]=out[i+1]=" ";i+=2;state="code";continue
   if c!="\n": out[i]=" "
   i+=1;continue
  if state=="line":
   if c=="\n": state="code"
   else: out[i]=" "
   i+=1;continue
  if state=="string":
   if c=="\\" and i+1<len(s): out[i]=out[i+1]=" ";i+=2;continue
   if c==quote: state="code"
   if c!="\n": out[i]=" "
   i+=1;continue
  i+=1
 return "".join(out)


def matching(s,start,op,cl):
 depth=0
 for i in range(start,len(s)):
  if s[i]==op: depth+=1
  elif s[i]==cl:
   depth-=1
   if depth==0:return i
 return -1


def kr_declarations(s):
 parts=[x.strip() for x in s.split(";") if x.strip()]
 typ=re.compile(r"^(?:(?:register|const|volatile|static)\s+)*(?:struct\s+\w+|union\s+\w+|enum\s+\w+|unsigned|signed|short|long|int|char|boolean|void|xchar)\b",re.S)
 return bool(parts) and all(typ.match(re.sub(r"^\s*#.*?$","",x,flags=re.M).strip()) for x in parts)


def function_ranges(text,name):
 clean=scrub(text); out=[]
 for m in re.finditer(r"\b"+re.escape(name)+r"\s*\(",clean):
  op=clean.find("(",m.start()); close=matching(clean,op,"(",")")
  if close<0:continue
  p=close+1
  while p<len(clean) and clean[p].isspace():p+=1
  if p>=len(clean) or clean[p] in ";,":continue
  if clean[p]=="{": start=p
  else:
   start=clean.find("{",p,min(len(clean),p+4000))
   if start<0 or not kr_declarations(clean[p:start]):continue
  end=matching(clean,start,"{","}")
  if end>=0:out.append((m.start(),end+1,clean[start:end+1]))
 return out


def body(text,name):
 found=function_ranges(text,name)
 return found[0][2] if len(found)==1 else ""


def statement_end(s,start):
 while start<len(s) and s[start].isspace():start+=1
 if start>=len(s):return -1
 if s[start]=="{":return matching(s,start,"{","}")
 par=br=0
 for i in range(start,len(s)):
  c=s[i]
  if c=="(":par+=1
  elif c==")":par-=1
  elif c=="[":br+=1
  elif c=="]":br-=1
  elif c==";" and par==0 and br==0:return i
 return -1


def control_regions(s,kind):
 out=[]
 for m in re.finditer(r"\b"+kind+r"\s*\(",s):
  op=s.find("(",m.start()); close=matching(s,op,"(",")")
  if close<0:continue
  end=statement_end(s,close+1)
  if end>=0:out.append((m.start(),end+1,s[op+1:close],s[close+1:end+1]))
 return out


def calls(s,name):
 out=[]
 for m in re.finditer(r"\b"+re.escape(name)+r"\s*\(",s):
  op=s.find("(",m.start()); close=matching(s,op,"(",")")
  if close>=0:out.append((m.start(),close+1,s[op+1:close]))
 return out


def source_texts(root):
 out={}
 def visit(directory):
  for path in sorted(directory.iterdir(),key=lambda item:item.name):
   mode=path.stat(follow_symlinks=False).st_mode
   if stat.S_ISLNK(mode):continue
   if stat.S_ISDIR(mode):visit(path)
   elif stat.S_ISREG(mode) and path.suffix in (".c",".h"):
    out[path.relative_to(root).as_posix()]=path.read_bytes().decode("latin-1")
 for name in SOURCE_ROOTS:
  base=root/name
  try:mode=base.stat(follow_symlinks=False).st_mode
  except FileNotFoundError:continue
  if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):raise OSError("invalid source inventory root: "+name)
  visit(base)
 return out


def owner_ok(alltext,name,owner):
 defs=[]
 for path,text in alltext.items():
  defs.extend((path,x[0]) for x in function_ranges(text,name))
 return len(defs)==1 and defs[0][0]==owner


def enclosing(regions,pos):
 return [r for r in regions if r[0]<pos<r[1]]


def activation_flow(hook):
 cbs=calls(hook,"chaos_next_use_on_action")
 if len(cbs)!=1:return False,"EXACT_ONE_ACTION_CALLBACK"
 cb=cbs[0]; ifs=control_regions(hook,"if"); loops=control_regions(hook,"for")
 # Exactly one current-fmon traversal, with the canonical chain expression.
 floops=[r for r in loops if r[0]<cb[0] and re.search(r"\b\w+\s*=\s*fmon\b",r[2]) and re.search(r"->\s*nmon\b",r[2])]
 if len(floops)!=1 or not (floops[0][0]<cb[0]):return False,"ONE_PUBLIC_FMON_TRAVERSAL"
 loop=floops[0]
 preflights=calls(hook,PREFLIGHT)
 if len(preflights)!=1:return False,"EXACT_ONE_ACTION_PREFLIGHT"
 preflight=preflights[0]
 if preflight[0]>=loop[0]:return False,"PREFLIGHT_BEFORE_PUBLIC_SCAN"
 if not re.fullmatch(r"\s*CHAOS_NEXT_USE_FAMILY_W\s*,\s*completed_root\s*",preflight[2],re.S):
  return False,"PREFLIGHT_EXACT_TWO_PUBLIC_ARGUMENTS"
 if re.search(r"candidate|mtmp|fmon|glyph|mtyp|mtame|m_id|EDOG|PM_",preflight[2]):
  return False,"PREFLIGHT_HIDDEN_INPUT"
 preflight_guards=[r for r in ifs if r[0]<=preflight[0] and preflight[1]<=r[1]
                   and r[0]<=loop[0] and loop[1]<=r[1]
                   and PREFLIGHT in r[2]]
 if not preflight_guards:return False,"PREFLIGHT_RESULT_DOMINATES_PUBLIC_SCAN"
 positive=False
 for guard in preflight_guards:
  guard_calls=calls(guard[2],PREFLIGHT)
  if len(guard_calls)!=1:continue
  guarded_call=guard_calls[0]
  reduced=(guard[2][:guarded_call[0]]+" PREFLIGHT_SUCCESS "
           +guard[2][guarded_call[1]:])
  if not re.fullmatch(r"[A-Za-z0-9_\s()&]+",reduced,re.S):continue
  if re.search(r"(?<!&)&(?!&)",reduced):continue
  if len(re.findall(r"\bPREFLIGHT_SUCCESS\b",reduced))!=1:continue
  positive=True
 if not positive:return False,"PREFLIGHT_POSITIVE_SUCCESS_POLARITY"
 # One live conjunction inside that loop must select/count the callback candidate.
 required=(r"!\s*Hallucination",r"!\s*u\s*\.\s*uswallow",r"!\s*DEADMONSTER\s*\(",
  r"canseemon\s*\(",r"isok\s*\(",r"glyph_is_monster\s*\(",
  r"glyph_to_mon\s*\([^)]*\)\s*==\s*PM_LITTLE_DOG",r"tty_snapshot_projectable\s*\(")
 selectors=[]
 for r in ifs:
  if not (loop[0]<r[0] and r[1]<=loop[1]):continue
  inherited=" ".join(x[2] for x in enclosing(ifs,r[0]))+" "+r[2]
  stmt=r[3]
  glyph_assign=re.search(r"\b(\w+)\s*=\s*glyph_at\s*\(\s*(\w+)\s*->\s*mx\s*,\s*\2\s*->\s*my\s*\)\s*;",hook[loop[0]:r[0]])
  bound_glyph=(glyph_assign and re.search(r"glyph_is_monster\s*\(\s*"+re.escape(glyph_assign.group(1))+r"\s*\)",inherited)
               and re.search(r"tty_snapshot_projectable\s*\([^,]+,[^,]+,\s*"+re.escape(glyph_assign.group(1))+r"\s*\)",inherited))
  if all(re.search(p,inherited,re.S) for p in required) and bound_glyph and re.search(r"(?:\w+\s*=\s*\w+\s*;|\+\+\s*\w*(?:count|candidates)|\w*(?:count|candidates)\s*\+\+)",stmt,re.I):selectors.append(r)
 if len(selectors)!=1:return False,"EXACT_RENDERED_PUBLIC_PREDICATE"
 selector=selectors[0]
 # The callback branch must require exactly one selected candidate and contain that callback.
 cbguards=[r for r in enclosing(ifs,cb[0]) if re.search(r"(?:count|candidates?)\w*\s*==\s*1|1\s*==\s*\w*(?:count|candidates?)",r[2],re.I)]
 if len(cbguards)!=1:return False,"PUBLIC_CARDINALITY_DOMINATES_CALLBACK"
 branch=cbguards[0]
 loopmatch=re.search(r"\b(\w+)\s*=\s*fmon\b",loop[2])
 if loopmatch is None:return False,"ONE_PUBLIC_FMON_TRAVERSAL"
 loopvar=loopmatch.group(1)
 assignment=re.search(r"\b(\w+)\s*=\s*"+re.escape(loopvar)+r"\s*;",selector[3])
 if not assignment:return False,"PUBLIC_CANDIDATE_BOUND_TO_CALLBACK"
 candidate=assignment.group(1)
 if selector[0]>=branch[0] or re.search(r"\b(?:"+re.escape(candidate)+r"|"+re.escape(loopvar)+r")\b",cb[2]):return False,"PUBLIC_CANDIDATE_LEAKED_TO_CALLBACK"
 # Tool validation must dominate both the scan and callback, directly or through
 # one boolean whose defining conjunction precedes the scan.
 prefix=hook[:loop[0]]
 tool=(r"\binvent\b",r"obj\s*->\s*where\s*==\s*OBJ_INVENT",r"obj\s*->\s*otyp\s*==\s*WHISTLE",
       r"obj\s*->\s*known",r"!\s*obj\s*->\s*oartifact",r"obj\s*->\s*quan\s*==\s*1L?")
 direct_tool=any(r[0]<loop[0] and cb[0]<r[1] and all(re.search(p,r[2],re.S) for p in tool) for r in ifs)
 bound_tool=False
 for m in re.finditer(r"\b(\w*(?:tool|whistle|eligible|valid)\w*)\s*=\s*([^;]+);",prefix,re.I|re.S):
  if all(re.search(p,m.group(2),re.S) for p in tool):
   bound_tool=any(r[0]<loop[0] and cb[0]<r[1] and re.search(r"\b"+re.escape(m.group(1))+r"\b",r[2]) for r in ifs)
 if not (direct_tool or bound_tool):return False,"EXACT_TOOL_PUBLIC_PREDICATE"
 if re.search(r"->\s*(?:mtyp|data|m_ap_type|mappearance|mtame|m_id)\b|\bEDOG\s*\(",hook[:cb[1]]):return False,"PRIVATE_FIELD_IN_PUBLIC_PREDICATE"
 # A successful callback must guard all subsequent private work in the same branch.
 result_guards=[r for r in enclosing(ifs,cb[0]) if r[1]>cb[1] and ("chaos_next_use_on_action" in r[2] or re.search(r"\b(?:intent|accepted|attention)\b",r[2],re.I))]
 if not result_guards:return False,"CALLBACK_RESULT_DOES_NOT_CONTROL_CAPTURE"
 live=result_guards[-1]; tail=hook[cb[1]:live[1]]
 # No stale candidate dereference before a fresh fmon membership loop sets a boolean.
 member_loops=[r for r in control_regions(tail,"for") if re.search(r"=\s*fmon\b",r[2]) and re.search(r"->\s*nmon\b",r[2]) and re.search(r"(?:==\s*"+re.escape(candidate)+r"\b|\b"+re.escape(candidate)+r"\s*==)",r[3])]
 if len(member_loops)!=1:return False,"POSTCALLBACK_POINTER_REVALIDATION"
 ml=member_loops[0]; before=tail[:ml[1]]
 if re.search(r"\b"+re.escape(candidate)+r"\s*->",before):return False,"STALE_POINTER_DEREFERENCE"
 species=list(re.finditer(r"\b"+re.escape(candidate)+r"\s*->\s*mtyp\s*==\s*PM_LITTLE_DOG",tail))
 if len(species)!=1 or species[0].start()<=ml[1]:return False,"SOLE_PRIVATE_SPECIES_CHECK"
 member_set=re.search(r"\b(\w*(?:member|found|current|resident)\w*)\s*=\s*(?:1|TRUE)\s*;",ml[3],re.I)
 if member_set is None:return False,"MEMBERSHIP_GUARD_BEFORE_PRIVATE_CAPTURE"
 private_guards=[r for r in control_regions(tail,"if") if r[0]<species[0].start()<r[1]]
 if not any(re.search(r"\b"+re.escape(member_set.group(1))+r"\b",r[2]) for r in private_guards):return False,"MEMBERSHIP_GUARD_BEFORE_PRIVATE_CAPTURE"
 if not re.search(r"(?:capture|arm|reserve|m_id|run_token|level_token)",tail[species[0].end():],re.I):return False,"PRIVATE_CAPTURE_AFTER_SPECIES"
 return True,""


def tty_flow(ttybody):
 if not ttybody:return False
 forbidden=r"\b(?:rn2|rnd|rn1|rnl|random_monster|what_mon|newsym|show_glyph|flush_screen|tty_print_glyph|putstr|pline)\s*\("
 if re.search(forbidden,ttybody):return False
 if re.search(r"\breturn\s+(?:1|TRUE)\s*;",ttybody) is None:return False
 ifs=control_regions(ttybody,"if")
 # Positive support must be earned after fail-closed window/map/coordinate/glyph checks.
 support=any(re.search(r"(?:windowprocs\s*\.\s*win_print_glyph|tty_procs|tty_print_glyph|WIN_MAP)",r[2]) and re.search(FALSE_RETURN,r[3]) for r in ifs)
 bounds=any(re.search(r"\b[xy]\b",r[2]) and re.search(r"(?:isok|clip|clipx|clipy|COLNO|ROWNO|cols|rows|offx|offy)",r[2]) and re.search(FALSE_RETURN,r[3]) for r in ifs)
 glyph=any(re.search(r"\bglyph\b",r[2]) and re.search(r"(?:glyph_at|gbuf|expected|!=|==)",r[2]) and re.search(FALSE_RETURN,r[3]) for r in ifs)
 init=bool(re.search(r"(?:ttyDisplay|wins\s*\[\s*WIN_MAP\s*\]|WIN_MAP\s*==\s*WIN_ERR)",ttybody))
 return support and bounds and glyph and init


def main():
 ap=argparse.ArgumentParser();ap.add_argument("--root",required=True);root=Path(ap.parse_args().root)
 if not root.is_dir():emit("ERROR","INVALID_ROOT");return 2
 paths={n:root/n for n in BASE}
 if any(not p.is_file() for p in paths.values()):emit("ERROR","MISSING_ACTIVATION_FIXTURE_PATH");return 2
 try:raw={n:p.read_bytes() for n,p in paths.items()};t={n:b.decode("utf-8") for n,b in raw.items()}
 except (OSError,UnicodeError):emit("ERROR","UNREADABLE_ACTIVATION_SOURCE");return 2
 joined="\n".join(t.values())
 if HOOK not in joined and TTY not in joined:
  if any(hashlib.sha256(raw[n]).hexdigest()!=h for n,h in BASE.items()):emit("ERROR","BASELINE_ACTIVATION_HASH_MISMATCH");return 2
  emit("RED","MISSING_ACTIVATION_SLICE",("WHISTLE_COMPLETION_HOOK","PUBLIC_RENDERED_PREDICATE","POSTCALLBACK_POINTER_REVALIDATION","TTY_SNAPSHOT_PROJECTABLE"));return 1
 try:alltext=source_texts(root)
 except (OSError,UnicodeError):emit("ERROR","UNREADABLE_TRACKED_ACTIVATION_SOURCE");return 2
 miss=[];apply=scrub(t["src/apply.c"]);engine=t["src/chaos_engine.c"]
 case=re.search(r"\bcase\s+WHISTLE\s*:(.*?)(?=\bcase\s+\w+\s*:|\bswitch\s*\(|\Z)",apply,re.S);case=case.group(1) if case else ""
 seq=(case.find("use_whistle"),case.find("chaos_observation_end"),case.find(HOOK))
 if min(seq)<0 or not seq[0]<seq[1]<seq[2] or len(calls(case,HOOK))!=1:miss.append("COMPLETED_WHISTLE_HOOK_ORDER")
 if not owner_ok(alltext,HOOK,"src/chaos_engine.c") or not owner_ok(alltext,TTY,"win/tty/wintty.c"):miss.append("FOREIGN_OR_DUPLICATE_ACTIVATION_OWNER")
 hook=body(engine,HOOK); ok,why=activation_flow(hook) if hook else (False,"ACTIVATION_HOOK_DEFINITION")
 if not ok:miss.append(why)
 forbidden=r"\b(?:rn2|rnd|rn1|rnl|random_monster|what_mon|newsym|show_glyph|flush_screen)\s*\("
 if hook and re.search(forbidden,hook):miss.append("ACTIVATION_RNG_OR_REDRAW")
 ttydecl=scrub(t["include/wintty.h"]);ttybody=body(t["win/tty/wintty.c"],TTY)
 if not re.search(r"boolean\s+"+TTY+r"\s*\(\s*xchar\s+\w+\s*,\s*xchar\s+\w+\s*,\s*int\s+\w+\s*\)\s*;",ttydecl):miss.append("TTY_PROJECTABLE_DECLARATION")
 if not tty_flow(ttybody):miss.append("TTY_PROJECTABLE_POSITIVE_FAIL_CLOSED_CHECK")
 if miss:emit("RED","MISSING_ACTIVATION_SLICE",tuple(dict.fromkeys(miss)));return 1
 emit("GREEN","ACTIVATION_SLICE_COMPLETE");return 0

if __name__=="__main__":
 try:sys.exit(main())
 except Exception as e:emit("ERROR","CHECKER_ERROR_"+type(e).__name__.upper());sys.exit(2)
