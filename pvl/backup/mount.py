"""
    Mount filesystems.
"""

from pvl.backup.invoke import invoke, optargs, command

import contextlib
import os, os.path
import logging
import tempfile

log = logging.getLogger('pvl.backup.mount')


class MountError (Exception) :
    pass

class Mount (object) :
    """
        Trivial filesystem mounting
    """

    MOUNT   = '/bin/mount'
    UMOUNT  = '/bin/umount'


    def __init__ (self, dev, mnt, readonly=False, sudo=None) :
        """
            dev         - device path
            mnt         - mount path
            readonly    - mount readonly
            sudo        - invoke sudo
        """

        self.dev = dev
        self.mnt = mnt
        self.readonly = readonly
        self.sudo = sudo

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

        if self.is_mounted() :
            raise MountError("Mountpoint is already mounted: {mnt}".format(mnt=self.mnt))

        if not os.path.exists(self.dev) :
            raise MountError("Device does not exist: {dev}".format(dev=self.dev))

        # mount
        invoke(self.MOUNT, optargs(self.dev, self.mnt, options=self.options()), sudo=self.sudo)

    def is_mounted (self) :
        """
            Test if the given mountpoint is mounted.
        """
        
        # workaround http://bugs.python.org/issue2466
        if os.path.exists(self.mnt) and not os.path.exists(os.path.join(self.mnt, '.')) :
            # this is a sign of a mountpoint that we do not have access to
            return True

        return os.path.ismount(self.mnt)

    def close (self) :
        """
            Un-mount
        """

        # check
        if not self.is_mounted() :
            raise MountError("Mountpoint is not mounted: {mnt}".format(mnt=self.mnt))

        # umount
        invoke(self.UMOUNT, optargs(self.mnt), sudo=self.sudo)

    def __repr__ (self) :
        return "Mount(dev={dev}, mnt={mnt})".format(
                dev     = repr(self.dev),
                mnt     = repr(self.mnt),
        )

    def __str__ (self) :
        return self.mnt

@contextlib.contextmanager
def mount (dev, mnt=None, name_hint='tmp', **kwargs) :
    """
        Use a temporary mount:

        with mount('/dev/...', readonly=True) as mount:
            ...

        Mounts at the given mountpoint path, or a tempdir
    """

    if mnt is None :
        mnt = tmpdir = tempfile.mkdtemp(suffix='.mnt', prefix=name_hint)

        log.debug("using tmp mnt: %s", tmpdir)

    else :
        tmpdir = None
        
    log.debug("mount: %s -> %s", dev, mnt)

    # with tempdir
    try :
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

            try :
                mount.close()

            except Exception as ex :
                log.warning("cleanup: %s: %s", mount, ex)

    finally:
        if tmpdir :
            # cleanup
            log.debug("cleanup tmp mnt: %s", tmpdir)
            os.rmdir(tmpdir)

