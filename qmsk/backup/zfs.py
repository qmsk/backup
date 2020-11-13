import contextlib
import datetime
import logging

import qmsk.invoke

log = logging.getLogger('qmsk.backup.zfs')

ZFS = '/sbin/zfs'

SNAPSHOT_PREFIX = 'qmsk-backup'
PROPERTY_MODULE = 'qmsk.backup'

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

def zfs(*args, invoker=qmsk.invoke.Invoker(), **opts):
    try:
        stdout = invoker.invoke(ZFS, qmsk.invoke.optargs(*args), **opts)
    except qmsk.invoke.InvokeError as error:
        if error.exit == 1:
            raise ZFSError(error.stderr)
        elif error.exit == 2:
            raise CommandError(error.stderr)
        else:
            raise Error(error.stderr)

    if stdout is None:
        return None
    else:
        return [line.strip().split('\t') for line in stdout]

@contextlib.contextmanager
def zfs_stream(*args, invoker=qmsk.invoke.Invoker(), **opts):
    try:
        with invoker.stream(ZFS, qmsk.invoke.optargs(*args), **opts) as stream:
            yield stream
    except qmsk.invoke.InvokeError as error:
        if error.exit == 1:
            raise ZFSError(error.stderr)
        elif error.exit == 2:
            raise CommandError(error.stderr)
        else:
            raise Error(error.stderr)

@contextlib.contextmanager
def snapshot(zfs, snapshot_name=None, prefix=SNAPSHOT_PREFIX, **opts):
    """
        With ZFS snapshot.

        Generates a temporary qmsk-backup_* snapshot by default.
    """

    if snapshot_name is None:
        snapshot_name = '{prefix}_{timestamp}'.format(prefix=prefix, timestamp=datetime.datetime.now().isoformat())

    snapshot = zfs.snapshot(snapshot_name, **opts)

    try:
        yield snapshot
    finally:
        snapshot.destroy()

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

    def __init__(self, name, noop=None, invoker=None):
        self.name = str(name)
        self.noop = noop
        self.invoker = invoker

        # cache
        self._snapshots = None

    def __str__(self):
        return self.name

    def zfs_read (self, *args, **opts):
        """
            ZFS wrapper for sudo+noop

            Run read-only commands that are also executed when --noop.
        """

        return zfs(*args, invoker=self.invoker, **opts)

    def zfs_stream (self, *args, **opts):
        """
            ZFS wrapper for sudo+noop

            Run read-only commands that are also executed when --noop.

            Contextmanager yielding stdout stream.
        """

        return zfs_stream(*args, invoker=self.invoker, **opts)

    def zfs_write (self, *args, **opts):
        """
            ZFS wrapper for sudo+noop

            Run commands that are not executed when --noop.
        """

        if self.noop:
            return log.warning("noop: zfs %s", args)
        else:
            return zfs(*args, invoker=self.invoker, **opts)

    def check(self):
        """
            Raises ZFSError if unable to list the zfs filesystem.
        """

        self.zfs_read('list', '-tfilesystem', self.name)

    def get(self, property_name):
        """
            Get property value.

            Returns None if the property does not exist or is not set.
        """

        for fs, property_name, value, source in self.zfs_read('get', '-H', property_name, self.name):
            if value == '-' and source == '-':
                return None
            else:
                return value

    def set(self, property, value):
        self.zfs_write('set', '{property}={value}'.format(property=property, value=value), self.name)

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

        self.zfs_write('create', *args)

    def parse_snapshot(self, name, **opts):
        filesystem, snapshot = name.split('@', 1)

        return Snapshot(self, snapshot,
            noop    = self.noop,
            **opts
        )

    def list_snapshots(self, *properties):
        o = ','.join(('name', 'userrefs') + properties)

        for name, userrefs, *propvalues in self.zfs_read('list', '-H', '-tsnapshot', '-o' + o, '-r', self.name):
            snapshot = self.parse_snapshot(name,
                    userrefs    = int(userrefs),
                    properties  = {name: (None if value == '-' else value) for name, value in zip(properties, propvalues)},
            )

            log.debug("%s: snapshot %s", self, snapshot)

            yield snapshot

    def last_snapshot(self):
        """
            Return the most recent Snapshot.

            Raises ZFSError if there are no snapshots.
        """

        snapshot = None

        for snapshot in self.list_snapshots():
            continue

        if snapshot:
            return snapshot
        else:
            raise ZFSError("No snapshots")

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

        self.zfs_write('snapshot', *args)

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

        for name, tag, timestamp in self.zfs_read('holds', '-H', *snapshots):
            snapshot = self.parse_snapshot(name.strip())

            yield snapshot, tag.strip()

    def bookmark(self, snapshot_name, bookmark):
        self.zfs_write('bookmark', '{snapshot}@{filesystem}'.format(snapshot=snapshot_name, filesystem=self.name), bookmark)

    def destroy_bookmark(self, bookmark):
        self.zfs_write('destroy', '{filesystem}#{bookmark}'.format(filesystem=self.name, bookmark=bookmark))

    def receive(self, snapshot_name=None, *, force=None, properties={}, stdin=True):
        if snapshot_name:
            target = '{zfs}@{snapshot}'.format(zfs=self, snapshot=snapshot_name)
        else:
            target = self

        options = ['-o{property}={value}'.format(property=key, value=value) for key, value in properties.items() if value is not None]

        # TODO: parse -v output to determine the received snapshot name?
        #   receiving full stream of test1/test@1 into test2/backup/test@1
        #   received 42,5KB stream in 1 seconds (42,5KB/sec)
        self.zfs_write('receive', '-F' if force else None, *options, target, stdin=stdin)

        if snapshot_name:
            return Snapshot(self, snapshot_name)
        else:
            # XXX: parse received snapshot name, if needed?
            pass

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


    @property
    def mountpoint(self):
        mountpoint = self.filesystem.mountpoint

        if mountpoint:
            return '{mountpoint}/.zfs/snapshot/{snapshot}'.format(mountpoint=mountpoint, snapshot=self.name)
        else:
            return None

    # TODO: default to properties=None to explode if not set?
    def __getitem__ (self, name):
        return self.properties[name]

    def get(self, property_name):
        """
            Get property value.

            Returns None if the property does not exist or is not set.
        """

        for fs, property_name, value, source in self.filesystem.zfs_read('get', '-H', property_name, str(self)):
            if value == '-' and source == '-':
                return None
            else:
                return value

    def set(self, property, value):
        self.filesystem.zfs_write('set', '{property}={value}'.format(property=property, value=value), str(self))

    # XXX: invalidate ZFS._snapshots cache
    def destroy (self):
        self.filesystem.zfs_write('destroy', self)

    def bookmark(self, bookmark):
        self.filesystem.zfs_write('bookmark', self, str(self.filesystem) + '#' + bookmark)

    def hold (self, tag):
        self.filesystem.zfs_write('hold', tag, self)

    def holds (self):
        for name, tag, timestamp in self.filesystem.zfs_read('holds', self):
            yield tag

    def release(self, tag):
        self.filesystem.zfs_write('release', tag, self)

    def _send_options(self, incremental=None, full_incremental=None, properties=False, replication_stream=None, raw=None, compressed=None, large_block=None, dedup=None):
        """
            incremental: Snapshot, None     - send incremental from given snapshot
            properties: bool                - send ZFS properties
        """

        return (
            '--raw' if raw else None, # passed as first argument to allow whitelisting `sudo /usr/sbin/zfs send --raw *`
            '-c' if compressed else None,
            '-L' if large_block else None,
            '-D' if dedup else None,
            '-R' if replication_stream else None,
            '-p' if properties else None,
            '-i' + str(incremental) if incremental else None,
            '-I' + str(full_incremental) if full_incremental else None,
            self,
        )

    def send(self, stdout=True, **options):
        """
            Write out ZFS contents of this snapshot to stdout.
        """

        return self.filesystem.zfs_read('send', *self._send_options(**options), stdout=stdout)

    def stream_send(self, **options):
        """
            Returns a context manager for the send stream.
        """

        return self.filesystem.zfs_stream('send', *self._send_options(**options))

class Source:
    """
        ZFS sender, either local or remote over SSH
    """

    @classmethod
    def config(cls, source, invoker_options={}, ssh_options={}):
        if ':' in source:
            ssh_host, zfs_name = source.split(':', 1)

            invoker = qmsk.invoke.SSHInvoker(ssh_host, **ssh_options)
        else:
            zfs_name = source

            invoker = qmsk.invoke.Invoker(**invoker_options)

        return cls(source, invoker, zfs_name)

    def __init__(self, source, invoker: qmsk.invoke.Invoker, zfs_name: str):
        self.source = source
        self.invoker = invoker
        self.zfs_name = zfs_name

    def __str__(self):
        return self.source

    def stream_send(self, raw=None, compressed=None, large_block=None, dedup=None, incremental=None, full_incremental=None, properties=False, replication_stream=None, snapshot=None, bookmark=None, purge_bookmark=None):
        """
            Returns a context manager for the send stream.
        """

        name = self.zfs_name

        if snapshot:
            name += '@' + snapshot

        return self.invoker.stream('zfs', ['send'] + qmsk.invoke.optargs(
            '-w' if raw else None,
            '-c' if compressed else None,
            '-L' if large_block else None,
            '-D' if dedup else None,
            '-R' if replication_stream else None,
            '-p' if properties else None,
            '-i' + str(incremental) if incremental else None,
            '-I' + str(full_incremental) if full_incremental else None,

            name,

            # custom qmsk.backup-ssh-command extensions
            bookmark = bookmark,
            purge_bookmark = purge_bookmark,
        ))

    def _receive_opts(self, snapshot=None, force=None):
        name = self.zfs_name

        if snapshot:
            name += '@' + snapshot

        return qmsk.invoke.optargs(
            '-F' if force else None,

            name,
        )

    def receive(self, stdin, **options):
        """
            Invoke receive with given stdin stream.
        """

        return self.invoker.invoke('zfs', ['receive'] + self._receive_opts(**options), stdin=stdin)
