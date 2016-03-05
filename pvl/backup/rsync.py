"""
    rsync handling.

    Apologies for the 'RSync' nomenclature
"""

import contextlib
import logging
import os.path
import pvl.backup.mount

from pvl import invoke
from pvl.backup.lvm import LVM, LVMVolume, LVMSnapshot

log = logging.getLogger('pvl.backup.rsync')

RSYNC = '/usr/bin/rsync'

def rsync (options, paths, sudo=False):
    """
        Run rsync.

        Raises InvokeError
    """

    log.info("rsync %s %s", ' '.join(options), ' '.join(paths))

    try:
        # invoke directly; no option-handling, nor stdin/out redirection
        invoke.invoke(RSYNC, options + paths, stdin=True, stdout=True, sudo=sudo)
    except invoke.InvokeError as error:
        raise InvokeError(error.exit, error.stderr)

class Error (Exception):
    pass

class InvokeError (Error):
    def __init__(self, exit, stderr):
        self.exit = exit

        super(InvokeError, self).__init__(stderr)

class CommandError (Error):
    """
        Invalid rsync command.
    """

    pass

class SourceError (Error):
    """
        Invalid rsync source
    """

    pass

class Source (object):
    """
        rsync source
    """

    def __init__ (self, path, sudo=None):
        self.path = path
        self.sudo = sudo

    @contextlib.contextmanager
    def mount(self):
        """
            Return local filesystem path for source.
        """

        yield self.path

    def rsync_sender (self, options):
        """
            Run with --server --sender options.
        """

        with self.mount() as path:
            return rsync(options, ['.', path], sudo=self.sudo)

    def rsync (self, options, dest):
        """
            Run with the given destination.
        """
        
        with self.mount() as path:
            return rsync(options, [path, dest], sudo=self.sudo)

    def __str__ (self):
        return self.path
 
class LVMSource(Source):
    """
        Backup LVM LV by snapshotting + mounting it.
    """

    def __init__ (self, vg, lv, path, sudo=None, lvm_opts={}):
        """
            vg              - str: LVM vg name
            lv              - str: LVM vg name
            path            - str: filesystem path within lvm volume; no leading /

            sudo            - use sudo for LVM operations
            lvm_opts   - options for LVM.snapshot
        """
        
        self.path = path.lstrip('/')
        self.sudo = sudo

        self.lvm = LVM(vg, sudo=sudo)
        self.lvm_volume = self.lvm.volume(lv)
        self.lvm_opts = lvm_opts
 
    @contextlib.contextmanager
    def mount (self):
        """
            Mount LVM snapshot of volume
        """
        
        # snapshot
        log.info("Creating LVM snapshot: %s", self.lvm_volume)

        with self.lvm.snapshot(self.lvm_volume,
                tag     = 'backup',
                **self.lvm_opts
        ) as snapshot:
            # mount
            log.info("Mounting LVM snapshot: %s", snapshot)

            with pvl.backup.mount.mount(snapshot.dev_path,
                    name_hint   = 'lvm_' + snapshot.name + '_',
                    readonly    = True,
                    sudo        = self.sudo,
            ) as mountpoint:
                yield mountpoint.path + '/' + self.path
 
    def __str__ (self):
        return 'lvm:{volume}'.format(volume=self.lvm_volume)
 
def parse_command (command):
    """
        Parse rsync server command into bits. 

            command:            - list(argv) including 'rsync' command and options/arguments
        
        Returns:
            cmd:        rsync argv[0]
            options:    list of --options and -opts
            paths:      list of path arguments

        Raises:
            CommandError
        
        >>> import shlex
        >>> parse_command(shlex.split('rsync --server --sender -ax . lvm:asdf:test'))
        ('rsync', ['--server', '--sender', '-ax'], ['.', 'lvm:asdf:test'])

    """

    cmd = None
    options = []
    paths = []

    # parse
    for part in command:
        if cmd is None:
            cmd = part

        elif part.startswith('--'):
            options.append(part)
        
        elif part.startswith('-'):
            # XXX: parse out individual flags..?
            options.append(part)
        
        else:
            paths.append(part)

    return cmd, options, paths

def parse_server_command(command):
    """
        Parse rsync's internal --server command used when remoting over SSH.

        Returns:
            options:    list of --options and -opts from parse_options
            source:     source path if sender, or None
            dest:       dest path if receiver, or None
        
        Raises:
            CommandError
        
    """

    cmd, options, args = parse_command(command)

    if cmd.split('/')[-1] != 'rsync':
        raise CommandError("Invalid command: {cmd}".format(cmd=cmd))

    if len(args) != 2:
        raise CommandError("Invalid source/destination paths")
    
    if args[0] != '.':
        raise CommandError("Invalid source-path for server")

    path = args[1]

    # parse real source
    if not '--server' in options:
        raise CommandError("Missing --server")

    elif not '--sender' in options:
        # write
        source = None
        dest = path
        
    else:
        # read
        source = path
        dest = None

    # ok
    return options, source, dest
    
def parse_sender_command (command):
    """
        Parse rsync's internal --server --sender command used when reading over SSH.

        Returns:
            options:    list of --options and -opts from parse_options
            source:     source path
        
        Raises:
            CommandError
        
    """
    
    options, source, dest = parse_server_command(command)

    if dest:
        raise CommandError("Missing --sender")
    else:
        return options, source

def parse_source (path, restrict_paths=None, allow_remote=True, sudo=None, lvm_opts={}):
    """
        Parse an LVM source path, supporting custom extensions for LVM support.
            
            restrict_paths  - raise CommandError if source path is not under any of the given sources.
            allow_remote    - allow remote sources?
            lvm_opts        - **opts for LVMSource
    """

    if not path:
        raise SourceError("No path given")

    endslash = path.endswith('/')
        
    # normalize
    path = os.path.normpath(path)

    if endslash and not path.endswith('/'):
        # add it back in
        # happens for 'foo:/' and such
        path += '/'

    # verify path
    if restrict_paths:
        for restrict_path in restrict_paths:
            if path.startswith(restrict_path):
                # ok
                break
        else:
            # fail
            raise SourceError("Restricted path")

    if path.startswith('/'):
        # direct filesystem path
        log.debug("filesystem: %s", path)

        return Source(path,
                sudo    = sudo,
        )

    elif path.startswith('lvm:'):
        _, path = path.split(':', 1)

        # LVM VG
        try:
            if ':' in path:
                vg, path = path.split(':', 1)

                log.warn("old 'lvm:%s:%s' syntax; use 'lvm:%s/%s'", vg, path)

            elif '/' in path:
                vg, path = path.split('/', 1)

            else:
                raise ValueError("Invalid vg/lv separator")

        except ValueError as error:
            raise SourceError("Invalid lvm pseudo-path: {error}".format(error=error))

        # LVM LV, and path within LV
        if '/' in path:
            lv, path = path.split('/', 1)
        else:
            lv = path
            path = ''
       
        # lookup
        log.debug("LVM: %s/%s/%s", vg, lv, path)

        # open
        return LVMSource(vg, lv, path,
                sudo            = sudo,
                lvm_opts        = lvm_opts,
        )

    elif ':' in path:
        if not allow_remote:
            raise SourceError("Invalid remote path")

        # remote host
        log.debug("remote: %s", path)

        return Source(path,
                sudo        = sudo,
        )
       
    else:
        # invalid
        raise SourceError("Unknown path format")

