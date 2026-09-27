#!/usr/bin/env python3
"""Frozen source contract for N-PROTOCOL-GEN; never imports or runs candidate code."""
import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path

BASELINE = {
    "chaos/protocol_contract.json":"6c785a47cfd27e70aee4c2ed62a5984a10950bd9d601f37db1c5f6ea7e7f4946",
    "include/chaos_protocol.h":"b83dbbe46869d399383224aef37a0d5e6503dc3bc95f6afbb226f118ff638346",
    "chaos/_protocol_contract.py":"878f9f2e28b2b49ad4907ace532a98bc18b120a9ad53b71ed8131f225b38e9ce",
    "scripts/generate_protocol_contract.py":"9eb4eb4ade6275bb80549799c0868dd1d54eccba7f0f5a5779dec846d7b5fb2b",
}
OP = {"symbol":"CHAOS_OBS_OP_WHISTLE_ATTENTION","id":3,"name":"whistle_attention","allow_blocked":True,"projection":"completed_notice_by_operation"}
FACT = {"symbol":"CHAOS_OBS_FACT_ATTENTION","id":10,"name":"attention","operation":3,"channel":"message","implies_blocked":False}
ALTERNATES = {"next_use_w_manifestation", "w_manifestation"}
MISSING_ORDER = (
    "MISSING_PROTOCOL_SOURCE_OPERATION", "MISSING_PROTOCOL_SOURCE_FACT",
    "MISSING_PROTOCOL_HEADER_OPERATION", "MISSING_PROTOCOL_HEADER_FACT",
    "MISSING_PROTOCOL_PYTHON_OPERATION", "MISSING_PROTOCOL_PYTHON_FACT",
)

class DuplicateKey(ValueError): pass

def pairs(items):
    out = {}
    for key, value in items:
        if key in out: raise DuplicateKey(key)
        out[key] = value
    return out

def emit(status, code, missing=()):
    print(json.dumps({"checker":"N-PROTOCOL-GEN","code":code,"missing":list(missing),"scope":"source_completeness_only_not_semantic_acceptance","status":status}, sort_keys=True, separators=(",", ":")))

def strip_c_comments(text):
    out=[]; i=0; state="code"
    while i < len(text):
        c=text[i]; n=text[i+1] if i+1 < len(text) else ""
        if state == "code":
            if c=="/" and n=="/": out += "  "; i+=2; state="line"; continue
            if c=="/" and n=="*": out += "  "; i+=2; state="block"; continue
            out.append(c)
            if c=='"': state="string"
            elif c=="'": state="char"
            i+=1; continue
        if state == "line":
            out.append("\n" if c=="\n" else " ")
            if c=="\n": state="code"
            i+=1; continue
        if state == "block":
            if c=="*" and n=="/": out += "  "; i+=2; state="code"
            else: out.append("\n" if c=="\n" else " "); i+=1
            continue
        out.append(c)
        if c=="\\" and i+1 < len(text): out.append(text[i+1]); i+=2; continue
        if (state=="string" and c=='"') or (state=="char" and c=="'"): state="code"
        i+=1
    return "".join(out)

def literal_assignment(tree, name):
    found=[]
    for node in tree.body:
        targets=[]
        if isinstance(node, ast.Assign): targets=node.targets
        elif isinstance(node, ast.AnnAssign): targets=[node.target]
        if any(isinstance(t, ast.Name) and t.id==name for t in targets):
            found.append(ast.literal_eval(node.value))
    if len(found) != 1: raise ValueError("literal binding cardinality")
    return found[0]

def unique_rows(rows, keys):
    return (type(rows) is list and all(type(r) is dict for r in rows)
            and all(len({r.get(k) for r in rows}) == len(rows) for k in keys))

def complete_rows(obs):
    if type(obs) is not dict:
        return None, None
    families=obs.get("families"); facts=obs.get("facts")
    if type(families) is not list or type(facts) is not list:
        return None, None
    family_keys=set(OP)|{"hook_refs"}
    if (not unique_rows(families,("id","symbol","name"))
            or not unique_rows(facts,("id","symbol","name"))
            or any(set(row)!=family_keys or type(row.get("id")) is not int
                   or type(row.get("symbol")) is not str or type(row.get("name")) is not str
                   or type(row.get("allow_blocked")) is not bool
                   or type(row.get("projection")) is not str
                   or type(row.get("hook_refs")) is not list
                   for row in families)
            or any(set(row)!=set(FACT) or type(row.get("id")) is not int
                   or type(row.get("symbol")) is not str or type(row.get("name")) is not str
                   or type(row.get("operation")) is not int
                   or type(row.get("channel")) is not str
                   or type(row.get("implies_blocked")) is not bool
                   for row in facts)):
        return None, None
    operation_none=obs.get("operation_none"); fact_none=obs.get("fact_none")
    if (operation_none!={"symbol":"CHAOS_OBS_OP_NONE","id":0,"name":"none"}
            or fact_none!={"symbol":"CHAOS_OBS_FACT_NONE","id":0,"name":"none"}
            or any(row["id"]==0 or row["symbol"]==operation_none["symbol"]
                   or row["name"]==operation_none["name"] for row in families)
            or any(row["id"]==0 or row["symbol"]==fact_none["symbol"]
                   or row["name"]==fact_none["name"] for row in facts)):
        return None, None
    return families, facts

def target_rows(obs):
    families,facts=complete_rows(obs)
    if families is None:
        return None, None
    ops=[r for r in families if r.get("id")==3 or r.get("symbol")==OP["symbol"] or r.get("name")==OP["name"]]
    frows=[r for r in facts if r.get("id")==10 or r.get("symbol")==FACT["symbol"] or r.get("name")==FACT["name"]]
    op_ok=(len(ops)==1 and set(ops[0])==set(OP)|{"hook_refs"} and all(ops[0].get(k)==v for k,v in OP.items())
           and type(ops[0].get("hook_refs")) is list and bool(ops[0]["hook_refs"]))
    fact_ok=len(frows)==1 and frows[0]==FACT
    return ops[0] if op_ok else None, frows[0] if fact_ok else None

def enum_entries(code, tag):
    matches=re.findall(r"\benum\s+"+re.escape(tag)+r"\s*\{([^{}]*)\}\s*;", code, re.S)
    if len(matches)!=1: return None
    entries=[]
    for part in matches[0].split(","):
        part=part.strip()
        if not part: continue
        m=re.fullmatch(r"([A-Za-z_]\w*)\s*=\s*(\d+)", part)
        if not m: return None
        entries.append((m.group(1),int(m.group(2))))
    if len({x for x,_ in entries})!=len(entries) or len({n for _,n in entries})!=len(entries): return None
    return entries

def macro_rows(code, name, argc):
    lines=code.splitlines()
    start_re=re.compile(r"^\s*#\s*define\s+"+re.escape(name)+r"\s*\(\s*X\s*\)\s*(.*)$")
    starts=[(i,start_re.match(line)) for i,line in enumerate(lines) if start_re.match(line)]
    if len(starts)!=1: return None
    index,match=starts[0]
    chunks=[]
    text=match.group(1)
    while True:
        continued=text.rstrip().endswith("\\")
        chunks.append(text.rstrip()[:-1] if continued else text)
        if not continued: break
        index+=1
        if index>=len(lines): return None
        text=lines[index]
    block="\n".join(chunks)
    rows=[]
    for call in re.findall(r"\bX\s*\(([^()]*)\)", block):
        fields=[]; cur=""; quote=False; esc=False
        for ch in call:
            if esc: cur+=ch; esc=False; continue
            if ch=="\\" and quote: cur+=ch; esc=True; continue
            if ch=='"': cur+=ch; quote=not quote; continue
            if ch=="," and not quote: fields.append(cur.strip()); cur=""; continue
            cur+=ch
        fields.append(cur.strip())
        if len(fields)!=argc: return None
        rows.append(tuple(fields))
    return rows or None

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--root",required=True); root=Path(ap.parse_args().root)
    if not root.is_dir(): emit("ERROR","INVALID_ROOT"); return 2
    paths={n:root/n for n in BASELINE}
    if any(not p.is_file() for p in paths.values()): emit("ERROR","MISSING_PROTOCOL_FIXTURE_PATH"); return 2
    try:
        raw={n:p.read_bytes() for n,p in paths.items()}
        source=json.loads(raw["chaos/protocol_contract.json"].decode("utf-8"),object_pairs_hook=pairs)
        header=raw["include/chaos_protocol.h"].decode("utf-8")
        pytext=raw["chaos/_protocol_contract.py"].decode("utf-8")
    except (OSError,UnicodeError,json.JSONDecodeError,DuplicateKey): emit("ERROR","INVALID_PROTOCOL_SOURCE_FIXTURE"); return 2
    generator_ok=hashlib.sha256(raw["scripts/generate_protocol_contract.py"]).hexdigest()==BASELINE["scripts/generate_protocol_contract.py"]
    if not generator_ok: emit("ERROR","UNAUTHORIZED_PROTOCOL_GENERATOR"); return 2
    obs=source.get("observations") if type(source) is dict else None
    op,fact=target_rows(obs)
    op_ok=op is not None; fact_ok=fact is not None
    code=strip_c_comments(header)
    op_enum=enum_entries(code,"chaos_observation_operation") or []
    fact_enum=enum_entries(code,"chaos_observation_fact") or []
    fam=macro_rows(code,"CHAOS_OBS_FAMILY_ROWS",3) or []
    frows=macro_rows(code,"CHAOS_OBS_FACT_ROWS",5) or []
    families,facts=complete_rows(obs)
    header_inventory_ok=False
    if families is not None and facts is not None:
        expected_op_enum=[(obs["operation_none"]["symbol"],obs["operation_none"]["id"])]
        expected_op_enum += [(row["symbol"],row["id"]) for row in families]
        expected_fact_enum=[(obs["fact_none"]["symbol"],obs["fact_none"]["id"])]
        expected_fact_enum += [(row["symbol"],row["id"]) for row in facts]
        expected_fam=[(row["symbol"],str(int(row["allow_blocked"])),json.dumps(row["name"])) for row in families]
        expected_frows=[(row["symbol"],str(row["operation"]),"CHAOS_OBS_CHANNEL_"+row["channel"].upper(),str(int(row["implies_blocked"])),json.dumps(row["name"])) for row in facts]
        header_inventory_ok=(op_enum==expected_op_enum and fact_enum==expected_fact_enum
                             and fam==expected_fam and frows==expected_frows)
    op_tuple=(OP["symbol"],3); fact_tuple=(FACT["symbol"],10)
    h_op=(op_ok and header_inventory_ok and op_enum.count(op_tuple)==1
          and sum(n==3 or s==OP["symbol"] for s,n in op_enum)==1 and fam is not None
          and fam.count((OP["symbol"],"1",'"whistle_attention"'))==1
          and sum(r[0]==OP["symbol"] or r[2]=='"whistle_attention"' for r in fam)==1)
    h_fact=(fact_ok and header_inventory_ok and fact_enum.count(fact_tuple)==1
            and sum(n==10 or s==FACT["symbol"] for s,n in fact_enum)==1 and frows is not None
            and frows.count((FACT["symbol"],"3","CHAOS_OBS_CHANNEL_MESSAGE","0",'"attention"'))==1
            and sum(r[0]==FACT["symbol"] or r[4]=='"attention"' for r in frows)==1)
    try:
        pyobs=literal_assignment(ast.parse(pytext,filename="generated-python-source"),"OBSERVATIONS")
        pyop,pyfact=target_rows(pyobs)
    except (SyntaxError,ValueError,TypeError): emit("ERROR","INVALID_GENERATED_PYTHON_SOURCE"); return 2
    # Exact subtree parity rejects stale, duplicated, or aliased generated Python identities.
    py_parity=type(obs) is dict and pyobs==obs
    py_op=op_ok and pyop==op and py_parity
    py_fact=fact_ok and pyfact==fact and py_parity
    semantic_names=set()
    if type(obs) is dict:
        for group in (obs.get("families",[]),obs.get("facts",[])):
            if type(group) is list:
                for row in group:
                    if type(row) is dict: semantic_names.add(row.get("name")); semantic_names.add(row.get("symbol"))
    forbidden=bool(ALTERNATES & semantic_names)
    checks=(op_ok,fact_ok,h_op,h_fact,py_op,py_fact)
    missing=[name for name,ok in zip(MISSING_ORDER,checks) if not ok]
    if forbidden: missing.append("FORBIDDEN_PROTOCOL_ALTERNATE_NAMES")
    if missing:
        if not any(checks):
            for name in BASELINE:
                if hashlib.sha256(raw[name]).hexdigest()!=BASELINE[name]: emit("ERROR","BASELINE_PROTOCOL_HASH_MISMATCH"); return 2
        emit("RED","MISSING_PROTOCOL_SLICE",missing); return 1
    emit("GREEN","PROTOCOL_SLICE_COMPLETE"); return 0

if __name__=="__main__":
    try: sys.exit(main())
    except Exception as exc: emit("ERROR","CHECKER_ERROR_"+type(exc).__name__.upper()); sys.exit(2)
