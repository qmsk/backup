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

def optargs (*args, **kwargs) :
    """
        Convert args/options into command-line format
    """

    # process
    opts = [('--{opt}'.format(opt=opt), value if value != True else None) for opt, value in kwargs.iteritems() if value]

    # flatten
    opts = [str(opt_part) for opt_parts in opts for opt_part in opt_parts if opt_part]

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
 
