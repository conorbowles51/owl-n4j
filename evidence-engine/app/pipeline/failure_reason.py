"""The reason written on a failed job."""


def failure_reason(error: BaseException) -> str:
    """The error's text, or its name when it has none.

    httpx transport errors carry no text: 11 Nov a ConnectTimeout failed a file with an empty reason, and 12 Nov a
    ReadError failed ReportThomasKeyes.pdf with one, which the app showed as "stopped without giving a reason".
    """
    return str(error).strip() or type(error).__name__
