import datetime
import logging
import os.path
import pvl.backup.rsync
import pvl.invoke

log = logging.getLogger('pvl.backup.target')

class Error (Exception):
    pass

class Interval:
    @classmethod
    def config (cls, interval):
        if '@' in interval:
            limit, interval = interval.split('@', 1)
            limit = int(limit)
        else:
            limit = None

        strftime = interval

        return cls(strftime,
                limit   = limit,
        )

    def __init__ (self, strftime, limit=None):
        self.strftime = strftime
        self.limit = limit

    def __str__(self):
        if self.limit:
            return "{self.limit}@{self.strftime}".format(self=self)
        else:
            return "{self.strftime}".format(self=self)

    def format(self, now):
        return now.strftime(self.strftime)

    def match(self, name):
        """
            Returns True if the given snapshot name matches our format.
        """

        try:
            datetime.datetime.strptime(name, self.strftime)
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

            Raises pvl.backup.rsync.Error
        """
        
        rsync_options = dict(self.rsync_options)
        
        if link_dest:
            # rsync links absolute paths..
            rsync_options['link-dest'] = os.path.abspath(link_dest)
 
        opts = pvl.invoke.optargs(**rsync_options)

        try:
            # run the rsync.RSyncServer; None as a placeholder will get replaced with the actual source
            self.rsync_source.rsync(opts, dest_path)

        except pvl.backup.rsync.Error as error:
            log.warn("%s rsync error: %s", self, error)
            raise

