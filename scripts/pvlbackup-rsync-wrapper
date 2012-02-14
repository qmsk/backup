#!/usr/bin/python

from pvl.backup.rsync import RSyncCommandFormatError
from pvl.backup.invoke import InvokeError
from pvl.backup import rsync

import optparse
import os
import logging

log = logging.getLogger()

# command-line options
options = None

def parse_options (argv) :
    """
        Parse command-line arguments.
    """


    parser = optparse.OptionParser()

    # logging
    parser.add_option('-q', '--quiet',      dest='loglevel', action='store_const', const=logging.WARNING, help="Less output")
    parser.add_option('-v', '--verbose',    dest='loglevel', action='store_const', const=logging.INFO,  help="More output")
    parser.add_option('-D', '--debug',      dest='loglevel', action='store_const', const=logging.DEBUG, help="Even more output")

    # 
    parser.add_option('-c', '--command',    default=os.environ.get('SSH_ORIGINAL_COMMAND'),
            help="rsync command to execute")

    parser.add_option('-R', '--readonly',   action='store_true', default=False,
            help="restrict to read operations")

    parser.add_option('-P', '--restrict-path', default=False,
            help="restrict to given path")

    # defaults
    parser.set_defaults(
        loglevel    = logging.WARNING,
    )

    # parse
    options, args = parser.parse_args(argv[1:])

    # configure
    logging.basicConfig(
        format  = '%(processName)s: %(name)s: %(levelname)s %(funcName)s : %(message)s',
        level   = options.loglevel,
    )

    return options, args

def rsync_wrapper (command, restrict='lvm:') :
    """
        Wrap given rsync command.
        
        Backups the LVM LV given in the rsync command.
    """

    try :
        # parse
        rsync_cmd, rsync_options, source_path, dest_path = rsync.parse_command(command, 
                restrict_readonly   = options.readonly,
            )

    except RSyncCommandFormatError, e:
        log.error("invalid rsync command: %r: %s", command, e)
        return 2

    # XXX: the real path is always given second..
    path = dest_path

    try :
        # parse source
        source = rsync.parse_source(path,
                restrict_path       = options.restrict_path,
            )

    except RSyncCommandFormatError, e:
        log.error("invalid rsync source: %r: %s", path, e)
        return 2

    try :
        # run
        source.execute(rsync_options)

    except InvokeError, e:
        log.error("%s failed: %d", e.cmd, e.exit)
        return e.exit

    # ok
    return 0

def main (argv) :
    """
        SSH authorized_keys command="..." wrapper for rsync.
    """

    global options

    # global options + args
    options, args = parse_options(argv)

    # args
    if args :
        log.error("No arguments are handled")
        return 2

    if not options.command:
        log.error("SSH_ORIGINAL_COMMAND not given")
        return 2

    try :
        # handle it
        return rsync_wrapper(options.command)

    except Exception, e:
        log.error("Internal error:", exc_info=e)
        return 3

    # ok
    return 0

if __name__ == '__main__' :
    import sys

    sys.exit(main(sys.argv))

