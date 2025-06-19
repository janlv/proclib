# src/proclib/__init__.py
__version__ = "0.1.0"

from .Process import Process
from .Runner import Runner
from .Timer import Timer, TimerThread

#from psutil import NoSuchProcess

__all__ = ['Process', 'Runner', 'Timer', 'TimerThread']