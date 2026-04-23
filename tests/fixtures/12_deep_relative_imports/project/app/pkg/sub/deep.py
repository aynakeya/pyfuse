from ..core.base import token
from ...root import suffix


def run() -> str:
    return f"{token()}:{suffix()}"
