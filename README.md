# Automated ZFS/rsync backups for LVM/ZFS snapshots

A suite of Python scripts used to automate backups and restores of ZFS/LVM volumes.

Supports incremental rsync backups over SSH, from remote LVM and ZFS filesystem snapshots to local ZFS or `rsync --link-dest` storage.

## Features

### `qmsk.rsync-ssh-command`

SSH `authorized_keys` command wrapper for `rsync`. Compatible with standard rsync SSH remotes.

* Use `--readonly` to only allow read-only rsync send operations
* Use `--restrict-path` to only allow rsync sends from specific paths
* Support for rsync `HOST:lvm:VG/LV` sources to use LVM snapshots for consistent filesystem-level backups
* Support for rsync `HOST:zfs:POOL/DATASET` sources to use ZFS snapshots for consistent filesystem-level backups
* Use `--allow-restore` to allow rsync write operations for restores to filesystem or LVM volumes
* Optional `--sudo` to elevate privileges from non-root SSH user for privileged `rsync`, `lvm` operations

### `qmsk.zfs-ssh-command`

SSH `authorized_keys` command wrapper for `zfs`. Compatible with `ssh ... zfs send ... | zfs recv`.

* Restricted to `zfs send` only
* Use `--restrict-glob` to only allow ZFS sends from specific datasets
* Use `--restrict-raw` to only allow sending raw (encrypted) snapshots
* Use `zfs send POOL/DATASET` to send from temporary snapshot
* Use `zfs send POOL/DATASET@*` to send from most recent snapshot
* Compatible with incremental and replication sends
* Optional `--sudo` to elevate privileges from non-root SSH user for privileged `zfs` operations

### `qmsk.backup-zfs`

Manage ZFS snapshots with optional rsync or ZFS sources

* Use `--rsync-source` to backup remote filesystems using `rsync`, supporting remote LVM/ZFS snapshots for consistent filesystem-level backups when used with `qmsk.rsync-ssh-command`
* Use `--zfs-source` to backup remote ZFS datasets using `zfs send | zfs recv`
* Use `--zfs-raw` to transfer encrypted ZFS snapshots that cannot be mounted without the encryption key
* Use `--ssh-identity/config` to configure SSH credentials used
* Use `--interval` to manage timed hold policies for snapshots
* Use `--purge` to rotate old snapshots
* Use `--restore` to restore from local ZFS snapshot back to remote rsync/ZFS target

## Install

    virtualenv -p python3 /opt/qmsk-backup && /opt/qmsk-backup/bin/pip install \
        git+https://github.com/qmsk/backup.git

## Usage

### Scripts

The `qmsk.backup-*` scripts does not use any configuration file, all configuration is in the form of options.
You can create a backup script file for each backup target, such as:

#### `/etc/qmsk-backup/targets/test`
```
#!/bin/bash

exec /opt/qmsk-backup/bin/qmsk.backup-rsync /srv/backup/test \
        --rsync-source='backup@test.example.com:lvm:raid10/test-root' \
        --rsync-option='rsh=ssh -F /srv/backup/.ssh/config' \
        --rsync-option='exclude-from=/etc/qmsk-backup/rsync.exclude' \
        --interval='10@recent:%Y%m%d-%H%M%S' \
        --interval='7@day:%Y-%m-%d' \
        --interval='4@week:%Y-%W' \
        "$@"
```

### `cron`
Use a wrapper script such as the following to run multiple targets from cron.

You probably want to have cron run the wrapper script with `--purge`:

```
15 22 * * *   root         /etc/qmsk-backup/targets.sh --purge
```

#### `/etc/qmsk-backup/targets.sh`
```
#!/bin/bash

for target in /etc/qmsk-backup/targets/*; do
        [ -x $target ] || continue

        $target "$@"
done
```

## Features

### Restricted `rsync`for `.ssh/authorized_keys` `command=`

The `bin/qmsk.rsync-ssh-command` script can be used as an `~/.ssh/authorized_keys` `command="..."` wrapper, and provides options to restrict/secure access:

        command="/opt/qmsk-backup/bin/qmsk.rsync-ssh-command --readonly --restrict-path=/foo" ssh-rsa ...


***NOTE***: the current implementation is not exactly security-audited, the restrictions serve more to avoid mistakes, and do not protect against determined misuse of your ssh key...

#### `--readonly`

Limit to rsync sender, i.e. rsync from this source.

This is the default behavior. For safety, this requires an explicit `--allow-restore` for write operations

#### `--restrict-path=`

Limit to paths under the given prefix. Can be given multiple times to allow different paths.

#### `--sudo`

Run any `rsync`, `lvm`, `mount` operations using sudo, which allows for use of non-root account with a sudo command whitelist.

### `rsync` from LVM Snapshots

The rsync source syntax is extended to support `lvm:<vg>/<lv>`, which creates an LVM snapshot of the LV, mounts it readonly, and runs rsync from the mounted snapshot. This allows for atomic rsync operations, to avoid rsync "file has vanished" etc errors where files change during the rsync operation.

This syntax is supported for both local rsync sources, as well as by the remote `qmsk.backup-rsync` wrapper.

When rsyncing from a remote LVM snapshot, the source syntax is:

    rsync --options hostname:lvm:vg/lv /target

TODO: freeze/sync the filesystem for the snapshot?

### `rsync` from ZFS Snapshots

The rsync source syntax also supports two forms of ZFS filesystems: `zfs:<pool>/<name>` and `zfs:/path`.
The former will take a `zfs snapshot <pool>/<name>`, mount that, and rsync the contents of the ZFS root.
The later will find the ZFS mount for the given path, take a ZFS snapshot, mount it, and rsync the contents of that path within the ZFS snapshot.

This syntax is supported for both local rsync sources, as well as by the remote `qmsk.rsync-ssh-command` wrapper.

### zfs snapshot storage

The `qmsk.backup-zfs` script can be used manage ZFS snapshots with retention intervals.

The script has three modes of operation:

* Using `--rsync-source` will first rsync from the remote source, and then create a local ZFS snapshot.
* Using `--zfs-source` will use ZFS bookmarks to create and send a temporary snapshot from the remote source.
  This relies on the remote source using the `pvl.zfs-ssh-command` wrapper script.
* Otherwise, a local ZFS snapshot will be created without any remote sync.

It also supports using rsync to backup remote filesystems onto the local ZFS filesystems before snapshotting.

### `rsync --link-dest` snapshot storage

The `qmsk.backup-rsync` script can be used to manage incremental backups as a series of hardlinked filesystem trees over traditional filesystems like ext4.
This uses `rsync --link-dest` internally to hardlink files between snapshots, and only store changed files on disk.

#### `rsync --stats`

The `qmsk.backup-rsync` will collect additional `snapshots/*.meta` JSON files containing the `start` and `end `time of the backup, and the rsync paths used:

```json
{
   "link_dest" : "/srv/backup/rauta/snapshots/20161230-223923",
   "rsync_source" : "backup@rauta.paivola.fi:lvm:raid10/herukka-root",
   "stats" : {
      "Total file size" : 4410744757,
      "File list generation time" : 0.172,
      "Number of files transferred" : 80,
      "Total bytes sent" : 393791,
      "Matched data" : 1255258651,
      "Number of files" : 74687,
      "Total transferred file size" : 1306565504,
      "File list transfer time" : 0,
      "File list size" : 1683291,
      "Total bytes received" : 53261465,
      "Literal data" : 51306853
   },
   "end" : "2016-12-31T20:41:01.939445",
   "start" : "2016-12-31T20:38:57.876767"
}
```

Use `qmsk.backup-rsync --no-backup --stats` to summarize this output:

```
NAME               TIME       |    FILES /    TOTAL =       % |     SIZE /    TOTAL =       % |     SEND     RECV
20161210-222623    126.60     |  295.00  /   74.64K =   0.40% |    1.33G /    4.41G =  30.13% |  438.91K  102.49M
20161211-223031    135.71     |  193.00  /   74.67K =   0.26% |    1.37G /    4.43G =  31.01% |  525.04K  263.11M
20161212-222952    126.10     |  430.00  /   74.71K =   0.58% |    1.36G /    4.42G =  30.76% |  502.53K   71.53M
20161213-223119    129.60     |  104.00  /   74.73K =   0.14% |    1.37G /    4.45G =  30.80% |  417.95K  100.76M
20161214-223013    127.44     |  156.00  /   74.76K =   0.21% |    1.37G /    4.42G =  30.98% |  526.12K  119.36M
20161215-223047    130.27     |  104.00  /   74.78K =   0.14% |    1.33G /    4.42G =  30.11% |  407.62K  107.83M
20161216-223854    114.15     |  109.00  /   74.80K =   0.15% |    1.31G /    4.40G =  29.90% |  436.03K  152.16M
20161217-223717    115.24     |   82.00  /   74.80K =   0.11% |    1.30G /    4.40G =  29.63% |  401.38K  111.77M
20161218-225629    119.07     |  124.00  /   74.80K =   0.17% |    1.32G /    4.40G =  29.89% |  446.69K   78.32M
20161219-223721    113.16     |   81.00  /   74.80K =   0.11% |    1.31G /    4.41G =  29.70% |  391.75K   94.88M
20161221-223943    139.89     |  220.00  /   74.84K =   0.29% |    1.34G /    4.41G =  30.36% |  463.13K  100.99M
20161222-223104    131.72     |   88.00  /   74.82K =   0.12% |    1.30G /    4.37G =  29.72% |  447.29K  132.06M
20161223-224139    137.45     |  100.00  /   74.82K =   0.13% |    1.31G /    4.41G =  29.76% |  393.77K  100.01M
20161224-224024    272.91     |   80.00  /   74.81K =   0.11% |    1.28G /    4.37G =  29.17% |  399.00K  108.75M
20161225-224116    139.32     |  122.00  /   74.79K =   0.16% |    1.32G /    4.40G =  29.92% |  443.57K  114.10M
20161226-224748    116.64     |  211.00  /   74.77K =   0.28% |    1.32G /    4.41G =  29.97% |  462.92K  154.75M
20161227-223659    116.24     |   80.00  /   74.75K =   0.11% |    1.30G /    4.41G =  29.58% |  381.03K   38.67M
20161228-223808    121.67     |   80.00  /   74.74K =   0.11% |    1.27G /    4.37G =  28.97% |  383.17K  122.87M
20161229-223024    146.64     |   72.00  /   74.72K =   0.10% |    1.30G /    4.41G =  29.48% |  357.01K  146.53M
20161230-223923    142.18     |  128.00  /   74.70K =   0.17% |    1.32G /    4.41G =  29.86% |  443.95K   99.60M
20161231-223857    124.06     |   80.00  /   74.69K =   0.11% |    1.31G /    4.41G =  29.62% |  393.79K   53.26M
```

#### `du` stats

Shell oneliner to determine the disk space used by given set of snapshots:

    du -hxsc $(ls -rd $snapshots/*/)

This lists the disk usage of each snapshot in reverse order, such that it tells you how much disk space removing the oldest snapshots at the end would free up:

```
4.3G    snapshots/20161231-223857/
1.3G    snapshots/20161230-223923/
1.3G    snapshots/20161229-223024/
1.3G    snapshots/20161228-223808/
1.3G    snapshots/20161227-223659/
1.3G    snapshots/20161226-224748/
1.3G    snapshots/20161225-224116/
1.3G    snapshots/20161224-224024/
1.3G    snapshots/20161223-224139/
1.3G    snapshots/20161222-223104/
1.3G    snapshots/20161221-223943/
1.3G    snapshots/20161219-223721/
1.3G    snapshots/20161218-225629/
1.3G    snapshots/20161217-223717/
1.3G    snapshots/20161216-223854/
1.3G    snapshots/20161215-223047/
1.3G    snapshots/20161214-223013/
1.4G    snapshots/20161213-223119/
1.3G    snapshots/20161212-222952/
```
