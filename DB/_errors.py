class DatabaseError(Exception):
    """Base exception for the DB package."""


class DatabaseConfigurationError(DatabaseError):
    """Raised when database configuration is invalid."""


class DatabaseConnectionError(DatabaseError):
    """Raised when a database connection or pool can not be established."""


class DatabaseQueryError(DatabaseError):
    """Raised when a query execution fails."""


class MigrationError(DatabaseError):
    """Raised when a migration fails."""

