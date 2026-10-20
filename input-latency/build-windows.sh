#!/usr/bin/env bash
# Build a separate Sunshine package without changing the installed service.
set -euo pipefail
if [[ "${MSYSTEM:-}" != "UCRT64" ]]; then
    echo 'Run build-windows.cmd, or use the MSYS2 UCRT64 terminal.' >&2
    exit 1
fi
if ! command -v node >/dev/null || [[ "$(node -p 'process.platform')" != win32 ]]; then
    echo 'Install native Windows Node.js, reopen the terminal, then run this again.' >&2
    exit 1
fi
bundle_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
pacman -S --needed --noconfirm git \
    mingw-w64-ucrt-x86_64-boost mingw-w64-ucrt-x86_64-cmake \
    mingw-w64-ucrt-x86_64-ninja mingw-w64-ucrt-x86_64-cppwinrt \
    mingw-w64-ucrt-x86_64-curl-winssl mingw-w64-ucrt-x86_64-miniupnpc \
    mingw-w64-ucrt-x86_64-onevpl mingw-w64-ucrt-x86_64-openssl \
    mingw-w64-ucrt-x86_64-libtiff mingw-w64-ucrt-x86_64-harfbuzz \
    mingw-w64-ucrt-x86_64-opus mingw-w64-ucrt-x86_64-toolchain \
    mingw-w64-ucrt-x86_64-qt6-static mingw-w64-ucrt-x86_64-MinHook \
    mingw-w64-ucrt-x86_64-nsis
if [[ ! -d "$bundle_dir/Sunshine" ]]; then
    git clone --branch v2026.1018.5342 --depth 1 --recurse-submodules \
        https://github.com/LizardByte/Sunshine.git "$bundle_dir/Sunshine"
fi
cd "$bundle_dir/Sunshine"
if [[ "$(git rev-parse HEAD)" != 3d6e1d6008bd4a24906283ab25fcd0becc0a1c07 ]]; then
    echo 'Unexpected Sunshine revision. Use a fresh folder for this bundle.' >&2
    exit 1
fi
if git apply --reverse --check "$bundle_dir/sunshine-input-latency.patch" 2>/dev/null; then
    echo 'Receipt ACK patch already applied.'
else
    git apply --check "$bundle_dir/sunshine-input-latency.patch"
    git apply "$bundle_dir/sunshine-input-latency.patch"
fi
cmake -S . -B cmake-build-input-latency -G Ninja \
    -DCMAKE_BUILD_TYPE=Release -DBUILD_DOCS=OFF -DBUILD_TESTS=ON
cmake --build cmake-build-input-latency --parallel 2
./cmake-build-input-latency/tests/test_sunshine.exe --gtest_filter='InputLatency.*'
cpack -G ZIP --config cmake-build-input-latency/CPackConfig.cmake -B "$bundle_dir/packages"
echo 'Package built in packages/. The installed Sunshine service was not modified.'
