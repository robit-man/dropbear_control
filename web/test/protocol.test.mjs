// web/test/protocol.test.mjs
// Verifies the JS protocol port against the Python host library reference.
// Run: node web/test/protocol.test.mjs
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { Frame, FrameType, crc16Ccitt, FRAME_SIZE } from "../js/protocol.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, "../.."); // repo root (web/test -> web -> myactuator)

let failures = 0;
function check(name, cond) {
  if (cond) {
    console.log(`  ok  ${name}`);
  } else {
    console.error(`  FAIL ${name}`);
    failures++;
  }
}

// 1. Round-trip: pack -> unpack -> pack is byte-stable.
const f = new Frame({
  frameType: FrameType.STATUS_REPORT,
  motorId: 0x01,
  commandType: 0x00,
  payload: new Uint8Array([10, 0, 0, 0, 200, 0, 0, 0, 244, 1, 40, 0, 0, 0, 0, 0]),
  sequence: 3,
  headerSeq: 7,
});
const raw = f.pack();
check("frame is 64 bytes", raw.length === FRAME_SIZE);
const g = Frame.unpack(raw);
check("round-trip byte-stable", g.pack().every((b, i) => b === raw[i]));
check("motorId preserved", g.motorId === 0x01);
check("payload width preserved (32)", g.payload.length === 32);

// 2. CRC mismatch is detected.
const bad = new Uint8Array(raw);
bad[20] ^= 0xff;
let threw = false;
try { Frame.unpack(bad); } catch (_e) { threw = true; }
check("CRC mismatch throws", threw);

// 3. Bad sync word is detected.
const badSync = new Uint8Array(raw);
badSync[0] ^= 0xff;
threw = false;
try { Frame.unpack(badSync); } catch (_e) { threw = true; }
check("bad sync throws", threw);

// 4. Cross-check CRC against the Python host library (source of truth).
const py = execFileSync("python3", [
  "-c",
  "import sys; sys.path.insert(0,'host');" +
  "from myactuator_lib.protocol import Frame, FrameType, crc16_ccitt;" +
  "import struct;" +
  "f=Frame(frame_type=FrameType.STATUS_REPORT, motor_id=0x01, command_type=0x00," +
  "payload=(10).to_bytes(4,'little')+(200).to_bytes(4,'little')+(500).to_bytes(2,'little')+bytes([40])+bytes([0,0])+bytes([0])," +
  "sequence=3, header_seq=7);" +
  "raw=f.pack();" +
  "print('%d %d' % (len(raw), struct.unpack('<H', raw[43:45])[0]))",
], { cwd: root }).toString().trim().split(/\s+/).map(Number);

check("python frame length 64", py[0] === 64);
const jsCrc = crc16Ccitt(raw.subarray(0, 43));
check(`CRC matches Python (js=0x${jsCrc.toString(16)} py=0x${py[1].toString(16)})`, jsCrc === py[1]);

console.log(failures === 0 ? "\nPROTOCOL TESTS PASSED" : `\nPROTOCOL TESTS FAILED (${failures})`);
process.exit(failures === 0 ? 0 : 1);
