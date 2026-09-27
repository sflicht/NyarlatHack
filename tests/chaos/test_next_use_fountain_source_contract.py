#!/usr/bin/env python3
"""Structural source contract for N-F-TOKEN; not runtime proof."""
import argparse, hashlib, json, re, stat, sys
from pathlib import Path

BASE={
 "include/chaos.h":"6f88c919c2785ecb830b0aa69bd87d47ef1a430cce3f23ed48761dc0bdaa07e9",
 "include/extern.h":"601d032e45fbf34dae3664381066b8af2537856cd9a5f9c29804ac2a09475e80",
 "src/potion.c":"1ab06acb050aaef305e4c518972e8e3c4d285313a3efb029b799e89b049bfc9c",
 "src/fountain.c":"bd70dbc82d7219aebbe4697acd2b9e7046b2b398e108da7575f5dfeb3dec8487"}
CONTACT="chaos_next_use_fountain_contact"; CLEAR="chaos_next_use_fountain_clear"
FALSE_RETURN=r"\breturn\s+(?:0|FALSE)\s*;"
RNG=r"\b(?:rn2|rnd|rn1|rnl|d)\s*\("
SOURCE_ROOTS=("src","include","win","util","sys")


def emit(status,code,missing=()):
 print(json.dumps({"checker":"N-F-TOKEN","code":code,"missing":list(missing),
  "scope":"source_completeness_only_not_semantic_acceptance","status":status},sort_keys=True,separators=(",",":")))


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
 typ=re.compile(r"^(?:(?:register|const|volatile|static)\s+)*(?:struct\s+\w+|union\s+\w+|enum\s+\w+|unsigned|signed|short|long|int|char|boolean|void)\b",re.S)
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
  elif s[i]==";" and not par and not br:return i
 return -1


def if_regions(s):
 out=[]
 for m in re.finditer(r"\bif\s*\(",s):
  op=s.find("(",m.start());cl=matching(s,op,"(",")")
  if cl<0:continue
  en=statement_end(s,cl+1)
  if en>=0:out.append((m.start(),en+1,s[op+1:cl],s[cl+1:en+1]))
 return out


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


def owners(alltext,name,owner):
 defs=[]
 for path,text in alltext.items():defs.extend(path for _ in function_ranges(text,name))
 return len(defs)==1 and defs[0]==owner


def exact_zeroed_local(dodrink):
 decl=list(re.finditer(r"struct\s+chaos_fountain_token\s+token\s*(?:=\s*\{\s*(?:0|FALSE)?\s*\})?\s*;",dodrink))
 if len(decl)!=1:return False
 m=decl[0]
 initialized=bool(re.search(r"=\s*\{\s*(?:0|FALSE)?\s*\}",m.group()))
 zeroings=list(re.finditer(r"\bmemset\s*\(\s*&\s*token\s*,\s*0\s*,\s*sizeof\s*(?:\(\s*token\s*\)|\s+token)\s*\)\s*;",dodrink))
 contacts=calls(dodrink,CONTACT)
 if len(contacts)!=1:return False
 if initialized:return not zeroings
 return len(zeroings)==1 and m.end()<=zeroings[0].start() and zeroings[0].end()<contacts[0][0]


def contact_controls_drink(dodrink):
 cc=calls(dodrink,CONTACT);dc=[c for c in calls(dodrink,"drinkfountain") if re.fullmatch(r"\s*&\s*token\s*",c[2])]
 if len(cc)!=1 or len(dc)!=1:return False
 if not re.fullmatch(r"\s*completed_root\s*,\s*&\s*token\s*",cc[0][2]):return False
 if dc[0][0]<=cc[0][1]:return False
 # Either the bool call itself is the controlling if-condition, or its assigned bool is.
 for st,en,cond,stmt in if_regions(dodrink):
  if not (st<dc[0][0]<en):continue
  direct=st<=cc[0][0]<en and CONTACT in cond
  assigned=re.search(r"\b(\w+)\s*=\s*"+CONTACT+r"\s*\(",dodrink[:st])
  by_name=assigned and re.search(r"\b"+re.escape(assigned.group(1))+r"\b",cond)
  if (direct or by_name) and not re.search(r"!\s*(?:"+CONTACT+r"\s*\(|"+(re.escape(assigned.group(1)) if assigned else r"$^")+r"\b)",cond):return True
 return False


def remap_flow(drink,alltext):
 # The one native draw must flow into the original natural/default partition.
 draw=list(re.finditer(r"\bfate\s*=\s*rnd\s*\(\s*30\s*\)",drink))
 fate_writes=list(re.finditer(r"\bfate\s*=(?!=)",drink))
 natural=[r for r in if_regions(drink) if re.fullmatch(r"\s*fate\s*<\s*10\s*",r[2])]
 switch=re.search(r"\bswitch\s*\(\s*fate\s*\)",drink)
 if len(draw)!=1 or len(fate_writes)!=1 or len(natural)!=1 or switch is None:return False
 nat=natural[0]
 op=drink.find("{",switch.end())
 if op<0:return False
 switch_end=matching(drink,op,"{","}")
 if switch_end<0:return False
 switch_body=drink[op+1:switch_end]
 defaults=list(re.finditer(r"\bdefault\s*:",switch_body))
 if len(defaults)!=1:return False
 default_body=switch_body[defaults[0].end():]

 # Infer the extracted refresh seam from the sole call shared by the natural
 # branch and the default 10..18 branch; the contract does not freeze a name.
 keywords={"if","for","while","switch","sizeof","return"}
 natural_names={m.group(1) for m in re.finditer(r"\b([A-Za-z_]\w*)\s*\(",nat[3])
                if m.group(1) not in keywords}
 default_names={m.group(1) for m in re.finditer(r"\b([A-Za-z_]\w*)\s*\(",default_body)
                if m.group(1) not in keywords}
 seams=[name for name in sorted(natural_names&default_names)
        if len(calls(nat[3],name))==1 and len(calls(default_body,name))==1]
 if len(seams)!=1:return False
 seam=seams[0]
 definitions=[(path,item) for path,text in alltext.items()
              for item in function_ranges(text,seam)]
 if len(definitions)!=1 or definitions[0][0]!="src/fountain.c":return False
 refresh=definitions[0][1][2]
 arms=calls(refresh,"chaos_observation_arm")
 messages=calls(refresh,"pline_The")
 if (len(arms)!=1 or "CHAOS_OBS_OP_FOUNTAIN_DRINK" not in arms[0][2]
     or "CHAOS_OBS_FACT_WATER_REFRESHED" not in arms[0][2]
     or len(messages)!=1 or len(calls(refresh,"chaos_observation_disarm"))!=1
     or len(calls(refresh,"newuhs"))!=1
     or not re.fullmatch(r"\s*FALSE\s*",calls(refresh,"newuhs")[0][2])
     or not re.search(r"Race_if\s*\(\s*PM_INCANTIFIER\s*\)",refresh)
     or not re.search(r"u\s*\.\s*uen\s*\+=\s*rnd\s*\(\s*10\s*\)",refresh)
     or not re.search(r"u\s*\.\s*uhunger\s*\+=\s*rnd\s*\(\s*10\s*\)",refresh)
     or re.search(r"\b(?:lesshungry|dryup)\s*\(|\bmgkftn\b",refresh)):
  return False

 regions=[]
 requirements=(r"\btoken\b",r"token\s*->\s*active",r"token\s*->\s*remap",
               r"!\s*token\s*->\s*consumed")
 for st,en,cond,stmt in if_regions(default_body):
  if all(re.search(p,cond) for p in requirements):regions.append((st,en,cond,stmt))
 if len(regions)!=1:return False
 _st,_en,_cond,stmt=regions[0]
 consume=list(re.finditer(r"token\s*->\s*consumed\s*=\s*(?:1|TRUE)\s*;",stmt))
 seam_calls=calls(stmt,seam)
 if len(consume)!=1 or len(seam_calls)!=1 or consume[0].end()>seam_calls[0][0] or re.search(RNG,stmt):return False

 mgk=any(re.fullmatch(r"\s*mgkftn\s*",cond) and re.search(r"\breturn\s*;",stmt)
         for _st,_en,cond,stmt in if_regions(nat[3]))
 dry=calls(drink,"dryup")
 return (mgk and len(dry)==1 and re.fullmatch(r"\s*u\s*\.\s*ux\s*,\s*u\s*\.\s*uy\s*,\s*TRUE\s*",dry[0][2])
         and draw[0].end()<nat[0]<switch.start()<switch_end<dry[0][0]
         and all(re.search(r"\bcase\s+"+str(i)+r"\s*:",switch_body) for i in range(19,31)))


def total_clear(drink):
 # Every direct return is immediately dominated by a clear in its statement, or exits through one cleanup label.
 returns=list(re.finditer(r"\breturn\s*;",drink));gotos=list(re.finditer(r"\bgoto\s+(\w+)\s*;",drink))
 for r in returns:
  prefix=drink[max(0,r.start()-240):r.start()]
  if not re.search(r"\b"+CLEAR+r"\s*\(\s*token\s*\)\s*;\s*$",prefix,re.S):
   # A sole final return after the cleanup clear is also valid.
   label=re.search(r"(\w+)\s*:\s*"+CLEAR+r"\s*\(\s*token\s*\)\s*;\s*$",prefix,re.S)
   if not label:return False
 if gotos:
  labels={g.group(1) for g in gotos}
  if len(labels)!=1:return False
  label=next(iter(labels))
  if not re.search(r"\b"+re.escape(label)+r"\s*:\s*"+CLEAR+r"\s*\(\s*token\s*\)\s*;",drink):return False
 # Normal fallthrough must clear after dryup and no later token use may reactivate it.
 last=drink.rfind(CLEAR);dry=drink.rfind("dryup")
 return last>dry and not re.search(r"token\s*->\s*(?:active|remap|consumed)\s*=",drink[last:])


def caller_closure(alltext):
 found=[]
 for path,text in alltext.items():
  clean=scrub(text)
  defs=function_ranges(text,"drinkfountain")
  def_ranges=[(x[0],x[1]) for x in defs]
  for call in calls(clean,"drinkfountain"):
   if any(st<=call[0]<en for st,en in def_ranges):continue
   # Exclude prototypes by checking the call's following token.
   p=call[1]
   while p<len(clean) and clean[p].isspace():p+=1
   if p<len(clean) and clean[p]==";":found.append((path," ".join(call[2].split())))
 nonnull=[x for x in found if x[1] not in ("","0","NULL","( struct chaos_fountain_token * ) 0","(struct chaos_fountain_token *)0")]
 return len([x for x in nonnull if x[1]=="& token"])==1 and all(a=="& token" for _,a in nonnull) and any(a in ("0","NULL","(struct chaos_fountain_token *)0","( struct chaos_fountain_token * ) 0") for _,a in found)


def main():
 ap=argparse.ArgumentParser();ap.add_argument("--root",required=True);root=Path(ap.parse_args().root)
 if not root.is_dir():emit("ERROR","INVALID_ROOT");return 2
 paths={n:root/n for n in BASE}
 if any(not p.is_file() for p in paths.values()):emit("ERROR","MISSING_FOUNTAIN_FIXTURE_PATH");return 2
 try:raw={n:p.read_bytes() for n,p in paths.items()};t={n:b.decode("utf-8") for n,b in raw.items()}
 except (OSError,UnicodeError):emit("ERROR","UNREADABLE_FOUNTAIN_SOURCE");return 2
 fclean=scrub(t["src/fountain.c"])
 if CONTACT not in "\n".join(t.values()) and re.search(r"\bdrinkfountain\s*\(\s*\)",fclean):
  if any(hashlib.sha256(raw[n]).hexdigest()!=h for n,h in BASE.items()):emit("ERROR","BASELINE_FOUNTAIN_HASH_MISMATCH");return 2
  emit("RED","MISSING_FOUNTAIN_TOKEN_SLICE",("TOKEN_SIGNATURE","CONFIRMED_CONTACT_CALLBACK","ONE_USE_REMAP","TOTAL_TOKEN_CLEAR"));return 1
 try:alltext=source_texts(root)
 except (OSError,UnicodeError):emit("ERROR","UNREADABLE_FOUNTAIN_CALLER_SOURCE");return 2
 miss=[];shared=root/"include/chaos_next_use_contract.h"
 try:st=shared.read_text(encoding="utf-8")
 except (OSError,UnicodeError):st=""
 token=re.search(r"struct\s+chaos_fountain_token\s*\{(.*?)\}\s*;",scrub(st),re.S)
 if not token or not all(re.search(r"\b"+x+r"\s*;",token.group(1)) for x in (r"long\s+root",r"(?:int|boolean)\s+active",r"(?:int|boolean)\s+remap",r"(?:int|boolean)\s+consumed")):miss.append("EXACT_FOUNTAIN_TOKEN_SHAPE")
 ext=scrub(t["include/extern.h"])
 direct=r"void\s+drinkfountain\s*\(\s*struct\s+chaos_fountain_token\s*\*\s*\w+\s*\)\s*;";macro=r"void\s+FDECL\s*\(\s*drinkfountain\s*,\s*\(\s*struct\s+chaos_fountain_token\s*\*\s*\)\s*\)\s*;"
 if not (re.search(direct,ext) or re.search(macro,ext)):miss.append("TOKEN_DRINKFOUNTAIN_DECLARATION")
 if not owners(alltext,"drinkfountain","src/fountain.c") or not owners(alltext,CONTACT,"src/chaos_engine.c") or not owners(alltext,CLEAR,"src/chaos_engine.c"):miss.append("FOREIGN_OR_DUPLICATE_FOUNTAIN_OWNER")
 drink=body(t["src/fountain.c"],"drinkfountain");dodrink=body(t["src/potion.c"],"dodrink")
 if not drink:miss.append("TOKEN_DRINKFOUNTAIN_DEFINITION")
 if not exact_zeroed_local(dodrink):miss.append("EXACT_ZEROED_LOCAL_TOKEN")
 if not contact_controls_drink(dodrink):miss.append("CONTACT_BOOLEAN_CONTROLS_PRODUCTION_DRINK")
 if not remap_flow(drink,alltext):miss.append("DEFAULT_10_18_ONE_USE_REMAP")
 if not total_clear(drink):miss.append("TOTAL_TOKEN_CLEAR")
 if not caller_closure(alltext):miss.append("NULL_DIRECT_OR_HELPER_CALLERS")
 joined="\n".join(alltext.values())
 if re.search(r"\b(?:fountain_witness|F_WITNESSED|FOUNTAIN_PUBLIC_WITNESS|chaos_next_use_on_fountain_manifestation)\b",joined):miss.append("FORBIDDEN_PUBLIC_F_WITNESS")
 if miss:emit("RED","MISSING_FOUNTAIN_TOKEN_SLICE",tuple(dict.fromkeys(miss)));return 1
 emit("GREEN","FOUNTAIN_TOKEN_SLICE_COMPLETE");return 0

if __name__=="__main__":
 try:sys.exit(main())
 except Exception as e:emit("ERROR","CHECKER_ERROR_"+type(e).__name__.upper());sys.exit(2)
