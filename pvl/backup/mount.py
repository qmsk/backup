"""
    Mount filesystems.
"""

from pvl.backup.invoke import command

import contextlib
import os.path
import logging

log = logging.getLogger('pvl.backup.mount')


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

    def __repr__ (self) :
        return "Mount(dev={dev}, mnt={mnt})".format(
                dev     = repr(self.dev),
                mnt     = repr(self.mnt),
        )

    def __str__ (self) :
        return self.mnt

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


