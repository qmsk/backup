import datetime
import logging
import os.path
import pvl.backup.rsync
import pvl.invoke

log = logging.getLogger('pvl.backup.target')

class Error (Exception):
    pass

class Interval:
    """
        Manage snapshot retention over time intervals using strftime formatting.

        An interval link is created from the snapshot's datetime.strftime() using the given STRFTIME format, unless one already exists.
        
        When purging, the LIMIT most recent interval links are retained, and the older ones removed. Snapshots with no interval links remaining are also removed.

        The resulting timestamp string is used as a filesystem name, and cannot contain any / characters.
    """

    METAVAR = '[LIMIT@]NAME:STRFTIME'

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
    
    @classmethod
    def config(cls,
            rsync_source=None,
            rsync_options=None,
            **opts
    ):
        """
            Parse rsync options from list.
        """

        if rsync_source:
            try:
                rsync_source    = pvl.backup.rsync.parse_source(rsync_source)
            except pvl.backup.rsync.SourceError as error:
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
                **opts
        )

    def __init__(self,
            rsync_source    = None,
            rsync_options   = [],
            intervals       = [],
    ):
        self.rsync_source = rsync_source
        self.rsync_options = rsync_options
        self.intervals = intervals

    def mount(self):
        """
            Return backup destination path.
        """

        abstract

    def rsync (self, dest_path, link_dest=None):
        """
            rsync source to given dest.

            Return the --stats dict, or None if unparseable.

            Raises pvl.backup.rsync.Error
        """
        
        rsync_options = dict(self.rsync_options)
        
        if link_dest:
            # rsync links absolute paths..
            rsync_options['link-dest'] = os.path.abspath(link_dest)

        # use stats
        rsync_options['stats'] = True
 
        opts = pvl.invoke.optargs(**rsync_options)

        try:
            # run the rsync.RSyncServer; None as a placeholder will get replaced with the actual source
            stats = self.rsync_source.rsync(opts, dest_path)

        except pvl.backup.rsync.Error as error:
            log.warn("%s rsync error: %s", self, error)
            raise

        else:
            return stats

