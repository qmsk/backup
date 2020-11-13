"""
    Invoke external commands, with python kwargs -> options mangling.
"""

import collections
import contextlib
import io
import logging
import os
import subprocess

log = logging.getLogger('qmsk.invoke')

SUDO = '/usr/bin/sudo'
ENCODING = 'utf-8'

class InvokeError (Exception):
    def __init__ (self, cmd, exit, stderr):
        self.cmd = cmd
        self.exit = exit
        self.stderr = stderr

    def __str__ (self):
        return "{self.cmd} failed ({self.exit}): {self.stderr}".format(self=self)

def invoke (cmd, args, stdin=None, stdout=None, quiet=False, setenv=None, sudo=False, encoding=ENCODING):
    """
        Invoke a command directly.

        cmd:string
            Command executable to invoke

        args:[string]
            Arguments for command, not including executable name (i.e. argv[1:])

        stdin:
            None:       empty pipe on stdin (EOF)
            False:      /dev/null
            True:       passthrough stdin
            str/btes:   write data on stdin
            File:       read from file

        stdout:
            None:       return stdout
            True:       passthrough stdout
            False:      /dev/null

        quiet:bool
            Supress log.warning() with stderr on success.

        setenv:{str:str}
            Run with expanded environment

        sudo:
            True:       Run using sudo as the default user (root)

        encoding:str
            Encode stdin, and decode stdout.

            None:       Use bytes instead, without encoding/decoding.

        Raises InvokeError on nonzero exit, otherwise log.warn's any stderr.

        Returns stdout str.
    """

    log.debug("{sudo}{cmd} {args}".format(sudo=('sudo ' if sudo else ''), cmd=cmd, args=' '.join(args)))

    if stdin is True:
        # keep process stdin/out
        popen_stdin = None
        input = None
    elif stdin is False:
        # EOF
        popen_stdin = subprocess.DEVNULL
    elif stdin is None:
        # return stdout, EOF on stdin
        popen_stdin = subprocess.PIPE
        input = None
    elif isinstance(stdin, (str, bytes)):
        # return stdout, give stdin
        popen_stdin = subprocess.PIPE
        input = stdin
    else:
        # stdin from given open file
        popen_stdin = stdin
        input = None

    if stdout is True:
        # keep process stdout
        popen_stdout = None
    elif stdout is None:
        # capture stdout
        popen_stdout = subprocess.PIPE
    elif stdout is False:
        # discard
        popen_stdout = subprocess.DEVNULL
    else:
        # stdout from given open file
        popen_stdout = stdout

    if setenv:
        env = dict(os.environ)
        env.update(setenv)
    else:
        env = None

    argv = [cmd] + list(args)

    if sudo:
        argv = [SUDO] + argv

    # run
    if input and encoding:
        input = input.encode(encoding)

    p = subprocess.Popen(argv, stdin=popen_stdin, stdout=popen_stdout, stderr=subprocess.PIPE, env=env)

    # get output
    # returns None if not io
    stdout, stderr = p.communicate(input=input)

    if stderr:
        stderr = stderr.decode(encoding or 'ascii', errors='replace')

    if p.returncode:
        # failed
        raise InvokeError(cmd, p.returncode, stderr)
    elif stderr and not quiet:
        log.warning("%s: %s", cmd, stderr)

    if stdout is None:
        return None
    elif encoding:
        return io.StringIO(stdout.decode(encoding))
    else:
        return io.BytesIO(stdout)

def process_opt (name, value):
    """
        Mangle from python keyword-argument dict format to command-line option tuple format.

        >>> process_opt('foo', True)
        ('--foo',)
        >>> process_opt('foo', 2)
        ('--foo', '2')
        >>> process_opt('foo', 'bar')
        ('--foo', 'bar')
        >>> process_opt('foo_bar', 'asdf')
        ('--foo-bar', 'asdf')

        # multi
        >>> process_opt('foo', ['bar', 'quux'])
        ('--foo', 'bar', '--foo', 'quux')
        >>> process_opt('foo', [False, 'bar', True])
        ('--foo', 'bar', '--foo')

        # empty
        >>> process_opt('foo', False)
        ()
        >>> process_opt('foo', None)
        ()
        >>> process_opt('bar', '')
        ()

        Returns a tuple of argv items.
    """

    # mangle opt
    opt = '--' + name.replace('_', '-')

    if value is True:
        # flag opt
        return (opt, )

    elif not value:
        # flag opt / omit
        return ( )

    elif isinstance(value, str):
        return (opt, value)

    elif isinstance(value, collections.Iterable):
        opts = (process_opt(name, subvalue) for subvalue in value)

        # flatten
        return tuple(part for parts in opts for part in parts)

    else:
        # as-is
        return (opt, str(value))

def optargs (*args, **kwargs):
    """
        Convert args/options into command-line format

        >>> optargs('foo')
        ['foo']
        >>> optargs(foo=True)
        ['--foo']
        >>> optargs(foo=False)
        []
        >>> optargs(foo='bar')
        ['--foo', 'bar']
    """

    ## opts
    # process
    opts = [process_opt(opt, value) for opt, value in kwargs.items()]

    # flatten
    opts = [str(part) for parts in opts for part in parts]

    ## args
    args = [str(arg) for arg in args if arg]

    return opts + args

def command (cmd, *args, **opts):
    """
        Invoke a command with options/arguments, given via Python arguments/keyword arguments.

        Return stdout. See invoke()
    """

    log.debug("{cmd} {opts} {args}".format(cmd=cmd, args=args, opts=opts))

    # invoke
    return invoke(cmd, optargs(*args, **opts))


@contextlib.contextmanager
def stream (cmd, args, sudo=None, stdin=None, encoding=ENCODING):
    """
        Invoke command with streaming stdout.

        This acts as a context manager that gives the command stdout as a file object:

            >>> with stream('test') as stdout:
            >>>     print(stdout.read())

        XXX: deadlock on stderr?
    """

    log.debug("{sudo}{cmd} {args}".format(sudo=('sudo ' if sudo else ''), cmd=cmd, args=' '.join(args)))

    argv = [cmd] + args

    if sudo:
        argv = [SUDO] + argv

    p = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    error = None

    try:
        yield p.stdout

    except Exception as ex:
        error = ex # re-raise after logging stderr

        log.debug("kill on error while streaming %s: %s", cmd, ex)

        p.kill()

    finally:
        status = p.wait()

    # collect any output
    stderr = p.stderr.read()

    if stderr:
        stderr = stderr.decode(encoding or 'ascii', errors='replace')

    log.debug("stream %s: status=%d stderr=%r", cmd, status, stderr)

    if status:
        log.warning("%s: %s", cmd, stderr)

    if error:
        # with-block failed
        raise error

    elif status:
        # command failed
        raise InvokeError(cmd, status, stderr)

    elif stderr:
        log.debug("%s: %s", cmd, stderr)


class Invoker:
    def __init__(self, sudo=None):
        self.sudo = sudo

    def invoke(self, cmd, args, **opts):
        return invoke(cmd, args, sudo=self.sudo, **opts)

    def stream(self, cmd, args, **opts):
        return stream(cmd, args, sudo=self.sudo, **opts)


SSH = '/usr/bin/ssh'

class SSHInvoker:
    """
        Remote Invoke over SSH
    """

    def __init__(self, ssh_host, config_file=None, identity_file=None):
        self.ssh_host = ssh_host
        self.config_file = config_file
        self.identity_file = identity_file

    def ssh_args (self, cmd, args):
        return optargs(
            '-F' + self.config_file if self.config_file else None,
            '-i' + self.identity_file if self.identity_file else None,
            self.ssh_host,
        ) + [cmd] + args

    def invoke(self, cmd, args, **opts):
        return invoke(SSH, self.ssh_args(cmd, args), **opts)

    def stream(self, cmd, args, **opts):
        return stream(SSH, self.ssh_args(cmd, args), **opts)

if __name__ == '__main__':
    import doctest
    doctest.testmod()
