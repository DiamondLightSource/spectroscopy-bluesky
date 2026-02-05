import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version

import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator


def install_package(pkg_string: str) -> None :
    """
        Install package using pip install for install_package
        :param pkg_string: name of package to install. It can also include version
        specifier (e.g. 'numpy', or 'matplotlib==3.10.3')
    """
    print("Installing {pkg_string}")
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg_string])

def check_install_packages(package_names : list[str]) -> MsgGenerator :
    """
    Docstring for check_intstall_packages

    :param package_names: Description
    :type package_names: 
    """
    for pkg_string in package_names :

        # split string to separate package name from the version (regex that splits on
        # ==, >=, < etc would be better!)
        pkg_arr = pkg_string.split("==")

        pkg_name = pkg_arr[0]
        pkg_version = pkg_arr[1] if len(pkg_arr) == 2 else ""
        print(f"Checking for {pkg_name} {pkg_version}")

        try :
            # see if module is installed in environment
            version_string = version(pkg_name)

            print(f"{pkg_name} version {version_string} found")
            # update package if installed version doesn't match specified version
            if pkg_version != "" and version_string != pkg_version :
                print("f{pkg_name} version {pkg_version} required")
                install_package(pkg_string)

        except PackageNotFoundError as pe :
            # Install package if it's installed in environment
            print("Package "+pe.name+" not found")
            print("Install "+pkg_name+" "+pkg_version)
            install_package(pkg_string)

    # yield somthing, to keep RunEngine happy!
    yield from bps.sleep(1)

