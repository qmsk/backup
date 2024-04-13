"""
    rsync-based backups.

    Supports LVM w/ snapshots.
"""

try:
    import importlib.metadata

    __version__ = importlib.metadata.version('qmsk-backup')

except ImportError:
    import pkg_resources

    __version__ = pkg_resources.get_distribution('qmsk-backup').version
