"""
Helper: import the car's modules from a checkout, without installing anything.

`course/` is a plain folder of scripts, not a package, and the on-car modules
expect to be run from inside it (course_navigator.py puts its own directory on
sys.path). So the tests load modules by file path rather than by package name.

Nothing here touches hardware. `gpiozero` and `picamera2` are imported lazily
inside the functions that use them, so every module below imports cleanly on a
CI runner with only numpy installed.
"""

import importlib.util
import os
import sys

COURSE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "course")

if COURSE not in sys.path:
    sys.path.insert(0, COURSE)


def load(name, relpath):
    """Load course/<relpath> as a module called <name>."""
    path = os.path.join(COURSE, relpath)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def mission_path(name="demo_course.json"):
    return os.path.join(COURSE, "missions", name)
