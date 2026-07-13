"""Protocol layer for myactuator_lib.

Exposes the unified 64-byte frame model defined in
``contracts/PROTOCOLS_CONTRACT.md`` (section 3). Transport and device layers
build on top of this; it has no dependencies inside the package.
"""

from .frame import (
    Frame,
    FrameType,
    crc16_ccitt,
)

__all__ = ["Frame", "FrameType", "crc16_ccitt"]
