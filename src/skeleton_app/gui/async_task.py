"""
Utilities for running asyncio code in Qt applications.

Provides async/await integration for Qt GUI code without requiring qasync.
"""

import asyncio
import logging
from typing import Any, Callable, Coroutine, Optional

from PySide6.QtCore import QThread, Signal, QObject

logger = logging.getLogger(__name__)


class AsyncTask(QObject):
    """
    Run an async coroutine in a separate thread and emit results via Qt signals.
    
    Usage:
        task = AsyncTask(some_async_function(args))
        task.finished.connect(lambda result: print(result))
        task.error.connect(lambda err: print(err))
        task.start()
    """
    
    # Signals
    finished = Signal(object)  # Emitted with result when task completes
    error = Signal(Exception)  # Emitted with exception if task fails
    
    def __init__(self, coro: Coroutine):
        super().__init__()
        self.coro = coro
        self.thread = None
    
    def start(self):
        """Start the async task in a background thread."""
        self.thread = QThread()
        self.moveToThread(self.thread)
        
        self.thread.started.connect(self._run_async)
        self.thread.finished.connect(self.thread.deleteLater)
        
        self.thread.start()
    
    def _run_async(self):
        """Run the async coroutine in this thread."""
        try:
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                result = loop.run_until_complete(self.coro)
                self.finished.emit(result)
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Async task error: {e}")
            self.error.emit(e)
        finally:
            self.thread.quit()


def run_async(coro: Coroutine, on_finished: Optional[Callable] = None, on_error: Optional[Callable] = None) -> AsyncTask:
    """
    Run an async coroutine in a background thread.
    
    Args:
        coro: The coroutine to run
        on_finished: Optional callback when task completes
        on_error: Optional callback on error
    
    Returns:
        AsyncTask object (you can connect to its signals)
    """
    task = AsyncTask(coro)
    
    if on_finished:
        task.finished.connect(on_finished)
    if on_error:
        task.error.connect(on_error)
    
    task.start()
    return task
