"""Host-library self-test: protocol + transport + device stack."""
import sys, struct, traceback

def main():
    # ---- protocol ----
    from myactuator_lib.protocol import Frame, FrameType, crc16_ccitt
    f = Frame(frame_type=FrameType.POSITION_CMD, motor_id=0x01, command_type=0x12,
              payload=b'\x10\x27\x00\x00', sequence=3, header_seq=7)
    raw = f.pack()
    assert len(raw) == 64, len(raw)
    g = Frame.unpack(raw)
    assert g.pack() == raw, 'protocol round-trip not byte-stable'
    assert g.payload == b'\x10\x27\x00\x00' + b'\x00' * 28, g.payload  # no-strip fix
    bad = bytearray(raw); bad[20] ^= 0xFF
    try:
        Frame.unpack(bytes(bad)); raise SystemExit('CRC FAILED')
    except ValueError as e:
        assert 'CRC' in str(e), e
    bad2 = bytearray(raw); bad2[0] ^= 0xFF
    try:
        Frame.unpack(bytes(bad2)); raise SystemExit('sync FAILED')
    except ValueError as e:
        assert 'sync' in str(e), e

    # ---- transport ----
    from myactuator_lib.transport import LoopbackTransport, TransportError, ProtocolType
    t = LoopbackTransport()
    assert t.get_type() is ProtocolType.CAN
    with t as tt:
        assert tt.is_connected()
        frames = [Frame(FrameType.POSITION_CMD, motor_id=i, command_type=0x10, payload=b'\x01\x02') for i in range(3)]
        for fr in frames:
            assert tt.send(fr)
        for i, fr in enumerate(frames):
            gg = tt.receive(timeout_ms=200)
            assert gg is not None and gg.motor_id == i and gg.payload == b'\x01\x02' + b'\x00' * 30, (gg.motor_id, gg.payload)
        assert tt.receive(timeout_ms=50) is None
    try:
        t.send(Frame(FrameType.HEARTBEAT, motor_id=0, command_type=0)); raise SystemExit('disconnected send FAILED')
    except TransportError as e:
        assert 'not connected' in str(e), e

    # ---- device ----
    from myactuator_lib.device import Device
    t2 = LoopbackTransport(); t2.connect()
    dev = Device(t2, motor_id=1)
    r = dev.set_position(10000)
    assert r is not None and r.frame_type == FrameType.POSITION_CMD and r.payload[:4] == struct.pack("<i", 10000) and len(r.payload) == 32 and r.motor_id == 1
    s = dev.get_status()
    assert s is not None and s.frame_type == FrameType.STATUS_REPORT
    t2.disconnect()
    try:
        dev.set_position(5); raise SystemExit('disconnected device FAILED')
    except TransportError as e:
        assert 'not connected' in str(e), e

    print("HOSTLIB_OK")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
