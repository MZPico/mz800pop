# pop-800 build: pasmo assembles raw binaries, tools/mkmzf.py wraps them as MZF,
# mzdisk (external/mzdisk/build) produces the bootable DSK.
PASMO ?= pasmo$(if $(CHEATS), --equ CHEATS=1)$(if $(PACE), --equ PACE=$(PACE))
PY    ?= python3
MZD   ?= external/mzdisk/build
BUILD  = build

all: $(BUILD)/colorbars.mzf $(BUILD)/m0.dsk $(BUILD)/pop800.dsk $(BUILD)/m1test.mzf $(BUILD)/m1.pack

$(BUILD):
	mkdir -p $(BUILD)

# test programs: src/test/<name>.asm -> build/<name>.mzf (load/exec 0x2000)
$(BUILD)/%.bin: src/test/%.asm | $(BUILD)
	$(PASMO) --bin $< $@ $(BUILD)/$*.sym
$(BUILD)/%.mzf: $(BUILD)/%.bin
	$(PY) tools/mkmzf.py $< $@ $* 2000

# M0 boot program (load/exec 0x3000, relocated there by the ROM IPL)
$(BUILD)/m0boot.bin: src/m0/m0boot.asm src/m0/font.inc | $(BUILD)
	cd src/m0 && $(PASMO) --bin m0boot.asm ../../$(BUILD)/m0boot.bin ../../$(BUILD)/m0boot.sym
$(BUILD)/m0boot.mzf: $(BUILD)/m0boot.bin
	$(PY) tools/mkmzf.py $< $@ POP800 3000

# M0 test disk (retired as build/pop800.dsk in M5; tests/m0_test.py boots it): formatted MZ-BASIC disk,
# 2 x 40 tracks, IPLPRO bootstrap = m0boot
$(BUILD)/m0.dsk: $(BUILD)/m0boot.mzf
	rm -f $@
	$(MZD)/mzdsk-create $@ --format-basic 40 --sides 2 > /dev/null
	$(MZD)/mzdsk-fsmz $@ boot put $(BUILD)/m0boot.mzf > /dev/null
	$(MZD)/mzdsk-fsmz $@ boot | grep -E "start|boot_type"

# M5: the game disk. src/boot/boot.asm (the floppy loader, load/exec 0xB000) is the IPLPRO bootstrap; the files
# POP800.D1, D2... hold the compressed RAM-disk data and program (tools/mkgamedisk.py, tools/pzpack.py; compressed
# blocks are cached in build/pzcache). Needs `make assets` and the game (build/m4game.bin, build/m4ovl.bin).
$(BUILD)/boot.bin: src/boot/boot.asm src/boot/rdspeed.asm src/boot/fdc.asm src/boot/unpz.asm src/boot/font.inc src/boot/launch.inc | $(BUILD)
	cd src/boot && $(PASMO) --bin boot.asm ../../$(BUILD)/boot.bin ../../$(BUILD)/boot.sym
$(BUILD)/boot.mzf: $(BUILD)/boot.bin
	$(PY) tools/mkmzf.py $< $@ POP800 B000
# tools/build_assets.py's outputs that the programs and the disk read (its rule: after the `assets` target below)
ASSET_SETS = dungeon dungeon_wall objects sword kid palace palace_wall guard fat skel vizier shadow guard_palace
ASSET_OUT = $(BUILD)/assets/tables.inc $(BUILD)/assets/logic.bin $(BUILD)/assets/seqtbl_z80.bin \
            $(foreach s,$(ASSET_SETS),$(BUILD)/assets/$(s).pack $(BUILD)/assets/$(s).dir)
GAME_ASSETS = $(wildcard $(BUILD)/assets/*.pack $(BUILD)/assets/*.dir $(BUILD)/assets/level*.bin) $(BUILD)/assets/logic.bin $(BUILD)/assets/sound.bin $(BUILD)/assets/fstore_masks.bin $(BUILD)/assets/fstore_gmasks.bin
# M7: the PSG sound bank (effects re-made for 50 Hz from the DOS sound data, the MIDI music arranged by tools/midi2psg.py;
# src/m4/psg.asm plays it); the notes' OPL level curves: assets/opl/levels.json (committed: assets/opl/README.md)
$(BUILD)/assets/sound.bin: tools/sndconv.py tools/midi2psg.py tools/sndsim.py tools/datfile.py assets/opl/levels.json
	$(PY) tools/sndconv.py
# M7 step 11: the presentation's sound banks (sound_pres.bin, _b, _c) from the Master System pieces (assets/sms/: the
# converted streams, committed; remade locally from the ROM only: assets/sms/README.md) + the effects
$(BUILD)/assets/sound_pres.bin: tools/presbank.py tools/sndsim.py $(BUILD)/assets/sound.bin assets/sms/pieces.json $(wildcard assets/sms/*.psg)
	$(PY) tools/presbank.py
# M7: boot.asm is also the launcher (src/boot/launch.inc); src/pres/pres.asm (PRES, the presentation program) goes into
# POP800.PRS with its scenes; the boot keeps the game's compressed image in the RAM disk (tests/m7_launch.py).
# M7 step 6: PRES plays the title (its art: build/assets/title.pack, tools/build_assets.py build_title, which also
# writes title.inc: step f's wait from the ticks model); the PSG player, the PZ decoder and load_saved are included
$(BUILD)/assets/title.inc $(BUILD)/assets/title.pack: tools/build_assets.py tools/titleref.py tools/kidsim.py tools/datfile.py
	$(PY) tools/build_assets.py --title
# M7 step 7: the cutscene engine (src/pres/cut.asm: the room entry of POP800.PRS) and its tables (tools/cutart.py)
$(BUILD)/assets/cut.inc: tools/cutart.py tools/cutsim.py tools/kidsim.py tools/build_assets.py $(BUILD)/assets/seqtbl.bin $(BUILD)/assets/seqtbl_offsets.txt $(BUILD)/assets/seqtbl_z80.bin
	$(PY) tools/cutart.py
$(BUILD)/pres.bin: src/pres/pres.asm src/boot/launch.inc src/boot/unpz.asm src/boot/fdc.asm src/m1/far.asm src/m4/psg.asm src/m4/save.asm $(BUILD)/assets/title.inc src/pres/cut.asm $(BUILD)/assets/cut.inc | $(BUILD)
	cd src/pres && $(PASMO) --bin pres.asm ../../$(BUILD)/pres.bin ../../$(BUILD)/pres.sym
$(BUILD)/pop800.dsk: $(BUILD)/boot.mzf $(BUILD)/pres.bin $(BUILD)/m4game.mzf $(BUILD)/m4ovl.bin $(GAME_ASSETS) $(ASSET_OUT) $(BUILD)/assets/title.pack $(BUILD)/assets/sound_pres.bin tools/mkgamedisk.py tools/pzpack.py tools/cutart.py tools/cutsim.py
	$(PY) tools/mkgamedisk.py $@ $(BUILD)/boot.mzf
m5boot: $(BUILD)/pop800.dsk
	$(PY) tests/m5_boot.py
# the keys Ctrl+A / Ctrl+G and the saved game on a copy of the game disk (src/m4/save.asm)
m5save: $(BUILD)/pop800.dsk
	$(PY) tests/m5_save.py
m7launch: $(BUILD)/pop800.dsk
	$(PY) tests/m7_launch.py
# M7 step 6: the title in PRES (tests/m7_title.py: VRAM against tools/titleref.py, the step timing, the wipe, the keys,
# Ctrl+L, the music against tools/sndsim.py)
m7title: $(BUILD)/pop800.dsk
	$(PY) tests/m7_title.py
# M7 step 7: the level cutscenes: tools/cutsim.py against SDLPoP (tools/cut_suite.py, the POP800_CUT hook), PRES against
# cutsim (tests/m7_cut.py: the C lines, VRAM every frame, the timing, a key, Ctrl+L)
m7story: $(BUILD)/pop800.dsk
	$(PY) tests/m7_story.py

m7cut: $(BUILD)/pop800.dsk
	$(PY) tools/cut_suite.py
	$(PY) tests/m7_cut.py
# M7 step 3: the PSG player against tools/sndsim.py in the emulator (tests/m7_sound.py), the WAVs to listen to
# M7 step 10: the keys (tests/m7_keys.py); the cheat build: the sources assembled with CHEATS=1 in build/cheat (the release
# binaries in build/ stay as they are), the art and data shared
m7keys: $(BUILD)/pop800.dsk $(BUILD)/m4test.mzf cheats
	$(PY) tests/m7_keys.py
cheats:
	mkdir -p $(BUILD)/cheat/build
	rsync -a --delete src Makefile $(BUILD)/cheat/
	for d in tools tests external assets; do ln -sfn $(CURDIR)/$$d $(BUILD)/cheat/$$d; done
	ln -sfn $(CURDIR)/$(BUILD)/assets $(BUILD)/cheat/build/assets
	$(MAKE) -C $(BUILD)/cheat CHEATS=1 build/m4game.mzf build/m4test.mzf build/pop800.dsk
# M8a part 2: the time-exact pacing prototype (game.asm PACE_MODE 1) as a disk to try: build/pace/build/pop800.dsk (the release
# binaries in build/ stay as they are; tests/m8_pace.py pokes the mode into the release binary instead)
pace:
	mkdir -p $(BUILD)/pace/build
	rsync -a --delete src Makefile $(BUILD)/pace/
	for d in tools tests external assets; do ln -sfn $(CURDIR)/$$d $(BUILD)/pace/$$d; done
	ln -sfn $(CURDIR)/$(BUILD)/assets $(BUILD)/pace/build/assets
	$(MAKE) -C $(BUILD)/pace PACE=1 build/m4game.mzf build/pop800.dsk
.PHONY: m7keys cheats pace
m7sound: $(BUILD)/m4game.mzf
	$(PY) tests/m7_sound.py
sound-wav: $(BUILD)/assets/sound.bin
	$(PY) tools/sndsim.py --wav
	$(PY) tools/midi2psg.py --wav
.PHONY: m5boot m5save m7launch m7title m7cut m7story m7sound sound-wav

test: all
	$(PY) tests/smoke_test.py
	$(PY) tests/m0_test.py
	$(PY) tests/m1_compare.py

clean:
	rm -rf $(BUILD)

.PHONY: all test clean

# M1 kernel test scene
$(BUILD)/m1.pack: src/m1/manifest.json tools/pack.py | $(BUILD)
	$(PY) tools/pack.py src/m1/manifest.json $(BUILD)/m1.pack $(BUILD)/m1.dir $(BUILD)/m1.json
src/m1/kernel_gen.inc: tools/gen_kernel.py
	$(PY) tools/gen_kernel.py $@
$(BUILD)/m1test.bin: src/m1/m1test.asm src/m1/gfx.asm src/m1/tables.asm src/m1/far.asm src/m1/kernel_gen.inc | $(BUILD)
	cd src/m1 && $(PASMO) --bin m1test.asm ../../$(BUILD)/m1test.bin ../../$(BUILD)/m1test.sym
$(BUILD)/m1test.mzf: $(BUILD)/m1test.bin
	$(PY) tools/mkmzf.py $< $@ M1TEST 3000
m1: $(BUILD)/m1test.mzf $(BUILD)/m1.pack
	$(PY) tests/m1_compare.py
	$(PY) tests/m1_test.py
.PHONY: m1

# M2 assets: packs for every image set, level blueprints, tables
assets: $(BUILD)/assets/seqtbl.bin $(BUILD)/assets/seqtbl_offsets.txt
	$(PY) tools/build_assets.py
# the same run as a file rule (ASSET_OUT, above), so that a plain `make` in a fresh checkout builds what the programs
# and the disk read
$(ASSET_OUT) &: tools/build_assets.py tools/popdata.py tools/datfile.py $(BUILD)/assets/seqtbl.bin $(BUILD)/assets/seqtbl_offsets.txt
	$(PY) tools/build_assets.py
# SDLPoP's sequence table (external/SDLPoP/src/seqtbl.c) as data: build/assets/seqtbl.bin, seqtbl_offsets.txt (tools/seqdump.c)
SDL2_CFLAGS ?= $(shell pkg-config --cflags sdl2 2>/dev/null || echo -I/usr/include/SDL2)
$(BUILD)/assets/seqtbl.bin $(BUILD)/assets/seqtbl_offsets.txt &: tools/seqdump.c external/SDLPoP/src/seqtbl.c
	mkdir -p $(BUILD)/seqdump $(BUILD)/assets
	$(CC) -O2 -I external/SDLPoP/src $(SDL2_CFLAGS) tools/seqdump.c -o $(BUILD)/seqdump/dump
	$(BUILD)/seqdump/dump
m2: assets
	$(PY) tests/m2_oracle.py 1
	$(PY) tests/m2_oracle.py 4
	$(PY) tests/m2_ega_capture.py
.PHONY: assets m2

# M3 room renderer test (needs `make assets`); M3LEVELS = levels to check (all rooms of each)
M3LEVELS ?= 1 2 3 4 5 6 7 8 9 10 11 12 13 14
$(BUILD)/m3test.bin: src/m3/m3test.asm src/m3/room.asm src/m3/prbuild.asm src/m3/roomfull.asm src/m3/altmods.asm src/m1/gfx.asm src/m1/tables.asm src/m1/far.asm src/m1/kernel_gen.inc $(BUILD)/assets/tables.inc | $(BUILD)
	cd src/m1 && $(PASMO) --bin ../m3/m3test.asm ../../$(BUILD)/m3test.bin ../../$(BUILD)/m3test.sym
$(BUILD)/m3test.mzf: $(BUILD)/m3test.bin
	$(PY) tools/mkmzf.py $< $@ POP800 2000
m3: $(BUILD)/m3test.mzf
	for lv in $(M3LEVELS); do echo "== level $$lv"; $(PY) tests/m3_test.py $$lv | grep -v "pixels differing 0 " || true; done
.PHONY: m3

# M3 animated-tile test and camera demo
m3anim: $(BUILD)/m3test.mzf
	for lv in $(M3LEVELS); do echo "== level $$lv"; $(PY) tests/m3_anim_test.py $$lv | grep -v "^   \|total differing pixels so far 0$$" || true; done
$(BUILD)/m3demo.bin: src/m3/demo.asm src/m3/room.asm src/m3/prbuild.asm src/m3/roomfull.asm src/m3/altmods.asm src/m1/gfx.asm src/m1/tables.asm src/m1/far.asm src/m1/kernel_gen.inc $(BUILD)/assets/tables.inc | $(BUILD)
	cd src/m1 && $(PASMO) --bin ../m3/demo.asm ../../$(BUILD)/m3demo.bin ../../$(BUILD)/m3demo.sym
$(BUILD)/m3demo.mzf: $(BUILD)/m3demo.bin
	$(PY) tools/mkmzf.py $< $@ POP800 2000
m3demo: $(BUILD)/m3demo.mzf
	$(PY) tests/m3_demo.py
.PHONY: m3anim m3demo

# M4: the prince. m4test = logic versus tools/kidsim.py, m4game = the playable program and its screen test
$(BUILD)/m4test.bin: src/m4/m4test.asm src/m4/kid.asm src/m4/kid2.asm src/m4/objects.asm src/m4/rare.asm src/m4/guard.asm src/m4/levelstart.asm src/m4/evres.asm src/m4/events.asm src/m4/gleave.asm src/m4/genter.asm src/m4/shadinit.asm src/m4/sound.asm src/m4/keys.asm src/m4/sndobj.asm src/m3/room.asm src/m3/roomfull.asm src/m3/altmods.asm src/m3/prbuild.asm src/m1/gfx.asm src/m1/tables.asm src/m1/far.asm src/m1/kernel_gen.inc $(BUILD)/assets/tables.inc | $(BUILD)
	cd src/m1 && $(PASMO) --bin ../m4/m4test.asm ../../$(BUILD)/m4test.bin ../../$(BUILD)/m4test.sym
$(BUILD)/m4game.bin: src/m4/game.asm src/m4/ovl.asm src/m4/kid.asm src/m4/objects.asm src/m4/evres.asm src/m4/fx.asm src/m4/sprite.asm src/m4/overlay.asm src/m4/people2.asm src/m4/kid2.asm src/m4/view.asm src/m4/tcache.asm src/m4/rcache.asm src/m4/guard.asm src/m4/sound.asm src/m4/psg.asm src/m4/keyres.asm src/m4/gate.asm src/m4/sndobj.asm src/m4/fslook.asm src/m4/spike.asm src/m3/room.asm src/m1/gfx.asm src/m1/far.asm src/m1/kernel_gen.inc $(BUILD)/assets/tables.inc $(BUILD)/assets/fstore_equ.inc | $(BUILD)
	cd src/m1 && $(PASMO) --bin ../m4/game.asm ../../$(BUILD)/m4game.bin ../../$(BUILD)/m4game.sym
# the frame store's fixed layout (docs/ramdisk-tiers.md "As built: step 1"): the keys from assets/fstore_uses.txt, the
# sizes from the image directories (fstore_equ.inc, the fill's masks fstore_masks.bin for the RAM disk, the tables for the tests)
$(BUILD)/assets/fstore_equ.inc $(BUILD)/assets/fstore_masks.bin $(BUILD)/assets/fstore_gmasks.bin $(BUILD)/assets/fstore_tab1.bin &: tools/fstore.py assets/fstore_uses.txt assets/fstore_guses.txt src/m4/fstore.asm src/m4/fsgen.asm src/m1/kernel_gen.inc src/m1/gfx.asm src/m1/tables.asm $(BUILD)/assets/kid.dir $(BUILD)/assets/sword.dir $(BUILD)/assets/kid.pack $(BUILD)/assets/sword.pack $(foreach g,guard fat skel vizier shadow guard_palace,$(BUILD)/assets/$(g).dir $(BUILD)/assets/$(g).pack)
	$(PY) tools/fstore.py
# code overlays (src/m4/ovl.asm): assembled after the main program against its symbols (build/m4game.sym, written
# with the .bin), packed into build/m4ovl.bin for the RAM disk (tests/m4_game.py setup writes it)
$(BUILD)/ovl_%.inc: src/m4/ovl_%.asm $(BUILD)/m4game.bin tools/ovltool.py
	$(PY) tools/ovltool.py equ $(BUILD)/m4game.sym $< src/m1 $@
$(BUILD)/ovl_room.bin: src/m4/ovl_room.asm src/m3/roomfull.asm $(BUILD)/ovl_room.inc
	cd src/m1 && $(PASMO) --bin ../m4/ovl_room.asm ../../$(BUILD)/ovl_room.bin ../../$(BUILD)/ovl_room.sym
$(BUILD)/ovl_level.bin: src/m4/ovl_level.asm src/m3/altmods.asm src/m4/levelstart.asm src/m4/gstart.asm src/m4/fsvars.inc src/m1/tables.asm src/m3/prbuild.asm src/boot/launch.inc $(BUILD)/ovl_level.inc
	cd src/m1 && $(PASMO) --bin ../m4/ovl_level.asm ../../$(BUILD)/ovl_level.bin ../../$(BUILD)/ovl_level.sym
$(BUILD)/ovl_fill.bin: src/m4/ovl_fill.asm src/m4/fstore.asm src/m4/fsgen.asm src/m4/fsvars.inc src/boot/launch.inc $(BUILD)/assets/fstore_equ.inc $(BUILD)/ovl_fill.inc
	cd src/m1 && $(PASMO) --bin ../m4/ovl_fill.asm ../../$(BUILD)/ovl_fill.bin ../../$(BUILD)/ovl_fill.sym
$(BUILD)/ovl_event.bin: src/m4/ovl_event.asm src/m4/events.asm src/m4/shadinit.asm $(BUILD)/ovl_event.inc
	cd src/m1 && $(PASMO) --bin ../m4/ovl_event.asm ../../$(BUILD)/ovl_event.bin ../../$(BUILD)/ovl_event.sym
$(BUILD)/ovl_gleave.bin: src/m4/ovl_gleave.asm src/m4/gleave.asm $(BUILD)/ovl_gleave.inc
	cd src/m1 && $(PASMO) --bin ../m4/ovl_gleave.asm ../../$(BUILD)/ovl_gleave.bin ../../$(BUILD)/ovl_gleave.sym
$(BUILD)/ovl_genter.bin: src/m4/ovl_genter.asm src/m4/genter.asm src/m4/shadinit.asm $(BUILD)/ovl_genter.inc
	cd src/m1 && $(PASMO) --bin ../m4/ovl_genter.asm ../../$(BUILD)/ovl_genter.bin ../../$(BUILD)/ovl_genter.sym
$(BUILD)/ovl_save.bin: src/m4/ovl_save.asm src/m4/save.asm src/boot/fdc.asm $(BUILD)/ovl_save.inc
	cd src/m1 && $(PASMO) --bin ../m4/ovl_save.asm ../../$(BUILD)/ovl_save.bin ../../$(BUILD)/ovl_save.sym
$(BUILD)/ovl_text.bin: src/m4/ovl_text.asm src/m4/text.asm $(BUILD)/assets/font_text.inc $(BUILD)/ovl_text.inc
	cd src/m1 && $(PASMO) --bin ../m4/ovl_text.asm ../../$(BUILD)/ovl_text.bin ../../$(BUILD)/ovl_text.sym
$(BUILD)/assets/font_text.inc: tools/build_assets.py
	$(PY) tools/build_assets.py --font-text
$(BUILD)/ovl_keys.bin: src/m4/ovl_keys.asm src/m4/keys.asm src/boot/launch.inc $(BUILD)/ovl_keys.inc
	cd src/m1 && $(PASMO) --bin ../m4/ovl_keys.asm ../../$(BUILD)/ovl_keys.bin ../../$(BUILD)/ovl_keys.sym
$(BUILD)/ovl_keys.inc: src/m4/keys.asm src/boot/launch.inc
$(BUILD)/ovl_rare.bin: src/m4/ovl_rare.asm src/m4/hpstrip.asm src/m4/rare.asm $(BUILD)/ovl_rare.inc
	cd src/m1 && $(PASMO) --bin ../m4/ovl_rare.asm ../../$(BUILD)/ovl_rare.bin ../../$(BUILD)/ovl_rare.sym
$(BUILD)/ovl_rare.inc: src/m4/hpstrip.asm src/m4/rare.asm
$(BUILD)/ovl_room.inc: src/m3/roomfull.asm
$(BUILD)/ovl_level.inc: src/m3/altmods.asm src/m4/levelstart.asm src/m4/gstart.asm src/m4/fsvars.inc src/m1/tables.asm src/m3/prbuild.asm src/boot/launch.inc
$(BUILD)/ovl_fill.inc: src/m4/fstore.asm src/m4/fsgen.asm src/m4/fsvars.inc src/boot/launch.inc
$(BUILD)/ovl_event.inc: src/m4/events.asm src/m4/shadinit.asm
$(BUILD)/ovl_gleave.inc: src/m4/gleave.asm
$(BUILD)/ovl_genter.inc: src/m4/genter.asm src/m4/shadinit.asm
$(BUILD)/ovl_save.inc: src/m4/save.asm src/boot/fdc.asm
$(BUILD)/ovl_text.inc: src/m4/text.asm
$(BUILD)/m4ovl.bin: $(BUILD)/ovl_room.bin $(BUILD)/ovl_level.bin $(BUILD)/ovl_event.bin $(BUILD)/ovl_text.bin $(BUILD)/ovl_gleave.bin $(BUILD)/ovl_genter.bin $(BUILD)/ovl_save.bin $(BUILD)/ovl_keys.bin $(BUILD)/ovl_rare.bin $(BUILD)/ovl_fill.bin tools/ovltool.py
	$(PY) tools/ovltool.py pack $(BUILD)/m4game.sym $@ $(BUILD)/ovl_room.bin $(BUILD)/ovl_level.bin $(BUILD)/ovl_event.bin $(BUILD)/ovl_text.bin $(BUILD)/ovl_gleave.bin $(BUILD)/ovl_genter.bin $(BUILD)/ovl_save.bin $(BUILD)/ovl_keys.bin $(BUILD)/ovl_rare.bin $(BUILD)/ovl_fill.bin
$(BUILD)/m4test.mzf: $(BUILD)/m4test.bin
	$(PY) tools/mkmzf.py $< $@ POP800 2000
$(BUILD)/m4game.mzf: $(BUILD)/m4game.bin $(BUILD)/m4ovl.bin $(BUILD)/assets/sound.bin
	$(PY) tools/mkmzf.py $< $@ POP800 1200 2000
m4game: $(BUILD)/m4game.mzf
m4test: $(BUILD)/m4test.mzf
m4: $(BUILD)/m4test.mzf $(BUILD)/m4game.mzf
	$(PY) tests/m4_test.py
	$(PY) tests/m4_game.py
	$(PY) tools/perfcheck.py
# speed regression check alone (tools/perfcheck.py --update after an intended change)
perf: $(BUILD)/m4game.mzf
	$(PY) tools/perfcheck.py
.PHONY: m4 perf m4game m4test

# CI (docs/ci.md, .github/workflows/pr-checks.yml). ci-build: the assets, then everything `all` builds (the game disk
# too) and build/m4test.mzf
CI_TARGETS = $(BUILD)/colorbars.mzf $(BUILD)/m0.dsk $(BUILD)/m1test.mzf $(BUILD)/m1.pack $(BUILD)/m4game.mzf $(BUILD)/m4ovl.bin \
             $(BUILD)/m4test.mzf $(BUILD)/boot.mzf $(BUILD)/pres.bin $(BUILD)/pop800.dsk
ci-build:
	$(MAKE) assets
	$(MAKE) $(CI_TARGETS)
# the PR test tier, exactly what the PR jobs run (tools/ci/check_pr.py; PART=a, b, c or d: one job's part, default all)
PART ?= all
check-pr: $(BUILD)/m4game.mzf $(BUILD)/m4test.mzf $(BUILD)/pop800.dsk
	$(PY) tools/ci/check_pr.py $(PART)
.PHONY: ci-build check-pr

# Local testing (tools/testrun.py, docs/ci.md "Local testing"; the tests: tools/ci/suite.py). The runner builds (make
# ci-build and what the selected tests need), runs the tests in parallel (J jobs, default half the cores) and skips each
# test that passed before with the same inputs. check: the full regression's tests that the changes since BASE (default:
# the merge base with origin/main; BASE=HEAD: the uncommitted changes only) can affect, plus the tests that failed
# last time; ALL=1: every test, cached. check-smoke: a few minutes cold. check-full: every test, no cache (the full
# regression normally runs on GitHub's runners: docs/ci.md). K=text: only the tests whose id contains it (several:
# K="m4_test oracle"). Results: build/testrun/last.json and build/testrun/logs/.
TESTRUN = $(PY) tools/testrun.py $(if $(J),-j $(J)) $(foreach k,$(K),-k $(k))
check-smoke:
	$(TESTRUN) --tier smoke
check:
	$(TESTRUN) --tier $(if $(ALL),all,check) $(if $(BASE),--base $(BASE))
check-full:
	$(TESTRUN) --tier full
.PHONY: check-smoke check check-full
