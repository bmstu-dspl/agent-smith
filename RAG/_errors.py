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


class EmbeddingError(MemoryError):
    """Raised when embedding generation fails or returns invalid data."""


class EmbeddingConfigurationError(EmbeddingError):
    """Raised when the embedding provider is misconfigured."""


class FileParsingError(MemoryError):
    """Raised when a supported file can not be converted to text."""


class UnsupportedFileTypeError(FileParsingError):
    """Raised when ingestion receives an unsupported file extension."""
