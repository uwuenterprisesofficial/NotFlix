The desktop app's latest release, served by the backend at `/updates/` for the app's
auto-update (electron-updater, generic provider). `scripts/publish.sh` copies it here from
`desktop/dist` before building the backend image; the files themselves aren't committed.
