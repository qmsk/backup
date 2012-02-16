from distutils.core import setup


setup(
    name        = 'pvl.backup',
    version     = '0.1',

    # code
    packages    = ['pvl', 'pvl.backup'],

    # binaries
    scripts     = ['scripts/pvlbackup-rsync-wrapper'],
)
