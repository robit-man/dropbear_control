import sys, os, inspect

HERE = os.path.dirname(os.path.abspath(__file__))
PASS_MARKER = os.path.join(HERE, "VERIFIED_v1.marker")
FAIL_MARKER = os.path.join(HERE, "VERIFY_FAILED_v1.marker")


def cleanup():
    for p in (PASS_MARKER, FAIL_MARKER):
        try:
            if os.path.exists(p):
                os.remove(p)
        except OSError:
            pass


def fail(reason):
    cleanup()
    try:
        with open(FAIL_MARKER, "w") as f:
            f.write(reason[:120])
    except OSError:
        pass
    sys.stdout.write("FAIL:" + reason[:120] + "\n")


def main():
    try:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        from myactuator_lib.protocol.frame import Frame
    except Exception as e:
        fail("import:" + repr(e))
        return

    # 32-byte payload with meaningful trailing zeros (little-endian int32 0x00002710
    # at the front, zero-padded to 32 bytes). Buggy rstrip(b"\x00") would collapse
    # this to b"\x10\x27" (2 bytes); the fix must preserve all 32 bytes.
    test_payload = b"\x10\x27\x00\x00" + b"\x00" * 28

    try:
        sig = inspect.signature(Frame.__init__)
    except Exception as e:
        fail("sig:" + repr(e))
        return

    kwargs = {}
    for name, p in sig.parameters.items():
        if name == "self":
            continue
        if name in ("payload", "data"):
            kwargs[name] = test_payload
        elif name in ("frame_type", "type"):
            kwargs[name] = 0x02
        elif name in ("motor_id", "id", "node_id"):
            kwargs[name] = 1
        elif name in ("command_type", "cmd", "command"):
            kwargs[name] = 0
        elif p.default is not inspect.Parameter.empty:
            kwargs[name] = p.default
        else:
            kwargs[name] = 0

    try:
        f = Frame(**kwargs)
    except Exception as e:
        fail("construct:" + repr(e))
        return

    try:
        if hasattr(f, "pack"):
            data = f.pack()
        elif hasattr(Frame, "pack"):
            data = Frame.pack(f)
        else:
            fail("nopack")
            return
    except Exception as e:
        fail("pack:" + repr(e))
        return

    try:
        if hasattr(Frame, "unpack"):
            f2 = Frame.unpack(data)
        elif hasattr(f, "unpack"):
            f2 = f.unpack(data)
        else:
            fail("nounpack")
            return
    except Exception as e:
        fail("unpack:" + repr(e))
        return

    try:
        if hasattr(f2, "payload"):
            got = f2.payload
        elif hasattr(f2, "data"):
            got = f2.data
        else:
            fail("nopayloadattr")
            return
    except Exception as e:
        fail("payloadget:" + repr(e))
        return

    if got != test_payload:
        fail("payload_mismatch:len=%d" % len(got))
        return

    cleanup()
    try:
        with open(PASS_MARKER, "w") as fp:
            fp.write("ok")
    except OSError:
        pass
    sys.stdout.write("PASS\n")


if __name__ == "__main__":
    main()
