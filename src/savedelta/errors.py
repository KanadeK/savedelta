from __future__ import annotations


class SaveDeltaError(Exception):
    """Base class for expected, user-facing failures."""


class SnapshotFormatError(SaveDeltaError):
    """Raised when a .sdelta file is malformed or unsupported."""


class WorkLimitError(SaveDeltaError):
    """Raised when an input exceeds a configured safety budget."""


class AnalysisError(SaveDeltaError):
    """Raised when a specialized analyzer cannot safely read an input."""
