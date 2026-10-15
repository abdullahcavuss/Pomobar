# Pomobar

Pomobar is a sleek and customizable Pomodoro timer built with Python and PyQt5. It lives as a thin, always-on-top progress bar at the edge of your screen, so you always see how much of your work or break session is left without it getting in the way.

## Download (Windows)

Grab the latest version from the [Releases page](https://github.com/abdullahcavuss/Pomobar/releases/latest):

- **Pomobar-Setup-x.y.z.exe**: installer with Start menu entry, optional "start with Windows" and an uninstaller. No admin rights needed.
- **Pomobar-x.y.z-portable.zip**: no installation needed. Unzip anywhere and run `Pomobar.exe`.

> Windows SmartScreen may warn about an unknown publisher because the app isn't code-signed. Click **More info → Run anyway**.

## Features

- Thin progress bar that expands on hover to show remaining time, session dots and controls
- Work, short break and long break (every N sessions)
- Tray icon with a live progress ring, plus a notification and sound when a session ends
- Optionally wait for a click before starting the next session
- Right-click menu: pause, skip, reset, settings, quit
- Custom durations, colours (with transparency), position and size
- Settings saved to `%APPDATA%\Pomobar\config.json`

## Usage

| Action | How |
| --- | --- |
| Show time & buttons | Hover over the bar |
| Pause / resume | Hover button, right-click menu, or click the tray icon |
| Settings | Double-click the bar or the tray icon |
| Start the next session (when waiting) | Click the bar |
| Quit | Right-click → Quit |

## Run from source

```bat
pip install -r requirements.txt
python pomoBar_v2.py
```

## Build it yourself

On Windows, run:

```bat
build.bat
```

It creates a virtual environment, builds `dist\Pomobar\Pomobar.exe` with PyInstaller, zips a portable copy and, if [Inno Setup 6](https://jrsoftware.org/isdl.php) is installed, builds the installer too.

### Publishing a release

Push a version tag and GitHub Actions builds and publishes the downloads automatically:

```bat
git tag v2.0.0
git push origin v2.0.0
```

## License

MIT, see [LICENSE](LICENSE).
