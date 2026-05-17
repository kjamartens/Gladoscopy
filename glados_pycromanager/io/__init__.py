"""Persistent IO helpers (AppData JSON, temp-folder cleanup).

Note: this shadows the stdlib `io` *within* the `glados_pycromanager`
namespace, but external callers reach the stdlib by plain `import io`,
which resolves to the standard library — only `from
glados_pycromanager.io ...` would touch this package.
"""

from glados_pycromanager.io.appdata import (  # noqa: F401
    appdata_root,
    cleanUpTemporaryFiles,
    glados_state_path,
    load_config_from_json,
    save_config_to_json,
    storeSharedData_GlobalData,
)
