"""Exceptions raised by the protocol layer."""


class InverterError(Exception):
    """Base class for all inverter communication errors."""


class InverterConnectionError(InverterError):
    """The gateway could not be reached or closed the connection."""


class InverterTimeoutError(InverterError):
    """The inverter did not answer in time (unknown commands are silent)."""


class InverterProtocolError(InverterError):
    """Malformed frame, CRC mismatch or unparsable payload."""


class InverterNakError(InverterError):
    """The inverter answered NAK (command known but refused)."""


class InvalidCommandError(InverterError, ValueError):
    """A command or command argument failed local validation; nothing was sent."""
