"""Deploy the full bot stack (router + chore + rental). Run from the repo root instead."""

import os
import runpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
runpy.run_path(os.path.join(ROOT, "deploy_stack.py"), run_name="__main__")
