"""
    Invoke external commands.
"""

import subprocess
import logging

log = logging.getLogger('pvl.backup.invoke')

class InvokeError (Exception) :
    def __init__ (self, cmd, exit) :
        self.cmd = cmd
        self.exit = exit

    def __str__ (self) :
        return "{cmd} failed: {exit}".format(cmd=self.cmd, exit=self.exit)

def invoke (cmd, args, data=None) :
    """
        Invoke a command directly.
        
        data:       data to pass in on stdin, returning stdout.
                    if given as False, passes through our process stdin/out

        Doesn't give any data on stdin, and keeps process stderr.
        Returns stdout.
    """
    
    log.debug("cmd={cmd}, args={args}".format(cmd=cmd, args=args))

    if data is False :
        # keep process stdin/out
        io = None
    else :
        io = subprocess.PIPE

    p = subprocess.Popen([cmd] + args, stdin=io, stdout=io)

    # get output
    stdout, stderr = p.communicate(input=data)

    if p.returncode :
        # failed
        raise InvokeError(cmd, p.returncode)

    return stdout

def process_opt (opt, value) :
    """
        Mangle from python keyword-argument dict format to command-line option tuple format.

        >>> process_opt('foo', True)
        ('--foo',)
        >>> process_opt('foo', False)
        ()
        >>> process_opt('foo', 2)
        ('--foo', '2')
        >>> process_opt('foo', 'bar')
        ('--foo', 'bar')
        >>> process_opt('foo_bar', 'asdf')
        ('--foo-bar', 'asdf')

        # XXX: weird?
        >>> process_opt('bar', '')
        ('--bar', '')

        Returns a tuple of argv items.
    """

    # mangle opt
    opt = '--' + opt.replace('_', '-')

    if value is True :
        # flag opt
        return (opt, )

    elif value is False or value is None:
        # flag opt / omit
        return ( )

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

