"""
    rsync handling.

    Apologies for the 'RSync' nomenclature
"""

from pvl.backup.invoke import invoke
from pvl.backup.lvm import LVM, LVMVolume, LVMSnapshot
from pvl.backup.mount import mount

import shlex
import os.path

import logging

log = logging.getLogger('pvl.backup.rsync')


class RSyncCommandFormatError (Exception) :
    """
        Improper rsync command
    """

    pass

class RSyncSource (object) :
    RSYNC = '/usr/bin/rsync'

    def _execute (self, options, path) :
        """
            Underlying rsync just reads from filesystem.
        """

        invoke(self.RSYNC, options + [path, '.'], data=False)

class RSyncFSSource (RSyncSource) :
    """
        Normal filesystem backup.
    """

    def __init__ (self, path) :
        RSyncSource.__init__(self)

        self.path = path

    def execute (self, options) :
        return self._execute(options, self.path)

class RSyncLVMSource (RSyncSource) :
    """
        Backup LVM LV by snapshotting + mounting it.
    """

    def __init__ (self, volume) :
        RSyncSource.__init__(self)

        self.volume = volume
 
    def execute (self, options) :
        """
            Snapshot, mount, execute
        """
        
        # backup target from LVM command
        lvm = self.volume.lvm
        volume = self.volume

        # XXX: generate
        path = '/mnt'

        # snapshot
        log.info("Open snapshot...")

        # XXX: generate snapshot nametag to be unique?
        with lvm.snapshot(volume, tag='backup') as snapshot:
            log.info("Snapshot opened: %s", snapshot.lvm_path)

            # mount
            log.info("Mounting snapshot: %s -> %s", snapshot, path)

            with mount(snapshot.dev_path, path) as mountpoint:
                log.info("Mounted snapshot: %s", mountpoint)
                
                # rsync!
                log.info("Running rsync: ...")

                return self._execute(options, mountpoint.path)

            # cleanup
        # cleanup
 
def parse_command (command, restrict_server=True, restrict_readonly=True) :
    """
        Parse given rsync server command into bits. 

            command             - the command-string sent by rsync
            restrict_server     - restrict to server-mode
            restrict_readonly   - restrict to read/send-mode
        
        Returns:

            (cmd, options, source, dest)
    """

    # split
    parts = shlex.split(command)

    cmd = None
    options = []
    source = None
    dest = None

    # parse
    for part in parts :
        if cmd is None :
            cmd = part

        elif part.startswith('-') :
            options.append(part)

        elif source is None :
            source = part

        elif dest is None :
            dest = part

    # options
    have_server = ('--server' in options)
    have_sender = ('--sender' in options)

    # verify
    if not have_server :
        raise RSyncCommandFormatError("Missing --server")

    if restrict_readonly and not have_sender :
        raise RSyncCommandFormatError("Missing --sender for readonly")

    # parse path
    if have_sender :
        # read
        # XXX: which way does the dot go?
        if source != '.' :
            raise RSyncCommandFormatError("Invalid dest for sender")
        
        path = dest

    else :
        # write
        if source != '.' :
            raise RSyncCommandFormatError("Invalid source for reciever")

        path = dest

    # ok
    return cmd, options, source, dest

      
def parse_source (path, restrict_path=False) :
    """
        Figure out source to rsync from, based on pseudo-path given in rsync command.
    """
        
    # normalize
    path = os.path.normpath(path)

    # verify path
    if restrict_path :
        if not path.startswith(restrict_path) :
            raise RSyncCommandFormatError("Restricted path ({restrict})".format(restrict=restrict_path))

    if path.startswith('/') :
        # direct filesystem path
        # XXX: how to handle=
        log.info("filesystem: %s", path)

        return RSyncFSSource(path)

    elif path.startswith('lvm:') :
        # LVM LV
        try :
            lvm, vg, lv = path.split(':')

        except ValueError, e:
            raise RSyncCommandFormatError("Invalid lvm pseudo-path: {error}".format(error=e))
        
        # XXX: validate

        log.info("LVM: %s/%s", vg, lv)

        # open
        lvm = LVM(vg)
        volume = lvm.volume(lv)

        return RSyncLVMSource(volume)
       
    else :
        # invalid
        raise RSyncCommandFormatError("Unrecognized backup path")


