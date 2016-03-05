import logging

from pvl import invoke

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
        stdout = invoke.command(ZFS, *args)
    except invoke.InvokeError as error:
        if error.exit == 1:
            raise ZFSError(error.stderr)
        elif error.exit == 2:
            raise CommandError(error.stderr)
        else:
            raise Error(error.stderr)

    return [line.strip().split('\t') for line in stdout]

class Filesystem (object):
    @classmethod
    def list(cls):
        for name, in zfs('list', '-H', '-tfilesystem', '-oname'):
            yield cls(name)

    def __init__(self, name, noop=None):
        self.name = str(name)
        self.noop = noop

        # cache
        self._snapshots = None

    def __str__(self):
        return self.name

    def check(self):
        """
            Raises ZFSError if unable to list the zfs filesystem.
        """

        zfs('list', '-tfilesystem', self.name)

    def get(self, property_name):
        """
            Get property value.

            Returns None if the property does not exist or is not set.
        """

        for fs, property_name, value, source in zfs('get', '-H', property_name, self.name):
            if value == '-' and source == '-':
                return None
            else:
                return value

    def set(self, property, value):
        if self.noop:
            return log.warning("zfs set %s=%s %s", property, value, self.name)
        else:
            zfs('set', '{property}={value}'.format(property=property, value=value), self.name)        

    @property
    def mountpoint(self):
        mountpoint = self.get('mountpoint')

        if mountpoint == 'none':
            return None
        else:
            return mountpoint

    def create(self, properties={}):
        options = ['-o{property}={value}'.format(property=key, value=value) for key, value in properties.iteritems() if value is not None]
        args = options + [self.name]
        
        if self.noop:
            return log.warning("zfs create %s", self.name)
        else:
            zfs('create', *args)

    def list_snapshots(self):
        for name, in zfs('list', '-H', '-tsnapshot', '-oname', '-r', self.name):
            snapshot = Snapshot.parse(name, noop=self.noop)

            log.debug("%s: snapshot %s", self, snapshot)

            yield snapshot

    @property
    def snapshots(self):
        if not self._snapshots:
            self._snapshots = {snapshot.name: snapshot for snapshot in self.list_snapshots()}

        return self._snapshots

    def snapshot(self, name):
        """
            Create and return a new Snapshot()

            Raises ZFSError if the snapshot already exists.
        """

        snapshot = Snapshot(self, name, noop=self.noop)

        if self.noop:
            log.warning("zfs snapshot %s", snapshot)
        else:
            zfs('snapshot', snapshot)
            
        if self._snapshots:
            self._snapshots[name] = snapshot

        return snapshot

    def bookmark(self, snapshot, bookmark):
        if self.noop:
            return log.warning("zfs bookmark %s@%s %s", snapshot, self.name, bookmark)
        else:
            zfs('bookmark', '{snapshot}@{filesystem}'.format(snapshot=snapshot, filesystem=self.name), bookmark)

class Snapshot (object):
    @classmethod
    def parse(cls, name, **opts):
        filesystem, snapshot = name.split('@', 1)

        return cls(filesystem, snapshot, **opts)

    def __init__ (self, filesystem, name, noop=None):
        self.filesystem = filesystem
        self.name = name
        self.noop = noop

    def __str__ (self):
        return '{filesystem}@{name}'.format(name=self.name, filesystem=self.filesystem)

    # XXX: invalidate ZFS._snapshots cache
    def destroy (self):
        if self.noop:
            log.warning("zfs destroy %s", self)
        else:
            zfs('destroy', self)
