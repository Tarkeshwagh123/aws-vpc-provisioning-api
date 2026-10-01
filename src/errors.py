class ApiError(Exception):
    def __init__(self, status_code, message, details=None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.details = details or {}


class ValidationError(ApiError):
    def __init__(self, message, details=None):
        super().__init__(400, message, details)


class NotFoundError(ApiError):
    def __init__(self, message="Resource not found"):
        super().__init__(404, message)


class UpstreamError(ApiError):
    def __init__(self, message, details=None):
        super().__init__(502, message, details)
