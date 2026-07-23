#pragma once

#include <stdint.h>
#include <stddef.h>

// ---------------------------------------------------------------------------
// Unified protocol frame — contracts/PROTOCOLS_CONTRACT.md section 3.
//
// This is the wire format the web dashboard (web/js/protocol.js) and the host
// Python library (host/myactuator_lib/protocol/frame.py) speak. It is a pure
// C++ implementation with NO Arduino dependency so it can be unit-tested on
// the host with g++ (see the CRC cross-check against the Python/JS reference).
//
// Frame layout (64 bytes), faithful to the contract diagram:
//   Header (8):  Sync Word 0xAA55 LE (2) | Frame Type (1) | Header Seq (1) | Reserved (4)
//   Motor ID (1)
//   Command Type (1)
//   Sequence Number (1)
//   Payload (32)
//   CRC-16/CCITT (2)
//   Padding (19)
//
// CRC: CRC-16/CCITT-FALSE (poly=0x1021, init=0xFFFF, non-reflected) — matches
// the Python host library and the JS port. Computed over header (8) + body (35)
// = bytes [0, 43).
// ---------------------------------------------------------------------------

namespace serial_frame {

static const uint16_t SYNC_WORD     = 0xAA55;
static const uint8_t  FRAME_SIZE    = 64;
static const uint8_t  HEADER_SIZE   = 8;
static const uint8_t  RESERVED_SIZE = 4;
static const uint8_t  PAYLOAD_SIZE  = 32;
static const uint8_t  PADDING_SIZE  = 19;
static const uint16_t CRC_POLY      = 0x1021;
static const uint16_t CRC_INIT      = 0xFFFF;

// Byte offsets within the packed frame.
static const uint8_t  BODY_OFFSET = HEADER_SIZE;             // 8
static const uint8_t  BODY_SIZE   = 3 + PAYLOAD_SIZE;        // 35 (motor_id + command_type + sequence + payload)
static const uint8_t  CRC_OFFSET  = BODY_OFFSET + BODY_SIZE;  // 43
// PADDING_OFFSET = 45

// Frame type enum (contract section 3.3).
enum FrameType {
    FRAME_TYPE_STATUS_REPORT   = 0x01,
    FRAME_TYPE_POSITION_CMD    = 0x02,
    FRAME_TYPE_VELOCITY_CMD    = 0x03,
    FRAME_TYPE_TORQUE_CMD      = 0x04,
    FRAME_TYPE_PARAM_READ      = 0x05,
    FRAME_TYPE_PARAM_WRITE     = 0x06,
    FRAME_TYPE_DIAGNOSTIC      = 0x07,
    FRAME_TYPE_FIRMWARE_UPDATE = 0x08,
    FRAME_TYPE_HEARTBEAT       = 0x09,
};

// Decoded view of a frame (after unpacking).
struct Frame {
    uint8_t frameType;
    uint8_t motorId;
    uint8_t commandType;
    uint8_t sequence;
    uint8_t headerSeq;
    uint8_t payload[PAYLOAD_SIZE];
    uint8_t payloadLen;
};

// CRC-16/CCITT-FALSE (poly=0x1021, init=0xFFFF, non-reflected).
// Matches web/js/protocol.js crc16Ccitt and host frame.py crc16_ccitt.
inline uint16_t crc16Ccitt(const uint8_t* data, uint8_t len,
                           uint16_t init = CRC_INIT, uint16_t poly = CRC_POLY) {
    uint16_t crc = init & 0xFFFF;
    for (uint8_t i = 0; i < len; ++i) {
        crc ^= (uint16_t)data[i] << 8;
        for (uint8_t b = 0; b < 8; ++b) {
            if (crc & 0x8000) crc = (uint16_t)((crc << 1) ^ poly) & 0xFFFF;
            else              crc = (uint16_t)(crc << 1) & 0xFFFF;
        }
    }
    return crc & 0xFFFF;
}

// Pack a frame into a 64-byte buffer (out must be >= FRAME_SIZE).
// Returns FRAME_SIZE on success, 0 if out is null.
inline uint8_t pack(const Frame& in, uint8_t* out) {
    if (!out) return 0;
    for (uint8_t i = 0; i < FRAME_SIZE; ++i) out[i] = 0;

    // Header (8): sync(2 LE) | frameType(1) | headerSeq(1) | reserved(4)
    out[0] = SYNC_WORD & 0xFF;
    out[1] = (SYNC_WORD >> 8) & 0xFF;
    out[2] = in.frameType & 0xFF;
    out[3] = in.headerSeq & 0xFF;
    // reserved bytes [4..7] stay zero

    // Body (35): motorId(1) | commandType(1) | sequence(1) | payload(32)
    out[8]  = in.motorId & 0xFF;
    out[9]  = in.commandType & 0xFF;
    out[10] = in.sequence & 0xFF;
    for (uint8_t i = 0; i < PAYLOAD_SIZE; ++i) out[11 + i] = in.payload[i];

    // CRC over header + body = bytes [0, 43)
    uint16_t crc = crc16Ccitt(out, CRC_OFFSET);
    out[CRC_OFFSET]     = crc & 0xFF;
    out[CRC_OFFSET + 1] = (crc >> 8) & 0xFF;
    // padding [45, 64) stays zero
    return FRAME_SIZE;
}

// Unpack a 64-byte buffer into a Frame. Returns true on success
// (valid sync word + CRC), false otherwise.
inline bool unpack(const uint8_t* raw, Frame& out) {
    if (!raw) return false;
    if (raw[0] != (SYNC_WORD & 0xFF) || raw[1] != ((SYNC_WORD >> 8) & 0xFF))
        return false; // bad sync word
    uint16_t crc = (uint16_t)raw[CRC_OFFSET] | ((uint16_t)raw[CRC_OFFSET + 1] << 8);
    uint16_t expected = crc16Ccitt(raw, CRC_OFFSET);
    if (crc != expected) return false; // CRC mismatch

    out.frameType   = raw[2];
    out.headerSeq   = raw[3];
    out.motorId     = raw[8];
    out.commandType = raw[9];
    out.sequence    = raw[10];
    for (uint8_t i = 0; i < PAYLOAD_SIZE; ++i) out.payload[i] = raw[11 + i];
    out.payloadLen  = PAYLOAD_SIZE;
    return true;
}

} // namespace serial_frame
