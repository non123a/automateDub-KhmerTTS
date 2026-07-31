# Install

AutomateDub Studio is distributed as platform packages so users do not need a
Python development environment.

## Windows

Download the Windows installer:

```text
AutomateDub-Studio-<version>-windows-setup.exe
```

Run the installer and open AutomateDub Studio from the Start menu. The installer
registers `.autodub` projects so double-clicking a project opens Studio.

## macOS

Download either:

```text
AutomateDub-Studio-<version>-macos.dmg
```

or the `.app` bundle from the release assets. Drag the application into
`Applications`. The bundle declares `.autodub` project support.

## Linux

Download:

```text
AutomateDub-Studio-<version>-linux.AppImage
```

Make it executable and run it:

```bash
chmod +x AutomateDub-Studio-<version>-linux.AppImage
./AutomateDub-Studio-<version>-linux.AppImage
```

Desktop integration metadata lives in the AppImage and includes the
`.autodub` MIME association.

## External Tools

The application still depends on system media capabilities. FFmpeg and FFprobe
must be available for processing, proxy creation, and export workflows.
