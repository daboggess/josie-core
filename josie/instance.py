"""Windows named-mutex guard for a single Josie GUI instance."""

from __future__ import annotations

import ctypes
from contextlib import contextmanager
from collections.abc import Iterator

_ERROR_ALREADY_EXISTS = 183


@contextmanager
def gui_instance(name: str = "Local\\JosieCoreGui") -> Iterator[bool]:
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.SetLastError(0)
    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        raise OSError("Windows could not create the Josie GUI instance guard")
    acquired = kernel32.GetLastError() != _ERROR_ALREADY_EXISTS
    try:
        yield acquired
    finally:
        kernel32.CloseHandle(handle)

