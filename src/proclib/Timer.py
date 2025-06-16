from pathlib import Path
from time import time, sleep
from threading import Thread
from datetime import datetime


#====================================================================================
class Timer:
#====================================================================================

    #--------------------------------------------------------------------------------    
    def __init__(self, filename=None):
    #--------------------------------------------------------------------------------    
        self.counter = 0
        self.timefile = Path(f'{filename}_timer.dat')
        self.timefile.write_text('# step \t seconds\n')
        self.starttime = time()
        self.info = f'Execution time saved in {self.timefile.name}'


    #--------------------------------------------------------------------------------    
    def start(self):
    #--------------------------------------------------------------------------------    
        self.counter += 1
        self.starttime = time()


    #--------------------------------------------------------------------------------    
    def stop(self):
    #--------------------------------------------------------------------------------    
        with self.timefile.open('a') as f:
            f.write(f'{self.counter:d}\t{time()-self.starttime:.3e}\n')

#====================================================================================
class TimerThread:
#====================================================================================
    DEBUG = False
    
    #--------------------------------------------------------------------------------    
    def __init__(self, limit=0, prec=0.5, func=None):
    #--------------------------------------------------------------------------------    
        self._func = func
        self._call_func = func
        self._limit = limit
        self._idle = prec   # Idle time between checks given by precision
        self._running = False
        self._starttime = None
        self._endtime = None
        self._thread = Thread(target=self._timer, daemon=True)
        self.DEBUG and print(f'Creating {self}')

    #--------------------------------------------------------------------------------    
    def __str__(self):
    #--------------------------------------------------------------------------------    
        return f'<TimerThread (limit={self._limit}, prec={self._idle}, func={self._func.__qualname__}, thread={self._thread})>'

    #--------------------------------------------------------------------------------    
    def __del__(self):
    #--------------------------------------------------------------------------------    
        self.DEBUG and print(f'Deleting {self}')

    #--------------------------------------------------------------------------------    
    def __enter__(self):
    #--------------------------------------------------------------------------------    
        return self

    #--------------------------------------------------------------------------------    
    def __exit__(self, exc_type, exc_value, traceback):
    #--------------------------------------------------------------------------------    
        self.close()

    #--------------------------------------------------------------------------------    
    def endtime(self):
    #--------------------------------------------------------------------------------    
        return self._endtime

    #--------------------------------------------------------------------------------    
    def uptime(self):
    #--------------------------------------------------------------------------------    
        return self._limit - self.time()


    #--------------------------------------------------------------------------------    
    def start(self):
    #--------------------------------------------------------------------------------    
        self._endtime = None
        self._call_func = self._func
        self._starttime = datetime.now()
        if not self._running:
            self._running = True
            self._thread.start()

    #--------------------------------------------------------------------------------    
    def close(self):
    #--------------------------------------------------------------------------------    
        self._running = False
        if self._thread.is_alive():
            self._thread.join()

    #--------------------------------------------------------------------------------    
    def cancel_if_alive(self):
    #--------------------------------------------------------------------------------    
        #print((datetime.now()-self._starttime).total_seconds(), self._is_alive)
        if not self._endtime:
            self._call_func = lambda : None
            self._endtime = self.time()
            return True
        return False

    #--------------------------------------------------------------------------------    
    def is_alive(self):
    #--------------------------------------------------------------------------------    
        return not self._endtime

    #--------------------------------------------------------------------------------    
    def time(self):
    #--------------------------------------------------------------------------------    
        return (datetime.now()-self._starttime).total_seconds()

    #--------------------------------------------------------------------------------    
    def _timer(self):
    #--------------------------------------------------------------------------------    
        while self._running:
            sleep(self._idle)
            if not self._endtime:
                time = self.time()
                if time >= self._limit:
                    self._call_func()
                    self._endtime = time
                    #print('Called '+self._caller.__qualname__+f' at {sec}')


