from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
from pathlib import Path


TCL_GLOBAL_ONLY = 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dll", type=Path)
    parser.add_argument("library", type=Path)
    args = parser.parse_args()
    dll_path = args.dll.resolve()
    library = args.library.resolve()
    dll_directory = os.add_dll_directory(str(dll_path.parent))
    try:
        tcl = ctypes.WinDLL(str(dll_path))
        tcl.Tcl_FindExecutable.argtypes = [ctypes.c_char_p]
        tcl.Tcl_FindExecutable.restype = None
        tcl.Tcl_CreateInterp.argtypes = []
        tcl.Tcl_CreateInterp.restype = ctypes.c_void_p
        tcl.Tcl_SetVar.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
        tcl.Tcl_SetVar.restype = ctypes.c_char_p
        tcl.Tcl_EvalFile.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        tcl.Tcl_EvalFile.restype = ctypes.c_int
        tcl.Tcl_GetStringResult.argtypes = [ctypes.c_void_p]
        tcl.Tcl_GetStringResult.restype = ctypes.c_char_p
        tcl.Tcl_GetVar.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        tcl.Tcl_GetVar.restype = ctypes.c_char_p
        tcl.Tcl_DeleteInterp.argtypes = [ctypes.c_void_p]
        tcl.Tcl_DeleteInterp.restype = None

        tcl.Tcl_FindExecutable(os.fsencode(sys.executable))
        interpreter = tcl.Tcl_CreateInterp()
        if not interpreter:
            raise RuntimeError("Tcl_CreateInterp returned NULL")
        try:
            library_text = str(library).replace("\\", "/").encode("utf-8")
            tcl.Tcl_SetVar(interpreter, b"tcl_library", library_text, TCL_GLOBAL_ONLY)
            code = tcl.Tcl_EvalFile(interpreter, str(library / "init.tcl").replace("\\", "/").encode("utf-8"))
            result = (tcl.Tcl_GetStringResult(interpreter) or b"").decode("utf-8", errors="replace")
            error_info_raw = tcl.Tcl_GetVar(interpreter, b"errorInfo", TCL_GLOBAL_ONLY)
            error_info = (error_info_raw or b"").decode("utf-8", errors="replace")
            print(
                json.dumps(
                    {
                        "dll": str(dll_path),
                        "library": str(library),
                        "init_exists": (library / "init.tcl").is_file(),
                        "return_code": code,
                        "result": result,
                        "error_info": error_info,
                    },
                    indent=2,
                )
            )
            return 0 if code == 0 else 1
        finally:
            tcl.Tcl_DeleteInterp(interpreter)
    finally:
        dll_directory.close()


if __name__ == "__main__":
    raise SystemExit(main())

