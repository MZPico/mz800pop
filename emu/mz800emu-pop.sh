#!/bin/sh
# Launch mz800emu with the pop-800 project configuration (used by .mcp.json and tools/emu.py).
exec /home/matyamar/src/mz800emu/build/build-mz800emu/mz800emu --config /home/matyamar/src/pop-800/emu/mz800emu.ini --no-save-ini "$@"
