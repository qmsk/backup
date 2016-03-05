# encoding: utf-8

from distutils.core import setup

setup(
    name            = 'pvl-backup',
    version         = '1.0-dev',
    description     = "Päivölä rsync backup utilities",
    url             = 'http://verkko.paivola.fi/hg/pvl-backup/',
    license         = 'MIT',

    author          = 'Tero Marttila',
    author_email    = 'terom@paivola.fi',

    # deps
    install_requires    = [
        # pvl.args
        # pvl.invoke
        'pvl-common >= 0.5.1',
    ],
 
    # lib
    namespace_packages = [ 'pvl' ],
    packages        = [
        'pvl',
        'pvl.backup',
    ],

    # binaries
    scripts         = [
        'bin/pvl.backup-rsync', 
        'bin/pvl.backup-snapshot',
        'bin/pvl.backup-zfs',
    ],
)
