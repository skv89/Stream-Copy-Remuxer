# Third-Party Notices

Stream Copy Remuxer 1.3.2 is packaged with Python 3.11, Tcl/Tk, TkinterDnD2/TkDND, and the PyInstaller bootloader. Their license texts are included in the release `licenses` folder.

## FFmpeg and FFprobe

FFmpeg and FFprobe are **not distributed in this application package**. The application first invokes a compatible paired installation already present on the user's computer. If it is missing or older than the current stable release, the user can choose to download the gyan.dev Windows release build linked by FFmpeg.org. The app verifies the provider-published SHA-256 checksum and installs the selected release into a versioned `ffmpeg` subfolder beside the app. That optional download remains governed by its own GPLv3 license and build configuration; its archive includes its license and readme material.

FFmpeg project information: https://ffmpeg.org/

Windows build provider: https://www.gyan.dev/ffmpeg/builds/

## TkinterDnD2 and TkDND

TkinterDnD2 0.6.2 is an MIT-licensed Python wrapper and packaged Tk extension for native OLE2 drag-and-drop on Windows. See `licenses/TkinterDnD2-MIT-LICENSE.txt`.

Project information: https://github.com/Eliav2/tkinterdnd2

## Python

Python Software Foundation License. See `licenses/Python-3.11-LICENSE.txt`.

## Tcl/Tk

BSD-style Tcl/Tk license. See `licenses/Tcl-Tk-license.terms`.

## PyInstaller

GPL license with the PyInstaller bootloader exception. See `licenses/PyInstaller-COPYING.txt`.
