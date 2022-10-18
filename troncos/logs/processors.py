"""
The processors are used by Structlog to process incoming log entries, a bit like how the stdlib
logging uses logging filters. This is currently implemented alongside the filters to allow for
parallel feature parity while we finish the current troncos adoption.
"""


class StaticValue:
    """
    Annotating log entries with values that are not subject to change after logger instantiation
    (i.e. version number or environment)
    """

    def __init__(self, key: str, value: str):
        self.key = key
        self.value = value

    def __call__(self, name, method, event_dict):
        event_dict[self.key] = self.value
        return event_dict
