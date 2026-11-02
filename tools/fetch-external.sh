#!/bin/sh
# Clone the reference repositories into external/ (ignored by git).
set -e
cd "$(dirname "$0")/.."
mkdir -p external && cd external
[ -d pop-spectrum ] || git clone -b zx-spectrum-port https://github.com/PotapovSergey77/POP_Spectrum_128K.git pop-spectrum
if [ ! -d SDLPoP ]; then
    git clone --depth 1 https://github.com/NagyD/SDLPoP.git
    # the pop-800 oracle hooks (scripted controls, kid state trace, fixed seed, level patches; see tools/oracle.py)
    (cd SDLPoP && git apply ../../tools/sdlpop-pop800.patch && make -C src)
fi
[ -d mzdisk ] || git clone --depth 1 https://github.com/michalhucik/mzdisk.git
