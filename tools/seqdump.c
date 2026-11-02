/* Dump SDLPoP's sequence table (external/SDLPoP/src/seqtbl.c) for tools/build_assets.py, tools/kidsim.py and
   tools/cutart.py: build/assets/seqtbl.bin (the table's bytes) and build/assets/seqtbl_offsets.txt (sequence id, offset
   from SEQTBL_BASE). Compiled into build/seqdump/ and run from the project root by the Makefile (`make assets`). */
#include "common.h"
fixes_options_type* fixes = NULL; custom_options_type* custom = NULL;
#include "seqtbl.c"
static int fail(const char* what) { perror(what); return 1; }
int main(void) {
    FILE* f = fopen("build/assets/seqtbl.bin", "wb");
    if (!f) return fail("build/assets/seqtbl.bin");
    if (fwrite(seqtbl, 1, sizeof(seqtbl), f) != sizeof(seqtbl) || fclose(f) != 0) return fail("build/assets/seqtbl.bin");
    f = fopen("build/assets/seqtbl_offsets.txt", "w");
    if (!f) return fail("build/assets/seqtbl_offsets.txt");
    for (unsigned i = 0; i < sizeof(seqtbl_offsets)/sizeof(seqtbl_offsets[0]); i++)
        if (fprintf(f, "%u %u\n", i, seqtbl_offsets[i] - SEQTBL_BASE) < 0) { fclose(f); return fail("build/assets/seqtbl_offsets.txt"); }
    if (fclose(f) != 0) return fail("build/assets/seqtbl_offsets.txt");
    printf("seqtbl %zu bytes, %zu offsets, base %#x\n", sizeof(seqtbl), sizeof(seqtbl_offsets)/sizeof(seqtbl_offsets[0]), SEQTBL_BASE);
    return 0;
}
