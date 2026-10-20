# Mouse receipt acknowledgement HUD

This experimental build adds separate click and mouse movement receipt measurements
to Moonlight's performance overlay. It requires the matching Sunshine fork for
receipt acknowledgements.

- [Moonlight client](https://github.com/PR3FL0P/moonlight-qt/tree/input-latency)
- [Streaming core library](https://github.com/PR3FL0P/moonlight-common-c/tree/input-latency)
- [Sunshine host](https://github.com/PR3FL0P/Sunshine/tree/input-latency)

## Build and run Moonlight

Clone the feature branch with submodules so the modified streaming core is included:

```bash
git clone --branch input-latency --recurse-submodules https://github.com/PR3FL0P/moonlight-qt.git
cd moonlight-qt
qmake6 moonlight-qt.pro
make -j4 release
./app/moonlight
```

Install the platform dependencies listed in the main [Moonlight README](../README.md)
first. During a stream, press **Ctrl+Alt+Shift+S** to toggle the performance overlay.

## What the values mean

`Mouse receipt ACK (round trip) click/move` displays the latest acknowledged button
transition (press or release) and sampled mouse movement, in milliseconds.
Measurement starts at the SDL event timestamp on the client and ends when the
Sunshine receipt ACK arrives back at the client. It includes:

1. Event handling, batching, and sending on the Moonlight client.
2. Network transit to Sunshine.
3. Receipt and submission to Sunshine's input queue.
4. Sending the ACK and its return network transit.

SDL event timestamp precision is approximately 1 ms. A movement batch uses its
oldest event's timestamp. Movement is sampled at most 10 times per second; every
button transition is sampled. Reliable retransmission delays contribute to the
reported measurement.

This measures a receipt round trip. It does **not** measure exact one-way delivery,
Windows input injection, game processing, or click-to-photon delay. The computers'
clocks do not need synchronization. Half of network RTT is not presented as a
measured input delay.

`waiting for input` means no receipt ACK has arrived yet. `stale` means the last
ACK is more than five seconds old. `unsupported host` means the server did not
advertise the extension; ordinary input remains compatible with stock Sunshine.

## Download a Windows build from GitHub Actions

Open [Windows Input Latency Build](https://github.com/PR3FL0P/Sunshine/actions/workflows/windows-input-latency.yml).
A successful run provides the **Sunshine-Windows-x64-input-latency** artifact.
Download and extract the artifact, then extract its inner Sunshine ZIP. The inner ZIP contains
`sunshine.exe` and the required assets. The artifact also includes a SHA-256
checksum and source commit details.
You do not need MSYS2 or a local compiler to use this package.

To start another build, select **Run workflow** and the `input-latency` branch.
The workflow builds Windows x64, runs the receipt parser tests, and retains its
artifact for 30 days. The package is unsigned. Stop the installed Sunshine and
back up its configuration before running a custom build. A separate configuration
may require pairing again.

## Sunshine on Windows x64

The host changes are based on Sunshine **v2026.1018.5342**, commit
`3d6e1d6008bd4a24906283ab25fcd0becc0a1c07`. The extension is advertised through
`a=x-ss-input-latency:1` in the RTSP DESCRIBE response.

1. Download [the Windows source bundle](sunshine-input-latency-windows.zip) using
   GitHub's download button and extract it to a short path such as
   `C:\sunshine-latency`. Alternatively, copy this entire `input-latency` directory.
2. Install [MSYS2](https://www.msys2.org/) into `C:\msys64`. Run `pacman -Syu` in
   its UCRT64 terminal and finish the update, restarting the terminal if requested.
   Also install native [Node.js for Windows](https://nodejs.org/).
3. Run `build-windows.cmd`. It installs MSYS2 build dependencies, downloads the
   pinned upstream source and submodules, applies `sunshine-input-latency.patch`,
   builds Sunshine, runs the parser regression tests, and creates a ZIP in
   `packages`. This requires network access, disk space, and time to compile.
4. After a successful build, back up your Sunshine configuration and end the
   stream. Stop the installed Sunshine before running the new build from the
   extracted package. Do not run both instances at once. The build script does
   not change the installed service or migrate its configuration. A separate
   configuration may require pairing again.
5. Connect using the modified Moonlight, enable the overlay, move the mouse, and
   click. The two measurements should appear. To roll back, stop the custom build
   and restart the previously installed Sunshine.

The Windows build script and real streaming session have not been validated on
Windows here. **No prebuilt Sunshine.exe is included.** This bundle contains source
patches and build scripts, rather than an installer.

See the [official Windows build instructions](https://github.com/LizardByte/Sunshine/blob/v2026.1018.5342/docs/building.md).
You can also build the `input-latency` branch of the Sunshine fork directly;
its source changes are already applied, so do not apply the patch again.

## Validation

The Linux Moonlight release build and protocol tests passed. Protocol tests cover
both mouse movement modes, press/release packets, ACK timing, malformed packets,
stale ACKs, movement sampling, stock-host fallback, and host queue/ACK behavior
with mocked transport and encryption boundaries. They also passed with Clang
AddressSanitizer and UndefinedBehaviorSanitizer. They are not a substitute for a
full Windows build or an end-to-end streaming test.

With the Moonlight client and Sunshine fork checked out next to each other:

```bash
python3 scripts/test-input-latency.py ../Sunshine
```

Run Sunshine's added regression tests after building it:

```bash
./cmake-build-input-latency/tests/test_sunshine.exe --gtest_filter='InputLatency.*'
```

The patch files are provided for clean upstream checkouts:

- `moonlight-qt-input-latency.patch`: Moonlight client, based on `e4db5c2`.
- `moonlight-common-c-input-latency.patch`: core library, based on `f900dd4`.
- `sunshine-input-latency.patch`: Sunshine, based on `3d6e1d6`.

Do not apply these patches to the feature branches; their changes are already
included. The Moonlight submodule URL points to the matching library fork and its
revision is pinned in Git.
