from distutils.core import setup

# XXX: for determining version
import pvl.backup

setup(
    name            = 'pvl.backup',
    version         = pvl.backup.__version__,

    url             = 'http://hg.qmsk.net/pvl-backup/',
    author          = 'Tero Marttila',
    author_email    = 'terom@paivola.fi',

    # code
    packages        = ['pvl', 'pvl.backup'],

    # binaries
    scripts         = [
        'bin/pvl.backup-rsync', 
        'bin/pvlbackup-rsync-snapshot',
    ],
)
