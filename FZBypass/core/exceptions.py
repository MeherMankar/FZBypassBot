class DDLException(Exception):
    """Not method found for extracting direct download link from the http link"""

    pass


class ResolverStepError(DDLException):
    """A resolver failure with a machine-readable resolver and step."""

    def __init__(self, resolver: str, step: str, detail: str):
        self.resolver = resolver
        self.step = step
        self.detail = detail
        super().__init__(f"{resolver} [{step}]: {detail}")
