class UserError(Exception):
    """An error whose message is safe and useful to show the user as-is. `detail` goes under 'View technical details'."""

    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.detail = detail
