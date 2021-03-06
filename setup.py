# Copyright 2022 Mathworks, Inc.

from setuptools import setup, find_packages
from setuptools.command.build_py import build_py 
import os
import sys
import platform
import xml.etree.ElementTree as xml
if platform.system() == 'Windows':
    import winreg

class _MatlabFinder(build_py):
    """
    Private class that finds MATLAB on user's computer prior to package installation.
    """
    PLATFORM_DICT = {
        'Windows': 'PATH', 
        'Linux': 'LD_LIBRARY_PATH', 
        'Darwin': 'DYLD_LIBRARY_PATH'
    }
    
    # MUST_BE_UPDATED_EACH_RELEASE (Search repo for this string)
    MATLAB_REL = 'R2022a'

    # MUST_BE_UPDATED_EACH_RELEASE (Search repo for this string)
    MATLAB_VER = '9.12' 

    # MUST_BE_UPDATED_EACH_RELEASE (Search repo for this string)
    SUPPORTED_PYTHON_VERSIONS = set(['3.8', '3.9'])

    # MUST_BE_UPDATED_EACH_RELEASE (Search repo for this string)
    VER_TO_REL = {
        "9.6": "R2019a",
        "9.7": "R2019b",
        "9.8": "R2020a",
        "9.9": "R2020b",
        "9.10": "R2021a",
        "9.11": "R2021b",
        "9.12": "R2022a"
    }

    DEFAULT_INSTALLS = {
        'Darwin': f"/Applications/MATLAB_{MATLAB_REL}.app",
        'Linux': f"/usr/local/MATLAB/{MATLAB_REL}"
    }

    arch = ''
    path_name = ''
    python_ver = ''
    platform = ''
    found_matlab = ''

    # ERROR MESSAGES
    minimum_required = "No compatible version of MATLAB was found. This feature supports MATLAB R2019a and later."
    dir_not_found = "Directory not found: "
    install_compatible = "To install a compatible version, call python -m pip install matlabengine=="
    no_windows_install = "MATLAB installation not found in Windows Registry:"
    unsupported_platform = "{platform:s} is not a supported platform."
    unsupported_python = "{python:s} is not supported. The supported Python versions are {supported:s}."
    set_path = "MATLAB installation not found in {path1:s}. Add matlabroot/bin/{arch:s} to {path2:s}."
    no_compatible_matlab = "No compatible MATLAB installation found in Windows Registry. This release of " + \
        "MATLAB Engine API for Python is compatible with version {ver:s}. The found versions were"
    no_matlab = "No MATLAB installation found in Windows Registry."
    incompatible_ver = "MATLAB version {ver:s} was found, but MATLAB Engine API for Python is not compatible with it. " + \
        "To install a compatible version, call python -m pip install matlabengine=={found:s}."
    
    def set_platform_and_arch(self):
        """
        Sets the platform and architecture. 
        """
        self.platform = platform.system()
        if self.platform not in self.PLATFORM_DICT:
            raise RuntimeError(self.unsupported_platform.format(platform=self.platform))
        else:
            self.path_name = self.PLATFORM_DICT[self.platform]
        
        if self.platform == 'Windows':
            self.arch = 'win64'
        elif self.platform == 'Linux':
            self.arch = 'glnxa64'
        elif self.platform == 'Darwin':
            if platform.mac_ver()[-1] == 'arm64':
                self.arch = 'maca64'
            else:
                self.arch = 'maci64'
        else:
            raise RuntimeError(self.unsupported_platform.format(platform=self.platform))
    
    def set_python_version(self):
        """
        Gets Python version and ensures it is supported.
        """
        ver = sys.version_info
        self.python_ver = f"{ver.major}.{ver.minor}"

        if self.python_ver not in self.SUPPORTED_PYTHON_VERSIONS:
            raise RuntimeError(self.unsupported_python.format(python=self.python_ver, supported=str(self.SUPPORTED_PYTHON_VERSIONS)))

    def unix_default_install_exists(self):
        """
        Determines whether MATLAB is installed in default UNIX location.
        """
        path = self.DEFAULT_INSTALLS[self.platform]
        return os.path.exists(path)
    
    def _create_path_list(self):
        """
        Creates a list of directories on the path to be searched.
        """
        path_dirs = []
        path_string = ''
        if self.path_name in os.environ:
            path_string = os.environ[self.path_name]
            path_dirs.extend(path_string.split(os.pathsep))
        
        if not path_dirs:
            raise RuntimeError(self.set_path.format(path1=self.path_name, arch=self.arch, path2=self.path_name))
        
        return path_dirs
    
    def _get_matlab_root_from_unix_bin(self, dir):
        """
        Searches bin directory for presence of MATLAB file. Used only for
        UNIX systems. 
        """
        matlab_path = os.path.join(dir, 'MATLAB')
        possible_root = os.path.normpath(os.path.join(dir, os.pardir, os.pardir))
        matlab_root = ''
        if os.path.isfile(matlab_path) and self.verify_matlab_release(possible_root):
            matlab_root = possible_root
            
        return matlab_root
    
    def get_matlab_root_from_windows_reg(self):
        """
        Searches Windows Registry for MATLAB installs and gets the root directory of MATLAB.
        """
        try:
            reg = winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)
            key = winreg.OpenKey(reg, "SOFTWARE\\MathWorks\\MATLAB")
        except OSError as err:
            raise RuntimeError(f"{self.no_windows_install} {err}")
        
        matlab_ver_key = self._find_matlab_key_from_windows_registry(key)
        return self._get_root_from_version_key(reg, matlab_ver_key)
    
    def _get_root_from_version_key(self, reg, ver_key):
        """
        Opens a registry corresponding to the version of MATLAB specified and queries for
        MATLABROOT.
        """
        try:
            key = winreg.OpenKey(reg, "SOFTWARE\\MathWorks\\MATLAB\\" + ver_key)
            matlab_root = winreg.QueryValueEx(key, "MATLABROOT")[0]
        except (OSError, FileNotFoundError) as err:
            raise RuntimeError(f"{self.no_windows_install} {err}")
        
        return matlab_root
    
    def _find_matlab_key_from_windows_registry(self, key):
        """
        Searches the MATLAB folder in Windows registry for the specified version of MATLAB. When found, 
        the MATLAB root directory will be returned.
        """
        # QueryInfoKey returns a tuple, index 0 is the number of sub keys we need to search
        num_keys = winreg.QueryInfoKey(key)[0]
        key_value = ''
        found_vers = []
        for idx in range(num_keys):
            sub_key = winreg.EnumKey(key, idx)
            found_vers.append(sub_key)
            # Example: the version in the registry could be "9.13.1" whereas our version is "9.13"
            # we still want to allow this
            if sub_key.startswith(self.MATLAB_VER):
                key_value = sub_key
                break
        
        if not key_value:
            if found_vers:
                vers = ', '.join(found_vers)
                raise RuntimeError(f"{self.no_compatible_matlab.format(ver=self.MATLAB_VER)} {vers}. {self.install_compatible}{found_vers[-1]}.")
            else:
                raise RuntimeError(f"{self.no_matlab}")

        return key_value       

    def verify_matlab_release(self, root):
        """
        Parses VersionInfo.xml to verify the MATLAB release matches the supported release
        for the Python Engine.
        """
        version_info = os.path.join(root, 'VersionInfo.xml')
        if not os.path.isfile(version_info):
            return False
        
        tree = xml.parse(version_info)
        tree_root = tree.getroot()

        matlab_release = ''
        for child in tree_root:
            if child.tag == 'release':
                matlab_release = self.found_matlab = child.text
                break
        
        if matlab_release != self.MATLAB_REL:
            return False
        return True

    def search_path_for_directory_unix(self):
        """
        Used for finding MATLAB root in UNIX systems. Searches all paths ending in
        /bin/<arch> for the presence of MATLAB file to ensure the path is within
        the MATLAB tree. 
        """
        path_dirs = self._create_path_list()
        dir_to_find = os.path.join('bin', self.arch)
        # directory could end with slashes
        endings = [dir_to_find, dir_to_find + os.sep]

        matlab_root = ''
        dir_idx = 0
        while not matlab_root and dir_idx < len(path_dirs):
            path = path_dirs[dir_idx]
            ending_idx = 0
            while not matlab_root and ending_idx < len(endings):
                ending = endings[ending_idx]
                if path.endswith(ending):
                    # _get_matlab_root_from_unix_bin will return an empty string if MATLAB is not found
                    # non-empty string (MATLAB found) will break both loops
                    matlab_root = self._get_matlab_root_from_unix_bin(path)
                ending_idx += 1
            dir_idx += 1
        
        if not matlab_root:
            if self.found_matlab:
                if self.found_matlab in self.VER_TO_REL:
                    raise RuntimeError(self.incompatible_ver.format(ver=self.VER_TO_REL[self.found_matlab], found=self.found_matlab))
                # we found a MATLAB release but it is older than R2019a
                else:
                    raise RuntimeError(self.minimum_required)
            else:
                raise RuntimeError(self.set_path.format(path1=self.path_name, arch=self.arch, path2=self.path_name))
        
        if not os.path.isdir(matlab_root):
            raise RuntimeError(f"{self.dir_not_found} {matlab_root}")
        return matlab_root
    
    def write_text_file(self, matlab_root):
        """
        Writes root.txt for use at import time.
        """
        file_location = os.path.join(os.getcwd(), 'src', 'matlab', 'engine', '_arch.txt')
        bin_arch = os.path.join(matlab_root, 'bin', self.arch)
        engine_arch = os.path.join(matlab_root, 'extern', 'engines', 'python', 'dist', 'matlab', 'engine', self.arch)
        extern_bin = os.path.join(matlab_root, 'extern', 'bin', self.arch)
        with open(file_location, 'w') as root_file:
            root_file.write(self.arch + '\n')
            root_file.write(bin_arch + '\n')
            root_file.write(engine_arch + '\n')
            root_file.write(extern_bin)

    def run(self):
        """
        Logic that runs prior to installation.
        """
        self.set_platform_and_arch()
        self.set_python_version()

        if self.platform == 'Windows':
            matlab_root = self.get_matlab_root_from_windows_reg()
        else:
            if self.unix_default_install_exists():
                matlab_root = self.DEFAULT_INSTALLS[self.platform]
            else:
                matlab_root = self.search_path_for_directory_unix()
        self.write_text_file(matlab_root)
        build_py.run(self)


if __name__ == '__main__':
    with open('README.md', 'r', encoding='utf-8') as rm:
        long_description = rm.read()

    setup(
        name="pythonengine",
        # MUST_BE_UPDATED_EACH_RELEASE (Search repo for this string)
        version="9.13",
        description='A module to call MATLAB from Python',
        author='MathWorks',
        license="MathWorks XSLA License",
        url='https://github.com/mathworks/matlab-engine-for-python/',
        long_description=long_description,
        long_description_content_type="text/markdown",
        package_dir={'': 'src'},
        packages=find_packages(where="src"),
        cmdclass={'build_py': _MatlabFinder},
        package_data={'': ['_arch.txt']},
        zip_safe=False,
        project_urls={
            'Documentation': 'https://www.mathworks.com/help/matlab/matlab-engine-for-python.html',
            'Source': 'https://github.com/mathworks/matlab-engine-for-python',
            'Tracker': 'https://github.com/mathworks/matlab-engine-for-python/issues'
        },
        keywords=[
            "MATLAB",
            "MATLAB Engine for Python"
        ],
        classifiers=[
            "Natural Language :: English",
            "Intended Audience :: Developers",
            # MUST_BE_UPDATED_EACH_RELEASE (Search repo for this string)
            "Programming Language :: Python :: 3.8",
            "Programming Language :: Python :: 3.9"
        ],
        # MUST_BE_UPDATED_EACH_RELEASE (Search repo for this string)
        python_requires=">=3.8, <3.10"
    )
