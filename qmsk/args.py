"""
    CLI argument handling; common stuff: logging
"""

import argparse
import logging
import os.path
import shlex
import sys

import logging; log = logging.getLogger('qmsk.args')

CONFDIR = '/etc/qmsk'

def parser (package=None, module=None, version=None, **opts):
    """
        Add an argparse.ArgumentGroup.
    """

    parser = argparse.ArgumentParser(
            fromfile_prefix_chars='@',
            **opts
    )
    parser.convert_arg_line_to_args = lambda line: shlex.split(line, comments=True)

    general = parser.add_argument_group('qmsk.args', "General options")

    general.add_argument('-q', '--quiet',     dest='loglevel', action='store_const', const=logging.ERROR, help="Less output")
    general.add_argument('-v', '--verbose',   dest='loglevel', action='store_const', const=logging.INFO,  help="More output")
    general.add_argument('-D', '--debug',     dest='loglevel', action='store_const', const=logging.DEBUG, help="Even more output")
    general.add_argument('--debug-module',    action='append', metavar='MODULE',
            help="Enable logging for the given logger/module name")

    if version:
        parser.add_argument('--version', action='version', version=version)

    if package and module:
        parser.set_defaults(
            config_path = os.path.join(CONFDIR, package, module + '.conf'),
        )

    # defaults
    parser.set_defaults(
        logname             = parser.prog,
        loglevel            = logging.WARN,
        debug_module        = [],
    )

    return parser

def apply (args):
    """
        Apply the options.
    """

    # configure
    logging.basicConfig(
        # XXX: log Class.__init__ as Class, not __init__?
        format      = '%(levelname)8s %(name)20s.%(funcName)s: %(message)s',
        level       = args.loglevel,
    )

    # TODO: use --quiet for stdout output?
    args.quiet = args.loglevel > logging.WARN

    # enable debugging for specific targets
    for logger in args.debug_module:
        logging.getLogger(logger).setLevel(logging.DEBUG)

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
