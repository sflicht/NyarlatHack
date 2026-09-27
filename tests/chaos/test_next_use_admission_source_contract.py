#!/usr/bin/env python3
"""Finite source contract for I-ADMISSION-DEBIT; never compiles or runs candidate code."""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

BASELINE_MAKE="f6cf0fa493dadb27a7470e042bda5e7e7a1f1c304852640d21f8cad751146d80"
NEW=("include/chaos_next_use_admission.h","src/chaos_next_use_admission.c")
SYMBOLS=("chaos_next_use_reserve","chaos_next_use_debit","chaos_next_use_admit","chaos_next_use_append_private","chaos_next_use_deliver_receipt")
PROTOCOL=("chaos/protocol_contract.json","include/chaos_protocol.h","chaos/_protocol_contract.py")
FORBIDDEN_PROTOCOL=("CHAOS_OBS_OP_WHISTLE_ATTENTION","CHAOS_OBS_FACT_ATTENTION")
FORBIDDEN_CALLS=("system","popen","fork","vfork","execv","execve","socket","connect","dlopen","dlsym","lua_","luaL_")

def emit(status,code,missing=()):
    print(json.dumps({"checker":"I-ADMISSION-DEBIT","code":code,"missing":list(missing),"scope":"source_completeness_only_not_semantic_acceptance","status":status},sort_keys=True,separators=(",",":")))

def strip_comments(text):
    out=[]; i=0; state="code"
    while i<len(text):
        c=text[i]; n=text[i+1] if i+1<len(text) else ""
        if state=="code":
            if c=="/" and n=="/": out.extend("  "); i+=2; state="line"; continue
            if c=="/" and n=="*": out.extend("  "); i+=2; state="block"; continue
            out.append(c)
            if c=='"': state="str"
            elif c=="'": state="chr"
            i+=1; continue
        if state=="line":
            out.append("\n" if c=="\n" else " "); state="code" if c=="\n" else state; i+=1; continue
        if state=="block":
            if c=="*" and n=="/": out.extend("  "); i+=2; state="code"
            else: out.append("\n" if c=="\n" else " "); i+=1
            continue
        out.append(c)
        if c=="\\" and i+1<len(text): out.append(text[i+1]); i+=2; continue
        if (state=="str" and c=='"') or (state=="chr" and c=="'"): state="code"
        i+=1
    return "".join(out)

def mask_literals(text):
    out=list(text); i=0; q=None
    while i<len(text):
        c=text[i]
        if q is None and c in "\"'": q=c; out[i]=" "; i+=1; continue
        if q is not None:
            if c=="\n": q=None; i+=1; continue
            out[i]=" "
            if c=="\\" and i+1<len(text): out[i+1]=" "; i+=2; continue
            if c==q: q=None
        i+=1
    return "".join(out)

def closing(text,start,left="{",right="}"):
    depth=0
    for i in range(start,len(text)):
        if text[i]==left: depth+=1
        elif text[i]==right:
            depth-=1
            if depth==0: return i
    return -1

def functions(text):
    clean=strip_comments(text); masked=mask_literals(clean); result={}; spans=[]
    pat=re.compile(r"(?m)(?:^|[;}]\s*)\s*([A-Za-z_][\w\s\*]*?)\b([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{")
    for m in pat.finditer(masked):
        name=m.group(2)
        if name in {"if","for","while","switch"}: continue
        op=masked.find("{",m.start(),m.end()); end=closing(masked,op)
        if end<0 or any(a<=m.start()<b for a,b in spans): continue
        spans.append((m.start(),end+1)); result.setdefault(name,[]).append({"signature":clean[m.start():op],"body":clean[op+1:end],"masked":masked[op+1:end]})
    return result,clean,masked

def call_sites(body,name):
    out=[]
    for m in re.finditer(r"\b"+re.escape(name)+r"\s*\(",body):
        op=body.find("(",m.start(),m.end()); end=closing(body,op,"(",")")
        if end>=0: out.append((m.start(),end+1,body[op+1:end]))
    return out

def checked_before(body,site):
    prefix=body[max(0,site-350):site]
    suffix=body[site:site+500]
    direct=bool(re.search(r"\bif\s*\([^)]*$",prefix,re.S))
    assigned=bool(re.search(r"(?:=|\breturn\s+)\s*$",prefix)) and bool(re.search(r";\s*if\s*\(",suffix,re.S))
    return direct or assigned

def is_assignment(body,name):
    return bool(re.search(r"(?:\b|->|\.)"+re.escape(name)+r"\s*(?:\[[^]]*\]\s*)?(?:=|\+=|-=|\+\+|--)",body))

def reserve_contract(item):
    body=item["masked"]
    has_capacity=re.search(r"carrier|capacity|reserve",body,re.I) and re.search(r"attempt",body,re.I) and re.search(r"admission",body,re.I) and re.search(r"termination",body,re.I)
    bounded=re.search(r"(?:>|>=|<|<=|==|!=).*?(?:CAP|MAX|SIZE|bytes|needed)|(?:CAP|MAX|SIZE|bytes|needed).*?(?:>|>=|<|<=|==|!=)",body,re.I|re.S)
    precommit=re.search(r"PRIVATE_CARRIER_RESERVE|REJECTED_PRECOMMIT|precommit",body,re.I)
    allocation=re.search(r"reserve|alloc|capacity|buffer",body,re.I)
    return bool(has_capacity and bounded and precommit and allocation and re.search(r"\b(return|goto)\b",body))

def debit_contract(item):
    body=item["masked"]
    # A single checked transition owns all committed fields; reserved may be read/snapshotted but not assigned.
    fields=all(re.search(r"\b"+x+r"\b",body,re.I) for x in ("spent","admitted","commit","slot","reserved"))
    transitions=is_assignment(body,"spent") and is_assignment(body,"admitted") and (is_assignment(body,"phase") or is_assignment(body,"slot_w") or is_assignment(body,"slot_f"))
    no_reserved=not is_assignment(body,"reserved")
    first_write=min([m.start() for m in re.finditer(r"(?:=|\+=|-=)",body)],default=-1)
    guard=body.find("if")
    checked=guard>=0 and first_write>=0 and guard<first_write and re.search(r"capacity|cost|spent|budget|overflow|OPEN",body[:first_write],re.I)
    return bool(fields and transitions and no_reserved and checked)

def append_kind(args,kind):
    return bool(re.search(r"\b"+kind+r"\b",args,re.I))

def sequence_expr(args,offset):
    if offset==0: return bool(re.search(r"\b(?:N|base_seq|seq_base|first_seq|seq)\b",args,re.I))
    return bool(re.search(r"(?:\bN\b|base_seq|seq_base|first_seq|seq)\s*\+\s*"+str(offset)+r"\b",args,re.I))

def failure_branch_contains(body,pos):
    # The termination append must be controlled by a post-receipt failure branch, not unconditional/dead text.
    for m in re.finditer(r"\bif\s*\(",body):
        pend=closing(body,body.find("(",m.start(),m.end()),"(",")")
        if pend<0: continue
        op=body.find("{",pend,pend+80)
        if op<0: continue
        end=closing(body,op)
        if op<pos<end:
            cond=body[m.end():pend]
            return bool(re.search(r"receipt|transport|deliver|rc|ok|success",cond,re.I))
    return False

def admit_contract(item):
    body=item["masked"]
    reserves=call_sites(body,"chaos_next_use_reserve")
    debits=call_sites(body,"chaos_next_use_debit")
    appends=call_sites(body,"chaos_next_use_append_private")
    receipts=call_sites(body,"chaos_next_use_deliver_receipt")
    if len(reserves)!=1 or len(debits)!=1 or len(appends)!=3 or len(receipts)!=1: return False
    r,d=reserves[0],debits[0]; a0,a1,a2=appends; receipt=receipts[0]
    ordered=r[0]<d[0]<a0[0]<a1[0]<receipt[0]<a2[0]
    checked=checked_before(body,r[0]) and checked_before(body,d[0])
    kinds=append_kind(a0[2],"attempt") and append_kind(a0[2],"committed") and append_kind(a1[2],"admission") and append_kind(a2[2],"termination") and append_kind(a2[2],"TRANSPORT_FAILURE")
    seqs=sequence_expr(a0[2],0) and sequence_expr(a1[2],1) and sequence_expr(a2[2],2)
    failure=failure_branch_contains(body,a2[0]) and re.search(r"TERMINATED_TRANSPORT",body[receipt[1]:a2[1]]) and re.search(r"TRANSPORT_TERMINATED",body[receipt[1]:a2[1]])
    suffix=body[d[0]:]
    forbidden=bool(re.search(r"rollback|refund|retry|second_attempt",suffix,re.I))
    forbidden=forbidden or bool(re.search(r"\bspent\s*(?:-=|--)",suffix)) or is_assignment(suffix,"reserved")
    # The two carrier writes are statements, not predicates whose failure can divert committed control flow.
    nonfailing=all(not checked_before(body,a[0]) for a in (a0,a1,a2))
    return bool(ordered and checked and kinds and seqs and failure and not forbidden and nonfailing)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--root",required=True); root=Path(ap.parse_args().root)
    if not root.is_dir(): emit("ERROR","INVALID_ROOT"); return 2
    make=root/"GNUmakefile"
    if not make.is_file() or any(not (root/p).is_file() for p in PROTOCOL): emit("ERROR","MISSING_ADMISSION_FIXTURE_PATH"); return 2
    paths=[root/p for p in NEW]
    if any(not p.is_file() for p in paths):
        try:
            if hashlib.sha256(make.read_bytes()).hexdigest()!=BASELINE_MAKE: emit("ERROR","BASELINE_ADMISSION_HASH_MISMATCH"); return 2
        except OSError: emit("ERROR","UNREADABLE_ADMISSION_FIXTURE"); return 2
        emit("RED","MISSING_ADMISSION_SLICE",("MISSING_ADMISSION_SLICE",)); return 1
    try:
        header=paths[0].read_text(encoding="utf-8"); source=paths[1].read_text(encoding="utf-8"); mk=make.read_text(encoding="utf-8"); protocol="\n".join((root/p).read_text(encoding="utf-8") for p in PROTOCOL)
    except (OSError,UnicodeError): emit("ERROR","UNREADABLE_ADMISSION_SOURCE"); return 2
    defs,clean,masked=functions(source); missing=[]
    if not all(n in defs and len(defs[n])==1 for n in SYMBOLS): missing.append("MISSING_REQUIRED_DEFINITION")
    hclean=strip_comments(header)
    if not all(len(re.findall(r"\b"+re.escape(n)+r"\s*\(",hclean))==1 for n in SYMBOLS): missing.append("INVALID_ADMISSION_DECLARATION")
    if not ("chaos_next_use_reserve" in defs and len(defs["chaos_next_use_reserve"])==1 and reserve_contract(defs["chaos_next_use_reserve"][0])): missing.append("UNBOUND_PRECOMMIT_RESERVE")
    if not ("chaos_next_use_debit" in defs and len(defs["chaos_next_use_debit"])==1 and debit_contract(defs["chaos_next_use_debit"][0])): missing.append("UNBOUND_ATOMIC_DEBIT")
    if not ("chaos_next_use_append_private" in defs and len(defs["chaos_next_use_append_private"])==1 and re.search(r"\bvoid\b",defs["chaos_next_use_append_private"][0]["signature"]) and not re.search(r"alloc|realloc|malloc|calloc|fail",defs["chaos_next_use_append_private"][0]["masked"],re.I)): missing.append("FALLIBLE_POSTCOMMIT_APPEND")
    if not ("chaos_next_use_admit" in defs and len(defs["chaos_next_use_admit"])==1 and admit_contract(defs["chaos_next_use_admit"][0])): missing.append("UNBOUND_POSTCOMMIT_SEQUENCE")
    if any(re.search(r"\b"+re.escape(name)+r"\s*\(",masked) for name in FORBIDDEN_CALLS if not name.endswith("_")): missing.append("FORBIDDEN_ADMISSION_CAPABILITY")
    if re.search(r"\b(?:lua_|luaL_)\w*\s*\(",masked): missing.append("FORBIDDEN_ADMISSION_LUA")
    if any(name in clean for name in FORBIDDEN_PROTOCOL) or any(name in protocol for name in SYMBOLS): missing.append("INVALID_ADMISSION_OWNERSHIP")
    if "chaos_next_use_admission.c" not in strip_comments(mk): missing.append("MISSING_BUILD_BINDING")
    if missing: emit("RED","MISSING_ADMISSION_SLICE",missing); return 1
    emit("GREEN","ADMISSION_SLICE_COMPLETE"); return 0

if __name__=="__main__":
    try: sys.exit(main())
    except Exception as exc: emit("ERROR","CHECKER_ERROR_"+type(exc).__name__.upper()); sys.exit(2)
