"""Device layer for myactuator_lib.

Binds a :class:`~myactuator_lib.transport.Transport` to a single motor and
exposes typed command helpers built on the contract frame types
(``contracts/PROTOCOLS_CONTRACT.md`` section 3.4). The ROS node layer is
built on top of this package.
"""

from .base import Device

__all__ = ["Device"]
