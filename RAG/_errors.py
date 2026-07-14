class MemoryError(Exception):
    """Base package error."""


class ValidationError(MemoryError):
    """Raised when an input value violates domain invariants."""


class DocumentNotFoundError(MemoryError):
    """Raised when a document can not be found."""


class DocumentAlreadyExistsError(MemoryError):
    """Raised when a document key is already occupied."""


class ConcurrentModificationError(MemoryError):
    """Raised when an aggregate was changed after it was loaded."""
