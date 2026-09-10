import os

if not os.environ.get("SKIP_INIT"):
    from .main import *
