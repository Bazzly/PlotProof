"""
Shared JS/CSS for PlotProof's static Streamlit map components
(utils/shape_georeferencer, utils/map_traverse_sketch,
utils/image_traverse_sketch) - see DIAGONAL_CALCULATOR_AUDIT.md section 2
for why this exists: three components independently duplicated the same
postMessage protocol boilerplate, the same ResizeObserver height fix, and
(in two of them) the same bearing/distance math - one real bug and one
latent inconsistency already slipped through that duplication before this
existed.

Each component's __init__.py calls sync_into() once at import time to copy
shared.js/shared.css into its own frontend/ directory. Copying rather than
a relative-path <script src="../../..."> reference or a symlink: Streamlit
serves each declare_component() path in isolation (no way to load a file
living outside it directly), and a plain file copy works identically
across OSes and survives a zip-based deploy, unlike a symlink.
"""

import shutil
from pathlib import Path

_SHARED_DIR = Path(__file__).resolve().parent
_SHARED_FILES = ("shared.js", "shared.css")


def sync_into(frontend_dir: str) -> None:
    """Copies this module's shared.js/shared.css into frontend_dir,
    overwriting any existing copy there - called once per component module
    import (cheap; these are small files), so an edit to the shared source
    is picked up the next time the app restarts with no separate build
    step to remember."""
    frontend_path = Path(frontend_dir)
    for name in _SHARED_FILES:
        shutil.copyfile(_SHARED_DIR / name, frontend_path / name)
