set -u
export TMPDIR=<scratch>/ PKG_CONFIG=/usr/bin/pkg-config PKG_CONFIG_PATH=/usr/lib/x86_64-linux-gnu/pkgconfig
unset NYARLATHACK_PACING NYARLATHACK_GAME_TESTS NYARLATHACK_KEEP_ARTIFACTS
for d in main fix1; do for st in bard; do
  cd <scratch>/$d; rm -rf <scratch>/rw-$d
  /usr/bin/python3 scripts/seed_sweep.py --seeds 10-10 --policy baseline-v2 --starts $st --jobs 1 --work <scratch>/rw-$d --game-dir <scratch>/$d/dnethackdir --out <reports>/$d-$st-10 > <reports>/$d-$st-10.log 2>&1
  echo "$d $st exit $?"
done; done
