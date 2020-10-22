import datetime
import logging
import os.path
import qmsk.backup.rsync
import qmsk.invoke

log = logging.getLogger('qmsk.backup.target')

class Error (Exception):
    pass

class Interval:
    """
        Manage snapshot retention over time intervals using strftime formatting.

        An interval link is created from the snapshot's datetime.strftime() using the given STRFTIME format, unless one already exists.

        When purging, the LIMIT most recent interval links are retained, and the older ones removed. Snapshots with no interval links remaining are also removed. The LIMIT@ part may also be omitted for infinite retention.

        The resulting timestamp string is used as a filesystem name, and cannot contain any / characters.
    """

    # XXX:  can't use [LIMIT@] due to argparse bug
    #       https://bugs.python.org/issue11874
    METAVAR = 'LIMIT@NAME:STRFTIME'

    @classmethod
    def config (cls, value):
        """
            Parse from string syntax.

            Raises ValueError.
        """

        if '@' in value:
            limit, value = value.split('@', 1)
            limit = int(limit)
        else:
            limit = None

        if ':' in value:
            name, value = value.split(':', 1)
        else:
            raise ValueError("Invalid interval missing 'NAME:'")

        strftime = value

        return cls(name, strftime,
                limit   = limit,
        )

    def __init__ (self, name, strftime, limit=None):
        if '/' in name:
            raise ValueError("Invalid interval name: {name!r}".format(
                name        = self.name,
            ))


        self.name = name
        self.strftime = strftime
        self.limit = limit

    def __str__(self):
        if self.limit:
            return "{self.name}:{self.limit}@{self.strftime}".format(self=self)
        else:
            return "{self.name}:{self.strftime}".format(self=self)

    def format(self, now):
        value = now.strftime(self.strftime)

        if '/' in value:
            raise ValueError("Invalid interval {name} strftime={strftime!r} value: {value!r}".format(
                name        = self.name,
                strftime    = self.strftime,
                value       = value,
            ))

        return value

    def parse(self, value):
        """
            Parse datetime from formatted value, at whatever percision is used.


            Returns True if the given snapshot name matches our format.
        """

        return datetime.datetime.strptime(value, self.strftime)

    def match(self, value):
        """
            Test if given value is a valid format() output.
        """

        try:
            self.parse(value)
        except ValueError:
            return False
        else:
            return True

class BaseTarget:
    # rsync options, in invoke.optargs format
    RSYNC_OPTIONS = {
        'archive':          True,
        'hard-links':       True,
        'one-file-system':  True,
        'numeric-ids':      True,
        'delete':           True,
    }

    SNAPSHOT_STRFTIME = '%Y%m%d-%H%M%S'

    @classmethod
    def config(cls,
            rsync_source=None,
            rsync_options=None,
            sudo=None,
            noop=None,
            **opts
    ):
        """
            Parse rsync options from list.
        """

        if rsync_source:
            try:
                rsync_source    = qmsk.backup.rsync.parse_source(rsync_source,
                        sudo    = sudo,
                )
            except qmsk.backup.rsync.SourceError as error:
                raise Error("--source=%s: %s", source, error)

        _rsync_options = dict(cls.RSYNC_OPTIONS)

        if rsync_options:
            for opt in rsync_options:
                if '=' in opt:
                    opt, value = opt.split('=', 1)
                else:
                    value = True

                # update
                if value is True:
                    _rsync_options[opt] = value
                elif value:
                    _rsync_options.setdefault(opt, []).append(value)
                else:
                    del _rsync_options[opt]

        return cls(
                rsync_source    = rsync_source,
                rsync_options   = _rsync_options,
                noop = noop,
                **opts
        )

    def __init__(self,
            rsync_source    = None,
            rsync_options   = [],
            intervals       = [],
            noop            = None,
    ):
        self.rsync_source = rsync_source
        self.rsync_options = rsync_options
        self.intervals = intervals
        self.noop = noop

    def setup (self, create=False):
        abstract

    def mount(self):
        """
            Return backup destination path.
        """

        abstract

    def rsync (self, dest_path, link_dest=None):
        """
            rsync source to given dest.

            Return the --stats dict, or None if unparseable.

            Raises qmsk.backup.rsync.Error
        """

        rsync_options = dict(self.rsync_options)

        if link_dest:
            # rsync links absolute paths..
            rsync_options['link-dest'] = os.path.abspath(link_dest)

        # use stats
        rsync_options['stats'] = True

        if self.noop:
            rsync_options['dry-run'] = True

        opts = qmsk.invoke.optargs(**rsync_options)

        try:
            # run the rsync.RSyncServer; None as a placeholder will get replaced with the actual source
            stats = self.rsync_source.rsync(opts, dest_path)

        except qmsk.backup.rsync.Error as error:
            log.warn("%s rsync error: %s", self, error)
            raise

        else:
            return stats

    def rsync_restore (self, path):
        """
            rsync given path to source.

            Return the --stats dict, or None if unparseable.

            Raises qmsk.backup.rsync.Error
        """

        rsync_options = dict(self.rsync_options)

        # use stats
        rsync_options['stats'] = True

        if self.noop:
            rsync_options['dry-run'] = True

        opts = qmsk.invoke.optargs(**rsync_options)

        try:
            # run the rsync.RSyncServer; None as a placeholder will get replaced with the actual source
            stats = self.rsync_source.rsync_restore(opts, path)

        except qmsk.backup.rsync.Error as error:
            log.warn("%s rsync error: %s", self, error)
            raise

        else:
            return stats

    def snapshot (self, now):
        """
            Update the current snapshot to point to a new snapshot for the given datetime, containing changes from rsync.

            Returns the name of the new snapshot on completion.

            Raises rsync.RsyncError or Error.
        """

        abstract

    def backup (self):
        """
            Create snapshot with rsync, link intervals.
        """

        abstract

    def purge(self):
        """
            Unlink intervals per limits, purge any unlinked snapshots.
        """

        abstract
