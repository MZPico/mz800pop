#!/bin/sh
# Launch mz800emu with the pop-800 project configuration (used by .mcp.json and tools/emu.py).
# MZ800EMU_BIN: the emulator binary (default: the local build; CI sets it to its own build, docs/ci.md).
# POP800_RD_SIZE: the RAM disk's size (mz800emu's mr1r18_size: 64K, 256K, 512K, 1M, 2M, 4M, 8M or 16M; default: mz800emu.ini's,
# 1M). POP800_RD_WAIT: the RAM disk's extra wait states, T on every port access (mz800emu's mr1r18_wait, 0-255;
# default: mz800emu.ini's, 0; the MZPico asserts WAIT, at least 1). POP800_NET_RELAY: the NET device's relay, host:port
# (mz800emu's [UNICARD] net_relay, the JSON-lines TCP port of BomberNet's relay/relay.py; default: mz800emu.ini's,
# 127.0.0.1:8766; the duel's network play, docs/duel-design.md 14). POP800_UNICARD: 0 a machine without the Unicard /
# MZPico (its [UNICARD] connected = 0: no NET card, the duel starts local at once), 1 with it (mz800emu.ini's default).
# Any one set: a copy of the INI with those values in build/emu/ (docs/ramdisk-tiers.md section 1).
# The RAM disk is in memory only (mr1r18_type = STANDARD: 0xFF at every start, no file read or written), so emulators
# started in parallel or one after another share nothing through it.
dir="$(cd "$(dirname "$0")" && pwd)"
ini="$dir/mz800emu.ini"
if [ -n "$POP800_RD_SIZE$POP800_RD_WAIT$POP800_NET_RELAY$POP800_UNICARD" ]; then
    case "$POP800_UNICARD" in
        ''|0|1) ;;
        *) echo "mz800emu-pop.sh: POP800_UNICARD must be 0 or 1" >&2; exit 2 ;;
    esac
    case "$POP800_RD_SIZE" in
        ''|64K|256K|512K|1M|2M|4M|8M|16M) ;;
        *) echo "mz800emu-pop.sh: POP800_RD_SIZE must be 64K, 256K, 512K, 1M, 2M, 4M, 8M or 16M" >&2; exit 2 ;;
    esac
    case "$POP800_RD_WAIT" in
        '') ;;
        *[!0-9]*) echo "mz800emu-pop.sh: POP800_RD_WAIT must be a number of T-states, 0-255" >&2; exit 2 ;;
        *) [ "$POP800_RD_WAIT" -le 255 ] || { echo "mz800emu-pop.sh: POP800_RD_WAIT must be 0-255" >&2; exit 2; } ;;
    esac
    if [ -n "$POP800_NET_RELAY" ]; then
        nr_host="${POP800_NET_RELAY%:*}"; nr_port="${POP800_NET_RELAY##*:}"
        case "$POP800_NET_RELAY" in *:*) ;; *) nr_host= ;; esac
        case "$nr_host" in ''|*[!A-Za-z0-9.-]*) nr_host= ;; esac
        case "$nr_port" in ''|*[!0-9]*) nr_port=0 ;; esac
        if [ -z "$nr_host" ] || [ "${#nr_port}" -gt 5 ] || [ "$nr_port" -lt 1 ] || [ "$nr_port" -gt 65535 ]; then
            echo "mz800emu-pop.sh: POP800_NET_RELAY must be host:port (a host name or IPv4 address, a port 1-65535), not '$POP800_NET_RELAY'" >&2
            exit 2
        fi
    fi
    mkdir -p "$dir/../build/emu"
    gen="$dir/../build/emu/mz800emu${POP800_RD_SIZE:+-$POP800_RD_SIZE}${POP800_RD_WAIT:+-w$POP800_RD_WAIT}${POP800_NET_RELAY:+-n$(echo "$POP800_NET_RELAY" | tr ':' '_')}${POP800_UNICARD:+-u$POP800_UNICARD}.ini"
    sed -e "${POP800_RD_SIZE:+s/^mr1r18_size = .*/mr1r18_size = $POP800_RD_SIZE/}" \
        -e "${POP800_RD_WAIT:+s/^mr1r18_wait = .*/mr1r18_wait = $POP800_RD_WAIT/}" \
        -e "${POP800_NET_RELAY:+s/^net_relay = .*/net_relay = $POP800_NET_RELAY/}" \
        -e "${POP800_UNICARD:+/^\[UNICARD\]/,/^\[/s/^connected = .*/connected = $POP800_UNICARD/}" "$ini" > "$gen.$$" && mv "$gen.$$" "$gen"
    ini="$gen"
fi
exec "${MZ800EMU_BIN:-/home/matyamar/src/mz800emu/build/build-mz800emu/mz800emu}" \
    --config "$ini" --no-save-ini "$@"
