#!/bin/sh
# tools/fetchstat.py --rows on every script of tests/m4-m7_scripts, 6 at a time, each in its own directory (its own
# RAM-disk file): build/meas/k/<script>/calls.jsonl, the input of working_set.py, cost_model.py, session.py
# (docs/ramdisk-tiers.md). usage: tools/fetchmodel/run_all.sh
W="$(cd "$(dirname "$0")/../.." && pwd)"
ls "$W"/tests/m4_scripts "$W"/tests/m5_scripts "$W"/tests/m6_scripts "$W"/tests/m7_scripts | grep '\.txt$' | sed 's/\.txt$//' | sort -u |
    xargs -P 6 -I{} sh -c 'mkdir -p "$1/build/meas/k/$2" && cd "$1/build/meas/k/$2" && python3 "$1/tools/fetchstat.py" --rows --out calls.jsonl "$2" > out.txt 2>&1; echo "$2 rc=$?"' - "$W" {}
