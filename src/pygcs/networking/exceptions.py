class MessageFormatError(Exception):
    """Exception raised for errors in the message format."""
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message