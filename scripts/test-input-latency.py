#!/usr/bin/env python3
"""Exercise actual client envelope/ACK code and Sunshine parser without a live stream.

Usage: python3 scripts/test-input-latency.py /path/to/Sunshine-input-latency
The full Windows server and live network path still require testing on Windows.
"""
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUNSHINE = pathlib.Path(sys.argv[1]).resolve()
COMMON = ROOT / "moonlight-common-c/moonlight-common-c/src"
sender = (COMMON / "InputStream.c").read_text()
wrapper = sender[sender.index("    unsigned char wrappedPacket"):sender.index("    // On GFE 3.22,")]
control = (COMMON / "ControlStream.c").read_text()
handler = control[control.index("static void handleMouseReceiptAck"):control.index("#define IDX_START_A")]
constants = "\n".join(re.findall(r"^#define SS_INPUT_LATENCY_.*$", (COMMON / "Limelight-internal.h").read_text(), re.M))
stream = (SUNSHINE / "src/stream.cpp").read_text()
receiver = stream[stream.index("  void receive_input("):stream.index("  /**\n   * @brief Run the broadcast control-channel worker thread.")]
harness = r'''#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>
#include <string_view>
#include <string>
#include <cstdint>
#include <algorithm>
#include "Limelight.h"
#include "Input.h"
#include "input_latency.h"
#define LE32(x) (x)
#define LE64(x) (x)
#define BE32(x) __builtin_bswap32(x)
CONSTANTS
#define MAX_INPUT_PACKET_SIZE 128
#define LC_ASSERT(x) assert(x)
#define PACKET_SIZE(x) (BE32((x)->packet.header.size) + 4)
struct Holder {
    uint64_t timestampUs;
    union { NV_INPUT_HEADER header; NV_REL_MOUSE_MOVE_PACKET move; NV_ABS_MOUSE_MOVE_PACKET abs; NV_MOUSE_BUTTON_PACKET button; } packet;
};
uint32_t InputLatencyProtocol = 1;
bool encryptedControlStream = true;
uint64_t lastMouseLatencySampleUs = 0;
uint64_t clockUs = 1000000;
uint64_t LiGetMicroseconds() { return clockUs; }
std::vector<unsigned char> wrap(Holder* holder, bool& moreData) {
WRAPPER
    return {packetData, packetData + packetSize};
}
int enetMutex;
int lockCount;
void PltLockMutex(int*) { ++lockCount; }
void PltUnlockMutex(int*) { --lockCount; }
LI_MOUSE_ACK_STATS mouseAckStats[2] = {};
HANDLER
// Only transport/cipher and input queue boundaries are mocked here.
namespace input {
    std::vector<std::vector<uint8_t>> received;
    void passthrough(int&, std::vector<uint8_t>&& bytes) { received.push_back(std::move(bytes)); }
}
struct MockServer {
    std::vector<std::string> sent;
    int flushCount = 0;
    int send(std::string_view bytes, bool) { sent.emplace_back(bytes); return 0; }
    void flush() { ++flushCount; }
};
struct Broadcast { MockServer control_server; };
struct session_t { int input; struct { bool peer = true; } control; Broadcast* broadcast_ref; };
bool encryptionFails = false;
template<size_t N>
std::string_view encode_control(session_t*, std::string_view bytes, std::array<uint8_t, N>&) {
    return encryptionFails ? std::string_view{} : bytes;
}
RECEIVER
Holder holder(uint32_t magic, int size) {
    Holder h = {};
    h.timestampUs = clockUs - 5000;
    h.packet.header.magic = magic;
    h.packet.header.size = BE32(size - 4);
    return h;
}
void checkPacket(uint32_t magic, int size) {
    auto h = holder(magic, size);
    lastMouseLatencySampleUs = 0;
    bool more = true;
    auto bytes = wrap(&h, more);
    assert(!more && h.timestampUs == 0);
    auto receipt = input_latency::parse(bytes);
    assert(receipt && receipt->input.size() == unsigned(size));
    assert(std::memcmp(receipt->input.data(), &h.packet, size) == 0);
    Broadcast broadcast;
    session_t session {0, {}, &broadcast};
    input::received.clear();
    receive_input(&session, std::vector<uint8_t>(bytes));
    assert(input::received.size() == 1 && input::received[0].size() == unsigned(size));
    assert(std::memcmp(input::received[0].data(), &h.packet, size) == 0);
    assert(broadcast.control_server.sent.size() == 1 && broadcast.control_server.flushCount == 1);
    auto response = broadcast.control_server.sent[0];
    assert(response.size() == 16 && uint8_t(response[0]) == 0xf0 && uint8_t(response[1]) == 0x55);
    assert(response[2] == 12 && response[3] == 0);
    assert(std::memcmp(response.data() + 4, receipt->ack.data(), 12) == 0);
    // Missing peer and encryption failure still forward input, but cannot send an ACK.
    session.control.peer = false;
    receive_input(&session, std::vector<uint8_t>(bytes));
    session.control.peer = true;
    encryptionFails = true;
    receive_input(&session, std::vector<uint8_t>(bytes));
    encryptionFails = false;
    assert(input::received.size() == 3 && broadcast.control_server.sent.size() == 1);
    // A standard packet is forwarded without an acknowledgement.
    receive_input(&session, std::vector<uint8_t>(receipt->input.begin(), receipt->input.end()));
    assert(input::received.size() == 4 && broadcast.control_server.sent.size() == 1);
    auto corruptEnvelope = bytes;
    corruptEnvelope[3] ^= 1;
    receive_input(&session, std::move(corruptEnvelope));
    assert(input::received.size() == 4 && broadcast.control_server.sent.size() == 1);
    clockUs += 7000;
    handleMouseReceiptAck(receipt->ack.data(), receipt->ack.size());
    int index = (magic == 5 || magic == 7) ? 1 : 0;
    assert(mouseAckStats[index].lastDelayUs == 12000);
    assert(mouseAckStats[index].lastAckTimeUs == clockUs && lockCount == 0);
    // Every truncated envelope must be rejected.
    for (size_t i = 0; i < bytes.size(); ++i) {
        assert(!input_latency::parse(std::span(bytes).first(i)));
    }
    for (auto offset : {3, 4, 7, 19, 20}) {
        auto corrupt = bytes;
        corrupt[offset] ^= 1;
        // 8 XOR 1 is 9: another valid button type.
        if (offset == 20 && (magic == 8 || magic == 9)) continue;
        assert(!input_latency::parse(corrupt));
    }
    // Truncated, future, and obsolete ACKs cannot replace the last sample.
    auto saved = mouseAckStats[index];
    handleMouseReceiptAck(receipt->ack.data(), 11);
    std::array<uint8_t, 12> invalid = receipt->ack;
    uint64_t future = clockUs + 1;
    std::memcpy(invalid.data(), &future, 8);
    handleMouseReceiptAck(invalid.data(), 12);
    uint64_t old = clockUs - 500000;
    std::memcpy(invalid.data(), &old, 8);
    handleMouseReceiptAck(invalid.data(), 12);
    assert(mouseAckStats[index].sampleCount == saved.sampleCount);
}
int main() {
    checkPacket(7, sizeof(NV_REL_MOUSE_MOVE_PACKET));
    checkPacket(5, sizeof(NV_ABS_MOUSE_MOVE_PACKET));
    checkPacket(8, sizeof(NV_MOUSE_BUTTON_PACKET));
    checkPacket(9, sizeof(NV_MOUSE_BUTTON_PACKET));
    bool more = true;
    auto h = holder(7, sizeof(NV_REL_MOUSE_MOVE_PACKET));
    lastMouseLatencySampleUs = clockUs;
    auto bytes = wrap(&h, more);
    assert(bytes.size() == sizeof(NV_REL_MOUSE_MOVE_PACKET) && more);
    clockUs += 100000;
    bytes = wrap(&h, more);
    assert(input_latency::parse(bytes) && !more);
    InputLatencyProtocol = 0;
    for (auto magic : {5u, 7u, 8u, 9u}) {
        h = holder(magic, sizeof(NV_MOUSE_BUTTON_PACKET));
        more = true;
        bytes = wrap(&h, more);
        assert(bytes.size() == sizeof(NV_MOUSE_BUTTON_PACKET) && more);
        assert(std::memcmp(bytes.data(), &h.packet, bytes.size()) == 0);
    }
    InputLatencyProtocol = 1;
    encryptedControlStream = false;
    h = holder(8, sizeof(NV_MOUSE_BUTTON_PACKET));
    bytes = wrap(&h, more);
    assert(bytes.size() == sizeof(NV_MOUSE_BUTTON_PACKET));
    // Unknown or nested packet types and incorrect inner lengths are rejected.
    std::vector<uint8_t> malformed(28);
    malformed[3] = 24; malformed[4] = 0xf0; malformed[7] = 0x55;
    malformed[19] = 8; malformed[20] = 3;
    assert(!input_latency::parse(malformed));
    malformed[20] = 0xf0; malformed[23] = 0x55;
    assert(!input_latency::parse(malformed));
    std::array<uint8_t, 5> endian {0, 0x12, 0x34, 0x56, 0x78};
    assert(input_latency::read32(endian.data() + 1, true) == 0x12345678u);
    assert(input_latency::read32(endian.data() + 1, false) == 0x78563412u);
    puts("PASS: client/server envelope compatibility, both motion modes, buttons, ACK timing, invalid/stale ACKs, malformed packets, rate limit, stock-host fallback");
}
'''.replace("RECEIVER", receiver).replace("CONSTANTS", constants).replace("WRAPPER", wrapper).replace("HANDLER", handler)
with tempfile.TemporaryDirectory(prefix="moonlight-input-latency-") as tmp:
    source = pathlib.Path(tmp) / "protocol.cpp"
    binary = pathlib.Path(tmp) / "protocol"
    source.write_text(harness)
    subprocess.run([os.environ.get("CXX", "g++"), "-std=c++20", "-Wall", "-Wextra", "-Werror", "-Wno-sign-compare",
                    *os.environ.get("TEST_SANITIZERS", "").split(), "-g", str(source), "-I", str(COMMON),
                    "-I", str(SUNSHINE / "src"), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
