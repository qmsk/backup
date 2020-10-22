"""
    rsync handling.

    Apologies for the 'RSync' nomenclature
"""

import contextlib
import datetime
import logging
import os.path
import qmsk.backup.mount
import qmsk.invoke
import re

from qmsk.backup.lvm import LVM, LVMVolume, LVMSnapshot
from qmsk.backup import zfs

log = logging.getLogger('qmsk.backup.rsync')

RSYNC = '/usr/bin/rsync'

STATS_REGEX = re.compile(r'(.+?): ([0-9.]+)(?: (.+))?')

def parse_stats (stdout):
    """
        Parse rsync --stats output.

        Returns a { string: int/float } of values

        >>> lines = '''
        ... Number of files: 2 (reg: 1, dir: 1)
        ... Number of created files: 0
        ... Number of deleted files: 0
        ... Number of regular files transferred: 0
        ... Total file size: 29 bytes
        ... Total transferred file size: 0 bytes
        ... Literal data: 0 bytes
        ... Matched data: 0 bytes
        ... File list size: 0
        ... File list generation time: 0.001 seconds
        ... File list transfer time: 0.000 seconds
        ... Total bytes sent: 65
        ... Total bytes received: 19
        ...
        ... sent 65 bytes  received 19 bytes  168.00 bytes/sec
        ... total size is 29  speedup is 0.35
        ... '''.splitlines()
        >>> for n, v in parse_stats(lines): print((n, v))
        ('Number of files', 2)
        ('Number of files: reg', 1)
        ('Number of files: dir', 1)
        ('Number of created files', 0)
        ('Number of deleted files', 0)
        ('Number of regular files transferred', 0)
        ('Total file size', 29)
        ('Total transferred file size', 0)
        ('Literal data', 0)
        ('Matched data', 0)
        ('File list size', 0)
        ('File list generation time', 0.001)
        ('File list transfer time', 0.0)
        ('Total bytes sent', 65)
        ('Total bytes received', 19)
    """

    for line in stdout:
        match = STATS_REGEX.match(line)

        if not match:
            continue

        name = match.group(1)
        value = match.group(2)
        unit = match.group(3)

        if '.' in value:
            value = float(value)
        else:
            value = int(value)

        yield name, value

        if unit and unit.startswith('('):
            for part in unit.strip('()').split(', '):
                subname, value = part.split(': ')

                yield name + ': ' + subname, int(value)

FORMAT_UNITS = [
    (10**12,    'T'),
    (10**9,     'G'),
    (10**6,     'M'),
    (10**3,     'K'),
]

def format_units(value):
    for quant, unit in FORMAT_UNITS:
        if value > quant:
            return "{:3.2f}{:}".format(value / quant, unit)

    return "{:3.2f} ".format(value)

def format_percentage(num, total):
    if total > 0.0:
        return "{:3.2f}".format(num / total * 100.0)
    else:
        return " "

def read_stats(row, *names):
    for name in names:
        if name in row:
            return row[name]

def print_stats(rows):
    """
        Output stats from iterable of (name, duration, stats).
    """

    ROW = "{name:18} {time:10} | {files:>8} / {files_total:>8} = {files_pct:>6}% | {size:>8} / {size_total:>8} = {size_pct:>6}% | {send:>8} {recv:>8}"

    print(ROW.format(
            name        = "NAME",
            time        = "TIME",
            files       = "FILES",
            files_total = "TOTAL",
            files_pct   = "",
            size        = "SIZE",
            size_total  = "TOTAL",
            size_pct    = "",
            send        = "SEND",
            recv        = "RECV",
    ))

    for name, duration, stats in rows:
        files = read_stats(stats, "Number of regular files transferred", "Number of files transferred")

        print(ROW.format(
            name        = name,
            time        = format_units(duration.total_seconds()),
            files       = format_units(files),
            files_total = format_units(stats["Number of files"]),
            files_pct   = format_percentage(files, stats["Number of files"]),
            size        = format_units(stats["Total transferred file size"]),
            size_total  = format_units(stats["Total file size"]),
            size_pct    = format_percentage(stats["Total transferred file size"], stats["Total file size"]),
            send        = format_units(stats["Total bytes sent"]),
            recv        = format_units(stats["Total bytes received"]),
        ))

def rsync (options, paths, sudo=False):
    """
        Run rsync.

        Returns a stats dict if there is any valid --stats output, None otherwise.

        Raises qmsk.invoke.InvokeError
    """

    log.info("rsync %s %s", ' '.join(options), ' '.join(paths))

    stdout = qmsk.invoke.invoke(RSYNC, options + paths, sudo=sudo)

    try:
        stats = dict(parse_stats(stdout))
    except ValueError as error:
        log.exception("Invalid rsync --stats output: %s")

        return None
    else:
        return stats

def rsync_server (options, paths, sudo=False):
    """
        Run rsync in --server mode, passing through stdin/out.

        Raises qmsk.invoke.InvokeError
    """

    log.info("rsync-server %s %s", ' '.join(options), ' '.join(paths))

    # invoke directly; no option-handling, nor stdin/out redirection
    qmsk.invoke.invoke(RSYNC, options + paths, stdin=True, stdout=True, sudo=sudo)

class Error (Exception):
    pass

class CommandError (Error):
    """
        Invalid rsync command.
    """

    pass

class SourceError (Error):
    """
        Invalid rsync source
    """

    pass

class Source (object):
    """
        rsync source
    """

    def __init__ (self, path, sudo=None):
        self.path = path
        self.sudo = sudo

    @contextlib.contextmanager
    def mount_snapshot (self):
        """
            Return local filesystem path for rsync source.
        """

        yield self.path

    @contextlib.contextmanager
    def mount_restore (self):
        """
            Return local filesystem path for rsync dest.
        """

        yield self.path

    def rsync_server (self, options):
        """
            Run to restore path in --server mode, passing through stdin/stdout.
        """

        with self.mount_restore() as path:
            return rsync_server(options, ['.', path], sudo=self.sudo)

    def rsync_sender (self, options):
        """
            Run from snapshot path in --server --sender mode, passing through stdin/stdout.
        """

        with self.mount_snapshot() as path:
            return rsync_server(options, ['.', path], sudo=self.sudo)

    def rsync (self, options, dest):
        """
            Run from snapshot to given destination, returning optional stats dict.
        """

        with self.mount_snapshot() as path:
            return rsync(options, [path, dest], sudo=self.sudo)

    def rsync_restore (self, options, dest):
        """
            Run from given destination to restore path, returning optional stats dict.
        """

        with self.mount_restore() as path:
            return rsync(options, [dest, path], sudo=self.sudo)

    def __str__ (self):
        return self.path

class LVMSource(Source):
    """
        Backup LVM LV by snapshotting + mounting it.
    """

    def __init__ (self, vg, lv, path, sudo=None, lvm_opts={}):
        """
            vg              - str: LVM vg name
            lv              - str: LVM vg name
            path            - str: filesystem path within lvm volume; no leading /

            sudo            - use sudo for LVM operations
            lvm_opts   - options for LVM.snapshot
        """

        self.path = path.lstrip('/')
        self.sudo = sudo

        self.lvm = LVM(vg, sudo=sudo)
        self.lvm_volume = self.lvm.volume(lv)
        self.lvm_opts = lvm_opts

    @contextlib.contextmanager
    def mount_snapshot (self):
        """
            Mount LVM snapshot of volume
        """

        # snapshot
        log.info("Creating LVM snapshot: %s", self.lvm_volume)

        with self.lvm.snapshot(self.lvm_volume,
                tag     = 'backup',
                **self.lvm_opts
        ) as snapshot:
            # mount
            log.info("Mounting LVM snapshot: %s", snapshot)

            with qmsk.backup.mount.mount(snapshot.dev_path,
                    name_hint   = 'lvm_' + snapshot.name + '_',
                    readonly    = True,
                    sudo        = self.sudo,
            ) as mountpoint:
                yield mountpoint.path + '/' + self.path

    @contextlib.contextmanager
    def mount_restore (self):
        """
            Return local filesystem path for rsync dest.
        """

        raise NotImplementedError()

    def __str__ (self):
        return 'lvm:{volume}'.format(volume=self.lvm_volume)

class ZFSSource(Source):
    """
        Backup ZFS by snapshotting + mounting it.
    """

    def __init__ (self, zfs, path='/', **opts):
        """
            zfs             - qmsk.backup.zfs.ZFS
            path            - str: filesystem path within lvm volume; no leading /
        """

        super().__init__(path.lstrip('/'), **opts)

        self.zfs = zfs

    def snapshot(self):
        """
            With ZFS snapshot.
        """

        log.info("Creating ZFS snapshot: %s", self.zfs)

        return qmsk.backup.zfs.snapshot(self.zfs, properties={
            'qmsk-backup:source': self.path,
        })

    @contextlib.contextmanager
    def mount_snapshot (self):
        """
            Mount ZFS snapshot of volume.
        """

        with self.snapshot() as snapshot:
            # mount
            log.info("Mounting ZFS snapshot: %s", snapshot)

            with qmsk.backup.mount.mount(str(snapshot),
                    fstype      = 'zfs',
                    name_hint   = 'zfs_' + str(self.zfs).replace('/', '_') + '_',
                    readonly    = True,
                    sudo        = self.sudo,
            ) as mountpoint:
                yield mountpoint.path + '/' + self.path

    @contextlib.contextmanager
    def mount_restore (self):
        """
            Return local filesystem path for rsync dest.
        """

        raise NotImplementedError()

    def __str__ (self):
        return 'zfs:{zfs}'.format(zfs=self.zfs)

def parse_command (command):
    """
        Parse rsync server command into bits.

            command:            - list(argv) including 'rsync' command and options/arguments

        Returns:
            cmd:        rsync argv[0]
            options:    list of --options and -opts
            paths:      list of path arguments

        Raises:
            CommandError

        >>> import shlex
        >>> parse_command(shlex.split('rsync --server --sender -ax . lvm:asdf:test'))
        ('rsync', ['--server', '--sender', '-ax'], ['.', 'lvm:asdf:test'])

    """

    cmd = None
    options = []
    paths = []

    # parse
    for part in command:
        if cmd is None:
            cmd = part

        elif part.startswith('--'):
            options.append(part)

        elif part.startswith('-'):
            # XXX: parse out individual flags..?
            options.append(part)

        else:
            paths.append(part)

    return cmd, options, paths

def parse_server_command(command):
    """
        Parse rsync's internal --server command used when remoting over SSH.

        Returns:
            options:    list of --options and -opts from parse_options
            source:     source path if sender, or None
            dest:       dest path if receiver, or None

        Raises:
            CommandError

    """

    cmd, options, args = parse_command(command)

    if cmd.split('/')[-1] != 'rsync':
        raise CommandError("Invalid command: {cmd}".format(cmd=cmd))

    if len(args) != 2:
        raise CommandError("Invalid source/destination paths")

    if args[0] != '.':
        raise CommandError("Invalid source-path for server")

    path = args[1]

    # parse real source
    if not '--server' in options:
        raise CommandError("Missing --server")

    elif not '--sender' in options:
        # write
        source = None
        dest = path

    else:
        # read
        source = path
        dest = None

    # ok
    return options, source, dest

def parse_sender_command (command):
    """
        Parse rsync's internal --server --sender command used when reading over SSH.

        Returns:
            options:    list of --options and -opts from parse_options
            source:     source path

        Raises:
            CommandError

    """

    options, source, dest = parse_server_command(command)

    if dest:
        raise CommandError("Missing --sender")
    else:
        return options, source

def parse_source (path, restrict_paths=None, allow_remote=True, sudo=None, lvm_opts={}):
    """
        Parse an LVM source path, supporting custom extensions for LVM support.

            restrict_paths  - raise CommandError if source path is not under any of the given sources.
            allow_remote    - allow remote sources?
            lvm_opts        - **opts for LVMSource
    """

    if not path:
        raise SourceError("No path given")

    endslash = path.endswith('/')

    # normalize
    path = os.path.normpath(path)

    if endslash and not path.endswith('/'):
        # add it back in
        # happens for 'foo:/' and such
        path += '/'

    # verify path
    if restrict_paths:
        for restrict_path in restrict_paths:
            if path.startswith(restrict_path):
                # ok
                break
        else:
            # fail
            raise SourceError("Restricted path")

    if path.startswith('/'):
        log.debug("filesystem: %s", path)

        return Source(path,
                sudo    = sudo,
        )

    elif path.startswith('lvm:'):
        _, path = path.split(':', 1)

        # LVM VG
        try:
            if ':' in path:
                vg, path = path.split(':', 1)

                log.warn("old 'lvm:%s:%s' syntax; use 'lvm:%s/%s'", vg, path)

            elif '/' in path:
                vg, path = path.split('/', 1)

            else:
                raise ValueError("Invalid vg/lv separator")

        except ValueError as error:
            raise SourceError("Invalid lvm pseudo-path: {error}".format(error=error))

        # LVM LV, and path within LV
        if '/' in path:
            lv, path = path.split('/', 1)
        else:
            lv = path
            path = ''

        # lookup
        log.debug("LVM: %s/%s/%s", vg, lv, path)

        # open
        return LVMSource(vg, lv, path,
                sudo            = sudo,
                lvm_opts        = lvm_opts,
        )

    elif path.startswith('zfs:'):
        _, path = path.split(':', 1)

        if path.startswith('/'):
            device, mount, fstype, name = qmsk.backup.mount.find(path)

            log.debug("%s: mount=%s fstype=%s device=%s name=%s", path, mount, fstype, device, name)

            if fstype != 'zfs':
                raise SourceError("Not a ZFS mount %s: mount=%s fstype=%s", path, mount, device)
        else:
            device = path
            name = ''

        # lookup
        log.debug("ZFS %s: %s / %s", path, device, name)

        # open
        return ZFSSource(qmsk.backup.zfs.open(device, invoker=qmsk.invoke.Invoker(sudo=sudo)),
                path    = name,
                sudo    = sudo,
        )

    elif ':' in path: # remote host
        if not allow_remote:
            raise SourceError("Invalid remote path")

        # remote host
        log.debug("remote: %s", path)

        return Source(path,
                sudo        = sudo,
        )
    else:
        # invalid
        raise SourceError("Unknown path format")
