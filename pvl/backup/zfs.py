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


def open(name, **opts):
    """
        Return Filesystem for pool/zfs name.
    """

    zfs = Filesystem(name, **opts)
    zfs.check()

    return zfs

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
        options = ['-o{property}={value}'.format(property=key, value=value) for key, value in properties.items() if value is not None]
        args = options + [self.name]
        
        if self.noop:
            return log.warning("zfs create %s", self.name)
        else:
            zfs('create', *args)

    def parse_snapshot(self, name, **opts):
        filesystem, snapshot = name.split('@', 1)

        return Snapshot(self, snapshot,
            noop    = self.noop,
            **opts
        )

    def list_snapshots(self, *properties):
        o = ','.join(('name', 'userrefs') + properties)

        for name, userrefs, *propvalues in zfs('list', '-H', '-tsnapshot', '-o' + o, '-r', self.name):
            snapshot = self.parse_snapshot(name,
                    userrefs    = int(userrefs),
                    properties  = {name: (None if value == '-' else value) for name, value in zip(properties, propvalues)},
            )

            log.debug("%s: snapshot %s", self, snapshot)

            yield snapshot

    @property
    def snapshots(self):
        if not self._snapshots:
            self._snapshots = {snapshot.name: snapshot for snapshot in self.list_snapshots()}

        return self._snapshots

    def snapshot(self, name, properties=None):
        """
            Create and return a new Snapshot()

            Raises ZFSError if the snapshot already exists.
        """
        
        options = ['-o{property}={value}'.format(property=key, value=value) for key, value in properties.items() if value is not None]

        snapshot = Snapshot(self, name, properties, noop=self.noop)
        args = options + [snapshot]

        if self.noop:
            log.warning("zfs snapshot %s", snapshot)
        else:
            zfs('snapshot', *args)
            
        if self._snapshots:
            self._snapshots[name] = snapshot

        return snapshot

    def holds (self, *snapshots):
        """
            List snapshot holds.

            Yields (Snapshot, hold_tag).
        """

        if not snapshots:
            snapshots = list(self.list_snapshots())

        for name, tag, timestamp in zfs('holds', '-H', *snapshots):
            snapshot = self.parse_snapshot(name.strip())

            yield snapshot, tag.strip()

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

    def __init__ (self, filesystem, name, properties={}, noop=None, userrefs=None):
        self.filesystem = filesystem
        self.name = name
        self.properties = properties

        self.noop = noop
        self.userrefs = userrefs

    def __str__ (self):
        return '{filesystem}@{name}'.format(name=self.name, filesystem=self.filesystem)

    def __getitem__ (self, name):
        return self.properties[name]

    # XXX: invalidate ZFS._snapshots cache
    def destroy (self):
        if self.noop:
            log.warning("zfs destroy %s", self)
        else:
            zfs('destroy', self)

    def hold (self, tag):
        zfs('hold', tag, self)

    def holds (self):
        for name, tag, timestamp in zfs('holds', self):
            yield tag

    def release(self, tag):
        zfs('release', tag, self)
