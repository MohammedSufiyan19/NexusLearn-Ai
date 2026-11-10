"""
NexusLearn AI — Backend Package Initializer.
Ensures backend directory is on sys.path for top-level 'app' imports.
"""
import os
import sys

_backend_dir = os.path.dirname(os.path.abspath(__file__))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)
