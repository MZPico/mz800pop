#!/bin/sh
# Launch mz800emu with the pop-800 project configuration (used by .mcp.json and tools/emu.py).
# MZ800EMU_BIN: the emulator binary (default: the local build; CI sets it to its own build, docs/ci.md).
# POP800_RD_SIZE: the RAM disk's size (mz800emu's mr1r18_size: 64K, 256K, 512K, 1M or 16M; default: mz800emu.ini's,
# 1M). POP800_RD_WAIT: the RAM disk's extra wait states, T on every port access (mz800emu's mr1r18_wait, 0-255;
# default: mz800emu.ini's, 0; the MZPico asserts WAIT, at least 1). Either one set: a copy of the INI with those
# values in build/emu/ (docs/ramdisk-tiers.md section 1).
# The RAM disk is in memory only (mr1r18_type = STANDARD: 0xFF at every start, no file read or written), so emulators
# started in parallel or one after another share nothing through it.
dir="$(cd "$(dirname "$0")" && pwd)"
ini="$dir/mz800emu.ini"
if [ -n "$POP800_RD_SIZE$POP800_RD_WAIT" ]; then
    case "$POP800_RD_SIZE" in
        ''|64K|256K|512K|1M|16M) ;;
        *) echo "mz800emu-pop.sh: POP800_RD_SIZE must be 64K, 256K, 512K, 1M or 16M" >&2; exit 2 ;;
    esac
    case "$POP800_RD_WAIT" in
        '') ;;
        *[!0-9]*) echo "mz800emu-pop.sh: POP800_RD_WAIT must be a number of T-states, 0-255" >&2; exit 2 ;;
        *) [ "$POP800_RD_WAIT" -le 255 ] || { echo "mz800emu-pop.sh: POP800_RD_WAIT must be 0-255" >&2; exit 2; } ;;
    esac
    mkdir -p "$dir/../build/emu"
    gen="$dir/../build/emu/mz800emu${POP800_RD_SIZE:+-$POP800_RD_SIZE}${POP800_RD_WAIT:+-w$POP800_RD_WAIT}.ini"
    sed -e "${POP800_RD_SIZE:+s/^mr1r18_size = .*/mr1r18_size = $POP800_RD_SIZE/}" \
        -e "${POP800_RD_WAIT:+s/^mr1r18_wait = .*/mr1r18_wait = $POP800_RD_WAIT/}" "$ini" > "$gen.$$" && mv "$gen.$$" "$gen"
    ini="$gen"
fi
exec "${MZ800EMU_BIN:-/home/matyamar/src/mz800emu/build/build-mz800emu/mz800emu}" \
    --config "$ini" --no-save-ini "$@"
