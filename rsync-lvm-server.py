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

LVM_VG              = 'asdf'

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

    def invoke (self, cmd, args) :
        """
            Invoke LVM command directly.

            Doesn't give any data on stdin, and keeps process stderr.
            Returns stdout.
        """
        
        log.debug("cmd={cmd}, args={args}".format(cmd=cmd, args=args))

        p = subprocess.Popen([self.LVM, cmd] + args, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

        # get output
        stdout, stderr = p.communicate(input=None)

        if p.returncode :
            raise Exception("LVM ({cmd}) failed: {returncode}".format(cmd=cmd, returncode=p.returncode))

        return stdout

    def command (self, cmd, *args, **opts) :
        """
            Invoke simple LVM command with options/arguments, and no output.
        """

        log.debug("cmd={cmd}, opts={opts}, args={args}".format(cmd=cmd, args=args, opts=opts))

        # process
        opts = [('--{opt}'.format(opt=opt), value if value != True else None) for opt, value in opts.iteritems() if value]

        # flatten
        opts = [str(opt_part) for opt_parts in opts for opt_part in opt_parts if opt_part]

        args = [str(arg) for arg in args if arg]

        # invoke
        self.invoke(cmd, opts + args)

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

        log.debug("got snapshot={0}".format(snapshot))
        yield snapshot

        log.debug("cleanup: {0}".format(snapshot))
        snapshot.close()

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

def main (argv) :
    # LVM VolumeGroup to manipulate
    lvm = LVM('asdf')

    # XXX: get LV from rsync command
    backup_lv = lvm.volume('test')

    # snapshot
    log.info("Open snapshot...")

    with lvm.snapshot(backup_lv, tag='backup') as snapshot:
        log.info("Snapshot opened: {name}".format(name=snapshot.lvm_path))

        # ...


        log.info("Done, cleaning up")

    return 1

if __name__ == '__main__' :
    import sys

    sys.exit(main(sys.argv))

