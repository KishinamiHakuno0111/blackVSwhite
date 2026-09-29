"""Bundle Tcl/Tk scripts explicitly, including Tcl 9's DLL-embedded ZIPs."""

from pathlib import Path
import shutil
import sys
from importlib.metadata import distribution
import zipfile

from PyInstaller.utils.hooks.tcl_tk import tcltk_info


def collect(source, library, prefix, target):
    target.mkdir(parents=True, exist_ok=True)
    if source and Path(source).is_dir():
        shutil.copytree(source, target, dirs_exist_ok=True)
    elif library and zipfile.is_zipfile(library):
        with zipfile.ZipFile(library) as archive:
            for name in archive.namelist():
                if not name.startswith(prefix + "/") or name.endswith("/"):
                    continue
                relative = Path(name[len(prefix) + 1:])
                destination = (target / relative).resolve()
                if not destination.is_relative_to(target.resolve()):
                    raise ValueError("Invalid Tcl/Tk archive path")
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.read(name))
    else:
        raise RuntimeError(f"Cannot locate the {prefix} runtime resources")


if __name__ == "__main__":
    output = Path(__file__).resolve().parents[1] / "build" / "tk"
    collect(tcltk_info.tcl_data_dir, tcltk_info.tcl_shared_library, "tcl_library", output / "_tcl_data")
    collect(tcltk_info.tk_data_dir, tcltk_info.tk_shared_library, "tk_library", output / "_tk_data")
    for directory, required in (("_tcl_data", "init.tcl"), ("_tk_data", "tk.tcl")):
        if not (output / directory / required).is_file():
            raise RuntimeError(f"Missing {required}")
    notices = output.parent / "licenses"
    notices.mkdir(exist_ok=True)
    shutil.copy2(Path(sys.base_prefix) / "LICENSE.txt", notices / "Python.txt")
    for directory, label in (("_tcl_data", "Tcl"), ("_tk_data", "Tk")):
        shutil.copy2(output / directory / "license.terms", notices / (label + ".txt"))
    package = distribution("pyinstaller")
    license_file = next(p for p in package.files if str(p).endswith("licenses/COPYING.txt"))
    shutil.copy2(package.locate_file(license_file), notices / "PyInstaller.txt")
    print("Tcl/Tk runtime scripts ready")
