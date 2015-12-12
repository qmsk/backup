"""
    Invoke external commands.

    XXX: replace with pvl.invoke
"""

import subprocess
import logging

log = logging.getLogger('pvl.backup.invoke')

SUDO = '/usr/bin/sudo'

class InvokeError (Exception):
    def __init__ (self, cmd, exit, stderr):
        self.cmd = cmd
        self.exit = exit
        self.stderr = stderr

    def __str__ (self) :
        return "{self.cmd} exit {self.exit}: {self.stderr}".format(self=self)

def invoke (cmd, args, data=None, sudo=False) :
    """
        Invoke a command directly.
        
        data:       data to pass in on stdin, returning stdout.
                    if given as False, passes through our process stdin/out
        sudo:       exec using sudo

        Doesn't give any data on stdin, and keeps process stderr.
        Returns stdout.
    """
    
    log.debug("{sudo}{cmd} {args}".format(sudo=('sudo ' if sudo else ''), cmd=cmd, args=' '.join(args)))

    if data is False :
        # keep process stdin/out
        io = None
    else :
        io = subprocess.PIPE

    args = [cmd] + args

    if sudo :
        args = [SUDO] + args

    p = subprocess.Popen(args, stdin=io, stdout=io, stderr=subprocess.PIPE)

    # get output
    stdout, stderr = p.communicate(input=data)

    log.debug("%s exit %d", cmd, p.returncode)

    if p.returncode :
        # failed
        raise InvokeError(cmd, p.returncode, stderr)

    return stdout

def process_opt (opt, value) :
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
        >>> process_opt('asdf', ['foo', 'bar'])
        ('--asdf', 'foo', '--asdf', 'bar')

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
    opt = '--' + opt.replace('_', '-')

    if value is True :
        # flag opt
        return (opt, )

    elif not value :
        # flag opt / omit
        return ( )

    elif isinstance(value, (list, tuple)):
        # multiple flag
        return tuple(arg for subvalue in value for arg in (opt, str(subvalue)))

    else :
        # as-is
        return (opt, str(value))

def optargs (*args, **kwargs) :
    """
        Convert args/options into command-line format
    """

    ## opts
    # process
    opts = [process_opt(opt, value) for opt, value in kwargs.iteritems()]

    # flatten
    opts = [str(opt_part) for opt_parts in opts for opt_part in opt_parts if opt_part]

    ## args
    args = [str(arg) for arg in args if arg]

    return opts + args
 
def command (cmd, *args, **opts) :
    """
        Invoke a command with options/arguments, given via Python arguments/keyword arguments.

        Return stdout.
    """
    
    log.debug("{cmd} {opts} {args}".format(cmd=cmd, args=args, opts=opts))

    # invoke
    return invoke(cmd, optargs(*args, **opts))

if __name__ == '__main__':
    import doctest
    doctest.testmod()

