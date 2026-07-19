use std::{sync::Mutex, thread, time::Duration};
use tauri::{Manager, Url};
use tauri_plugin_shell::{process::CommandChild, ShellExt};

struct Backend(Mutex<Option<CommandChild>>);

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let (_, child) = app
                .shell()
                .sidecar("asksql-server")?
                .args(["ui", "--no-open"])
                .spawn()?;
            app.manage(Backend(Mutex::new(Some(child))));
            let handle = app.handle().clone();
            thread::spawn(move || {
                thread::sleep(Duration::from_millis(900));
                if let Some(window) = handle.get_webview_window("main") {
                    let url = Url::parse("http://127.0.0.1:7331/").expect("valid Studio URL");
                    let _ = window.navigate(url);
                }
            });
            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::Destroyed) {
                if let Some(backend) = window.app_handle().try_state::<Backend>() {
                    if let Some(child) = backend.0.lock().expect("backend lock").take() {
                        let _ = child.kill();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running AskSQL Studio");
}
