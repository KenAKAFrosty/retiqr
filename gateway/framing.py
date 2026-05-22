"""Shim — real implementation lives in shared/framing.py."""
import importlib.util, pathlib

_spec = importlib.util.spec_from_file_location(
    "framing",
    pathlib.Path(__file__).parent.parent / "shared" / "framing.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})
