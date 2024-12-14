class LinkPreviewException(Exception):
    pass


class SkipLink(LinkPreviewException):
    pass


class InvalidLink(LinkPreviewException):
    pass
