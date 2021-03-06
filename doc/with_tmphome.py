""" helper to run a command with a clean empty temporary home directory. """
from __future__ import unicode_literals
import os
import sys
import shutil
import subprocess


if __name__ == "__main__":
    #tmphome = sys.argv[1] output is uglier in the docs
    tmphome = "/tmp/home"
    tmphome = os.path.abspath(tmphome)
    assert tmphome
    if os.path.exists(tmphome):
        shutil.rmtree(tmphome)
    os.makedirs(os.path.join(tmphome, ".config"))
    gnupghome = os.path.join(tmphome, ".gnupg")
    os.mkdir(gnupghome)
    os.chmod(gnupghome, 0o700)
    os.environ["HOME"] = tmphome
    os.environ["USER"] = "tmpuser"
    os.environ["GNUPGHOME"] = gnupghome
    sys.exit(subprocess.call(sys.argv[1:]))
