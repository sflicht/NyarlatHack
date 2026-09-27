#!/usr/bin/env python3
"""Structural N-W-MANIFEST source contract; never compiles or runs candidates."""
import argparse, hashlib, json, re, stat, sys
from pathlib import Path

BASE={
 "include/chaos.h":"6f88c919c2785ecb830b0aa69bd87d47ef1a430cce3f23ed48761dc0bdaa07e9",
 "include/extern.h":"601d032e45fbf34dae3664381066b8af2537856cd9a5f9c29804ac2a09475e80",
 "include/wintty.h":"a85a3157ba4dc48878a496e549b0574c3073437e9f606552b0f1a882c2e811f3",
 "src/chaos_engine.c":"0f14d4709a0027b670e62aad5f0100fc7d4e44cc75e790614e0733850737c151",
 "src/dogmove.c":"5221df0f6fedd4cbf26de35c970327e669407354cfedddc32c2c34f67d3897dc",
 "src/monmove.c":"167051fa8b33b37ca87e8ea26835f4066d547ca945903c02f70fcc0e3a757ee5",
 "src/pline.c":"4124fcf073430426c96c05f57d336649af78073c9e45543886b575f169ca6428",
 "src/display.c":"ffdf201f8face9f2906bf087f9424dcf16e5d042f45ee576eba10426215c268f",
 "win/tty/topl.c":"69d0e0ce395944b8edfd2ef560c9acdb130fc61f1a5728e593afe4ba03511d68",
 "win/tty/wintty.c":"a1fa65e487766aab29841ae738f56848dac00a9ef17be6c7ddb081f3267e6d7f"}
FIXED="The whistle's echo sharpens your visible companion's attention."
FIELDS=("root","notice_seq","message_token","oldx","oldy","newx","newy","pre_glyph","post_glyph","production","active","classifier_ok","pre_public","manifestation_delivered","displaced","invalid","finalized")
MESSAGE="chaos_whistle_attention_message"; CERT="chaos_tty_publication_certificate"; FINAL="chaos_whistle_witness_finalize"
POLICY=("chaos_next_use_on_action","chaos_lua_next_use_on_action")
SOURCE_ROOTS=("src","include","win","util","sys")


def emit(status,code,missing=()):
 print(json.dumps({"checker":"N-W-MANIFEST","code":code,"missing":list(missing),"scope":"source_completeness_only_not_semantic_acceptance","status":status},sort_keys=True,separators=(",",":")))


def scrub(s):
 out=list(s);i=0;state="code";quote=""
 while i<len(s):
  c=s[i];n=s[i+1] if i+1<len(s) else ""
  if state=="code" and c=="/" and n=="*":out[i]=out[i+1]=" ";i+=2;state="block";continue
  if state=="code" and c=="/" and n=="/":out[i]=out[i+1]=" ";i+=2;state="line";continue
  if state=="code" and c in "\"'":quote=c;out[i]=" ";i+=1;state="string";continue
  if state=="block":
   if c=="*" and n=="/":out[i]=out[i+1]=" ";i+=2;state="code";continue
   if c!="\n":out[i]=" "
   i+=1;continue
  if state=="line":
   if c=="\n":state="code"
   else:out[i]=" "
   i+=1;continue
  if state=="string":
   if c=="\\" and i+1<len(s):out[i]=out[i+1]=" ";i+=2;continue
   if c==quote:state="code"
   if c!="\n":out[i]=" "
   i+=1;continue
  i+=1
 return "".join(out)


def matching(s,start,op,cl):
 d=0
 for i in range(start,len(s)):
  if s[i]==op:d+=1
  elif s[i]==cl:
   d-=1
   if d==0:return i
 return -1


def kr_declarations(s):
 parts=[x.strip() for x in s.split(";") if x.strip()]
 typ=re.compile(r"^(?:(?:register|const|volatile|static)\s+)*(?:struct\s+\w+|union\s+\w+|enum\s+\w+|unsigned|signed|short|long|int|char|boolean|void|xchar|winid)\b",re.S)
 return bool(parts) and all(typ.match(re.sub(r"^\s*#.*?$","",x,flags=re.M).strip()) for x in parts)


def function_ranges(text,name):
 clean=scrub(text);out=[]
 for m in re.finditer(r"\b"+re.escape(name)+r"\s*\(",clean):
  op=clean.find("(",m.start());cl=matching(clean,op,"(",")")
  if cl<0:continue
  p=cl+1
  while p<len(clean) and clean[p].isspace():p+=1
  if p>=len(clean) or clean[p] in ";,":continue
  if clean[p]=="{":st=p
  else:
   st=clean.find("{",p,min(len(clean),p+4000))
   if st<0 or not kr_declarations(clean[p:st]):continue
  en=matching(clean,st,"{","}")
  if en>=0:out.append((m.start(),en+1,clean[st:en+1]))
 return out


def body(text,name):
 f=function_ranges(text,name);return f[0][2] if len(f)==1 else ""


def statement_end(s,start):
 while start<len(s) and s[start].isspace():start+=1
 if start>=len(s):return -1
 if s[start]=="{":return matching(s,start,"{","}")
 par=br=0
 for i in range(start,len(s)):
  if s[i]=="(":par+=1
  elif s[i]==")":par-=1
  elif s[i]=="[":br+=1
  elif s[i]=="]":br-=1
  elif s[i]==";" and par==0 and br==0:return i
 return -1


def conditional_end(s,kind,en):
 if kind!="if":return en
 p=en+1
 while p<len(s) and s[p].isspace():p+=1
 if not (s.startswith("else",p) and (p+4==len(s) or not (s[p+4].isalnum() or s[p+4]=="_"))):return en
 extended=statement_end(s,p+4)
 return extended if extended>=0 else en


def without_preprocessor_conditionals(s):
 out=[];depth=0;continuation=False
 for line in s.splitlines(True):
  stripped=line.lstrip()
  is_if=bool(re.match(r"#\s*(?:if|ifdef|ifndef)\b",stripped))
  is_end=bool(re.match(r"#\s*endif\b",stripped))
  directive=stripped.startswith("#") or continuation
  blank=depth>0 or directive
  if is_if:depth+=1;blank=True
  elif is_end:depth=max(0,depth-1);blank=True
  continuation=directive and line.rstrip("\n").rstrip().endswith("\\")
  if blank:out.append("".join("\n" if ch=="\n" else " " for ch in line))
  else:out.append(line)
 return "".join(out)


def preprocessor_depth_at(s,pos):
 depth=0
 for line in s[:pos].splitlines():
  stripped=line.lstrip()
  if re.match(r"#\s*(?:if|ifdef|ifndef)\b",stripped):depth+=1
  elif re.match(r"#\s*endif\b",stripped):depth=max(0,depth-1)
 return depth


def if_regions(s):
 out=[]
 for m in re.finditer(r"\bif\s*\(",s):
  op=s.find("(",m.start());cl=matching(s,op,"(",")")
  if cl<0:continue
  en=statement_end(s,cl+1)
  if en>=0:
   en=conditional_end(s,"if",en)
   out.append((m.start(),en+1,s[op+1:cl],s[cl+1:en+1]))
 return out


def control_regions(s):
 out=[]
 for m in re.finditer(r"\b(if|for|while|switch)\s*\(",s):
  op=s.find("(",m.start());cl=matching(s,op,"(",")")
  if cl<0:continue
  en=statement_end(s,cl+1)
  if en>=0:
   en=conditional_end(s,m.group(1),en)
   out.append((m.start(),en+1,m.group(1),s[op+1:cl],s[cl+1:en+1]))
 return out


def split_top_level(s,operator):
 out=[];start=0;par=br=0;i=0
 while i<len(s):
  if s[i]=="(":par+=1
  elif s[i]==")":par-=1
  elif s[i]=="[":br+=1
  elif s[i]=="]":br-=1
  elif par==0 and br==0 and s.startswith(operator,i):
   out.append(s[start:i]);start=i+len(operator);i+=len(operator)-1
  i+=1
 out.append(s[start:]);return out


def calls(s,name):
 out=[]
 for m in re.finditer(r"\b"+re.escape(name)+r"\s*\(",s):
  op=s.find("(",m.start());cl=matching(s,op,"(",")")
  if cl>=0:out.append((m.start(),cl+1,s[op+1:cl]))
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


def owner_paths(alltext,name):
 found=[]
 for path,text in alltext.items():found.extend(path for _ in function_ranges(text,name))
 return found


def callsites(alltext,name):
 out=[]
 for path,text in alltext.items():
  clean=scrub(text);defs=[(x[0],x[1]) for x in function_ranges(text,name)]
  for c in calls(clean,name):
   if any(st<=c[0]<en for st,en in defs):continue
   p=c[1]
   while p<len(clean) and clean[p].isspace():p+=1
   # Function declarations are excluded by a type/declaration prefix.
   line=clean[clean.rfind("\n",0,c[0])+1:c[0]]
   prototype=(p<len(clean) and clean[p]==";" and re.search(r"\b(?:int|void|boolean|FDECL)\s*$",line))
   if not prototype:out.append((path,c[0]," ".join(c[2].split())))
 return out


def in_dead_branch(s,pos):
 return any(st<pos<en and re.fullmatch(r"\s*(?:0|FALSE)\s*",cond) for st,en,cond,_ in if_regions(s))


def carrier_contract(header):
 sm=re.search(r"struct\s+chaos_whistle_witness\s*\{(.*?)\}\s*;",header,re.S)
 if not sm:return False
 block=sm.group(1);names=[]
 for declaration in block.split(";"):
  declaration=declaration.strip()
  if not declaration:continue
  declaration=re.sub(r"^(?:long|int|boolean|xchar|struct\s+\w+)\s+","",declaration)
  for item in declaration.split(","):
   match=re.search(r"\b([A-Za-z_]\w*)\s*$",item.strip())
   if match:names.append(match.group(1))
 if tuple(names)!=FIELDS or "*" in block:return False
 types=(r"long\s+root\s*,\s*notice_seq",r"struct\s+chaos_observation_token\s+message_token",
  r"xchar\s+oldx\s*,\s*oldy\s*,\s*newx\s*,\s*newy",r"int\s+pre_glyph\s*,\s*post_glyph",
  r"boolean\s+production\s*,\s*active\s*,\s*classifier_ok\s*,\s*pre_public",
  r"boolean\s+manifestation_delivered\s*,\s*displaced\s*,\s*invalid\s*,\s*finalized")
 return all(re.search(x,block) for x in types)


def dog_call_closure(alltext,mon):
 sites=callsites(alltext,"dog_move")
 nonnull=[]
 for path,pos,args in sites:
  pieces=[x.strip() for x in args.split(",")]
  if len(pieces)!=3:return False
  third=pieces[2]
  if not re.fullmatch(r"(?:0|NULL|\(\s*struct\s+chaos_whistle_witness\s*\*\s*\)\s*0)",third):nonnull.append((path,pos,third))
 if len(nonnull)!=1 or nonnull[0][0]!="src/monmove.c" or nonnull[0][2] not in ("&witness","& witness"):return False
 if not sites or not any(len(x[2].split(","))==3 and x[2].split(",")[2].strip() in ("0","NULL","( struct chaos_whistle_witness * ) 0","(struct chaos_whistle_witness * ) 0","(struct chaos_whistle_witness *) 0") for x in sites):return False
 decl=re.findall(r"struct\s+chaos_whistle_witness\s+witness\s*=\s*\{\s*0\s*\}\s*;",mon)
 return len(decl)==1


def m_move_convergence(mon):
 pro=[c for c in calls(mon,"dog_move") if re.search(r",\s*&\s*witness\s*$",c[2])]
 if len(pro)!=1:return False
 call=pro[0];finals=[c for c in calls(mon,FINAL) if c[0]>call[1]]
 if len(finals)!=1 or not re.fullmatch(r"\s*mtmp\s*,\s*&\s*witness\s*",finals[0][2]):return False
 fin=finals[0];post=mon[call[1]:]
 # Canonical source-bound convergence: no post-call return precedes the sole finalizer;
 # all early paths target one cleanup label immediately owning that call.
 if re.search(r"\breturn\b",mon[call[1]:fin[0]]):return False
 gotos=list(re.finditer(r"\bgoto\s+(\w+)\s*;",mon[call[1]:fin[0]]))
 labels=re.findall(r"\b(\w+)\s*:\s*"+FINAL+r"\s*\(",mon[call[1]:])
 if gotos and (len(set(g.group(1) for g in gotos))!=1 or len(labels)!=1 or next(iter(set(g.group(1) for g in gotos)))!=labels[0]):return False
 # The sole post-call raw return belongs to the finalizer macro body; every path
 # invokes that macro rather than returning directly.
 returns=[call[1]+m.start() for m in re.finditer(r"\breturn\b",mon[call[1]:])]
 macro_start=mon.find("#define CHAOS_MANIFEST_RETURN",call[1])
 macro_end=mon.find("while (0)",macro_start)
 if not (len(returns)==1 and macro_start>=0 and macro_end>macro_start
         and macro_start<returns[0]<macro_end and fin[1]<returns[0]
         and not in_dead_branch(mon,fin[0])):return False
 terminal=[c for c in calls(mon,"CHAOS_MANIFEST_RETURN")
           if re.fullmatch(r"\s*mmoved\s*",c[2],re.S)]
 if len(terminal)!=1:return False
 if preprocessor_depth_at(mon,terminal[0][0])!=0:return False
 scope_mon=scrub(without_preprocessor_conditionals(mon))
 if any(st<=terminal[0][0]<en for st,en,_,_,_ in control_regions(scope_mon)):return False
 outer_depth=1 if scope_mon.lstrip().startswith("{") else 0
 prefix=scope_mon[:terminal[0][0]]
 if prefix.count("{")-prefix.count("}")!=outer_depth:return False
 newsyms=calls(mon,"newsym")
 if newsyms and terminal[0][0] <= max(c[1] for c in newsyms):return False
 tail=mon[terminal[0][1]:]
 tail=re.sub(r"(?m)^\s*#.*$","",tail)
 return not re.sub(r"[\s{};]","",tail)


def dog_root_flow(dog):
 goals=calls(dog,"dog_goal")
 if len(goals)!=1 or not re.search(r"whappr\s*\|\|\s*extra_attention",goals[0][2]):return False
 begins=calls(dog,"chaos_observation_begin_exclusive")
 ready=calls(dog,"chaos_next_use_whistle_decision_ready")
 no_root=calls(dog,"chaos_next_use_whistle_no_root")
 attention=calls(dog,"chaos_next_use_whistle_attention")
 if len(begins)!=1 or len(ready)!=1 or len(no_root)!=1 or len(attention)!=1:return False
 if "CHAOS_OBS_OP_WHISTLE_ATTENTION" not in begins[0][2] or in_dead_branch(dog,begins[0][0]):return False
 if not (ready[0][0]<begins[0][0]<no_root[0][0]<attention[0][0]<goals[0][0]):return False
 if not re.search(r"m_id",ready[0][2]+no_root[0][2]) or not (re.search(r"m_id",attention[0][2]) and re.search(r"manifestation_root",attention[0][2])):return False
 begin_guards=[r for r in if_regions(dog) if r[0]<begins[0][0]<r[1]]
 if not any(re.search(r"whistle_decision_ready",r[2]) and re.search(r"witness",r[2])
            and re.search(r"witness\s*->\s*(?:root|active)",r[3]) for r in begin_guards):return False
 if not any(re.search(r"chaos_observation_begin_exclusive",r[2])
            and re.search(r"\belse\b",r[3])
            and re.search(r"chaos_next_use_whistle_no_root\s*\(",r[3])
            for r in if_regions(dog)):return False
 public_exact=(r"canseemon",r"!\s*Hallucination",r"!\s*u\s*\.\s*uswallow",
  r"glyph_at",r"glyph_is_monster",r"glyph_to_mon\s*\([^)]*\)\s*==\s*PM_LITTLE_DOG",r"tty_snapshot_projectable")
 pre_public=None
 for m in re.finditer(r"\b(\w*pre_public\w*)\s*=\s*([^;]+);",dog[:begins[0][0]],re.I|re.S):
  if all(re.search(x,m.group(2),re.S) for x in public_exact):pre_public=m.group(1);break
 if not pre_public:return False
 post=dog[goals[0][1]:]
 decision_exact=(r"whappr\s*==\s*0",r"extra_attention\s*!=\s*0",r"appr\s*!=\s*-\s*2",r"gtyp\s*==\s*UNDEF",
  r"gx\s*==\s*u\s*\.\s*ux",r"gy\s*==\s*u\s*\.\s*uy",r"\b"+re.escape(pre_public)+r"\b")
 classifier=None;classifier_pos=-1
 for m in re.finditer(r"\b(\w*(?:classifier|qualif|manifest)\w*)\s*=\s*([^;]+);",post,re.I|re.S):
  if all(re.search(x,m.group(2),re.S) for x in decision_exact):
   classifier=m.group(1);classifier_pos=goals[0][1]+m.start();break
 if not classifier:return False
 messages=calls(dog,MESSAGE)
 if len(messages)!=1 or messages[0][0]<=classifier_pos:return False
 if not any(r[0]<messages[0][0]<r[1] and re.search(r"\b"+re.escape(classifier)+r"\b",r[2]) for r in if_regions(dog)):return False
 finishes=calls(dog,"chaos_observation_finish")
 if len(finishes)!=1 or finishes[0][0]<=classifier_pos:return False
 root=dog[begins[0][0]:max(messages[0][1],finishes[0][1])]
 return not any(x in root for x in POLICY)


def message_flow(raw,clean):
 if not clean or raw.count(FIXED)!=1:return False
 pcalls=calls(clean,"pline")+calls(clean,"pline_The")
 facts=calls(clean,"chaos_observation_arm")
 if len(pcalls)!=1 or len(facts)!=1 or "CHAOS_OBS_FACT_ATTENTION" not in facts[0][2]:return False
 if facts[0][0]>pcalls[0][0]:return False
 if len(calls(clean,"chaos_observation_notice"))>1:return False
 # Token/root/fact validation must fail closed before emission and delivery controls notice/success.
 guards=[r for r in if_regions(clean) if r[0]<pcalls[0][0] and re.search(r"(?:token|root|fact|supported|tty|deliver)",r[2],re.I) and re.search(r"\breturn\s+(?:0|FALSE)\s*;",r[3])]
 return bool(guards) and not in_dead_branch(clean,pcalls[0][0])


def tty_certificate_flow(cert,printer):
 fc=calls(cert,"flush_screen")
 if len(fc)!=1 or not re.fullmatch(r"\s*0\s*",fc[0][2]) or in_dead_branch(cert,fc[0][0]):return False
 if re.search(r"\b(?:rn2|rnd|rn1|rnl|newsym|show_glyph|print_glyph)\s*\(",cert):return False
 ifs=if_regions(cert)
 required=(r"(?:windowprocs\s*\.\s*win_print_glyph|tty_print_glyph|tty_procs)",r"(?:delay_flushing|flush_screen)",r"(?:observer|certificate)",r"\bx\b",r"\by\b",r"expected_glyph",r"(?:glyph_at|gbuf)",r"(?:clip|COLNO|ROWNO|rows|cols)",r"!\s*wins\s*\[\s*WIN_MAP\s*\](?!\s*->)",r"wins\s*\[\s*WIN_MAP\s*\]\s*->\s*active",r"wins\s*\[\s*WIN_MAP\s*\]\s*->\s*type\s*!=\s*NHW_MAP")
 for pat in required:
  if not any(re.search(pat,r[2],re.I) and re.search(r"\breturn\s+(?:0|FALSE)\s*;",r[3]) for r in ifs):return False
 effective_null=[]
 scope_cert=scrub(without_preprocessor_conditionals(cert))
 outer_depth=1 if scope_cert.lstrip().startswith("{") else 0
 all_controls=control_regions(scope_cert)
 null_atom=r"\s*\(*\s*!\s*wins\s*\[\s*WIN_MAP\s*\](?!\s*->)\s*\)*\s*"
 for st,en,condition,statement in ifs:
  if preprocessor_depth_at(cert,st)!=0:continue
  prefix=scope_cert[:st]
  if prefix.count("{")-prefix.count("}")!=outer_depth:continue
  if any(outer_st<st<outer_en for outer_st,outer_en,_,_,_ in all_controls):continue
  if not re.search(r"\breturn\s+(?:0|FALSE)\s*;",statement):continue
  if any(re.fullmatch(null_atom,term,re.I|re.S) for term in split_top_level(condition,"||")):
   local_null=re.search(r"!\s*wins\s*\[\s*WIN_MAP\s*\](?!\s*->)",condition)
   local_deref=re.search(r"wins\s*\[\s*WIN_MAP\s*\]\s*->",condition)
   if not local_null:continue
   if local_deref and local_null.start()>local_deref.start():continue
   effective_null.append(st)
 first_deref=re.search(r"wins\s*\[\s*WIN_MAP\s*\]\s*->",scope_cert)
 if not effective_null or not first_deref or min(effective_null)>first_deref.start():return False
 before=cert[:fc[0][0]];after=cert[fc[0][1]:]
 if not re.search(r"(?:observer|certificate)\w*\s*=\s*&?\s*\w+\s*;",before,re.I):return False
 if not re.search(r"(?:observer|certificate)\w*\s*=\s*(?:0|NULL|\([^)]*\)0)\s*;",after,re.I):return False
 if not re.search(r"\breturn\s+\w+\s*\.\s*seen\s*;|\breturn\s+(?:observer|certificate)\w*\s*->\s*seen\s*;",after,re.I):return False
 # tty_print_glyph must bind observer success to the exact post-clipping emitted tuple.
 clipret=re.search(r"\bif\s*\([^)]*(?:clip|clipx|clipy)[^)]*\)[^{;]*\{?\s*return\s*;",printer,re.S)
 emitters=[m for m in re.finditer(r"\b(?:g_putch|pututf8char|xputg)\s*\(",printer)]
 seen=re.search(r"(?:observer|certificate)\w*\s*->\s*seen\s*=\s*(?:1|TRUE)\s*;",printer,re.I)
 bound=(r"window\s*==\s*WIN_MAP",r"\bx\s*==\s*(?:observer|certificate)\w*\s*->\s*x",r"\by\s*==\s*(?:observer|certificate)\w*\s*->\s*y",r"glyph\s*==\s*(?:observer|certificate)\w*\s*->\s*(?:glyph|expected_glyph)")
 if not clipret or not emitters or not seen or seen.start()<max(x.end() for x in emitters):return False
 guards=[r for r in if_regions(printer) if r[0]<seen.start()<r[1]]
 return any(all(re.search(x,r[2],re.I) for x in bound) for r in guards)


def finalizer_flow(final):
 if not final:return False
 guard=[r for r in if_regions(final) if all(re.search(x,r[2],re.I) for x in (r"witness",r"active",r"finalized"))]
 if len(guard)!=1:return False
 live=guard[0][3]
 if len(re.findall(r"witness\s*->\s*finalized\s*=\s*(?:1|TRUE)\s*;",live))!=1:return False
 cert=calls(live,CERT);finish=calls(live,"chaos_observation_finish");wit=calls(live,"chaos_next_use_on_manifestation")
 if len(cert)!=1 or len(finish)!=1 or len(wit)!=1:return False
 if not cert[0][0]<finish[0][0]<wit[0][0] or any(in_dead_branch(live,x[0]) for x in (cert[0],finish[0],wit[0])):return False
 finish_args=finish[0][2]
 end_lvalue=r"&\s*(?:\(\s*)?(?:witness\s*->\s*end_seq|end_seq)(?:\s*\)\s*)?$"
 if (not re.search(r"witness\s*->\s*root",finish_args)
     or not re.search(r",\s*"+end_lvalue,finish_args)
     or re.search(r"witness\s*->\s*notice_seq",finish_args)):
  return False
 success=[r for r in if_regions(live) if r[0]<wit[0][0]<r[1]]
 req=(r"manifestation_delivered",r"displaced",r"pre_public",r"!\s*witness\s*->\s*invalid",r"root\s*<\s*witness\s*->\s*notice_seq",r"notice_seq\s*<\s*\w*(?:end_seq|end)")
 if not any(all(re.search(x,r[2],re.I) for x in req) and CERT in r[2] or all(re.search(x,r[2],re.I) for x in req) and re.search(r"published|certified",r[2],re.I) for r in success):return False
 if any(x in live[:finish[0][1]] for x in POLICY):return False
 return "CHAOS_OBS_STAGE_COMPLETED" in live and "CHAOS_OBS_STAGE_BLOCKED" in live


def identities(alltext):
 joined="\n".join(alltext.values());clean=scrub(joined)
 op=re.findall(r"\bCHAOS_OBS_OP_WHISTLE_ATTENTION\s*=\s*(\d+)\b",clean)
 fact=re.findall(r"\bCHAOS_OBS_FACT_ATTENTION\s*=\s*(\d+)\b",clean)
 wires=(alltext.get("include/chaos_protocol.h","").count('"whistle_attention"'),
        alltext.get("include/chaos_protocol.h","").count('"attention"'))
 bad=re.search(r"\b(?:next_use_w_manifestation|w_manifestation)\b",clean)
 return op==["3"] and fact==["10"] and wires==(1,1) and not bad


def main():
 ap=argparse.ArgumentParser();ap.add_argument("--root",required=True);root=Path(ap.parse_args().root)
 if not root.is_dir():emit("ERROR","INVALID_ROOT");return 2
 paths={n:root/n for n in BASE}
 if any(not p.is_file() for p in paths.values()):emit("ERROR","MISSING_MANIFESTATION_FIXTURE_PATH");return 2
 try:raw={n:p.read_bytes() for n,p in paths.items()};text={n:b.decode("utf-8") for n,b in raw.items()}
 except (OSError,UnicodeError):emit("ERROR","UNREADABLE_MANIFESTATION_SOURCE");return 2
 joined="\n".join(text.values())
 if "struct chaos_whistle_witness" not in joined and not any(n in joined for n in (MESSAGE,CERT,FINAL)):
  if any(hashlib.sha256(raw[n]).hexdigest()!=h for n,h in BASE.items()):emit("ERROR","BASELINE_MANIFESTATION_HASH_MISMATCH");return 2
  emit("RED","MISSING_MANIFESTATION_SLICE",("THIRD_ARGUMENT_CARRIER","EXCLUSIVE_ATTENTION_ROOT","TTY_PUBLICATION_CERTIFICATE","POST_END_WITNESS"));return 1
 try:alltext=source_texts(root)
 except (OSError,UnicodeError):emit("ERROR","UNREADABLE_TRACKED_MANIFESTATION_SOURCE");return 2
 miss=[];clean={n:scrub(s) for n,s in text.items()};header=clean["include/chaos.h"]
 if not carrier_contract(header):miss.append("EXACT_STACK_CARRIER")
 sig=r"int\s+dog_move\s*\(\s*struct\s+monst\s*\*\s*mtmp\s*,\s*int\s+after\s*,\s*struct\s+chaos_whistle_witness\s*\*\s*witness\s*\)"
 if not re.search(sig,clean["include/extern.h"]) or not re.search(sig,clean["src/dogmove.c"]):miss.append("EXACT_DOG_MOVE_SIGNATURE")
 owners={"dog_move":["src/dogmove.c"],MESSAGE:["src/pline.c","src/chaos_engine.c"],CERT:["win/tty/wintty.c"],FINAL:["src/chaos_engine.c","src/dogmove.c"]}
 if any(len(owner_paths(alltext,n))!=1 or owner_paths(alltext,n)[0] not in allowed for n,allowed in owners.items()):miss.append("FOREIGN_OR_DUPLICATE_MANIFESTATION_OWNER")
 dog=body(text["src/dogmove.c"],"dog_move");mon=body(text["src/monmove.c"],"m_move")
 if not dog_call_closure(alltext,mon):miss.append("SOLE_PRODUCTION_NONNULL_STACK_CARRIER")
 if not m_move_convergence(mon):miss.append("ALL_POST_DOG_MOVE_RETURNS_FINALIZE_ONCE")
 if not dog_root_flow(dog):miss.append("LIVE_EXCLUSIVE_OPERATION3_AFTER_CLASSIFIER")
 if not identities(alltext):miss.append("EXACT_OPERATION3_FACT10_NAMES_IDS")
 msgpaths=owner_paths(alltext,MESSAGE);msgraw=alltext[msgpaths[0]] if len(msgpaths)==1 else "";msg=body(msgraw,MESSAGE) if msgraw else ""
 if not message_flow(msgraw,msg):miss.append("EXACT_ONCE_FACT10_FIXED_MESSAGE")
 cert=body(text["win/tty/wintty.c"],CERT);printer=body(text["win/tty/wintty.c"],"tty_print_glyph")
 if not tty_certificate_flow(cert,printer):miss.append("EXACT_TTY_COORDINATE_GLYPH_CERTIFICATE")
 fpaths=owner_paths(alltext,FINAL);final=body(alltext[fpaths[0]],FINAL) if len(fpaths)==1 else ""
 if not finalizer_flow(final):miss.append("SAME_ROOT_END_THEN_POST_END_WITNESS")
 if any(x in dog[dog.find("chaos_observation_begin_exclusive"):] for x in POLICY) or any(x in final[:final.find("chaos_observation_finish")] for x in POLICY):miss.append("POLICY_CALLBACK_INSIDE_ROOT")
 if miss:emit("RED","MISSING_MANIFESTATION_SLICE",tuple(dict.fromkeys(miss)));return 1
 emit("GREEN","MANIFESTATION_SLICE_COMPLETE");return 0

if __name__=="__main__":
 try:sys.exit(main())
 except Exception as exc:emit("ERROR","CHECKER_ERROR_"+type(exc).__name__.upper());sys.exit(2)
