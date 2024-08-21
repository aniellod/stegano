import launch

ST_VERSION = "1.0"
needs_install = False

try:
    import jpeg_toolbox
    if stegato.__version__ != ST_VERSION:
        needs_install = True
except ImportError:
    needs_install = True

if needs_install:
    launch.run_pip(f"install git+https://github.com/aniellod/python-jpeg-toolbox", "requirements for stegano")
