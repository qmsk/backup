from distutils.core import setup


setup(
    name            = 'pvl.backup',
    version         = '0.2.2',

    url             = 'http://hg.qmsk.net/pvl-backup/',
    author          = 'Tero Marttila',
    author_email    = 'terom@paivola.fi',

    # code
    packages        = ['pvl', 'pvl.backup'],

    # binaries
    scripts         = [
        'scripts/pvlbackup-rsync-wrapper', 
        'scripts/pvlbackup-rsync-snapshot',
    ],
)
