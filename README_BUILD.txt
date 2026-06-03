MirthPluginSigner — Distribution Package
==========================================

CONTENTS
--------
  MirthPluginSigner          Linux x86-64 standalone executable (run directly)
  mirth_plugin_signer.py     Python source (rebuild on any platform)
  MirthPluginSigner.spec     PyInstaller build spec
  build_windows.bat          One-click Windows .exe builder
  build_linux.sh             One-click Linux / macOS builder
  README_BUILD.txt           This file


HOW TO RUN (no build needed)
-----------------------------

  Linux (x86-64):
    chmod +x MirthPluginSigner
    ./MirthPluginSigner

  Any platform with Python 3.8+:
    python mirth_plugin_signer.py


BUILD YOUR OWN EXECUTABLE
--------------------------

  Windows → MirthPluginSigner.exe  (no CMD window, native .exe):
    1. Install Python 3.8+ from https://python.org  (tick "Add to PATH")
    2. Double-click  build_windows.bat
    3. Find MirthPluginSigner.exe in  dist\

  Linux / macOS → MirthPluginSigner  (native binary):
    1. bash build_linux.sh
    2. Find binary in  dist/

  The output is a single self-contained file — copy it anywhere,
  no Python installation needed on the target machine.


REQUIREMENTS AT RUNTIME
------------------------
  - Java JDK on PATH (provides keytool + jarsigner)
  - On Linux: libX11 / libXext / Tk (usually pre-installed on desktop)
  - On Windows: nothing extra needed


FOLDER STRUCTURE (alongside the executable)
--------------------------------------------
  MirthPluginSigner.exe   ← or ./MirthPluginSigner on Linux
  config/                 ← auto-created; stores config.json
  plugins/
    <plugin-name>/        ← place JARs, WARs, plugin.xml here
  sign/                   ← signed output written here automatically
  certificates/           ← keystore + .cer auto-generated


LINUX DESKTOP SHORTCUT
-----------------------
  Create  ~/.local/share/applications/mirth-plugin-signer.desktop :

    [Desktop Entry]
    Name=Mirth Plugin Signer
    Exec=/path/to/MirthPluginSigner
    Type=Application
    Terminal=false
    Categories=Development;

  Then:  chmod +x ~/.local/share/applications/mirth-plugin-signer.desktop

