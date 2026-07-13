import glob
import inspect
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def _clear_markers():
    for p in glob.glob(os.path.join(HERE, "VERIFY*.marker")):
        try:
            os.remove(p)
        except OSError:
            pass


def fail(reason):
    _clear_markers()
    safe = "".join(c if (c.isalnum() or c in "._-") else "_" for c in str(reason))[:120]
    with open(os.path.join(HERE, "VERIFY_FAILED_%s.marker" % safe), "w") as fh:
        fh.write(str(reason))
    sys.exit(1)


def main():
    try:
        from myactuator_lib.protocol.frame import Frame
    except Exception as e:
        fail("import_err:%s:%s" % (type(e).__name__, e))

    try:
        sig = inspect.signature(Frame.__init__)
    except Exception as e:
        fail("no_ctor_sig:%s" % e)

    params = {k: v for k, v in sig.parameters.items() if k != "self"}
    known = {
        "frame_type": 0x02,
        "motor_id": 1,
        "command_type": 0x00,
        "payload": bytes([0, 0, 0x27, 0x10]) + bytes(28),
    }
    ctor_kwargs = {}
    for name, val in known.items():
        if name in params:
            ctor_kwargs[name] = val
    for name, p in params.items():
        if p.default is inspect.Parameter.empty and name not in ctor_kwargs:
            fail("missing_required:%s" % name)

    try:
        frame = Frame(**ctor_kwargs)
    except Exception as e:
        fail("ctor_err:%s:%s" % (type(e).__name__, e))

    pack = getattr(frame, "pack", None)
    if not callable(pack):
        fail("no_pack_method")
    try:
        raw = pack()
    except Exception as e:
        fail("pack_err:%s:%s" % (type(e).__name__, e))
    if not isinstance(raw, (bytes, bytearray)):
        fail("pack_not_bytes:%s" % type(raw).__name__)

    unpack = getattr(Frame, "unpack", None)
    if not callable(unpack):
        unpack = getattr(frame, "unpack", None)
    if not callable(unpack):
        fail("no_unpack_method")
    try:
        frame2 = unpack(raw)
    except Exception as e:
        fail("unpack_err:%s:%s" % (type(e).__name__, e))

    got = getattr(frame2, "payload", None)
    if got is None:
        fail("no_payload_attr")
    expected = known["payload"]
    if got != expected:
        fail("payload_mismatch:got_len=%d_exp_len=%d" % (len(got), len(expected)))
    if got[:4] != bytes([0, 0, 0x27, 0x10]):
        fail("trailing_zero_bug")

    _clear_markers()
    with open(os.path.join(HERE, "VERIFIED.marker"), "w") as fh:
        fh.write("roundtrip_ok:payload_preserved")
    sys.exit(0)


if __name__ == "__main__":
    main()
