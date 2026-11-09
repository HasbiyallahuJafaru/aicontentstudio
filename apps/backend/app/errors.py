import errno


class Cancelled(Exception):
    """The user cancelled the job; raised from report() between steps."""


class UserError(Exception):
    """An error whose message is safe and useful to show the user as-is. `detail` goes under 'View technical details'."""

    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.detail = detail


def explain(e: BaseException) -> tuple[str, str]:
    """(message, detail) for any exception: a UserError as written, the common unplanned causes (no internet, full
    disk, a locked file) in plain words, everything else as a calm generic line. The raw error stays in `detail`."""
    if isinstance(e, UserError):
        return str(e), e.detail
    import httpx  # imported here so this module stays importable before anything else loads
    if isinstance(e, httpx.TimeoutException):
        message = "An online service took too long to answer. Check your internet connection and try again."
    elif isinstance(e, (httpx.ConnectError, httpx.NetworkError)):
        message = "Couldn't connect to an online service. Check your internet connection and try again."
    elif isinstance(e, OSError) and e.errno == errno.ENOSPC:
        message = "Your disk is full. Free up some space and try again."
    elif isinstance(e, PermissionError):
        message = "Windows blocked access to a file. Close any program that has it open and try again."
    elif isinstance(e, FileNotFoundError):
        message = "A file the studio needed is missing. It may have been moved or deleted."
    elif isinstance(e, MemoryError):
        message = "This computer ran out of memory. Close other programs and try again."
    else:
        message = "Something went wrong. Try again, and if it keeps happening, the technical details below help."
    return message, repr(e)[:2000]
