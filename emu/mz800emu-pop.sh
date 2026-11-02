#!/bin/sh
# Launch mz800emu with the pop-800 project configuration (used by .mcp.json and tools/emu.py).
# MZ800EMU_BIN: the emulator binary (default: the local build; CI sets it to its own build, docs/ci.md).
exec "${MZ800EMU_BIN:-/home/matyamar/src/mz800emu/build/build-mz800emu/mz800emu}" \
    --config "$(cd "$(dirname "$0")" && pwd)/mz800emu.ini" --no-save-ini "$@"
