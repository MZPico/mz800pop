#!/usr/bin/env python3
"""The RAM-disk access log of a patched mz800emu, and the MZPico's copy-on-write RAM disk model (docs/ramdisk-tiers.md
section 16).

The patch (`rdlog.py patch path/to/ramdisk.c`, applied by `tools/ci/build_deps.sh emu_rdlog` to a copy of mz800emu at
the pinned commit) adds a log of every STD RAM-disk data access to src/emulator/hw-generic/ramdisk/ramdisk.c, switched
on by the environment variable MZ800EMU_RDLOG=<path>. The stock emulator has no such log; a build without the patch
writes nothing. The log is a sequence of runs of consecutive bytes (same direction, same page, address +1), each a
16-byte record: 'R' or 'W', u8 page, u16 start, u32 length, u64 CPU cycle of the run's first byte; a 'W' record is
followed by its data bytes. 'F' + the cycle: a reset read on port F8h (page 0, address 0). Only the port accesses are
logged: the MCP's region_write (the test harness's pokes) is not.

The model (Cow): the card's RAM disk is a read-only image in flash plus a pool of SRAM blocks. A write to a block that
is not in the pool compares the byte with the image's and allocates the block only when they differ (write-compare);
a block once allocated stays (no rule frees it when it matches the image again), so the pool's peak is its final
size. Cow(free=True) models a card that does free such a block (checked after each write run).

usage: rdlog.py patch RAMDISK_C          patch an mz800emu source file (once)
       rdlog.py stat LOG IMAGE [BLOCK]   replay a log against an image: the blocks the pool needs
"""
import base64, struct, sys

REC = struct.Struct('<BBHIQ')
PAGE = 0x10000


def read_log(path):
    """-> iterator of (kind, page, start, length, cycle, data or None); kind 'R', 'W' or 'F'"""
    b = open(path, 'rb').read(); i = 0; n = len(b)
    while i + 16 <= n:
        k, pg, st, ln, cy = REC.unpack_from(b, i); i += 16
        k = chr(k)
        if k == 'W':
            if i + ln > n: raise ValueError('truncated log %s: a write of %d bytes at %d' % (path, ln, i))
            yield k, pg, st, ln, cy, b[i:i + ln]; i += ln
        elif k in 'RF':
            yield k, pg, st, ln, cy, None
        else:
            raise ValueError('bad record %r at %d of %s' % (k, i - 16, path))
    if i != n: raise ValueError('truncated log %s: %d of %d bytes' % (path, i, n))


def rd_regions(e):
    """{page: MCP region id} of the emulated STD RAM disk"""
    regs = sorted((r for r in e.call('regions_list')['regions'] if r['kind'] == 'ramdisk_std'), key=lambda r: r['id'])
    return {p: r['id'] for p, r in enumerate(regs)}


def read_image(e, pages=None, chunk=32768):
    """the RAM disk's pages (all, or the first `pages`) as one bytes object, page 0 first"""
    regs = rd_regions(e); out = bytearray()
    for p in range(len(regs) if pages is None else pages):
        for off in range(0, PAGE, chunk):
            r = e.call('region_read', region_id=regs[p], offset=off, length=chunk)
            out += base64.b64decode(r['data_b64'])
    return bytes(out)


def write_image(e, img, chunk=4096):
    """put an image (whole 64 KB pages, page 0 first) into the RAM disk, as the card starts with it"""
    regs = rd_regions(e)
    assert len(img) % PAGE == 0 and len(img) // PAGE <= len(regs), 'image of %d bytes, %d pages' % (len(img), len(regs))
    for off in range(0, len(img), chunk):
        e.call('region_write', region_id=regs[off // PAGE], offset=off % PAGE,
               data_b64=base64.b64encode(img[off:off + chunk]).decode())


class Cow:
    """the copy-on-write pool over a read-only image, with write-compare, in blocks of `block` bytes"""
    def __init__(self, image, block=1024, free=False):
        self.image = bytes(image); self.block = block; self.pool = {}       # block number -> its first allocation's
        self.mem = bytearray(image); self.writes = 0; self.cycle = 0        # (cycle, page, address) of the changing byte
        self.outside = 0                                                    # writes past the image's end
        self.free = free; self.peak = 0; self.freed = 0                     # free: a block that matches the image
                                                                            # again after a write leaves the pool
    def write(self, page, start, data, cycle):
        self.cycle = cycle; self.writes += len(data)
        img, mem, blk, pool = self.image, self.mem, self.block, self.pool
        o = page * PAGE + start; end = o + len(data)
        if end > len(img): self.outside += 1; return
        if mem[o:end] == data and img[o:end] == data: return        # (a write of what is there: the common case)
        for i, v in enumerate(data):
            a = o + i; b = a // blk
            if b not in pool:
                if img[a] == v: continue
                pool[b] = (cycle, page, start + i)
            mem[a] = v
        self.peak = max(self.peak, len(pool))
        if self.free:
            for b in range(o // blk, (end - 1) // blk + 1):
                if b in pool and mem[b * blk:(b + 1) * blk] == img[b * blk:(b + 1) * blk]:
                    del pool[b]; self.freed += 1
    def feed(self, path, until=None):
        """replay a log's writes (up to cycle `until`, exclusive); returns the number of blocks"""
        for k, pg, st, ln, cy, data in read_log(path):
            if until is not None and cy >= until: break
            if k == 'W': self.write(pg, st, data, cy)
        return len(self.pool)
    def blocks(self): return len(self.pool)
    def regions(self):
        """the allocated blocks as (page, first address, last address + 1) runs"""
        out = []
        for b in sorted(self.pool):
            a = b * self.block
            if out and out[-1][0] == a // PAGE and out[-1][2] == a % PAGE: out[-1][2] += self.block
            else: out.append([a // PAGE, a % PAGE, a % PAGE + self.block])
        return [tuple(r) for r in out]


def format_regions(regs):
    return ', '.join('%d:%04X-%04X' % (p, a, min(b, PAGE) - 1) for p, a, b in regs)


# ---- the emulator patch (src/emulator/hw-generic/ramdisk/ramdisk.c of mz800emu ca2b709)
LOGGER = r'''
/* ---- pop-800 tools/rdlog.py: RAM-disk access run log (a test build's patch, not for upstream) ----
 * MZ800EMU_RDLOG=<path>: every STD RAM-disk data access, coalesced into runs of consecutive bytes
 * (same direction, same bank, address +1). Record (16 bytes): 'R' or 'W', u8 bank, u16 start, u32 len, u64 CPU cycle
 * at the run's first byte; a 'W' record is followed by its len data bytes. 'F' + u64 cycle = a reset read on F8h. */
#include <stdint.h>
static FILE *rdl_fp = NULL; static int rdl_tried = 0;
static uint8_t rdl_dir = 0, rdl_bank = 0; static uint16_t rdl_start = 0; static uint32_t rdl_len = 0;
static uint64_t rdl_cyc = 0, rdl_hi = 0; static uint32_t rdl_last = 0; static uint8_t rdl_data [ 0x10000 ];
static uint64_t rdl_now ( void ) {
    uint32_t c = g_mzarch_main.cpu ? g_mzarch_main.cpu->total_cycles : 0;
    if ( c < rdl_last ) rdl_hi += 0x100000000ULL;
    rdl_last = c; return rdl_hi | c;
}
static void rdl_flush ( void ) {
    if ( !rdl_fp || !rdl_len ) return;
    uint8_t h [ 16 ]; h [ 0 ] = rdl_dir; h [ 1 ] = rdl_bank; h [ 2 ] = rdl_start & 0xff; h [ 3 ] = rdl_start >> 8;
    for ( int i = 0; i < 4; i++ ) h [ 4 + i ] = ( rdl_len >> ( 8 * i ) ) & 0xff;
    for ( int i = 0; i < 8; i++ ) h [ 8 + i ] = ( rdl_cyc >> ( 8 * i ) ) & 0xff;
    fwrite ( h, 1, 16, rdl_fp );
    if ( rdl_dir == 'W' ) fwrite ( rdl_data, 1, rdl_len, rdl_fp );
    rdl_len = 0;
}
static void rdl_atexit ( void ) { if ( rdl_fp ) { rdl_flush ( ); fclose ( rdl_fp ); rdl_fp = NULL; } }
static int rdl_open ( void ) {
    if ( !rdl_tried ) {
        rdl_tried = 1; const char *p = getenv ( "MZ800EMU_RDLOG" );
        if ( p && *p ) { rdl_fp = fopen ( p, "wb" ); if ( rdl_fp ) { setvbuf ( rdl_fp, NULL, _IOFBF, 1 << 20 ); atexit ( rdl_atexit ); } }
    }
    return rdl_fp != NULL;
}
static void rdl_access ( uint8_t dir, uint8_t bank, uint16_t off, uint8_t value ) {
    if ( !rdl_open ( ) ) return;
    if ( !( rdl_len && rdl_dir == dir && rdl_bank == bank && (uint16_t) ( rdl_start + rdl_len ) == off && off != 0 && rdl_len < 0x10000 ) ) {
        rdl_flush ( ); rdl_dir = dir; rdl_bank = bank; rdl_start = off; rdl_cyc = rdl_now ( );
    }
    if ( dir == 'W' ) rdl_data [ rdl_len ] = value;
    rdl_len++;
}
static void rdl_reset ( void ) {
    if ( !rdl_open ( ) ) return;
    rdl_flush ( ); uint64_t c = rdl_now ( ); uint8_t h [ 16 ] = { 'F' };
    for ( int i = 0; i < 8; i++ ) h [ 8 + i ] = ( c >> ( 8 * i ) ) & 0xff;
    fwrite ( h, 1, 16, rdl_fp );
}
/* ---- end of the RAM-disk access run log ---- */

uint8_t ramdisk_std_read_byte ( unsigned addr ) {
'''
EDITS = [
    ('\nuint8_t ramdisk_std_read_byte ( unsigned addr ) {\n', LOGGER),
    ('''        case 0xf8:
            g_ramdisk.std.bank = 0x00;''', '''        case 0xf8:
            rdl_reset ( );
            g_ramdisk.std.bank = 0x00;'''),
    ('''            ramdisc_addr = ( g_ramdisk.std.bank << 16 ) | g_ramdisk.std.offset++;
            return g_ramdisk.std.memory [ ramdisc_addr ];''', '''            rdl_access ( 'R', g_ramdisk.std.bank, g_ramdisk.std.offset, 0 );
            ramdisc_addr = ( g_ramdisk.std.bank << 16 ) | g_ramdisk.std.offset++;
            return g_ramdisk.std.memory [ ramdisc_addr ];'''),
    ('''            ramdisc_addr = ( g_ramdisk.std.bank << 16 ) | g_ramdisk.std.offset++;
            if ( !( g_ramdisk.std.type & RAMDISK_IS_READONLY ) ) {''', '''            rdl_access ( 'W', g_ramdisk.std.bank, g_ramdisk.std.offset, value );
            ramdisc_addr = ( g_ramdisk.std.bank << 16 ) | g_ramdisk.std.offset++;
            if ( !( g_ramdisk.std.type & RAMDISK_IS_READONLY ) ) {'''),
]


def patch_source(path):
    s = open(path).read()
    if 'MZ800EMU_RDLOG' in s: return False
    for a, b in EDITS:
        if s.count(a) != 1: raise SystemExit('rdlog.py patch: %s does not have the expected code (%r...)' % (path, a[:60]))
        s = s.replace(a, b, 1)
    open(path, 'w').write(s)
    return True


def main():
    a = sys.argv[1:]
    if a[:1] == ['patch'] and len(a) == 2:
        print('rdlog.py: %s %s' % ('patched' if patch_source(a[1]) else 'already patched', a[1]))
    elif a[:1] == ['stat'] and len(a) in (3, 4):
        c = Cow(open(a[2], 'rb').read(), int(a[3]) if len(a) == 4 else 1024)
        c.feed(a[1])
        print('%d bytes written, %d blocks of %d bytes: %s' % (c.writes, c.blocks(), c.block, format_regions(c.regions())))
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main()
