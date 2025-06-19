from time import sleep
from psutil import (STATUS_SLEEPING, STATUS_STOPPED, STATUS_ZOMBIE, Process as psutil_Process, process_iter, wait_procs,
                    NoSuchProcess, AccessDenied)

DEBUG = False

CHILD_SEARCH_WAIT = 0.5        # Seconds to sleep during child process search
CHILD_SEARCH_LIMIT = 500       # Total number of iterations in child process search 


#--------------------------------------------------------------------------------
def ignore_process_error(func):
#--------------------------------------------------------------------------------
    def inner(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (NoSuchProcess, ProcessLookupError):
            return f'{args[0]._name} is missing'
    return inner


#====================================================================================
class Process:                                                              # Process
#====================================================================================

    @classmethod
    #--------------------------------------------------------------------------------
    def find(self, name):                                                   # Process
    #--------------------------------------------------------------------------------        
        for proc in process_iter():
            if proc.name() == name:
                return proc
        
    #--------------------------------------------------------------------------------
    def __init__(self, process=None, pid=None, app_name=None, error_func=None):    # Process
    #--------------------------------------------------------------------------------
        if not process and not pid:
            raise SyntaxError("Missing argument in Process-class: 'process' or 'pid' is required")
        self._process = process or psutil_Process(pid=pid)
        self._pid = self._process.pid
        self._name = self._process.name()
        self._app_name = app_name
        self._suspend_errors = 0
        self._error_func = error_func or self.raise_error
        if DEBUG:
            print(f'Creating {self}')

    #--------------------------------------------------------------------------------
    def __str__(self):                                                      # Process
    #--------------------------------------------------------------------------------
        return f"'{self._name}' ({self._pid})"

    #--------------------------------------------------------------------------------
    def __repr__(self):                                                      # Process
    #--------------------------------------------------------------------------------
        return f'<Process(name={self._name}, pid={self._pid}>'


    #--------------------------------------------------------------------------------
    def __del__(self):                                                      # Process
    #--------------------------------------------------------------------------------
        if DEBUG:
            print(f'Deleting {self}')


    #--------------------------------------------------------------------------------
    def raise_error(self, log=None):                                        # Process
    #--------------------------------------------------------------------------------
        raise SystemError(
            f'ERROR {self._app_name} stopped unexpectedly' + (f', check {log}' if log else '')
        )

    #--------------------------------------------------------------------------------
    def process(self):                                                      # Process
    #--------------------------------------------------------------------------------
        return self._process

    #--------------------------------------------------------------------------------
    def kill(self, children=False):                              # Process
    #--------------------------------------------------------------------------------
        if children:
            procs = self._process.children(recursive=True) + [self._process]
            while procs:
                for p in procs:
                    p.kill()
                _, procs = wait_procs(procs, timeout=None)
        else:
            self._process.kill()


    #--------------------------------------------------------------------------------
    def name(self):                                                         # Process
    #--------------------------------------------------------------------------------
        return self._name

    # #--------------------------------------------------------------------------------
    # def name_pid(self):                                                     # Process
    # #--------------------------------------------------------------------------------
    #     return f"\'{self._name}\' ({self.pid}, {self._user})"

    # #--------------------------------------------------------------------------------
    # def info(self):                                                     # Process
    # #--------------------------------------------------------------------------------
    #     #return f"\'{self._name}\' ({self._pid}, {self._user})"
    #     return f"'{self._name}' ({self._pid})"

    #--------------------------------------------------------------------------------
    def suspend(self):                                                      # Process
    #--------------------------------------------------------------------------------
        try:
            self._process.suspend()
            return True
        except AccessDenied:
            self._suspend_errors += 1
            return False
        except (NoSuchProcess, ProcessLookupError):
            return False

    #--------------------------------------------------------------------------------
    def resume(self):                                                       # Process
    #--------------------------------------------------------------------------------
        try:
            self._process.resume()
            return True
        except (AccessDenied, NoSuchProcess, ProcessLookupError):
            return False


    @ignore_process_error
    #--------------------------------------------------------------------------------
    def current_status(self):                                               # Process
    #--------------------------------------------------------------------------------
        return f'{self._process.name()} {self._process.status()}'
    

    #--------------------------------------------------------------------------------
    def suspend_errors(self):                                               # Process
    #--------------------------------------------------------------------------------
        if self._suspend_errors > 0:
            return f'{self._name} failed to suspend {self._suspend_errors} times'
        return ''

    #--------------------------------------------------------------------------------
    def is_running(self, raise_error=False, **kwargs):                                # Process
    #--------------------------------------------------------------------------------
        try:
            if self._process.is_running() and self._process.status() != STATUS_ZOMBIE:
                return True
            if raise_error:
                raise SystemError(
                    f'ERROR {self._app_name} is not running ({self._name} is {self._process.status()})'
                )
        except (NoSuchProcess, ProcessLookupError):
            if raise_error:
                self._error_func(**kwargs)
            else:
                return False
        except AttributeError as error:
            if raise_error:
                raise SystemError(f'ERROR {self._app_name} process is {self._process}') from error
            return True

    #--------------------------------------------------------------------------------
    def is_not_running(self):                                               # Process
    #--------------------------------------------------------------------------------
        try:
            if (not self._process or
                    not self._process.is_running() or
                    self._process.status() == STATUS_ZOMBIE):
                return True
        except (NoSuchProcess, ProcessLookupError):
            return True
            
    #--------------------------------------------------------------------------------
    def is_sleeping(self):                                                  # Process
    #--------------------------------------------------------------------------------
        try:
            if self._process.status() in (STATUS_SLEEPING, STATUS_STOPPED):
                return True
            if not self._process.is_running() or self._process.status() == STATUS_ZOMBIE:
                raise SystemError(f'ERROR Process {self.name()} disappeared while trying to sleep')
        except (NoSuchProcess, ProcessLookupError, AttributeError) as error:
            raise SystemError(
                f'ERROR Process {self._process} disappeared while trying to sleep'
            ) from error

                
    #--------------------------------------------------------------------------------
    def assert_running(self, raise_error=True, **kwargs):                   # Process
    #--------------------------------------------------------------------------------
        return self.is_running(raise_error=raise_error, **kwargs)


    #--------------------------------------------------------------------------------
    def get_children(self, raise_error=True, log=False, wait=CHILD_SEARCH_WAIT, limit=CHILD_SEARCH_LIMIT):      # Process
    #--------------------------------------------------------------------------------
        # Looking for child-processes with a name that match the app_name
        # Only do search if app_name is different from the name of this process  
        children, time = [], None
        if not self._process:
            if raise_error:
                raise SystemError('Parent-process missing, unable to look for child-processes')
            return children, time
        name = self._app_name.lower()
        # Return if this is the main process
        if self._process.name().lower().startswith(name):
            return children, time
        time = None
        for i in range(limit):
            #print(self)
            sleep(wait)
            if self.is_not_running():
                if raise_error:
                    raise SystemError(
                        f'ERROR {self} disappeared while searching for child-processes!'
                    )
                return children, time
            children = self._process.children(recursive=True)
            if log:
                log(children and children or f"  searching for child-process '{name}' ...", v=3)
            # Stop if named child process is found
            if any(p.name().lower().startswith(name) for p in children):
                time = wait*i
                break
        if time is None and raise_error:
            raise SystemError(
                f'Unable to find child process of {self} in {wait*limit:.1f} seconds, aborting...'
            )
        # Child processes inherit app_name and error_func from parent
        children = [Process(process=c, app_name=self._app_name, error_func=self._error_func) for c in children]
        return children, time

