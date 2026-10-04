#!/bin/sh
# Build the pilot's validator: the repository's own native parser and Lua
# sandbox (src/chaos_lua.c, src/chaos_next_use.c), unmodified, as one shared
# library. Run under hermes-heavy on the VPS. Usage: build_validator.sh <out.so>
set -eu
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
FLAGS=$(/usr/bin/pkg-config --cflags --libs lua5.4)
cc -shared -fPIC -O1 -Wall -Wextra -Werror -Wno-misleading-indentation -std=c99 \
   -Wl,-z,defs -I"$ROOT/include" "$ROOT/src/chaos_next_use.c" "$ROOT/src/chaos_lua.c" \
   $FLAGS -o "$1"
