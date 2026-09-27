#!/usr/bin/env python3
"""Finite source contract for I-PARSER-JCS-LUA; never compiles or runs candidate code."""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

BASELINE={"include/chaos_lua.h":"82fee7baaf3a3b3edb360013a5642abf58d93aee43b82209c21f2a6cec9404b9","src/chaos_lua.c":"69ca2f75d3b5fc49753c7ae71aa62d0453988500369aaaa217b4834919c43a98","GNUmakefile":"f6cf0fa493dadb27a7470e042bda5e7e7a1f1c304852640d21f8cad751146d80"}
NEW=("include/chaos_next_use.h","src/chaos_next_use.c")
PARSERS=("chaos_next_use_parse_author","chaos_next_use_parse_envelope","chaos_next_use_parse_context","chaos_next_use_parse_intent")
SYMBOLS=PARSERS+("chaos_next_use_jcs","chaos_next_use_sha256","chaos_lua_next_use_load","chaos_lua_next_use_on_action")
DENY_CALLS={"system","popen","fork","vfork","execv","execve","execl","execlp","execvp","posix_spawn","socket","connect","bind","listen","accept","send","recv","getaddrinfo","dlopen","dlsym","LoadLibrary","CreateProcess","fopen","freopen","open","openat","creat","read","write","remove","rename","unlink","tmpfile","mkstemp","getrandom","arc4random","random","rand","srand","gettimeofday","clock_gettime","time","luaL_openlibs","luaL_requiref","luaL_loadfile","luaL_loadfilex","luaL_dofile"}
SAFE_EXTERNAL={"malloc","calloc","realloc","free","memcpy","memmove","memset","memcmp","strlen","strnlen","strcmp","strncmp","qsort","bsearch","snprintf","vsnprintf","isfinite","floor","signbit","SHA256_Init","SHA256_Update","SHA256_Final"}
SAFE_LUA_CALLS={
    "lua_newstate","lua_close","lua_sethook","lua_pcall","lua_pcallk","lua_call",
    "lua_getextraspace","lua_pushcclosure",
    "lua_gettop","lua_settop","lua_type","lua_typename","lua_isinteger",
    "lua_tointegerx","lua_tolstring","lua_toboolean","lua_pushnil","lua_pushboolean",
    "lua_pushinteger","lua_pushlstring","lua_pushvalue","lua_createtable","lua_getfield",
    "lua_setfield","lua_rawget","lua_rawgeti","lua_rawset","lua_rawseti","lua_next",
    "lua_load","luaL_loadbufferx","lua_error",
}
SAFE_CHAOS_LUA_CALLS=set(PARSERS)|{"chaos_next_use_jcs","chaos_next_use_sha256"}


def emit(status,code,missing=()):
    print(json.dumps({"checker":"I-PARSER-JCS-LUA","code":code,"missing":list(missing),"scope":"source_completeness_only_not_semantic_acceptance","status":status},sort_keys=True,separators=(",",":")))

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
    out=list(text); i=0; quote=None
    while i<len(text):
        c=text[i]
        if quote is None and c in "\"'": quote=c; out[i]=" "; i+=1; continue
        if quote is not None:
            if c=="\n": quote=None; i+=1; continue
            out[i]=" "
            if c=="\\" and i+1<len(text): out[i+1]=" "; i+=2; continue
            if c==quote: quote=None
        i+=1
    return "".join(out)

def match_brace(text,start):
    depth=0
    for i in range(start,len(text)):
        if text[i]=="{": depth+=1
        elif text[i]=="}":
            depth-=1
            if depth==0: return i
    return -1

def functions(text):
    clean=strip_comments(text); masked=mask_literals(clean); found={}; spans=[]
    pat=re.compile(r"(?m)(?:^|[;}]\s*)\s*([A-Za-z_][\w\s\*]*?)\b([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{")
    for m in pat.finditer(masked):
        name=m.group(2)
        if name in {"if","for","while","switch"}: continue
        open_at=masked.find("{",m.start(),m.end()); end=match_brace(masked,open_at)
        if end<0 or any(a<=m.start()<b for a,b in spans): continue
        spans.append((m.start(),end+1))
        item={"signature":clean[m.start():open_at],"body":clean[open_at+1:end],"masked":masked[open_at+1:end]}
        found.setdefault(name,[]).append(item)
    return found,clean,masked

def calls(body):
    ignored={"if","for","while","switch","sizeof","return","defined"}
    return [n for n in re.findall(r"\b([A-Za-z_]\w*)\s*\(",body) if n not in ignored]

def closure(name,defs):
    seen=set(); todo=[name]
    while todo:
        cur=todo.pop()
        if cur in seen or cur not in defs or len(defs[cur])!=1: continue
        seen.add(cur)
        todo.extend(n for n in calls(defs[cur][0]["masked"]) if n in defs)
    return seen

def words_for(names,defs):
    return "\n".join(defs[n][0]["masked"] for n in names if n in defs and len(defs[n])==1)

def exact_def(defs,name): return name in defs and len(defs[name])==1

def guarded_limit(code,value):
    # The exact value must participate in an executable branch that fails before proceeding.
    for m in re.finditer(r"\bif\s*\(([^)]*\b"+str(value)+r"\b[^)]*)\)",code,re.S):
        tail=code[m.end():m.end()+500]
        if re.search(r"\b(return|goto)\b",tail): return True
    return False

def parser_contract(defs):
    all_code=words_for(defs,defs)
    utf=[n for n,v in defs.items() if len(v)==1 and re.search(r"utf8|utf_8",n,re.I) and len(set(re.findall(r"0x(?:80|C0|E0|F0|F4)",v[0]["masked"],re.I)))>=3 and re.search(r"\b(return|goto)\b",v[0]["masked"])]
    dup=[n for n,v in defs.items() if len(v)==1 and re.search(r"duplicate|dup(?:licate)?_?key",n+v[0]["masked"],re.I) and re.search(r"\b(return|goto)\b",v[0]["masked"])]
    non=[]
    for n,v in defs.items():
        if len(v)!=1: continue
        b=v[0]["masked"]
        ranges=(re.search(r"(?:0x|U\+)?FDD0",b,re.I) and re.search(r"(?:0x|U\+)?FDEF",b,re.I)
                and re.search(r"(?:0x|U\+)?FFFE",b,re.I) and re.search(r"(?:0x|U\+)?FFFF",b,re.I)
                and re.search(r"(?:0x10FFFF|16\s*\)|<=\s*16|17)",b,re.I))
        recursive=(n in calls(b) or re.search(r"\b(array|object|member|child|value|string|key)\b",b,re.I) and any(x in calls(b) for x in defs))
        if ranges and recursive and re.search(r"NONCHARACTER",b): non.append(n)
    ijson=[n for n,v in defs.items() if len(v)==1 and re.search(r"ijson|i_json|json_value|json_validate",n,re.I)
           and re.search(r"2147483647|isfinite|surrogate|signbit|integer",v[0]["masked"],re.I)
           and re.search(r"string|number|scalar|nul",v[0]["masked"],re.I)]
    if not (utf and dup and non and ijson): return False
    for p in PARSERS:
        reach=closure(p,defs)
        if not (reach&set(utf) and reach&set(dup) and reach&set(non) and reach&set(ijson)): return False
        scoped=words_for(reach,defs)
        limits={
            "chaos_next_use_parse_author":(4096,8192),
            "chaos_next_use_parse_envelope":(4096,8192),
            "chaos_next_use_parse_context":(6144,),
            "chaos_next_use_parse_intent":(4096,),
        }[p]
        if not all(guarded_limit(scoped,n) for n in limits): return False
        body=defs[p][0]["masked"]
        # Bind the front-door validation call (possibly a common transitive
        # helper) ahead of every schema/JCS/Lua/carrier consumer.
        validation_positions=[]
        for n in calls(body):
            if n in defs:
                r=closure(n,defs)
                if r&set(utf) and r&set(dup) and r&set(non) and r&set(ijson):
                    validation_positions.append(body.find(n+"("))
        uses=[m.start() for m in re.finditer(r"\b(jcs|schema|lua|carrier|sha256)\w*\s*\(",body,re.I)]
        if not validation_positions or (uses and min(validation_positions)>=min(uses)): return False
    return "NONCHARACTER" in all_code

def jcs_contract(defs):
    reach=closure("chaos_next_use_jcs",defs); code=words_for(reach,defs)
    has_order=re.search(r"utf16|utf_16",code,re.I) and re.search(r"qsort|sort|compar",code,re.I)
    has_emit=re.search(r"escape|solidus|quote|control",code,re.I) and re.search(r"utf8|utf_8|append|emit|write",code,re.I)
    has_recursive=any(n in calls(defs[n][0]["masked"]) for n in reach)
    return bool(has_order and has_emit and has_recursive and re.search(r"array|object|member",code,re.I))

def sha_contract(defs):
    if not exact_def(defs,"chaos_next_use_sha256"): return False
    code=words_for(closure("chaos_next_use_sha256",defs),defs)
    return bool(re.search(r"SHA256|sha256|digest",code) and re.search(r"update|transform|final",code,re.I) and re.search(r"\breturn\b",code))

def lua_contract(defs):
    entries=("chaos_lua_next_use_load","chaos_lua_next_use_on_action")
    if not all(exact_def(defs,n) for n in entries): return False
    reach=set().union(*(closure(n,defs) for n in entries)); code=words_for(reach,defs)
    m=re.search(r"\blua_newstate\s*\(\s*([A-Za-z_]\w*)\s*,",code)
    if not m or not exact_def(defs,m.group(1)): return False
    alloc=defs[m.group(1)][0]["masked"]
    if not guarded_limit(alloc,262144) or not re.search(r"realloc|malloc|free",alloc): return False
    execution=False
    for n in reach:
        body=defs[n][0]["masked"]
        hook=body.find("lua_sethook("); run=min([x for x in (body.find("lua_pcall("),body.find("lua_pcallk("),body.find("lua_call(")) if x>=0],default=-1)
        if hook>=0 and run>hook:
            site=re.search(r"\blua_sethook\s*\(([^)]*)\)",body,re.S)
            if site:
                args=site.group(1)
                hook_names=re.findall(r"\b([A-Za-z_]\w*)\b",args)
                if any(h in defs and len(defs[h])==1 and guarded_limit(defs[h][0]["masked"],20000) for h in hook_names):
                    execution=True
    if not execution: return False
    all_calls=[]
    for n in reach: all_calls.extend(calls(defs[n][0]["masked"]))
    if any(n in DENY_CALLS for n in all_calls): return False
    for n in all_calls:
        if n in defs or n in SAFE_EXTERNAL or n in SAFE_LUA_CALLS or n in SAFE_CHAOS_LUA_CALLS: continue
        return False
    # No standard-library injection, indirect call syntax, userdata, RNG, I/O, clock, or dynamic load.
    if re.search(r"\(\s*\*\s*\w+\s*\)\s*\(",code): return False
    forbidden=r"\b(?:luaL_openlibs|luaL_requiref|lua_pushcfunction|lua_pushlightuserdata|lua_newuserdata|require|package|io|os|debug|random|dylib|dlopen)\b"
    return not re.search(forbidden,code,re.I)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--root",required=True); root=Path(ap.parse_args().root)
    if not root.is_dir(): emit("ERROR","INVALID_ROOT"); return 2
    existing={n:root/n for n in BASELINE}
    if any(not p.is_file() for p in existing.values()): emit("ERROR","MISSING_INTERFACE_FIXTURE_PATH"); return 2
    newpaths=[root/n for n in NEW]
    if any(not p.is_file() for p in newpaths):
        try:
            if any(hashlib.sha256(existing[n].read_bytes()).hexdigest()!=h for n,h in BASELINE.items()): emit("ERROR","BASELINE_INTERFACE_HASH_MISMATCH"); return 2
        except OSError: emit("ERROR","UNREADABLE_INTERFACE_FIXTURE"); return 2
        emit("RED","MISSING_INTERFACE_PARSER_SLICE",("MISSING_INTERFACE_PARSER_SLICE",)); return 1
    try: text={n:(root/n).read_text(encoding="utf-8") for n in NEW+tuple(BASELINE)}
    except (OSError,UnicodeError): emit("ERROR","UNREADABLE_INTERFACE_SOURCE"); return 2
    next_defs,next_clean,next_mask=functions(text["src/chaos_next_use.c"])
    lua_defs,lua_clean,lua_mask=functions(text["src/chaos_lua.c"])
    all_defs=dict(next_defs)
    for n,v in lua_defs.items(): all_defs.setdefault(n,[]).extend(v)
    missing=[]
    if not all(exact_def(all_defs,n) for n in SYMBOLS): missing.append("MISSING_REQUIRED_DEFINITION")
    headers=strip_comments(text["include/chaos_next_use.h"]+text["include/chaos_lua.h"])
    if not all(len(re.findall(r"\b"+re.escape(n)+r"\s*\(",headers))==1 for n in SYMBOLS): missing.append("INVALID_INTERFACE_DECLARATION")
    if not parser_contract(all_defs): missing.append("UNBOUND_IJSON_VALIDATION")
    if not jcs_contract(all_defs): missing.append("UNBOUND_RFC8785_JCS")
    if not sha_contract(next_defs) or "chaos_next_use_sha256" in lua_defs: missing.append("INVALID_SHA256_OWNERSHIP")
    limits=next_mask+"\n"+lua_mask
    for value in (4096,6144,8192,262144,20000):
        if not guarded_limit(limits,value): missing.append("UNGUARDED_LIMIT_"+str(value))
    if not lua_contract(lua_defs): missing.append("UNSAFE_OR_UNBOUNDED_LUA")
    owned_mask=next_mask+"\n"+lua_mask
    if any(re.search(r"\b"+re.escape(n)+r"\s*\(",owned_mask) for n in DENY_CALLS): missing.append("FORBIDDEN_CAPABILITY")
    if "chaos_next_use.c" not in strip_comments(text["GNUmakefile"]): missing.append("MISSING_BUILD_BINDING")
    if any(n in lua_defs for n in SYMBOLS[:6]) or any(n in next_defs for n in SYMBOLS[6:]): missing.append("INVALID_INTERFACE_OWNERSHIP")
    if missing: emit("RED","MISSING_INTERFACE_PARSER_SLICE",missing); return 1
    emit("GREEN","INTERFACE_PARSER_SLICE_COMPLETE"); return 0

if __name__=="__main__":
    try: sys.exit(main())
    except Exception as exc: emit("ERROR","CHECKER_ERROR_"+type(exc).__name__.upper()); sys.exit(2)
