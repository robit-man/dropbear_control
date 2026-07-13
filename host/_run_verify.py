"""Robust host-lib verifier.

Writes a marker file whose NAME encodes the result so the outcome survives
context retirement (list_directory shows real filenames). On failure the
marker name includes the exact failing assertion / exception type.
"""
import sys, os, glob, struct, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from myactuator_lib.protocol import Frame, FrameType
from myactuator_lib.transport import LoopbackTransport, TransportError, ProtocolType
from myactuator_lib.device import Device


def clear_markers():
    for p in glob.glob(os.path.join(HERE, ".verify_*")):
        try:
            os.remove(p)
        except OSError:
            pass


def mark(name, detail=""):
    with open(os.path.join(HERE, name), "w") as fh:
        fh.write(detail)


def main():
    clear_markers()
    try:
        # --- protocol: pack/unpack roundtrip + fixed 32-byte payload ---
        f = Frame(
            frame_type=FrameType.POSITION_CMD,
            motor_id=0x01,
            command_type=0x12,
            payload=b"\x10\x27\x00\x00",
        )
        assert len(f.pack()) == 64, "pack_len"
        g = Frame.unpack(f.pack())
        assert g.payload == b"\x10\x27\x00\x00" + b"\x00" * 28, "payload_roundtrip"
        # CRC tamper must be rejected
        bad = bytearray(f.pack())
        bad[20] ^= 0xFF
        try:
            Frame.unpack(bytes(bad))
            raise AssertionError("CRC_not_detected")
        except ValueError:
            pass
        # SYNC0 tamper must be rejected
        bad2 = bytearray(f.pack())
        bad2[0] ^= 0xFF
        try:
            Frame.unpack(bytes(bad2))
            raise AssertionError("SYNC_not_detected")
        except ValueError:
            pass

        # --- transport: loopback FIFO + disconnect guard ---
        t = LoopbackTransport()
        with t as tt:
            frames = [
                Frame(FrameType.POSITION_CMD, motor_id=i, command_type=0x10, payload=b"\x01\x02")
                for i in range(3)
            ]
            for x in frames:
                assert tt.send(x), "send"
            for i in range(3):
                y = tt.receive(timeout_ms=200)
                assert y is not None, "recv_none_%d" % i
                assert y.motor_id == i, "recv_mid_%d" % i
                assert y.payload == b"\x01\x02" + b"\x00" * 30, "recv_payload_%d" % i
            assert tt.receive(timeout_ms=50) is None, "timeout_not_none"
        try:
            t.send(Frame(FrameType.HEARTBEAT, motor_id=0, command_type=0))
            raise AssertionError("dc_send_allowed")
        except TransportError:
            pass

        # --- device: typed helpers + disconnect guard ---
        t2 = LoopbackTransport()
        t2.connect()
        dev = Device(t2, motor_id=1)
        r = dev.set_position(10000)
        assert r is not None, "dev_pos_none"
        assert r.payload[:4] == struct.pack("<i", 10000), "dev_pos_val"
        assert len(r.payload) == 32, "dev_pos_len"
        assert dev.get_status() is not None, "dev_status_none"
        t2.disconnect()
        try:
            dev.set_position(5)
            raise AssertionError("dc_dev_allowed")
        except TransportError:
            pass

        mark(".verify_PASS")
    except AssertionError as e:
        mark(".verify_FAIL_AssertionError_" + str(e), traceback.format_exc())
    except Exception as e:
        mark(".verify_FAIL_" + type(e).__name__, traceback.format_exc())


if __name__ == "__main__":
    main()
