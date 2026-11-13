#!/bin/bash
# Build the tools the pop-800 build and tests need on a CI runner (docs/ci.md). Each part is skipped when its output
# is already there (the workflow restores them from the actions cache, keyed by the versions below).
#   build_deps.sh sdl3     SDL3, SDL3_image, minizip-ng (mz800emu's, not packaged in Ubuntu 24.04) -> $DEPS
#   build_deps.sh emu      mz800emu at $MZ800EMU_COMMIT -> $EMU_DIR (mz800emu + ui_resources/)
#   build_deps.sh sdlpop   SDLPoP at $SDLPOP_COMMIT + tools/sdlpop-pop800.patch -> external/SDLPoP (the oracle: prince)
#   build_deps.sh mzdisk   mzdisk at $MZDISK_COMMIT -> external/mzdisk/build (mzdsk-create, mzdsk-fsmz)
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
: "${DEPS:=$HOME/mzdeps}" "${EMU_DIR:=$HOME/mz800emu-bin}" "${SRC:=$HOME/depsrc}"
: "${SDL3_TAG:=release-3.4.14}" "${SDL3_IMAGE_TAG:=release-3.4.4}" "${MINIZIP_TAG:=4.2.2}"
: "${MZ800EMU_COMMIT:=ca2b709099139abeb9531f2b71f48084bd7160ce}"
: "${SDLPOP_COMMIT:=3c5add5fb7f83d4ceb542823ab66d00146c4271b}"
: "${MZDISK_COMMIT:=0db3add4b9964dc566442371852056b6aac61217}"
JOBS=$(nproc)
export PKG_CONFIG_PATH="$DEPS/lib/pkgconfig:$DEPS/lib64/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
export LD_LIBRARY_PATH="$DEPS/lib:$DEPS/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
# (mz800emu links minizip-ng by name only, as from /usr/local/lib locally: the linker has to find it in $DEPS)
export LIBRARY_PATH="$DEPS/lib${LIBRARY_PATH:+:$LIBRARY_PATH}"

fetch() {   # fetch <repo url> <commit or tag> <dir>: a shallow checkout of one commit
    rm -rf "$3"; mkdir -p "$3"     # (only scratch dirs and checked-in-place dirs: see keep_existing)
    git -C "$3" init -q
    git -C "$3" fetch -q --depth 1 "$1" "$2"
    git -C "$3" -c advice.detachedHead=false checkout -q FETCH_HEAD
}

log() {     # log <name> <command...>: run quietly into $SRC/<name>.log, show its tail on failure
    local n=$1; shift; mkdir -p "$SRC"
    "$@" >> "$SRC/$n.log" 2>&1 || { echo "FAILED: $*"; tail -60 "$SRC/$n.log"; exit 1; }
}

sdl3() {
    if [ -f "$DEPS/lib/pkgconfig/sdl3-image.pc" ] && [ -f "$DEPS/lib/pkgconfig/minizip-ng.pc" ]; then echo "sdl3: cached"; return; fi
    fetch https://github.com/libsdl-org/SDL.git "refs/tags/$SDL3_TAG" "$SRC/SDL"
    cmake -S "$SRC/SDL" -B "$SRC/SDL/build" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$DEPS" \
        -DCMAKE_INSTALL_LIBDIR=lib -DSDL_SHARED=ON -DSDL_STATIC=OFF -DSDL_TEST_LIBRARY=OFF -DSDL_TESTS=OFF
    log sdl3 cmake --build "$SRC/SDL/build" -j"$JOBS" && log sdl3 cmake --install "$SRC/SDL/build"
    fetch https://github.com/libsdl-org/SDL_image.git "refs/tags/$SDL3_IMAGE_TAG" "$SRC/SDL_image"
    cmake -S "$SRC/SDL_image" -B "$SRC/SDL_image/build" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$DEPS" \
        -DCMAKE_INSTALL_LIBDIR=lib -DSDLIMAGE_VENDORED=OFF -DSDLIMAGE_AVIF=OFF -DSDLIMAGE_JXL=OFF -DSDLIMAGE_TIF=OFF \
        -DSDLIMAGE_WEBP=OFF -DSDLIMAGE_SAMPLES=OFF -DSDLIMAGE_TESTS=OFF
    log sdl3 cmake --build "$SRC/SDL_image/build" -j"$JOBS" && log sdl3 cmake --install "$SRC/SDL_image/build"
    fetch https://github.com/zlib-ng/minizip-ng.git "refs/tags/$MINIZIP_TAG" "$SRC/minizip-ng"
    cmake -S "$SRC/minizip-ng" -B "$SRC/minizip-ng/build" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$DEPS" \
        -DCMAKE_INSTALL_LIBDIR=lib -DMZ_COMPAT=OFF -DMZ_ZSTD=OFF -DMZ_BZIP2=OFF -DMZ_LZMA=OFF -DMZ_PPMD=OFF \
        -DMZ_PKCRYPT=OFF -DMZ_WZAES=OFF -DMZ_OPENSSL=OFF -DMZ_LIBBSD=OFF -DMZ_FETCH_LIBS=OFF
    log sdl3 cmake --build "$SRC/minizip-ng/build" -j"$JOBS" && log sdl3 cmake --install "$SRC/minizip-ng/build"
    echo "sdl3: built SDL3 $(pkg-config --modversion sdl3), SDL3_image $(pkg-config --modversion sdl3-image), minizip-ng $(pkg-config --modversion minizip-ng)"
}

emu() {
    if [ -x "$EMU_DIR/mz800emu" ]; then echo "emu: cached"; return; fi
    fetch https://github.com/MZPico/mz800emu.git "$MZ800EMU_COMMIT" "$SRC/mz800emu"
    cmake -S "$SRC/mz800emu" -B "$SRC/mz800emu/build" -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF \
        -DMZ_BUILD_MZ1500=OFF -DMZ_BUILD_MZ700_PAL=OFF -DMZ_BUILD_MZ700_NTSC=OFF
    log emu cmake --build "$SRC/mz800emu/build" --target mz800emu -j"$JOBS"
    mkdir -p "$EMU_DIR"
    cp "$SRC/mz800emu/build/build-mz800emu/mz800emu" "$EMU_DIR/"
    cp -r "$SRC/mz800emu/ui_resources" "$EMU_DIR/"
    echo "emu: built mz800emu $MZ800EMU_COMMIT"
}

keep_existing() {   # keep_existing <dir>: refuse to replace a checkout that is there but not a complete build (a developer's
    # external/SDLPoP or external/mzdisk, possibly with local changes, reached through a worktree's symlinked external/)
    if [ -e "$1" ] && [ -z "${POP800_REPLACE_EXTERNAL:-}" ]; then
        echo "build_deps: $1 exists but is not a cached build: not replacing it (set POP800_REPLACE_EXTERNAL=1 to do so)" >&2
        exit 1
    fi
}

sdlpop() {
    local d="$ROOT/external/SDLPoP"
    if [ -x "$d/prince" ]; then echo "sdlpop: cached"; return; fi
    keep_existing "$d"
    fetch https://github.com/NagyD/SDLPoP.git "$SDLPOP_COMMIT" "$d"
    git -C "$d" apply "$ROOT/tools/sdlpop-pop800.patch"
    make -C "$d/src" -j"$JOBS" > "$d/build-sdlpop.log" 2>&1 || { tail -30 "$d/build-sdlpop.log"; exit 1; }
    rm -rf "$d/.git" "$d/src"/*.o
    echo "sdlpop: built SDLPoP $SDLPOP_COMMIT + tools/sdlpop-pop800.patch"
}

mzdisk() {
    local d="$ROOT/external/mzdisk"
    if [ -x "$d/build/mzdsk-fsmz" ]; then echo "mzdisk: cached"; return; fi
    keep_existing "$d"
    fetch https://github.com/michalhucik/mzdisk.git "$MZDISK_COMMIT" "$d"
    # (upstream's CMakeLists.txt at this commit lists src/libs/sharpmz_ascii/sharpmz_utf8.c, which is not in the
    # repository; the local copy drops that line, as here)
    [ -f "$d/src/libs/sharpmz_ascii/sharpmz_utf8.c" ] || sed -i '/sharpmz_ascii\/sharpmz_utf8\.c/d' "$d/CMakeLists.txt"
    log mzdisk cmake -S "$d" -B "$d/build" -DCMAKE_BUILD_TYPE=Release
    log mzdisk cmake --build "$d/build" -j"$JOBS" --target mzdsk-create mzdsk-fsmz
    echo "mzdisk: built mzdisk $MZDISK_COMMIT"
}

for part in "$@"; do "$part"; done
