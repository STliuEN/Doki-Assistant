"""Cross-process exclusion and durable tombstones for late Chroma worker threads."""

import os
from contextlib import contextmanager
from pathlib import Path

from app.rag.projection.contracts import ProjectionUnavailable


@contextmanager
def attempt_lock(directory: str, collection: str):
    # Callers validate the canonical UUID locator before deriving this basename.
    if not collection.replace("_", "").isalnum() or not collection.startswith("e5_"):
        raise ProjectionUnavailable("chroma_locator_invalid")
    locks = Path(directory) / ".e5-locks"
    locks.mkdir(parents=True, exist_ok=True)
    with (locks / (collection + ".lock")).open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ProjectionUnavailable("chroma_attempt_busy") from error
        try:
            yield locks / (collection + ".retired")
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
