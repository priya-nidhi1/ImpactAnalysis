import pathlib
import sys

# Make the ``impact`` package importable without an install step.
sys.path.insert(0, str(pathlib.Path(__file__).parent / "src"))
