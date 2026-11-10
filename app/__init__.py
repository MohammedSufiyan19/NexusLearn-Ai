"""NexusLearn AI — App Namespace Forwarder.

Allows 'app' package to resolve to 'backend/app' when running from project root.
"""
import sys
from pathlib import Path

_backend_dir = str(Path(__file__).resolve().parent.parent / "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

_backend_app_dir = str(Path(__file__).resolve().parent.parent / "backend" / "app")
__path__ = [_backend_app_dir]
