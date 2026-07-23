#!/usr/bin/env python3
"""Emit the deterministic host-link V1 cross-language corpus to stdout."""

from __future__ import annotations

import csv
import io
import math
import struct
import sys
from dataclasses import replace

from myactuator_lib import hostlink_v1 as hl


CONFIG_HASH = bytes.fromhex("11" * 32)
ZERO_HASH = bytes(32)
CONFIG = hl.ConfigIdentity("dropbear-main", "robot-rev-2026-07", CONFIG_HASH)
SESSION = 0x1020304050607080
NOW = 9_000_000_000


def frame(body, sequence, *, flags=hl.FrameFlag.NONE, config_hash=CONFIG_HASH):
    return hl.encode_message(
        body,
        session_id=SESSION,
        sequence=sequence,
        monotonic_ns=NOW,
        config_sha256=config_hash,
        flags=flags,
    )


def recalculate(raw: bytes) -> bytes:
    return raw[:-4] + struct.pack(">I", hl.crc32c(raw[:-4]))


def replace_payload(raw: bytes, payload: bytes) -> bytes:
    decoded = hl.decode_frame(raw)
    return hl.encode_frame(replace(decoded, payload=payload))


def config_hash_offset(payload: bytes) -> int:
    offset = 0
    for _ in range(3):
        length = struct.unpack_from(">H", payload, offset)[0]
        offset += 2 + length
    # The first text is actuator ID; the next two are config ID and revision.
    return offset


hello = hl.Hello(
    "dropbear-host",
    hl.EndpointRole.HOST,
    1,
    0,
    0,
    hl.MANDATORY_CAPABILITIES,
    hl.MANDATORY_CAPABILITIES,
    50,
    1000,
    500,
    hl.MAX_PAYLOAD_SIZE,
)
capabilities = hl.Capabilities(
    True,
    1,
    0,
    hl.MANDATORY_CAPABILITIES,
    500,
    hl.MAX_PAYLOAD_SIZE,
    hl.NegotiationRejection.NONE,
)
command = hl.Command(
    "left-knee-actuator",
    CONFIG,
    "controller-main",
    "locomotion-lease-7",
    "controller-main",
    41,
    NOW + 2_000_000_000,
    hl.CommandMode.IMPEDANCE,
    True,
    position_rad=0.2,
    velocity_rad_s=-0.1,
    effort_nm=0.15,
    stiffness_nm_per_rad=22.0,
    damping_nm_s_per_rad=0.8,
)
state = hl.State(
    "left-knee-actuator",
    CONFIG,
    NOW - 2_000_000,
    2_000_000,
    hl.SampleValidity.STALE,
    hl.Connectivity.DEGRADED,
    hl.DriveHealth.WARNING,
    hl.BusHealth.RECOVERING,
    hl.NativeResponseState.DRIVE_FAULT,
    "DRIVE_WARNING",
    hl.SafetyState.SHUTDOWN,
    position_rad=0.4,
    velocity_rad_s=-0.2,
    effort_nm=1.2,
    current_q_a=0.3,
    temperature_c=38.5,
    voltage_v=47.8,
    native_status_code=0x1234,
    native_fault_mask=0x1004,
)
disposition = hl.Disposition(
    SESSION,
    3,
    "left-knee-actuator",
    hl.DispositionPhase.REJECTED,
    NOW,
    "CONFIG_MISMATCH",
)
fault = hl.Fault(
    "BUS_OFF",
    hl.FaultSeverity.LATCHED,
    hl.SafetyState.FAULT,
    NOW - 1,
    3,
    "left-knee-actuator",
    "CAN controller entered bus-off; no physical-state claim",
)
heartbeat = hl.Heartbeat(
    "gateway-main",
    hl.EndpointRole.GATEWAY,
    hl.LinkHealth.DEGRADED,
    hl.SafetyState.SHUTDOWN,
    99_000,
    42,
)

rows = []


def add(name: str, outcome: str, message_type: str, raw: bytes):
    rows.append((name, outcome, message_type, raw.hex()))


positive = [
    ("hello", hello, ZERO_HASH),
    ("capabilities", capabilities, ZERO_HASH),
    ("command", command, CONFIG_HASH),
    ("state_health", state, CONFIG_HASH),
    ("disposition", disposition, CONFIG_HASH),
    ("fault", fault, CONFIG_HASH),
    ("heartbeat", heartbeat, CONFIG_HASH),
]
for sequence, (name, body, digest) in enumerate(positive, 1):
    flags = (
        hl.FrameFlag.RESPONSE | hl.FrameFlag.URGENT_SAFETY
        if name == "heartbeat"
        else hl.FrameFlag.NONE
    )
    add(
        name,
        "accept",
        type(body).__name__.upper(),
        frame(body, sequence, flags=flags, config_hash=digest),
    )

max_endpoint = "e" * hl.MAX_TEXT_BYTES
max_detail = "d" * hl.MAX_DETAIL_BYTES
add(
    "boundary_max_text",
    "accept",
    "HELLO",
    frame(replace(hello, endpoint_id=max_endpoint), 8, config_hash=ZERO_HASH),
)
add(
    "boundary_max_detail",
    "accept",
    "FAULT",
    frame(replace(fault, description=max_detail), 9),
)
add(
    "boundary_disable_command",
    "accept",
    "COMMAND",
    frame(
        hl.Command(
            "left-knee-actuator",
            CONFIG,
            "controller-main",
            "disable-lease-8",
            "controller-main",
            42,
            NOW + 1,
            hl.CommandMode.DISABLE,
            False,
        ),
        10,
    ),
)

base = bytearray(frame(heartbeat, 20, config_hash=CONFIG_HASH))
mutations = []

bad = bytearray(base)
bad[0] ^= 1
mutations.append(("bad_magic", "reject_frame", bytes(bad)))
bad = bytearray(base)
bad[4] = 2
mutations.append(("bad_version", "reject_frame", recalculate(bytes(bad))))
bad = bytearray(base)
bad[6:8] = struct.pack(">H", hl.HEADER_SIZE + 1)
mutations.append(("bad_header_length", "reject_frame", recalculate(bytes(bad))))
bad = bytearray(base)
bad[12] = 0xFF
mutations.append(("bad_type", "reject_frame", recalculate(bytes(bad))))
bad = bytearray(base)
bad[13] = 0x80
mutations.append(("bad_flags", "reject_frame", recalculate(bytes(bad))))
bad = bytearray(base)
bad[14] = 1
mutations.append(("bad_reserved", "reject_frame", recalculate(bytes(bad))))
bad = bytearray(base)
bad[16:24] = bytes(8)
mutations.append(("zero_session", "reject_frame", recalculate(bytes(bad))))
bad = bytearray(base)
bad[24:32] = bytes(8)
mutations.append(("zero_sequence", "reject_frame", recalculate(bytes(bad))))
bad = bytearray(base)
bad[-1] ^= 1
mutations.append(("bad_crc", "reject_frame", bytes(bad)))
mutations.append(("truncated_frame", "reject_frame", bytes(base[:-1])))
mutations.append(("trailing_frame", "reject_frame", bytes(base) + b"x"))
for name, outcome, raw in mutations:
    add(name, outcome, "ENVELOPE", raw)

command_raw = frame(command, 30)
decoded_command = hl.decode_frame(command_raw)
payload = bytearray(decoded_command.payload)
payload = payload[:-40]  # remove the five impedance float64 values
payload[-2:] = b"\x00\x00"
add(
    "command_missing_fields",
    "reject_body",
    "COMMAND",
    replace_payload(command_raw, bytes(payload)),
)
payload = bytearray(decoded_command.payload)
payload[-8:] = struct.pack(">d", math.nan)
add(
    "command_nan",
    "reject_body",
    "COMMAND",
    replace_payload(command_raw, bytes(payload)),
)
payload = bytearray(decoded_command.payload)
payload[config_hash_offset(payload)] ^= 1
add(
    "command_body_hash_mismatch",
    "reject_body",
    "COMMAND",
    replace_payload(command_raw, bytes(payload)),
)
add(
    "command_trailing_body",
    "reject_body",
    "COMMAND",
    replace_payload(command_raw, decoded_command.payload + b"x"),
)
add(
    "command_truncated_body",
    "reject_body",
    "COMMAND",
    replace_payload(command_raw, decoded_command.payload[:-1]),
)

state_raw = frame(state, 31)
decoded_state = hl.decode_frame(state_raw)
payload = bytearray(decoded_state.payload)
offset = config_hash_offset(payload) + 32 + 16
payload[offset + 2] = 0xFF  # DriveHealth follows validity/connectivity.
add(
    "state_bad_drive_health",
    "reject_body",
    "STATE",
    replace_payload(state_raw, bytes(payload)),
)
payload = bytearray(decoded_state.payload)
age_offset = config_hash_offset(payload) + 32 + 8
payload[age_offset : age_offset + 8] = struct.pack(">Q", 1)
add(
    "state_age_mismatch",
    "reject_body",
    "STATE",
    replace_payload(state_raw, bytes(payload)),
)

disposition_raw = frame(disposition, 32)
decoded_disposition = hl.decode_frame(disposition_raw)
payload = bytearray(decoded_disposition.payload)
phase_offset = 16 + 2 + len("left-knee-actuator")
payload[phase_offset] = int(hl.DispositionPhase.ADMITTED)
add(
    "disposition_reason_mismatch",
    "reject_body",
    "DISPOSITION",
    replace_payload(disposition_raw, bytes(payload)),
)

fault_raw = frame(fault, 33)
decoded_fault = hl.decode_frame(fault_raw)
payload = bytearray(decoded_fault.payload)
fault_time_offset = 2 + len("BUS_OFF") + 2
payload[fault_time_offset : fault_time_offset + 8] = struct.pack(">Q", NOW + 1)
add(
    "fault_future_time",
    "reject_body",
    "FAULT",
    replace_payload(fault_raw, bytes(payload)),
)

hello_raw = frame(hello, 34, config_hash=ZERO_HASH)
decoded_hello = hl.decode_frame(hello_raw)
payload = bytearray(decoded_hello.payload)
required_offset = 2 + len("dropbear-host") + 4
payload[required_offset : required_offset + 8] = struct.pack(">Q", 1 << 63)
add(
    "hello_unknown_capability",
    "reject_body",
    "HELLO",
    replace_payload(hello_raw, bytes(payload)),
)

heartbeat_raw = frame(heartbeat, 35)
decoded_heartbeat = hl.decode_frame(heartbeat_raw)
payload = bytearray(decoded_heartbeat.payload)
payload[2 + len("gateway-main") + 1] = 0xFF
add(
    "heartbeat_unknown_health",
    "reject_body",
    "HEARTBEAT",
    replace_payload(heartbeat_raw, bytes(payload)),
)

stream = io.StringIO()
writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
writer.writerow(("name", "outcome", "message_type", "frame_hex"))
writer.writerows(rows)
sys.stdout.write(stream.getvalue())
