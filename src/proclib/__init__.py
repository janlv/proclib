# src/proclib/__init__.py

from ._version import version as __version__

# Importing necessary modules and classes from proclib
# This allows users to write code like 
#       from proclib import Process 
# instead of 
#       from proclib.Process import Process

from .Process import Process
from .Runner import Runner
from .Timer import Timer, TimerThread

#from psutil import NoSuchProcess

__all__ = ['Process', 'Runner', 'Timer', 'TimerThread']