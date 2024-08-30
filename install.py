import launch
from setuptools import setup, Extension
import subprocess
import sys

ST_VERSION = "1.0"
needs_install = False

# Helper function to check for a library
def check_library(lib_name):
    try:
        subprocess.check_call(["pkg-config", "--exists", lib_name])
        return True
    except subprocess.CalledProcessError:
        return False

# Check for libexif and libjpeg
missing_libraries = []
if not check_library("libexif"):
    missing_libraries.append("libexif")
if not check_library("libjpeg"):
    missing_libraries.append("libjpeg")

if missing_libraries:
    print("The following required libraries are missing: " + ", ".join(missing_libraries))
    print("Please install them before continuing.")
    sys.exit(1)

try:
    import jpeg_toolbox
    if jpeg_toolbox.version != ST_VERSION:
        needs_install = True
except ImportError:
    needs_install = True

if needs_install:
    launch.run_pip(f"install git+https://github.com/aniellod/python-jpeg-toolbox", "requirements for stegano")
