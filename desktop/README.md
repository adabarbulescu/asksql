# AskSQL Studio desktop

The Tauri shell bundles a PyInstaller `asksql-server` sidecar and opens the same localhost-only Studio used by
`asksql ui`. This keeps one backend implementation for CLI, browser Studio, and desktop.

Release builds are produced by `.github/workflows/desktop.yml`. Signed updater artifacts require the repository
secrets `TAURI_SIGNING_PRIVATE_KEY` and `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`; releases deliberately fail closed when
those credentials are absent.
