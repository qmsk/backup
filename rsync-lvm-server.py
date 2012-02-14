#!/usr/bin/python

import optparse, shlex

import subprocess
import os, os.path

import contextlib
import logging

log = logging.getLogger()

class InvokeError (Exception) :
    def __init__ (self, cmd, exit) :
        self.cmd = cmd
        self.exit = exit

    def __str__ (self) :
        return "{cmd} failed: {exit}".format(cmd=self.cmd, exit=self.exit)

def invoke (cmd, args, data=None) :
    """
        Invoke a command directly.
        
        data:       data to pass in on stdin, returning stdout.
                    if given as False, passes through our process stdin/out

        Doesn't give any data on stdin, and keeps process stderr.
        Returns stdout.
    """
    
    log.debug("cmd={cmd}, args={args}".format(cmd=cmd, args=args))

    if data is False :
        # keep process stdin/out
        io = None
    else :
        io = subprocess.PIPE

    p = subprocess.Popen([cmd] + args, stdin=io, stdout=io)

    # get output
    stdout, stderr = p.communicate(input=data)

    if p.returncode :
        # failed
        raise InvokeError(cmd, p.returncode)

    return stdout

def optargs (*args, **kwargs) :
    """
        Convert args/options into command-line format
    """

    # process
    opts = [('--{opt}'.format(opt=opt), value if value != True else None) for opt, value in kwargs.iteritems() if value]

    # flatten
    opts = [str(opt_part) for opt_parts in opts for opt_part in opt_parts if opt_part]

    args = [str(arg) for arg in args if arg]

    return opts + args
 
def command (cmd, *args, **opts) :
    """
        Invoke a command with options/arguments, given via Python arguments/keyword arguments.

        Return stdout.
    """
    
    log.debug("{cmd} {opts} {args}".format(cmd=cmd, args=args, opts=opts))

    # invoke
    return invoke(cmd, optargs(*args, **opts))
   
class LVM (object) :
    """
        LVM VolumeGroup
    """

    # path to lvm2 binary
    LVM = '/sbin/lvm'

    
    # VG name
    name = None

    def __init__ (self, name) :
        self.name = name

    def lv_name (self, lv) :
        """
            vg/lv name.
        """

        return '{vg}/{lv}'.format(vg=self.name, lv=lv)

    def lv_path (self, lv) :
        """
            /dev/vg/lv path.
        """

        return '/dev/{vg}/{lv}'.format(vg=self.name, lv=lv)

    def command (self, cmd, *args, **opts) :
        """
            Invoke a command with options/arguments, given via Python arguments/keyword arguments
        """
        
        log.debug("{cmd} {opts} {args}".format(cmd=cmd, args=args, opts=opts))

        # invoke
        invoke(self.LVM, [cmd] + optargs(*args, **opts))

    def volume (self, name) :
        """
            Return an LVMVolume for given named LV.
        """

        return LVMVolume(self, name)

    @contextlib.contextmanager
    def snapshot (self, base, **kwargs) :
        """
            A Context Manager for handling an LVMSnapshot.

            See LVMSnapshot.create()

            with lvm.snapshot(lv) as snapshot : ...
        """

        log.debug("creating snapshot from {base}: {opts}".format(base=base, opts=kwargs))
        snapshot = LVMSnapshot.create(self, base, **kwargs)

        try :
            log.debug("got: {0}".format(snapshot))
            yield snapshot

        finally:
            # cleanup
            # XXX: do we need to wait for it to get closed after mount?
            log.debug("cleanup: {0}".format(snapshot))
            snapshot.close()

    def __repr__ (self) :
        return "LVM(name={name})".format(name=repr(self.name))

class LVMVolume (object) :
    """
        LVM Logical Volume.
    """

    # VG
    lvm = None

    # name
    name = None

    def __init__ (self, lvm, name) :
        self.lvm = lvm
        self.name = name

    @property
    def lvm_path (self) :
        return self.lvm.lv_name(self.name)

    @property
    def dev_path (self) :
        return self.lvm.lv_path(self.name)

    def __repr__ (self) :
        return "LVMVolume(lvm={lvm}, name={name})".format(
                lvm     = repr(self.lvm),
                name    = repr(self.name),
        )

class LVMSnapshot (LVMVolume) :
    """
        LVM snapshot
    """
    
    # default snapshot size
    LVM_SNAPSHOT_SIZE   = '5G'

    # base lv
    base = None

    @classmethod
    def create (cls, lvm, base, tag, size=LVM_SNAPSHOT_SIZE) :
        """
            Create a new LVM snapshot of the given LV.
            
            Returns a (snapshot_name, dev_path) tuple.
        """

        # snapshot name
        name = '{name}-{tag}'.format(name=base.name, tag=tag)

        # snapshot
        snapshot = cls(lvm, base, name)

        # verify LV exists
        lvm.command('lvs', base.lvm_path)
        
        if not os.path.exists(base.dev_path) :
            raise Exception("lvm_snapshot: source LV does not exist: {path}".format(path=base.dev_path))

        if os.path.exists(snapshot.dev_path) :
            raise Exception("lvm_snapshot: target LV snapshot already exists: {path}".format(path=snapshot.dev_path))

        # create
        snapshot.open()

        # verify
        if not os.path.exists(snapshot.dev_path) :
            raise Exception("lvm_snapshot: target LV snapshot did not appear: {path}".format(path=snapshot.dev_path))

        # yay
        return snapshot

    def __init__ (self, lvm, base, name, size=LVM_SNAPSHOT_SIZE) :
        LVMVolume.__init__(self, lvm, name)

        self.base = base
        self.size = size

    def open (self) :
        """
            Create snapshot volume.
        """

        # create
        self.lvm.command('lvcreate', self.base.lvm_path, snapshot=True, name=self.name, size=self.size)

    def close (self) :
        """
            Remove snapshot volume.
        """

        # XXX: can't deactivate snapshot volume
        #self.lvm.command('lvchange', name, available='n')

        # XXX: risky!
        self.lvm.command('lvremove', '-f', self.lvm_path)

    def __repr__ (self) :
        return "LVMSnapshot(lvm={lvm}, base={base}, name={name})".format(
                lvm     = str(self.lvm),
                base    = str(self.base),
                name    = repr(self.name),
        )


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

class RSyncCommandFormatError (Exception) :
    """
        Improper rsync command
    """

    pass

def parse_rsync (command, restrict_server=True, restrict_readonly=True) :
    """
        Parse given rsync server command into bits. 

            command             - the command-string sent by rsync
            restrict_server     - restrict to server-mode
            restrict_readonly   - restrict to read/send-mode
        
        Returns:

            (cmd, options, source, dest)
    """

    # split
    parts = shlex.split(command)

    cmd = None
    options = []
    source = None
    dest = None

    # parse
    for part in parts :
        if cmd is None :
            cmd = part

        elif part.startswith('-') :
            options.append(part)

        elif source is None :
            source = part

        elif dest is None :
            dest = part

    # options
    have_server = ('--server' in options)
    have_sender = ('--sender' in options)

    # verify
    if not have_server :
        raise RSyncCommandFormatError("Missing --server")

    if restrict_readonly and not have_sender :
        raise RSyncCommandFormatError("Missing --sender for readonly")

    # parse path
    if have_sender :
        # read
        # XXX: which way does the dot go?
        if source != '.' :
            raise RSyncCommandFormatError("Invalid dest for sender")
        
        path = dest

    else :
        # write
        if source != '.' :
            raise RSyncCommandFormatError("Invalid source for reciever")

        path = dest

    # ok
    return cmd, options, source, dest

class RSyncSource (object) :
    RSYNC = '/usr/bin/rsync'

    def _execute (self, options, path) :
        """
            Underlying rsync just reads from filesystem.
        """

        invoke(self.RSYNC, options + [path, '.'], data=False)

class RSyncFSSource (RSyncSource) :
    """
        Normal filesystem backup.
    """

    def __init__ (self, path) :
        RSyncSource.__init__(self)

        self.path = path

    def execute (self, options) :
        return self._execute(options, self.path)

class RSyncLVMSource (RSyncSource) :
    """
        Backup LVM LV by snapshotting + mounting it.
    """

    def __init__ (self, volume) :
        RSyncSource.__init__(self)

        self.volume = volume
 
    def execute (self, options) :
        """
            Snapshot, mount, execute
        """
        
        # backup target from LVM command
        lvm = self.volume.lvm
        volume = self.volume

        # XXX: generate
        path = '/mnt'

        # snapshot
        log.info("Open snapshot...")

        # XXX: generate snapshot nametag to be unique?
        with lvm.snapshot(volume, tag='backup') as snapshot:
            log.info("Snapshot opened: %s", snapshot.lvm_path)

            # mount
            log.info("Mounting snapshot: %s -> %s", snapshot, path)

            with mount(snapshot.dev_path, path) as mountpoint:
                log.info("Mounted snapshot: %s", mountpoint)
                
                # rsync!
                log.info("Running rsync: ...")

                return self._execute(options, mountpoint.path)

            # cleanup
        # cleanup
       
def rsync_source (path, restrict_path=False) :
    """
        Figure out source to rsync from, based on pseudo-path given in rsync command.
    """
        
    # normalize
    path = os.path.normpath(path)

    # verify path
    if restrict_path :
        if not path.startswith(restrict_path) :
            raise RSyncCommandFormatError("Restricted path ({restrict})".format(restrict=restrict_path))

    if path.startswith('/') :
        # direct filesystem path
        # XXX: how to handle=
        log.info("filesystem: %s", path)

        return RSyncFSSource(path)

    elif path.startswith('lvm:') :
        # LVM LV
        try :
            lvm, vg, lv = path.split(':')

        except ValueError, e:
            raise RSyncCommandFormatError("Invalid lvm pseudo-path: {error}".format(error=e))
        
        # XXX: validate

        log.info("LVM: %s/%s", vg, lv)

        # open
        lvm = LVM(vg)
        volume = lvm.volume(lv)

        return RSyncLVMSource(volume)
       
    else :
        # invalid
        raise RSyncCommandFormatError("Unrecognized backup path")

# command-line options
options = None

def parse_options (argv) :
    """
        Parse command-line arguments.
    """


    parser = optparse.OptionParser()

    # logging
    parser.add_option('-q', '--quiet',      dest='loglevel', action='store_const', const=logging.WARNING, help="Less output")
    parser.add_option('-v', '--verbose',    dest='loglevel', action='store_const', const=logging.INFO,  help="More output")
    parser.add_option('-D', '--debug',      dest='loglevel', action='store_const', const=logging.DEBUG, help="Even more output")

    # 
    parser.add_option('-c', '--command',    default=os.environ.get('SSH_ORIGINAL_COMMAND'),
            help="rsync command to execute")

    parser.add_option('-R', '--readonly',   action='store_true', default=False,
            help="restrict to read operations")

    parser.add_option('-P', '--restrict-path', default=False,
            help="restrict to given path")

    # defaults
    parser.set_defaults(
        loglevel    = logging.WARNING,
    )

    # parse
    options, args = parser.parse_args(argv[1:])

    # configure
    logging.basicConfig(
        format  = '%(processName)s: %(name)s: %(levelname)s %(funcName)s : %(message)s',
        level   = options.loglevel,
    )

    return options, args


def rsync_wrapper (command, restrict='lvm:') :
    """
        Wrap given rsync command.
        
        Backups the LVM LV given in the rsync command.
    """

    try :
        # parse
        rsync_cmd, rsync_options, source_path, dest_path = parse_rsync(command, 
                restrict_readonly   = options.readonly,
            )

    except RSyncCommandFormatError, e:
        log.error("invalid rsync command: %r: %s", command, e)
        return 2

    # XXX: the real path is always given second..
    path = dest_path

    try :
        # parse source
        source = rsync_source(path,
                restrict_path       = options.restrict_path,
            )

    except RSyncCommandFormatError, e:
        log.error("invalid rsync source: %r: %s", path, e)
        return 2

    try :
        # run
        source.execute(rsync_options)

    except InvokeError, e:
        log.error("%s failed: %d", e.cmd, e.exit)
        return e.exit

    # ok
    return 0

def main (argv) :
    """
        SSH authorized_keys command="..." wrapper for rsync.
    """

    global options

    # global options + args
    options, args = parse_options(argv)

    # args
    if args :
        log.error("No arguments are handled")
        return 2

    if not options.command:
        log.error("SSH_ORIGINAL_COMMAND not given")
        return 2

    try :
        # handle it
        return rsync_wrapper(options.command)

    except Exception, e:
        log.error("Internal error:", exc_info=e)
        return 3

    # ok
    return 0

if __name__ == '__main__' :
    import sys

    sys.exit(main(sys.argv))

