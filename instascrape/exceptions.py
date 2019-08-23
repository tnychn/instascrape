class InstascrapeError(Exception):
    """Base exception class for all of the exceptions raised by Instascrape."""


class ExtractionError(InstascrapeError):
    """Raised when Instascrape fails to extract specified data from HTTP response."""

    def __init__(self, message: str):
        super().__init__("Failed to extract data from response. (message: '{0}')".format(message))


class PrivateAccessError(InstascrapeError):
    """Raised when user does not have permission to access specified data, i.e. private profile which the user is not following."""

    def __init__(self):
        super().__init__("The user profile is private and not being followed by you.")


class RateLimitedError(InstascrapeError):
    """Raised when Instascrape receives a 429 TooManyRequests from Instagram."""

    def __init__(self):
        super().__init__("(429) Too many requests. Failed to query data. Rate limited by Instagram.")


class NotFoundError(InstascrapeError):
    """Raised when Instascrape receives a 404 Not Found from Instagram."""

    def __init__(self, message: str = None):
        super().__init__(message or "(404) Nothing found.")


class ConnectionError(InstascrapeError):
    """Raised when Instascrape fails to connect to Instagram server."""

    def __init__(self, url: str):
        super().__init__("Failed to connect to '{0}'.".format(url))


class LoginError(InstascrapeError):
    """Raised when Instascrape fails to perform authentication, e.g. wrong credentials."""

    def __init__(self, message: str):
        super().__init__("Failed to log into Instagram. (message: '{0}')".format(message))


class TwoFactorAuthRequired(LoginError):
    """Raised when Instascrape fails to perform authentication due to two-factor authenticattion."""

    def __init__(self):
        super().__init__("two-factor authentication is required")


class CheckpointChallengeRequired(LoginError):
    """Raised when Instascrape fails to perform authentication due to checkpoint challenge."""

    def __init__(self):
        super().__init__("checkpoint challenge solving is required")


class AuthenticationRequired(InstascrapeError):
    """Raised when anonymous/unauthenticated (guest) user tries to perform actions that require authentication."""

    def __init__(self):
        super().__init__("Login is required in order to perform this action.")


class DownloadError(InstascrapeError):
    """Raised when Instascrape fails to download data from Instagram server."""

    def __init__(self, message: str, url: str):
        super().__init__("Download Failed -> {0} (url: '{1}')".format(message, url))
