#!/usr/bin/python

import subprocess
import os, os.path

import contextlib
import logging

logging.basicConfig(
    format  = '%(processName)s: %(name)s: %(levelname)s %(funcName)s : %(message)s',
    level   = logging.DEBUG,
)
log = logging.getLogger()

def invoke (cmd, args) :
    """
        Invoke a command directly.

        Doesn't give any data on stdin, and keeps process stderr.
        Returns stdout.
    """
    
    log.debug("cmd={cmd}, args={args}".format(cmd=cmd, args=args))

    p = subprocess.Popen([cmd] + args, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    # get output
    stdout, stderr = p.communicate(input=None)

    if p.returncode :
        raise Exception("{cmd} failed: {returncode}".format(cmd=cmd, returncode=p.returncode))

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
            log.debug("got snapshot={0}".format(snapshot))
            yield snapshot

        finally:
            # cleanup
            log.debug("cleanup: {0}".format(snapshot))
            snapshot.close()

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

        # snapshot
        snapshot = cls(lvm, base, name)

        # verify LV exists
        lvm.command('lvs', base.lvm_path)
        
        if not os.path.exists(base.dev_path) :
            raise Exception("lvm_snapshot: source LV does not exist: {path}".format(path=base.dev_path))

        if os.path.exists(snapshot.dev_path) :
            raise Exception("lvm_snapshot: target LV snapshot already exists: {path}".format(path=snapshot.dev_path))

        # create
        snapshot.open()

        # verify
        if not os.path.exists(snapshot.dev_path) :
            raise Exception("lvm_snapshot: target LV snapshot did not appear: {path}".format(path=snapshot.dev_path))

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


class MountError (Exception) :
    pass

class Mount (object) :
    """
        Trivial filesystem mounting
    """

    MOUNT   = '/bin/mount'
    UMOUNT  = '/bin/umount'


    def __init__ (self, dev, mnt, readonly=False) :
        """
            dev         - device path
            mnt         - mount path
            readonly    - mount readonly
        """

        self.dev = dev
        self.mnt = mnt
        self.readonly = readonly

    @property
    def path (self) :
        return self.mnt

    def options (self) :
        """
            Mount options as a comma-separated string.
        """

        options = [
                ('ro' if self.readonly else None),
        ]

        return ','.join(option for option in options if option)

    def open (self) :
        """
            Mount
        """

        # check
        if not os.path.isdir(self.mnt) :
            raise MountError("Mountpoint is not a directory: {mnt}".format(mnt=self.mnt))

        if os.path.ismount(self.mnt) :
            raise MountError("Mountpoint is already mounted: {mnt}".format(mnt=self.mnt))

        if not os.path.exists(self.dev) :
            raise MountError("Device does not exist: {dev}".format(dev=self.dev))

        # mount
        command(self.MOUNT, self.dev, self.mnt, options=self.options())

    def close (self) :
        """
            Un-mount
        """

        # check
        if not os.path.ismount(self.mnt):
            raise MountError("Mountpoint is not mounted: {mnt}".format(mnt=self.mnt))

        # umount
        command(self.UMOUNT, self.mnt)

@contextlib.contextmanager
def mount (dev, mnt, **kwargs) :
    """
        Use a temporary mount:

        with mount('/dev/...', '/mnt', readonly=True) as mount:
            ...
    """

    mount = Mount(dev, mnt, **kwargs)

    # open
    log.debug("open: %s", mount)
    mount.open()

    try :
        log.debug("got: %s", mount)
        yield mount

    finally:
        # cleanup
        log.debug("cleanup: %s", mount)
        mount.close()

def main (argv) :
    # LVM VolumeGroup to manipulate
    lvm = LVM('asdf')

    # XXX: get backup target from rsync command
    backup_lv = lvm.volume('test')
    backup_path = '/mnt'

    # snapshot
    log.info("Open snapshot...")

    with lvm.snapshot(backup_lv, tag='backup') as snapshot:
        log.info("Snapshot opened: {name}".format(name=snapshot.lvm_path))

        # mount
        log.info("Mounting snapshot: %s -> %s", snapshot, backup_path)

        with mount(snapshot.dev_path, backup_path) as mountpoint:
            log.info("Mounted snapshot: %s", mountpoint)

            # ...
            print command('ls', '-l', mountpoint.path)

    return 1

if __name__ == '__main__' :
    import sys

    sys.exit(main(sys.argv))

