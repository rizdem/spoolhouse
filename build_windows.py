"""
Build Spoolhouse for Windows: the app (PyInstaller, one folder) and its installer (Inno Setup).
Run on Windows, from the project folder:

    uv venv --python 3.12 --python-preference only-managed .venv
    uv pip install --python .venv\\Scripts\\python.exe -r requirements-dev.txt
    .venv\\Scripts\\python.exe build_windows.py

Output: dist\\Spoolhouse\\Spoolhouse.exe and dist\\Spoolhouse-<version>-windows-setup.exe.
Inno Setup 6 must be installed (https://jrsoftware.org/isdl.php); the GitHub build installs it.
"""
import glob
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
PY = sys.executable


def run(*cmd):
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def make_ico():
    """The One Strand icon as a Windows .ico (all the sizes Explorer and the taskbar use)."""
    from PIL import Image
    os.makedirs("build_tmp", exist_ok=True)
    ico = os.path.join("build_tmp", "Spoolhouse.ico")
    Image.open(os.path.join("branding", "Spoolhouse.png")).save(
        ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return os.path.abspath(ico)


def version_file(version):
    """File properties (right-click → Properties → Details) for Spoolhouse.exe."""
    nums = (version.split(".") + ["0", "0", "0"])[:4]
    t = ", ".join(nums)
    path = os.path.abspath(os.path.join("build_tmp", "version.txt"))
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({t}), prodvers=({t})),
  kids=[StringFileInfo([StringTable('080904B0', [
    StringStruct('CompanyName', 'Spoolhouse'),
    StringStruct('FileDescription', 'Spoolhouse - filament inventory for Creality CFS'),
    StringStruct('FileVersion', '{version}'),
    StringStruct('ProductName', 'Spoolhouse'),
    StringStruct('ProductVersion', '{version}'),
    StringStruct('LegalCopyright', 'GNU GPL v3.0'),
    StringStruct('OriginalFilename', 'Spoolhouse.exe')])]),
    VarFileInfo([VarStruct('Translation', [2057, 1200])])])
""")
    return path


def find_iscc():
    for p in [shutil.which("iscc"),
              os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Inno Setup 6", "ISCC.exe"),
              os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Inno Setup 6", "ISCC.exe"),
              os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 6", "ISCC.exe")]:
        if p and os.path.exists(p):
            return p
    sys.exit("Inno Setup 6 not found: install it from https://jrsoftware.org/isdl.php")


def self_test(exe):
    """Run the built app's self-test (it has no console, so the result is read from its log)."""
    log = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Spoolhouse", "Spoolhouse.log")
    before = os.path.getsize(log) if os.path.exists(log) else 0
    code = subprocess.run([exe, "--self-test"], timeout=120).returncode
    with open(log, encoding="utf-8", errors="replace") as f:
        f.seek(before)
        new = f.read()
    print(new.strip())
    if code != 0 or "self-test passed" not in new:
        sys.exit(f"Self-test of the built app failed (exit code {code}).")


def main():
    if sys.platform != "win32":
        sys.exit("Run this on Windows (the Mac builds use build_app.sh).")
    run(PY, "-m", "pytest", "-q", "-p", "no:cacheprovider")
    sys.path.insert(0, HERE)
    import cfs_gui
    name, version = cfs_gui.APP_NAME, cfs_gui.APP_VERSION
    shutil.rmtree(os.path.join("dist", name), ignore_errors=True)
    run(PY, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", name,
        "--icon", make_ico(), "--version-file", version_file(version),
        "--distpath", "dist", "--workpath", os.path.join("build_tmp", "win"), "--specpath", "build_tmp",
        "--paths", HERE, "--add-data", f"{os.path.join(HERE, 'web')}{os.pathsep}web",
        "--collect-submodules", "webview", "--collect-submodules", "smartcard",
        "--hidden-import", "pystray._win32", "--hidden-import", "app_windows",
        "cfs_app.py")
    exe = os.path.join("dist", name, f"{name}.exe")
    self_test(exe)
    run(find_iscc(), f"/DAppVersion={version}", f"/DSourceDir={os.path.join(HERE, 'dist', name)}",
        f"/DIconFile={make_ico()}", f"/DOutputDir={os.path.join(HERE, 'dist')}",
        os.path.join("installer", "spoolhouse.iss"))
    setup = glob.glob(os.path.join("dist", f"{name}-{version}-windows-setup.exe"))
    if not setup:
        sys.exit("The installer wasn't created.")
    shutil.rmtree("build_tmp", ignore_errors=True)
    print(f"Built: {os.path.abspath(exe)}\nInstaller: {os.path.abspath(setup[0])}")


if __name__ == "__main__":
    main()
