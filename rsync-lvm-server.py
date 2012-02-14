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

LVM                 = '/sbin/lvm'
LVM_VG              = 'asdf'
LVM_SNAPSHOT_SIZE   = '5G'

def lvm_name (vg, lv) :
    """
        LVM vg/lv name.
    """

    return '{vg}/{lv}'.format(vg=vg, lv=lv)

def lvm_path (vg, lv) :
    """
        Map LVM VG+LV to /dev path.
    """

    return '/dev/{vg}/{lv}'.format(vg=vg, lv=lv)

def lvm_invoke (cmd, args) :
    """
        Invoke LVM command directly.

        Doesn't give any data on stdin, and keeps process stderr.
        Returns stdout.
    """
    
    log.debug("cmd={cmd}, args={args}".format(cmd=cmd, args=args))

    p = subprocess.Popen([LVM, cmd] + args, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    # get output
    stdout, stderr = p.communicate(input=None)

    if p.returncode :
        raise Exception("LVM ({cmd}) failed: {returncode}".format(cmd=cmd, returncode=p.returncode))

    return stdout

def lvm (cmd, *args, **opts) :
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
    lvm_invoke(cmd, opts + args)

def lvm_snapshot_create (vg, lv, size=LVM_SNAPSHOT_SIZE) :
    """
        Create a new LVM snapshot of the given LV.
        
        Returns a (snapshot_name, dev_path) tuple.
    """

    # path to device
    lv_name = lvm_name(vg, lv)
    lv_path = lvm_path(vg, lv)

    # snapshot name
    snap_lv = '{lv}-backup'.format(lv=lv)
    snap_name = lvm_name(vg, snap_lv)
    snap_path = lvm_path(vg, snap_lv)

    # verify LV exists
    lvm('lvs', lv_name)
    
    if not os.path.exists(lv_path) :
        raise Exception("lvm_snapshot: source LV does not exist: {path}".format(path=lv_path))

    if os.path.exists(snap_path) :
        raise Exception("lvm_snapshot: target LV snapshot already exists: {path}".format(path=snap_path))

    # create
    lvm('lvcreate', lv_name, snapshot=True, name=snap_lv, size=size)

    # verify
    if not os.path.exists(snap_path) :
        raise Exception("lvm_snapshot: target LV snapshot did not appear: {path}".format(path=snap_path))

    # yay
    return snap_name, snap_path

def lvm_snapshot_remove (name) :
    """
        Remove given snapshot volume.
    """

    # XXX: can't deactivate snapshot volume
    #lvm('lvchange', name, available='n')

    # XXX: risky!
    lvm('lvremove', '-f', name)

@contextlib.contextmanager
def lvm_snapshot (*args, **kwargs) :
    """
        A Context Manager for handling an LVM snapshot.

        with lvm_snapshot(vg, lv) as (snapshot_name, snapshot_path) : ...
    """

    log.debug("creating snapshot: {0}".format(args))
    name, path = lvm_snapshot_create(*args, **kwargs)

    log.debug("got name={0}, path={1}".format(name, path))
    yield name, path

    log.debug("cleanup: {0}".format(name))
    lvm_snapshot_remove(name)

def main (argv) :
    # XXX: get LV from rsync command
    lvm_vg='asdf'
    backup_lv='test'

    # snapshot
    log.info("Open snapshot...")

    with lvm_snapshot(lvm_vg, backup_lv) as (snapshot_name, snapshot_path):
        log.info("Snapshot opened: {name}".format(name=snapshot_name))

        # ...


        log.info("Done, cleaning up")

    return 1

if __name__ == '__main__' :
    import sys

    sys.exit(main(sys.argv))

