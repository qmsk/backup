# encoding: utf-8

from distutils.core import setup

setup(
    name            = 'qmsk-backup',
    version         = '1.6-dev',

    description     = "Automated LVM/ZFS snapshot, rsync backups",
    url             = 'https://github.com/qmsk/backup',
    license         = 'MIT',

    author          = 'Tero Marttila',
    author_email    = 'terom@fixme.fi',

    namespace_packages = [
        'qmsk',
    ],
    packages = [
        'qmsk.backup',
    ],
    py_modules = [
        'qmsk.args',
        'qmsk.invoke',
    ],

    install_requires = [

    ],

    # binaries
    scripts = [
        'bin/qmsk.backup-rsync',
        'bin/qmsk.backup-zfs',
        'bin/qmsk.rsync-ssh-command',
        'bin/qmsk.zfs-ssh-command',
        'bin/qmsk.zfs-sync',
    ],
)
