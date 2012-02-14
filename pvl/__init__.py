# Namespace package
# http://docs.python.org/library/pkgutil.html#pkgutil.extend_path

from pkgutil import extend_path

# magic to support further pvl.foo packages
__path__ == extend_path(__path__, __name__)
