"""
    CLI argument handling; common stuff: logging
"""

import argparse
import grp
import logging
import os
import pwd
import shlex
import sys

import logging; log = logging.getLogger('pvl.args')

CONFDIR = '/etc/pvl'

def parser (setuid=None, package=None, module=None, version=None, **opts):
    """
        Add an argparse.ArgumentGroup.
    """

    parser = argparse.ArgumentParser(
            fromfile_prefix_chars='@',
            **opts
    )
    parser.convert_arg_line_to_args = lambda line: shlex.split(line, comments=True)

    if setuid is None:
        # autodetect: only if we will be capable of
        # XXX: use linux capabilities?
        setuid = (os.geteuid() == 0)

    general = parser.add_argument_group('pvl.args', "General options")

    general.add_argument('-q', '--quiet',     dest='loglevel', action='store_const', const=logging.ERROR, help="Less output")
    general.add_argument('-v', '--verbose',   dest='loglevel', action='store_const', const=logging.INFO,  help="More output")
    general.add_argument('-D', '--debug',     dest='loglevel', action='store_const', const=logging.DEBUG, help="Even more output")
    general.add_argument('--log-file',                                                                    help="Log to file")
    general.add_argument('--debug-module',    action='append', metavar='MODULE', 
            help="Enable logging for the given logger/module name")
    
    if package and module:
        parser.set_defaults(
            config_path = os.path.join(CONFDIR, package, module + '.conf'),
        )
  
    if version:
        parser.add_argument('--version', action='version', version=version)

    if setuid:
        general.add_argument('--uid',             help="Change uid")
        general.add_argument('--gid',             help="Change gid")

    # defaults
    parser.set_defaults(
        setuid              = setuid,
        logname             = parser.prog,
        loglevel            = logging.WARN,
        debug_module        = [],
    )

    return parser
 
def args (**args):
    """
        Synthensise options.
    """

    return argparse.Namespace(**args)

def apply_setid (args, rootok=None):
    """
        Drop privileges if running as root.

        XXX: this feature isn't very useful (import-time issues etc), but in certain cases (syslog-ng -> python),
        it's difficult to avoid this without some extra wrapper tool..?
    """

    # --uid -> pw
    if not args.uid :
        pw = None
    elif args.uid.isdigit() :
        pw = pwd.getpwuid(int(args.uid))
    else :
        pw = pwd.getpwnam(args.uid)

    # --gid -> gr
    if not args.gid and not pw :
        gr = None
    elif not args.gid :
        gr = grp.getgrgid(pw.pw_gid)
    elif args.gid.isdigit() :
        gr = grp.getgrgid(str(args.gid))
    else :
        gr = grp.getgrnam(args.gid)
    
    if gr :
        # XXX: secondary groups? seem to get cleared
        log.info("setgid: %s: %s", gr.gr_name, gr.gr_gid)
        os.setgid(gr.gr_gid)

    if pw :
        log.info("setuid: %s: %s", pw.pw_name, pw.pw_uid)
        os.setuid(pw.pw_uid)
    
    elif os.getuid() == 0 :
        if rootok :
            log.info("running as root")
        else :
            log.error("refusing to run as root, use --uid 0 to override")
            sys.exit(2)

# TODO: remove
def apply_config (args, parser, path, encoding=None) :
    """
        Load options from config.
    """

    file = open(path, encoding=encoding)
    
    lexer = shlex.shlex(file, infile=path)
    lexer.whitespace_split = True
    
    words = list(lexer)

    log.debug("%s: %r", path, words)

    args = parser.parse_args(words, args)

    return args

def apply (args, rootok=True):
    """
        Apply the optparse options.
    """

    # configure
    logging.basicConfig(
        # XXX: log Class.__init__ as Class, not __init__?
        format      = '%(levelname)8s %(name)20s.%(funcName)s: %(message)s',
        level       = args.loglevel,
        filename    = args.log_file,
    )

    # TODO: use --quiet for stdout output?
    args.quiet = args.loglevel > logging.WARN

    # enable debugging for specific targets
    for logger in args.debug_module:
        logging.getLogger(logger).setLevel(logging.DEBUG)

    if args.setuid:
        if args.uid or args.gid or not rootok:
            # set uid/gid
            apply_setid(args, rootok=rootok)
   
def parse (parser, args=None):
    """
        Parse args using the given argparse.ArgumentParser.
    """

    config_path = parser.get_default('config_path')
    
    if args is None:
        args = sys.argv[1:]

    if config_path and os.path.exists(config_path):
        log.info("config defaults from %s", config_path)
        
        args = ['@{path}'.format(path=config_path)] + args

    args = parser.parse_args(args)

    apply(args)
    
    return args

def main (main):
    """
        Run given main func.
    """

    sys.exit(main(sys.argv[1:]))
