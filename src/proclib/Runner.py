
# -*- coding: utf-8 -*-
from datetime import datetime
from re import findall
from subprocess import Popen, PIPE, STDOUT
from shutil import SameFileError, which, copy
from time import sleep
from pathlib import Path
from locale import getpreferredencoding

import psutil
from proclib.Process import Process
from proclib.Timer import Timer, TimerThread


# Constants
SUSPEND_TIMER_PRECICION = 0.1  # Precision of the delayed-suspend-timer in seconds

DEBUG = False

#/////////////////////////////////////////////////////////////////////////////////
#                                     Decorators
#/////////////////////////////////////////////////////////////////////////////////


#--------------------------------------------------------------------------------
def catch_permission_error(func):
#--------------------------------------------------------------------------------
    def inner(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except PermissionError as error:
            raise SystemError(f'WARNING PermissionError in {func.__qualname__}()') from error
    return inner

#--------------------------------------------------------------------------------
def ignore_permission_error(func):
#--------------------------------------------------------------------------------
    def inner(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except PermissionError:
            pass
    return inner

#--------------------------------------------------------------------------------
def pass_KeyboardInterrupt(func):
#--------------------------------------------------------------------------------
    def inner(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except KeyboardInterrupt:
            pass
    return inner

#/////////////////////////////////////////////////////////////////////////////////
#                                     Classes
#/////////////////////////////////////////////////////////////////////////////////


#====================================================================================
class Control_file:
#====================================================================================
    #--------------------------------------------------------------------------------
    def __init__(self, *args, path=None, log=False) -> None:
    #--------------------------------------------------------------------------------
        args = [str(a) for a in args]  # Ensure Path is cast to str
        self._base = ''.join(args[:2]) if len(args)>=2 else ''
        self._nr = (lambda x : f'{int(x):{args[2]}}') if len(args)>2 else (lambda x : '')
        self._path = Path(path if path else self._base + self._nr(0))
        self._log = log

    #--------------------------------------------------------------------------------
    def __repr__(self) -> str:
    #--------------------------------------------------------------------------------
        return f'<Control_file {self._path.name}>'

    #--------------------------------------------------------------------------------
    def __str__(self) -> str:
    #--------------------------------------------------------------------------------
        return f'{self._path.name}'

    #--------------------------------------------------------------------------------
    def __call__(self, n):
    #--------------------------------------------------------------------------------
        self._path = Path(self._base + self._nr(n))
        return self

    #--------------------------------------------------------------------------------
    def glob(self):
    #--------------------------------------------------------------------------------
        if self._base == '':
            return ()
        nr = self._nr(0).replace('0','?')
        path = Path(self._base + nr)
        return (Control_file(path=f, log=self._log) for f in path.parent.glob(path.name))

    #--------------------------------------------------------------------------------
    def name(self):
    #--------------------------------------------------------------------------------
        return self._path.name

    #--------------------------------------------------------------------------------
    def path(self):
    #--------------------------------------------------------------------------------
        return self._path

    @catch_permission_error
    #--------------------------------------------------------------------------------
    def create(self):
    #--------------------------------------------------------------------------------
        if self._log:
            self._log(f'Create empty {self}')
        self._path.touch()

    @catch_permission_error
    #--------------------------------------------------------------------------------
    def create_from(self, file=None, string=None, delete=False):
    #--------------------------------------------------------------------------------
        if file is None and string is None:
            raise SyntaxError(
                "ERROR Both 'file' and 'string' argument missing in Control_file.create_from()!"
            )
        file = file and Path(file)
        ### Create from file
        if file and file.is_file:
            if self._log:
                self._log(f'Create {self} from file {file.name}')
            try:
                copy(file, self._path)
            except SameFileError:
                if self._log:
                    self._log(f'WARNING in {self}: trying to copy same files {file.name}!')
            if delete:
                silentdelete(file)
        ### Create from string
        elif string:
            if self._log:
                self._log(f'Create {self} from text')
            self._path.write_text(string, encoding=getpreferredencoding())

    @catch_permission_error
    #--------------------------------------------------------------------------------
    def append(self, string):
    #--------------------------------------------------------------------------------
        if self._log:
            self._log(f'Append text to {self}')
        with open(self._path, 'a', encoding=getpreferredencoding()) as file:
            file.write(f'{string}\n')

    @ignore_permission_error
    #--------------------------------------------------------------------------------
    def delete(self):
    #--------------------------------------------------------------------------------
        if self._path.is_file():
            if self._log:
                self._log(f'Delete {self}')
            self._path.unlink()

    #--------------------------------------------------------------------------------
    def delete_all(self):
    #--------------------------------------------------------------------------------
        for file in self.glob():
            file.delete()
        #[file.delete() for file in self.glob()]

    #--------------------------------------------------------------------------------
    def is_deleted(self):
    #--------------------------------------------------------------------------------
        try:
            return not self._path.is_file()
        except PermissionError:
            return False





#====================================================================================
class Runner:                                                               # Runner
#====================================================================================
    """

    Class for running programs using Popen. 
    Execution is controlled by interface- and OK-files

    Initialization:
    runner(case, exe, log=None, children=[], pipe=False, verbose=2, timer=False, runlog=None)

    Methods:
      start(cmd)
      suspend()
      resume()
      kill()
 
    """
    
    #--------------------------------------------------------------------------------
    def __init__(self, end_time=0, n=0, t=0, name='', app_name='', case='', exe='', cmd=None, pipe=False,
                 verbose=3, timer=None, runlog=None, ext_iface=(), ext_OK=(),
                 keep_files=False, stop_children=True, keep_alive=False, logtag=None, 
                 time_regex=None, **kwargs):           # Runner
    #--------------------------------------------------------------------------------
        #print('runner.__init__: ',end_time, n, t, name, case,exe,cmd,ext_iface,ext_OK)
        self.reset_processes()
        self.name = name
        self.app_name = app_name
        self.parent = None
        self.children = ()
        self.main = None
        self.active = ()
        self.case = Path(case)
        self.exe = exe
        self.cmd = cmd
        self.logname = self.case.parent/f'{name.lower()}{logtag or ""}.log'
        self.logname.write_text('') # Clear old logs
        self.log = None
        self.runlog = runlog
        log4 = lambda x: self._print(x, v=4)
        self.interface_file = Control_file(self.case, *ext_iface, log=log4)
        self.OK_file = Control_file(self.case, *ext_OK, log=log4)
        self.popen = None
        self.stop_children = stop_children
        self.pipe = pipe
        self.verbose = verbose
        self.timer = timer
        if self.timer:
            self.timer = Timer(name.lower())
        self.keep_files = keep_files
        self.canceled = False
        self.t = t      # current time  
        self.n = int(n) # timestep counter
        self.end_time = end_time   # Max time
        #self.N = int(N)   # Max number of steps
        self.starttime = None
        self.keep_alive = keep_alive
        self.suspend_timer = None
        self.time_regex = time_regex
        self.kwargs = kwargs
        self.unexpected_stop = False
        self.stdin = None
        if DEBUG:
            print(f'Creating {self}')

    #--------------------------------------------------------------------------------
    def __str__(self):                                                       # Runner
    #--------------------------------------------------------------------------------
        return f'<Runner(name={self.name}, cmd={self.cmd}, verbose={self.verbose})>'

    #--------------------------------------------------------------------------------
    def __del__(self):                                                       # Runner
    #--------------------------------------------------------------------------------
        DEBUG and print(f'Deleting {self}')

    #--------------------------------------------------------------------------------
    def set_time(self, time):                                                # Runner
    #--------------------------------------------------------------------------------
        self.end_time = int(time)

    #--------------------------------------------------------------------------------
    def reset_processes(self):                                               # Runner
    #--------------------------------------------------------------------------------
        self.parent = None
        self.main = None
        self.children = []
        self.active = []

    #--------------------------------------------------------------------------------
    def check_input(self):                                                   # Runner
    #--------------------------------------------------------------------------------
        # check if executables exist on the system
        if which(self.exe) is None:
            raise SystemError('WARNING Executable not found: ' + self.exe)
        return True

    # #--------------------------------------------------------------------------------
    # def stopped_unexpectedly(self):                                                # Runner
    # #--------------------------------------------------------------------------------
    #     if self.unexpected_stop:
    #         raise SystemError(f'ERROR {self.name} stopped unexpectedly after {self.time()} days')
    #     return False

    #--------------------------------------------------------------------------------
    def unexpected_stop_error(self, **kwargs):                               # Runner
    #--------------------------------------------------------------------------------
        self.unexpected_stop = True
        raise SystemError(f'ERROR {self.name} stopped unexpectedly after {self.time()} days'
                          + (self.log and f', check {Path(self.log.name).name} for details' or '') 
                          )


    #--------------------------------------------------------------------------------
    def start(self, error_func=None):                                        # Runner
    #--------------------------------------------------------------------------------
        self.log = safeopen(self.logname, 'w') if not self.kwargs.get('to_screen', False) else None
        self.starttime = datetime.now()
        if self.pipe:
            self._print("Starting in PIPE-mode", v=1)
            self.popen = Popen(self.cmd, stdin=PIPE, stdout=self.log, stderr=STDOUT)
            self.stdin = self.popen.stdin
        else:
            self._print(f"Starting \'{' '.join(self.cmd)}\'", v=1)
            self.popen = Popen(self.cmd, stdout=self.log, stderr=self.log)
            #self.popen = Popen(self.cmd, stdout=self.log, stderr=STDOUT)
        self.set_processes(error_func=error_func)
        if self.keep_alive > 0:
            self.suspend_timer = TimerThread(limit=self.keep_alive, prec=SUSPEND_TIMER_PRECICION, func=self.suspend_active)

    #--------------------------------------------------------------------------------
    def is_mpi_process(self, wait=0.1):                                # Runner
    #--------------------------------------------------------------------------------
        proc = None
        cmd = ' '.join(self.cmd)
        # Only mpirun if np > 1
        if '--np ' in cmd and int(cmd.split('--np ')[-1][0]) > 1:
            # attempts = 20
            # while attempts and not (proc:=Process.find('mpirun')):
            #     attempts -= 1
            #     sleep(wait)
            n = 0
            while n < 20:
                if proc:=Process.find('mpirun'):
                    return proc
                sleep(wait)
                n += 1
        #return proc

    #--------------------------------------------------------------------------------
    def set_processes(self, error_func=None):                                # Runner
    #--------------------------------------------------------------------------------
        if error_func is None:
            error_func = self.unexpected_stop_error
        # Parent process
        # The 'mpirun' process is the parent if this is a parallel run
        proc = self.is_mpi_process()
        pid = None if proc else self.popen.pid
        self.parent = self.main = Process(pid=pid, process=proc, app_name=self.app_name, error_func=error_func)
        self._print(f'Parent process : {self.parent}, ')
        #self.parent.assert_running()
        # Find child processes (if they exists)
        self.children, time = self.parent.get_children(log=self.verbose>3 and self._print)
        self._print(
            'Child process' + (len(self.children)>1 and 'es' or '')
            + (time is not None and f' ({time:.1f} sec)' or '')
            + f' : {", ".join([str(p) for p in self.children])}'
        )
        # Set active and main processes
        if self.children:
            self.main = self.children[-1]
        self.active = [self.parent]
        if self.stop_children:
            self.active = self.children + [self.parent]


    #--------------------------------------------------------------------------------
    def get_logfile(self):                                                   # Runner
    #--------------------------------------------------------------------------------
        return self.log and self.log.name

    #--------------------------------------------------------------------------------
    def suspend_active(self):                                                # Runner
    #--------------------------------------------------------------------------------
        suspended = [p.suspend() for p in self.active]
        return all(suspended)

    #--------------------------------------------------------------------------------
    def resume_active(self):                                                # Runner
    #--------------------------------------------------------------------------------
        resumed = [p.resume() for p in self.active]
        return all(resumed)


    #--------------------------------------------------------------------------------
    def suspend(self, check=False, v=2):                                     # Runner
    #--------------------------------------------------------------------------------
        if self.keep_alive > 0:
            self._print('Delayed suspend', v=v)
            self.suspend_timer.start()
        elif self.keep_alive < 0:
            self._print('No suspend', v=v)
        else:
            self._print('Suspend', v=v)
            self.suspend_active()
            if check:
                for proc in self.active:
                    # self.wait_for(proc.is_sleeping, limit=100)
                    self.wait_for(proc.is_sleeping, wait_min=0.02)
            if self.timer:
                self.timer.stop()
        self.print_process_status()


    #--------------------------------------------------------------------------------
    def resume(self, check=False, v=2):                                      # Runner
    #--------------------------------------------------------------------------------
        if self.keep_alive > 0 and self.suspend_timer.cancel_if_alive():
            self._print(f'No resume (suspend delayed {self.suspend_timer.endtime():.0f} sec)', v=v)
        elif self.keep_alive < 0:
            self._print('No resume (not suspended)', v=v)
        else:
            msg = 'Resume'
            if self.suspend_timer and not self.suspend_timer.is_alive():
                msg += f' (suspended {-self.suspend_timer.uptime():.0f} sec ago)'
            self._print(msg, v=v)
            self.resume_active()
            if check:
                for proc in self.active:
                    # self.wait_for(proc.is_running, limit=100)
                    self.wait_for(proc.is_running, wait_min=0.02)
            if self.timer:
                self.timer.start()
        self.print_process_status()

    #--------------------------------------------------------------------------------
    def print_process_status(self, v=3):                                     # Runner
    #--------------------------------------------------------------------------------
        self._print(', '.join( [str(p.current_status()) for p in self.active] ), v=v)


    #--------------------------------------------------------------------------------
    def print_suspend_errors(self, v=1):                                     # Runner
    #--------------------------------------------------------------------------------
        errors = [p.suspend_errors() for p in self.active if p]
        text = ', '.join([e for e in errors if e])
        if text:
            self._print(text, v=v)


    #--------------------------------------------------------------------------------
    def time(self, tag='TIME'):                                              # Runner
    #--------------------------------------------------------------------------------
        t = 0
        if self.log:
            self.log.flush() 
        #     match = matches(file=self.logname, pattern=self.time_regex)
        #     time = [m.group(1) for m in match]
        #     t = time[-1] if time else 0           
        # return float(t)
            chunks = (txt for txt in tail_file(self.logname, size=10*1024) if tag in txt)
            if data:=next(chunks, None):
                days = findall(self.time_regex, data)
                t = float(days[-1]) if days else 0
        return t


    #--------------------------------------------------------------------------------
    def stop_if_canceled(self, unit='days'):                                 # Runner
    #--------------------------------------------------------------------------------
        if self.canceled:
            self.unexpected_stop = True
            self._print('', tag='')
            raise SystemError(
                f'INFO Run stopped after {self.time():.2f}'.rstrip('0').rstrip('.') + f' {unit}')
        return True

    #--------------------------------------------------------------------------------
    def is_running(self):                                                    # Runner
    #--------------------------------------------------------------------------------
        return all(proc.is_running() for proc in self.active)

    #--------------------------------------------------------------------------------
    def assert_running_and_stop_if_canceled(self, raise_error=True):         # Runner
    #--------------------------------------------------------------------------------
        log = self.log and self.log.name
        # for proc in self.active:
        #     proc.assert_running(raise_error=raise_error, log=log)
        is_running = [proc.assert_running(raise_error=raise_error, log=log) for proc in self.active]            
        is_not_stopped = self.stop_if_canceled()
        return all(is_running) and is_not_stopped

    #--------------------------------------------------------------------------------
    def run_time(self):                                                      # Runner
    #--------------------------------------------------------------------------------
        return datetime.now()-self.starttime


    #--------------------------------------------------------------------------------
    def complete_msg(self, run_time=None):                                   # Runner
    #--------------------------------------------------------------------------------
        if run_time is None:
            run_time = self.run_time()
        return 'INFO Simulation complete, run-time was ' + str(run_time).split('.')[0]


    #--------------------------------------------------------------------------------
    def get_time_and_stop_if_limit_reached(self):                            # Runner
    #--------------------------------------------------------------------------------
        self.t = self.time()
        if int(self.t) > int(self.end_time):
            raise SystemError(self.complete_msg())
        return self.t


    #--------------------------------------------------------------------------------
    #def wait_for(self, func, *args, timer=False, limit=None, pause=0.01, v=2, error=None, raise_error=False, log=None, loop_func=None, **kwargs):
    def wait_for(self, func, *args, timer=False, wait_min=None, pause=0.01, v=2, error=None, 
                 raise_error=False, log=None, loop_func=None, func_name=None, **kwargs):
    #--------------------------------------------------------------------------------
        limit = int(wait_min*60/pause) if wait_min else None
        if timer:
            starttime = datetime.now()
        if not loop_func:
            # Default checks during loop
            loop_func = self.assert_running_and_stop_if_canceled
        func_name = func_name or func.__qualname__
        passed_args = ','.join([f'{k}={v}' for k,v in kwargs.items()])
        self._print(f'Calling wait_for( {func_name}({passed_args}), limit={limit}, pause={pause} )... ', v=v, end='')
        # If limit is reached this function returns -1
        n = loop_until(func, *args, pause=pause, limit=limit, loop_func=loop_func, **kwargs)
        time = ''
        if timer:
            time = f' ({(datetime.now()-starttime).total_seconds():.2f} sec)'
        if n<0:
            if raise_error:
                raise SystemError(error or f'wait_for({func_name}) reached loop-limit {limit}')
            self._print(f'loop limit reached!{time}' or '', tag='', v=v)
            return False
        self._print(str(n) + f' loops{time}', tag='', v=v)
        if callable(log):
            self._print(log())
        return True


    #--------------------------------------------------------------------------------
    def wait_for_process_to_finish(self, v=2, wait_min=None, pause=None, loop_func=None, msg=None):      # Runner
    #--------------------------------------------------------------------------------
        msg = msg or 'Waiting for parent process to finish'
        self._print(msg, v=v)
        success = self.wait_for(self.parent.is_not_running, raise_error=False, pause=pause, wait_min=wait_min, loop_func=loop_func)
        if not success:
            #time = (limit or 0)*(pause or 0)/60
            self._print('', tag='')
            self._print(f'process did not finish within {wait_min:.2f} minutes and will be killed', v=v)
            self._print([p.name() for p in self.active if p])
            self.kill()


    #--------------------------------------------------------------------------------
    def wait_for_files(self, *files, wait_min=None, log=None, **kwargs):        # Runner
    #--------------------------------------------------------------------------------
        for path in map(Path, files):
            func_name = f'Path({path.name}).is_file'
            self.wait_for(path.is_file, wait_min=wait_min, raise_error=True, error=f'{path} is missing', func_name=func_name, **kwargs)
            if callable(log):
                log(f'{path.name} exists')


    #--------------------------------------------------------------------------------
    def cancel(self):                                                        # Runner
    #--------------------------------------------------------------------------------
        self.canceled = True

    #--------------------------------------------------------------------------------
    def close(self):                                                         # Runner
    #--------------------------------------------------------------------------------
        self.reset_processes()
        # Close log-file
        if self.log:
            self.log.close()
        self.log = None
        # Stop and delete the suspend-timer-thread
        if self.suspend_timer:
            self.suspend_timer.close()
        self.suspend_timer = None # For garbage collector (__del__)
        # Delete interface-files
        if not self.keep_files:
            self.interface_file.delete_all()
            self.OK_file.delete()


    #--------------------------------------------------------------------------------
    def quit(self, v=1, loop_func=lambda:None):                              # Runner
    #--------------------------------------------------------------------------------
        self._print('', tag='', v=v)
        self._print('Quitting', v=v)
        self.resume()
        #self.wait_for_process_to_finish(msg='Waiting for process to quit', limit=6000, pause=0.01, loop_func=loop_func)
        self.wait_for_process_to_finish(msg='Waiting for process to quit', wait_min=1, pause=0.01, loop_func=loop_func)
        self.close()
        self._print('Finished', v=v)


    #--------------------------------------------------------------------------------
    def kill(self, v=2):                                                     # Runner
    #--------------------------------------------------------------------------------
        # terminate children before parent
        #procs = self.children + (self.parent and [self.parent] or []) 
        for process in self.active:
            try:
                self._print(f'Killing {process}...', end='', v=v)
                process.kill()
                self._print('done', tag='', v=v)
            except (psutil.NoSuchProcess, ProcessLookupError):
                self._print('process already gone', tag='', v=v)            
            except psutil.AccessDenied:
                self._print('access denied!!!', tag='', v=v)            
        self.close()

    
    # #--------------------------------------------------------------------------------
    # def write_to_stdin(self, i):                                             # Runner
    # #--------------------------------------------------------------------------------
    #     if not self.pipe:
    #         raise SystemError('STDIN is not piped, unable to write. Aborting...')
    #     self._print(f'writing {i} to STDIN')
    #     inp = f'{i:d}\n'
    #     self.P.stdin.write(inp.encode())
    #     self.P.stdin.flush()

        
    #--------------------------------------------------------------------------------
    def _print(self, txt, v=1, tag=True, flush=True, **kwargs):              # Runner
    #--------------------------------------------------------------------------------
        if v <= self.verbose:
            if isinstance(txt, str):
                txt = [txt]
            txt = (str(t) for t in txt)
            if tag is True:
                txt = f'{self.name}: ' + f'\n{self.name}: '.join(txt)
            else:
                txt = '\n'.join(txt)
            #print(tag, txt, file=self.runlog, flush=flush, **kwargs)
            print(txt, file=self.runlog, flush=flush, **kwargs)


    #--------------------------------------------------------------------------------
    def _printerror(self, txt, **kwargs):                                    # Runner
    #--------------------------------------------------------------------------------
        print()
        print('  ERROR: ' + txt, **kwargs)
        print('', flush=True)


    #--------------------------------------------------------------------------------
    def _printwarning(self, txt, **kwargs):                                  # Runner
    #--------------------------------------------------------------------------------
        print()
        print('  WARNING: ' + txt, **kwargs)
        print('', flush=True)



#/////////////////////////////////////////////////////////////////////////////////
#                                   Utility Functions
#/////////////////////////////////////////////////////////////////////////////////


#------------------------------------------------
def loop_until(func, *args, limit=None, pause=None, loop_func=None, **kwargs):
#------------------------------------------------
    n = 0
    if not loop_func:
        loop_func = lambda:None
    while True:
        if func(*args, **kwargs):
            return n
        if pause:
            sleep(pause)
        n += 1
        if limit and n > limit:
            return -1
        loop_func()

#------------------------------------------------
def safeopen(filename, mode):
#------------------------------------------------
    try:
        filehandle = open(filename, mode)
        return filehandle
    except OSError as error:
        raise SystemError(f'Unable to open file {filename}: {error}') from error

#------------------------------------------------
def silentdelete(*fname, echo=False):
#------------------------------------------------
    for f in fname:
        file = Path(f)
        try:
            file.is_file() and file.unlink()
        except (PermissionError, FileNotFoundError) as e:
            if echo:
                print(f'Unable to delete {f}: {e}')
        if echo:
            print(f'Deleted {f}')

#--------------------------------------------------------------------------------
def decode(data):
#--------------------------------------------------------------------------------
    encoding = ('utf-8', 'latin1')
    for enc in encoding:
        try:
            return data.decode(encoding=enc)
        except UnicodeError:
            continue
    raise SystemError(f'ERROR decode with {encoding} encoding failed!')

#------------------------------------------------
def tail_file(path, size=10*1024, size_limit=False):
#------------------------------------------------
    """ 
    A generator that yields chunks the file starting from the end.
    
    Arguments:
        size : default, 10 kilobytes
            byte-size of the file-chunks
            
        size_limit : default, False
            return None if the size of the file is less than size   
    """
    path = Path(path)
    if not path.is_file():
        return
    filesize = path.stat().st_size
    if size_limit and filesize < size:
        return
    size = pos = min(size, filesize)
    with open(path, 'rb') as file:
        while pos <= filesize:
            file.seek(-pos, 2)
            yield decode(file.read(size))
            if pos == filesize:
                return
            pos = min(pos + size, filesize)

