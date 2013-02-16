"""
    rsync handling.

    Apologies for the 'RSync' nomenclature
"""

from pvl.backup.lvm import LVM, LVMVolume, LVMSnapshot
from pvl.backup.mount import mount
from pvl.backup import invoke

import os.path

import logging

log = logging.getLogger('pvl.backup.rsync')

RSYNC = '/usr/bin/rsync'

def rsync (source, dest, **opts) :
    """
        Run rsync.

        Raises RsyncError if rsync fails.

        XXX: never used anywhere?
    """

    try :
        invoke.command(RSYNC, source, dest, **opts)

    except invoke.InvokeError as ex :
        raise RsyncError(ex)

class RSyncCommandFormatError (Exception) :
    """
        Improper rsync command/source.
    """

    pass

class RsyncError (Exception) :
    """
        Rsync command invocation failed.
    """
    
    pass


class RSyncServer (object) :
    """
        rsync server-mode execution.
    """

    def _execute (self, options, srcdst, path, sudo=False) :
        """
            Underlying rsync just reads from filesystem.

                options     - list of rsync options
                srcdst      - the (source, dest) pair with None placeholder, as returned by parse_command
                path        - the real path to replace None with

                sudo        - execute rsync using sudo
        """
    
        # one of this will be None
        src, dst = srcdst

        # replace None -> path
        src = src or path
        dst = dst or path

        log.info("rsync %s %s %s", ' '.join(options), src, dst)

        try :
            # invoke directly; no option-handling, nor stdin/out redirection
            invoke.invoke(RSYNC, options + [ src, dst ], data=False, sudo=sudo)

        except invoke.InvokeError as ex :
            raise RsyncError(ex)

class RSyncFSServer (RSyncServer) :
    """
        Normal filesystem backup.
    """

    def __init__ (self, path) :
        RSyncServer.__init__(self)

        self.path = path

    def execute (self, options, srcdst, **opts) :
        """
                options     - list of rsync options
                srcdst      - the (source, dest) pair with None placeholder, as returned by parse_command
        """

        return self._execute(options, srcdst, self.path, **opts)

    def __str__ (self) :
        return self.path
    
class RSyncRemoteServer (RSyncServer) :
    """
        Remote filesystem backup.
    """

    def __init__ (self, host, path) :
        """
            host        - remote SSH host
            path        - remote path
        """

        RSyncServer.__init__(self)
    
        # glue
        self.path = host + ':' + path

    def execute (self, options, srcdst, **opts) :
        """
                options     - list of rsync options
                srcdst      - the (source, dest) pair with None placeholder, as returned by parse_command
        """

        return self._execute(options, srcdst, self.path, **opts)

    def __str__ (self) :
        return self.path
 
class RSyncLVMServer (RSyncServer) :
    """
        Backup LVM LV by snapshotting + mounting it.
    """

    def __init__ (self, vg, lv, sudo=None, **opts) :
        """
            **opts      - options for LVM.snapshot
        """

        RSyncServer.__init__(self)
        
        # lvm
        self.lvm = LVM(vg, sudo=sudo)
        self.volume = self.lvm.volume(lv)

        self.sudo = sudo
        self.snapshot_opts = opts
 
    def execute (self, options, srcdst, sudo=False, **opts) :
        """
            Snapshot, mount, execute

                options     - list of rsync options
                srcdst      - the (source, dest) pair with None placeholder, as returned by parse_command
        """
        
        # backup target from LVM command
        lvm = self.volume.lvm
        volume = self.volume

        # snapshot
        log.info("Open snapshot: %s", volume)

        # XXX: generate snapshot nametag to be unique?
        with lvm.snapshot(volume, tag='backup', **self.snapshot_opts) as snapshot:
            # mount
            log.info("Mounting snapshot: %s", snapshot)

            with mount(snapshot.dev_path, name_hint=('lvm_' + snapshot.name + '_'), readonly=True, sudo=sudo) as mountpoint:
                # rsync!
                log.info("Running rsync: %s", mountpoint)

                # with trailing slash
                return self._execute(options, srcdst, mountpoint.path + '/', sudo=sudo, **opts)

            # cleanup
        # cleanup
 
    def __str__ (self) :
        return 'lvm:{volume}'.format(volume=self.volume)
 
def parse_command (command_parts, restrict_server=True, restrict_readonly=True) :
    """
        Parse given rsync server command into bits. 

            command_parts       - the command-list sent by rsync
            restrict_server     - restrict to server-mode
            restrict_readonly   - restrict to read/send-mode
        
        In server mode, source will always be '.', and dest the source/dest.
        
        Returns:

            (cmd, options, path, (source, dest))
            
            options         -> list of -options
            path            -> real source path
            (source, dest)  -> combination of None for path, and the real source/dest

    """

    cmd = None
    options = []
    source = None
    dest = None

    # parse
    for part in command_parts :
        if cmd is None :
            cmd = part

        elif part.startswith('-') :
            options.append(part)

        elif source is None :
            source = part

        elif dest is None :
            dest = part

    log.debug("%s: %s", cmd, options)

    # options
    have_server = ('--server' in options)
    have_sender = ('--sender' in options)

    # verify
    if restrict_server and not have_server :
        raise RSyncCommandFormatError("Missing --server")

    if restrict_readonly and not have_sender :
        raise RSyncCommandFormatError("Missing --sender for readonly")

    if not source :
        raise RSyncCommandFormatError("Missing source path")
        
    if not dest:
        raise RSyncCommandFormatError("Missing dest path")


    # parse real source
    if have_sender :
        # read; first arg will always be .
        if source != '.' :
            raise RSyncCommandFormatError("Invalid dest for sender")

        path = dest
        dest = None
        
        log.debug("using server/sender source path: %s", path)

    elif have_server :
        # write
        if source != '.' :
            raise RSyncCommandFormatError("Invalid source for reciever")

        path = dest
        dest = None
        
        log.debug("using server dest path: %s", path)

    else :
        # local src -> dst
        path = source
        source = None

        log.debug("using local src path: %s -> %s", path, dest)

    # ok
    return cmd, options, path, (source, dest)
      
def parse_source (path, restrict_paths=None, allow_remote=True, lvm_opts={}) :
    """
        Figure out source to rsync from, based on pseudo-path given in rsync command.
            
            restrict_paths  - raise RsyncCommandFormatError if source path is not under any of the given sources.
            allow_remote    - allow remote backups?
            lvm_opts        - dict of **opts for RSyncLVMServer
    """

    endslash = path.endswith('/')
        
    # normalize
    path = os.path.normpath(path)

    if endslash and not path.endswith('/') :
        # add it back in
        # happens for 'foo:/' and such
        path += '/'

    # verify path
    if restrict_paths :
        for restrict_path in restrict_paths :
            if path.startswith(restrict_path) :
                # ok
                break
        else :
            # fail
            raise RSyncCommandFormatError("Restricted path".format())

    if path.startswith('/') :
        # direct filesystem path
        log.debug("filesystem: %s", path)

        return RSyncFSServer(path)

    elif path.startswith('lvm:') :
        _, lvm = path.split(':', 1)

        # LVM LV
        try :
            if ':' in lvm :
                vg, lv = lvm.split(':', 1)

                log.warn("old lvm: syntax: lvm:%s; use: lvm:%s/%s", path, vg, lv)

            elif '/' in lvm:
                vg, lv = lvm.split('/', 1)

            else :
                raise RSyncCommandFormatError("Invalid lvm pseudo-path: {lvm}: unrecognized vg/lv separator".format(lvm=lvm))

        except ValueError, e:
            raise RSyncCommandFormatError("Invalid lvm pseudo-path: {lvm}: {error}".format(lvm=lvm, error=e))
        
        # XXX: validate?
        log.debug("LVM: %s/%s", vg, lv)

        # open
        return RSyncLVMServer(vg, lv, **lvm_opts)

    elif ':' in path and allow_remote :
        host, path = path.split(':', 1)

        # remote host
        log.debug("remote: %s:%s", host, path)

        return RSyncRemoteServer(host, path)
       
    else :
        # invalid
        raise RSyncCommandFormatError("Unrecognized backup path: {path}".format(path=path))

