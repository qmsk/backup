"""
    Simple /sbin/lvm wrapper for handling snapshots.
"""

from pvl.backup.invoke import invoke, optargs, InvokeError

import contextlib
import os.path
import logging

log = logging.getLogger('pvl.backup.lvm')

class LVMError (Exception) :
    pass

class LVM (object) :
    """
        LVM VolumeGroup
    """

    # path to lvm2 binary
    LVM = '/sbin/lvm'

    
    # VG name
    name = None

    def __init__ (self, name) :
        self.name = name

    def lv_name (self, lv) :
        """
            vg/lv name.
        """

        return '{vg}/{lv}'.format(vg=self.name, lv=lv)

    def lv_path (self, lv) :
        """
            /dev/vg/lv path.
        """

        return '/dev/{vg}/{lv}'.format(vg=self.name, lv=lv)

    def command (self, cmd, *args, **opts) :
        """
            Invoke a command with options/arguments, given via Python arguments/keyword arguments
        """
        
        log.debug("{cmd} {opts} {args}".format(cmd=cmd, args=args, opts=opts))

        # invoke
        invoke(self.LVM, [cmd] + optargs(*args, **opts))

    def volume (self, name) :
        """
            Return an LVMVolume for given named LV.
        """

        return LVMVolume(self, name)

    @contextlib.contextmanager
    def snapshot (self, base, **kwargs) :
        """
            A Context Manager for handling an LVMSnapshot.

            See LVMSnapshot.create()

            with lvm.snapshot(lv) as snapshot : ...
        """

        log.debug("creating snapshot from {base}: {opts}".format(base=base, opts=kwargs))
        snapshot = LVMSnapshot.create(self, base, **kwargs)

        try :
            log.debug("got: {0}".format(snapshot))
            yield snapshot

        finally:
            # cleanup
            # XXX: there's some timing bug with an umount leaving the LV open, do we need to wait for it to get closed after mount?
            log.debug("cleanup: {0}".format(snapshot))
            snapshot.close()

    def __str__ (self) :
        return self.name

    def __repr__ (self) :
        return "LVM(name={name})".format(name=repr(self.name))

class LVMVolume (object) :
    """
        LVM Logical Volume.
    """

    # VG
    lvm = None

    # name
    name = None

    def __init__ (self, lvm, name) :
        self.lvm = lvm
        self.name = name

    @property
    def lvm_path (self) :
        return self.lvm.lv_name(self.name)

    @property
    def dev_path (self) :
        return self.lvm.lv_path(self.name)

    def verify_exists (self) :
        """
            Verify that the LV exists.

            Raises an LVMError otherwise.
        """

        # lvdisplay
        try :
            self.lvm.command('lvs', self.lvm_path)

        except InvokeError :
            raise LVMError("Unable to lvdisplay LV: {path}".format(path=self.lvm_path))

        # dev
        if not self.test_dev() :
            raise LVMError("LV dev does not exist: {path}".format(path=self.dev_path))

    def verify_missing (self) :
        """
            Verify that the LV does NOT exist.

            Raises an LVMError otherwise.
        """

        if self.test_dev() :
            raise Exception("LV already exists: {path}".format(path=self.dev_path))

    def test_dev (self) :
        """
            Tests for existance of device file, returning True/False.
        """

        return os.path.exists(self.dev_path)

    def __str__ (self) :
        return self.lvm_path

    def __repr__ (self) :
        return "LVMVolume(lvm={lvm}, name={name})".format(
                lvm     = repr(self.lvm),
                name    = repr(self.name),
        )

class LVMSnapshot (LVMVolume) :
    """
        LVM snapshot
    """
    
    # default snapshot size
    LVM_SNAPSHOT_SIZE   = '5G'

    # base lv
    base = None

    @classmethod
    def create (cls, lvm, base, tag, size=LVM_SNAPSHOT_SIZE) :
        """
            Create a new LVM snapshot of the given LV.
            
            Returns a (snapshot_name, dev_path) tuple.
        """

        # snapshot name
        name = '{name}-{tag}'.format(name=base.name, tag=tag)

        # snapshot instance
        snapshot = cls(lvm, base, name)

        ## verify
        # base should exist
        base.verify_exists()

        # snapshot should not
        snapshot.verify_missing()
        
        ## create
        snapshot.open()

        # verify
        if not snapshot.test_dev() :
            raise LVMError("Failed to find new snapshot LV device: {path}".format(path=snapshot.dev_path))

        # yay
        return snapshot

    def __init__ (self, lvm, base, name, size=LVM_SNAPSHOT_SIZE) :
        LVMVolume.__init__(self, lvm, name)

        self.base = base
        self.size = size

    def open (self) :
        """
            Create snapshot volume.
        """

        # create
        self.lvm.command('lvcreate', self.base.lvm_path, snapshot=True, name=self.name, size=self.size)

    def close (self) :
        """
            Remove snapshot volume.
        """

        # XXX: can't deactivate snapshot volume
        #self.lvm.command('lvchange', name, available='n')

        # XXX: risky!
        self.lvm.command('lvremove', '-f', self.lvm_path)

    def __repr__ (self) :
        return "LVMSnapshot(lvm={lvm}, base={base}, name={name})".format(
                lvm     = str(self.lvm),
                base    = str(self.base),
                name    = repr(self.name),
        )


