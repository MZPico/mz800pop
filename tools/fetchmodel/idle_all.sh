#!/bin/sh
# tools/fetchmodel/idle.py on every script of tests/m4-m7_scripts, 6 at a time, each in its own directory:
# build/meas/idle/<script>/idle.json (docs/ramdisk-tiers.md section 9). usage: tools/fetchmodel/idle_all.sh
W="$(cd "$(dirname "$0")/../.." && pwd)"
ls "$W"/tests/m4_scripts "$W"/tests/m5_scripts "$W"/tests/m6_scripts "$W"/tests/m7_scripts | grep '\.txt$' | sed 's/\.txt$//' | sort -u |
    xargs -P 6 -I{} sh -c 'mkdir -p "$1/build/meas/idle/$2" && cd "$1/build/meas/idle/$2" && python3 "$1/tools/fetchmodel/idle.py" --out idle.json "$2" > out.txt 2>&1; rc=$?; echo "$2 rc=$rc"; exit $rc' - "$W" {}
