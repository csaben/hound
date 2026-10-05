class HoundError(RuntimeError):
    """A user-actionable Hound failure."""


class AdapterError(HoundError):
    """An adapter is missing or invalid."""


class BackendError(HoundError):
    """The selected surface backend is unavailable."""


class DriverError(HoundError):
    """The selected SystemOne driver failed."""

