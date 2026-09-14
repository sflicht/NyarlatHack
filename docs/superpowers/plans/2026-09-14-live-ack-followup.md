# Live acknowledgement follow-up

The first foundation release was merged in pull request 14. Inspection of its
actual terminal artifacts found a nonempty director diagnostic. A local wrapper
exposed the static error reason: `consumed mailbox lacks exact ACK evidence`.
ACK means acknowledgement. A stronger native launcher test then failed on main.
Issue 3 was reopened rather than treating successful game exit as sufficient.

## Root cause and contract

The engine consumes the request identifier, logs the telegraph and presents the
warning before writing the acknowledgement. Presentation can wait for player
input. An already-running director must be able to keep waiting, within its
existing runtime cap, for an exact locally known request in that interval.

- Do not treat the telegraph or consumed identifier as acceptance.
- Do not publish over an unacknowledged mailbox, retry, retime or alter requests.
- Preserve strict startup checks for incomplete history, unknown consumed
  requests, stale indices and conflicting pending packs.
- Reject changed payloads, mismatched acknowledgements or incompatible progress;
  do not hide corruption as an ordinary in-flight request.
- Fix both the ordinary director loop and the offline launcher, which share the
  mailbox primitive. Do not change C code, the request protocol or save layout.

## Required evidence

Deterministic split event batches must show a known future request, telegraph,
waiting, matching acknowledgement and subsequent valid proposal. Negative
startup/corruption cases remain tested. Real terminal save/restore and normal
pack completion must now have an empty director error log, not merely a zero
game exit status. Run the full suite and an independent review before closing
issue 3 again. No live model calls are required.
