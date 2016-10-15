# encoding: utf-8

from distutils.core import setup

setup(
    name            = 'pvl-backup',
    version         = '1.0.0-dev',

    description     = "Päivölä rsync backup utilities",
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

    install_requires = [
        'pvl-common>=1.0.0-dev, <2'
    ],
 
    # binaries
    scripts = [
        'bin/pvl.backup-rsync', 
        'bin/pvl.backup-target',
        'bin/pvl.backup-zfs',
    ],
)
