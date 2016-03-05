# Backup tools using rsync

## Features

### Restricted rsync

The `bin/pvl.backup-rsync` script can be used as an `~/.ssh/authorized_keys` `command="..."` wrapper, and provides options to restrict/secure access:
        
        command="/opt/pvl-backup/bin/pvl.backup-rsync --readonly --restrict-path=/foo" ssh-rsa ...


XXX: the current implementation is not exactly security-audited, the restrictions serve more to avoid mistakes, and do not protect against
     determined misuse of your ssh key..
#### `--readonly`

Limit to rsync sender, i.e. rsync from this source.

#### `--restrict-path=`

Limit to paths under the given prefix. Can be given multiple times to allow different paths.

#### `--sudo`

Run any `rsync`, `lvm`, `mount` operations using sudo, which allows for use of non-root account with a sudo command whitelist.

### LVM Snapshots

The rsync source syntax is extended to support `lvm:<vg>/<lv>`, which creates an LVM snapshot of the LV, mounts it readonly, and runs rsync from the mounted snapshot. This allows for atomic rsync operations, to avoid rsync "file has vanished" etc errors where files change during the rsync operation.

This syntax is supported for both local rsync sources, as well as by the remote `pvl.backup-rsync` wrapper.

When rsyncing from a remote LVM snapshot, the source syntax is:

    rsync --options hostname:lvm:vg/lv /target

TODO: freeze/sync the filesystem for the snapshot?

### rsync snapshot storage

The `pvl.backup-snapshot` script can be used to manage a series of rsync snapshots on filesystems like ext4. This uses `rsync --link-dest` internally to hardlink files between snapshots, and only store changed files on disk.

### zfs snapshot storage

The `pvl.backup-zfs` script can be used manage ZFS snapshots with retention intervals when using rsync to backup remote filesystems onto local ZFS filesystems.
