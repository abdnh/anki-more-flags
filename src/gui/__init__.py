from typing import Callable, Union

from aqt.qt import pyqtBoundSignal, pyqtSignal


def qconnect(
    signal: Union[Callable, pyqtSignal, pyqtBoundSignal], func: Callable
) -> None:
    """Helper to work around type checking not working with signal.connect(func)."""
    signal.connect(func)  # type: ignore
