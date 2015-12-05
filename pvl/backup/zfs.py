import logging

from pvl.backup import invoke

log = logging.getLogger('pvl.backup.zfs')

ZFS = '/sbin/zfs'

class Error (Exception):
    pass

class ZFSError (Error):
    """
        An error occured
    """

    pass

class CommandError (Error):
    """
        Invalid command line options were specified
    """

    pass

def zfs(*args):
    try:
        out = invoke.invoke(ZFS, list(args))
    except invoke.InvokeError as error:
        if error.exit == 1:
            raise ZFSError(error.stderr)
        elif error.exit == 2:
            raise CommandError(error.stderr)
        else:
            raise Error(error.stderr)

    return [line.strip().split('\t') for line in out.splitlines()]

class Filesystem (object):
    @classmethod
    def list(cls):
        for name, in zfs('list', '-H', '-tfilesystem', '-oname'):
            yield cls(name)

    def __init__(self, name):
        self.name = str(name)

    def __str__(self):
        return self.name

    @property
    def exists(self):
        try:
            zfs('list', '-tfilesystem', self.name)
        except ZFSError as error:
            return False
        else:
            return True

    def get(self, property_name):
        for fs, property_name, value, source in zfs('get', '-H', property_name, self.name):
            return value

    @property
    def mountpoint(self):
        mountpoint = self.get('mountpoint')

        if mountpoint == 'none':
            return None
        else:
            return mountpoint

    def create(self):
        zfs('create', self.name)

    def snapshot(self, name):
        zfs('snapshot', '{filesystem}@{snapname}'.format(filesystem=self.name, snapname=name))

    def list_snapshots(self):
        for name in zfs('list', '-H', '-tsnapshot', '-oname', '-r', self.name):
            filesystem, snapshot = name.split('@', 1)

            yield snapshot

