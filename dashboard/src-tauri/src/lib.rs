//! Tauri entry point. The window loads the static SvelteKit build (or the dev
//! server in `tauri dev`); the dashboard talks to the FastAPI backend over HTTP
//! via `VITE_API_BASE`, so no Rust-side commands are needed yet.

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
