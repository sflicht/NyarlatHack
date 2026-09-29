# Inventory UI and object-stream tests

## Inventory UI via window procs

- Link real engine objects; rename only `unixmain.o`'s `main`. Keep Lua and native
  description/identification real.
- Drive windowprocs callbacks to select inventory entries and the `dotypeinv`
  action; capture putstr text literally. Use promoted `int` types for
  `BOOLEAN_P`/`CHAR_P` callback arguments.
- Drive the real `display_inventory` picker rather than wrapping same-object calls.
- Snapshot full player and object structs, `moves` and a reseeded RNG probe around
  inspection. Test both `item_use_menu` settings, including unidentified carriers.
- A controlled window port exercises real UI entrypoints, not terminal input or
  natural discovery; label it. Label injected objects and controlled bones returns
  as fixtures, not discovery or real bones loading.

## Object-stream (save serialization) regressions

- Audit the whole top-level save caller and every serialized root before choosing
  a seam; preparation filters are not serialization exclusions. Follow recursive
  contents and ancillary roots (trap ammo, billing chains).
- Expose native static helpers via private objcopy copies; check original object
  hashes stay unchanged.
- Use native buffered writer close/reopen semantics.
- Test hostile input separately from protected output; read output with an
  ordinary reader so incoming hardening can't hide an outgoing omission.
- Force native ID remapping to collide with a live owned record, then retry after
  repair to prove permanent revocation.
- Snapshot the complete nonempty owned record. Explain exclusion by structural
  write boundaries, not by missing plaintext in compressed bytes.
- Don't add destructor traversals over other chains: save cleanup may already have
  freed children or monster extras.
- State exactly what ran: object chains, whole levels, top-level save/bones,
  compression, or terminal gameplay.
