# encoding: utf-8

from distutils.core import setup

setup(
    name            = 'pvl-backup',
    version         = '1.3-dev',

    description     = "Paivola rsync backup utilities",
    url             = 'http://verkko.paivola.fi/hg/pvl-backup/',
    license         = 'MIT',

    author          = 'Tero Marttila',
    author_email    = 'terom@paivola.fi',

    namespace_packages = [
        'pvl',
    ],
    packages = [
        'pvl.backup',
    ],
    py_modules = [
        'pvl.args',
        'pvl.invoke',
    ],

    install_requires = [

    ],

    # binaries
    scripts = [
        'bin/pvl.backup-rsync',
        'bin/pvl.backup-target',
        'bin/pvl.backup-zfs',
        'bin/pvl.zfs-ssh-command',
        'bin/pvl.zfs-sync',
    ],
)
