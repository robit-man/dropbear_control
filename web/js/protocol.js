// web/js/protocol.js
//
// Faithful JavaScript port of host/myactuator_lib/protocol/frame.py.
// Implements the 64-byte unified frame from contracts/PROTOCOLS_CONTRACT.md
// (section 3: "Message Frame Format"). This is the lowest layer of the
// browser dashboard; the webserial and simulation layers depend on it.
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
// the Python host library. Verified against the Python reference (CRC=0xef0e
// for a known STATUS_REPORT payload) in test/protocol.test.mjs.

export const SYNC_WORD = 0xAA55;
export const FRAME_SIZE = 64;
export const HEADER_SIZE = 8;
export const PAYLOAD_SIZE = 32;
export const RESERVED_SIZE = 4;
export const PADDING_SIZE = 19;
export const CRC_POLY = 0x1021;
export const CRC_INIT = 0xFFFF;

// Byte offsets within the packed frame.
const BODY_OFFSET = HEADER_SIZE;            // 8
const BODY_SIZE = 3 + PAYLOAD_SIZE;         // 35 (motor_id + command_type + sequence + payload)
const CRC_OFFSET = BODY_OFFSET + BODY_SIZE; // 43
// PADDING_OFFSET = 45

export const FrameType = {
  STATUS_REPORT: 0x01,
  POSITION_CMD: 0x02,
  VELOCITY_CMD: 0x03,
  TORQUE_CMD: 0x04,
  PARAM_READ: 0x05,
  PARAM_WRITE: 0x06,
  DIAGNOSTIC: 0x07,
  FIRMWARE_UPDATE: 0x08,
  HEARTBEAT: 0x09,
};

export function crc16Ccitt(data, init = CRC_INIT, poly = CRC_POLY) {
  let crc = init & 0xffff;
  for (const byte of data) {
    crc ^= (byte << 8) & 0xffff;
    for (let i = 0; i < 8; i++) {
      if (crc & 0x8000) crc = ((crc << 1) ^ poly) & 0xffff;
      else crc = (crc << 1) & 0xffff;
    }
  }
  return crc & 0xffff;
}

export class Frame {
  constructor({
    frameType,
    motorId,
    commandType = 0,
    payload = new Uint8Array(0),
    sequence = 0,
    headerSeq = 0,
    reserved = new Uint8Array(0),
  }) {
    this.frameType = frameType & 0xff;
    this.motorId = motorId & 0xff;
    this.commandType = commandType & 0xff;
    this.payload = payload;
    this.sequence = sequence & 0xff;
    this.headerSeq = headerSeq & 0xff;
    this.reserved = reserved;
  }

  pack() {
    if (this.motorId < 0 || this.motorId > 0xff) throw new Error("motorId must fit in one byte");
    if (this.commandType < 0 || this.commandType > 0xff) throw new Error("command_type must fit in one byte");
    if (this.sequence < 0 || this.sequence > 0xff) throw new Error("sequence must fit in one byte");
    if (this.headerSeq < 0 || this.headerSeq > 0xff) throw new Error("header_seq must fit in one byte");
    if (this.payload.length > PAYLOAD_SIZE) throw new Error(`payload must be <= ${PAYLOAD_SIZE} bytes`);
    if (this.reserved.length > RESERVED_SIZE) throw new Error(`reserved must be <= ${RESERVED_SIZE} bytes`);

    const reserved = new Uint8Array(RESERVED_SIZE);
    reserved.set(this.reserved.subarray(0, RESERVED_SIZE));
    const payload = new Uint8Array(PAYLOAD_SIZE);
    payload.set(this.payload.subarray(0, PAYLOAD_SIZE));

    const buf = new ArrayBuffer(FRAME_SIZE);
    const dv = new DataView(buf);
    dv.setUint16(0, SYNC_WORD, true); // little-endian
    dv.setUint8(2, this.frameType);
    dv.setUint8(3, this.headerSeq);
    for (let i = 0; i < RESERVED_SIZE; i++) dv.setUint8(4 + i, reserved[i]);
    dv.setUint8(8, this.motorId);
    dv.setUint8(9, this.commandType);
    dv.setUint8(10, this.sequence);
    for (let i = 0; i < PAYLOAD_SIZE; i++) dv.setUint8(11 + i, payload[i]);

    // CRC computed over header (8) + body (35) = bytes [0, 43).
    const crcRegion = new Uint8Array(buf, 0, CRC_OFFSET);
    const crc = crc16Ccitt(crcRegion);
    dv.setUint16(CRC_OFFSET, crc, true);
    // padding bytes [45, 64) remain zero-initialized.
    return new Uint8Array(buf);
  }

  static unpack(raw) {
    if (raw.length !== FRAME_SIZE) throw new Error(`frame must be ${FRAME_SIZE} bytes, got ${raw.length}`);
    const dv = new DataView(raw.buffer, raw.byteOffset, raw.byteLength);
    const sync = dv.getUint16(0, true);
    if (sync !== SYNC_WORD) throw new Error(`bad sync word: 0x${sync.toString(16)}`);
    const frameType = dv.getUint8(2);
    const headerSeq = dv.getUint8(3);
    const motorId = dv.getUint8(8);
    const commandType = dv.getUint8(9);
    const sequence = dv.getUint8(10);
    const payload = raw.subarray(11, 11 + PAYLOAD_SIZE); // keep full 32-byte width
    const crc = dv.getUint16(CRC_OFFSET, true);
    const crcRegion = raw.subarray(0, CRC_OFFSET);
    const expected = crc16Ccitt(crcRegion);
    if (crc !== expected) {
      throw new Error(`CRC mismatch: frame=0x${crc.toString(16)} expected=0x${expected.toString(16)}`);
    }
    return new Frame({
      frameType,
      motorId,
      commandType,
      payload: new Uint8Array(payload),
      sequence,
      headerSeq,
    });
  }
}
