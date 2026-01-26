//! Kom-Emine Route Planner - Terminal UI
//!
//! Plan multi-day hikes on Bulgaria's 555km Kom-Emine (E3) trail.

mod app;
mod db;
mod ui;

use anyhow::{Context, Result};
use app::{App, InputMode, SearchDirection};
use crossterm::{
    event::{self, DisableMouseCapture, EnableMouseCapture, Event, KeyCode, KeyEventKind, KeyModifiers},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::{backend::CrosstermBackend, Terminal};
use std::io;
use std::path::PathBuf;

fn main() -> Result<()> {
    // Find database path
    let db_path = find_database()?;

    // Setup terminal
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen, EnableMouseCapture)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    // Create app and run
    let mut app = App::new(db_path)?;
    let result = run_app(&mut terminal, &mut app);

    // Restore terminal
    disable_raw_mode()?;
    execute!(
        terminal.backend_mut(),
        LeaveAlternateScreen,
        DisableMouseCapture
    )?;
    terminal.show_cursor()?;

    if let Err(err) = result {
        eprintln!("Error: {err:?}");
    }

    Ok(())
}

fn find_database() -> Result<PathBuf> {
    // Try relative paths from likely locations
    let candidates = [
        PathBuf::from("data/kom-emine.db"),
        PathBuf::from("../data/kom-emine.db"),
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../data/kom-emine.db"),
    ];

    for path in &candidates {
        if path.exists() {
            return Ok(path.clone());
        }
    }

    // Try from environment
    if let Ok(path) = std::env::var("KOM_EMINE_DB") {
        let p = PathBuf::from(path);
        if p.exists() {
            return Ok(p);
        }
    }

    anyhow::bail!(
        "Database not found. Tried:\n  {}\n\nSet KOM_EMINE_DB env var or run from project root.",
        candidates
            .iter()
            .map(|p| p.display().to_string())
            .collect::<Vec<_>>()
            .join("\n  ")
    )
}

fn run_app(terminal: &mut Terminal<CrosstermBackend<io::Stdout>>, app: &mut App) -> Result<()> {
    loop {
        terminal.draw(|f| ui::render(f, app))?;

        if let Event::Key(key) = event::read()? {
            // Only handle key press events (not release)
            if key.kind != KeyEventKind::Press {
                continue;
            }

            // Clear status message on any key
            app.status_msg = None;

            // Handle different input modes
            match app.input_mode {
                InputMode::Search => {
                    match key.code {
                        KeyCode::Enter => app.search_execute(),
                        KeyCode::Esc => app.search_cancel(),
                        KeyCode::Backspace => app.search_pop(),
                        KeyCode::Char(c) => app.search_push(c),
                        _ => {}
                    }
                    continue;
                }
                InputMode::GotG => {
                    app.input_mode = InputMode::Normal;
                    if key.code == KeyCode::Char('g') {
                        app.goto_first();
                    }
                    continue;
                }
                InputMode::Normal => {}
            }

            // Help popup intercepts all keys
            if app.show_help {
                app.show_help = false;
                continue;
            }

            // Check for Ctrl modifiers
            if key.modifiers.contains(KeyModifiers::CONTROL) {
                match key.code {
                    KeyCode::Char('d') => app.half_page_down(),
                    KeyCode::Char('u') => app.half_page_up(),
                    KeyCode::Char('c') => return Ok(()), // Ctrl+C to quit
                    _ => {}
                }
                continue;
            }

            match key.code {
                // Quit
                KeyCode::Char('q') | KeyCode::Esc => return Ok(()),

                // Help
                KeyCode::Char('?') => app.show_help = true,

                // Navigation - vim style
                KeyCode::Up | KeyCode::Char('k') => app.cursor_up(),
                KeyCode::Down | KeyCode::Char('j') => app.cursor_down(),
                KeyCode::Char('h') => app.panel_left(),
                KeyCode::Char('l') => app.panel_right(),
                KeyCode::PageUp => app.page_up(),
                KeyCode::PageDown => app.page_down(),
                KeyCode::Tab => app.switch_panel(),

                // Vim motions
                KeyCode::Char('g') => app.input_mode = InputMode::GotG,
                KeyCode::Char('G') => app.goto_last(),

                // Search
                KeyCode::Char('/') => app.start_search(SearchDirection::Forward),
                KeyCode::Char('n') => app.search_next(),
                KeyCode::Char('N') => app.search_prev(),

                // Actions
                KeyCode::Enter | KeyCode::Char(' ') => {
                    app.add_selected_to_route().context("Failed to add stop")?
                }
                KeyCode::Char('d') | KeyCode::Char('x') => app
                    .remove_selected_from_route()
                    .context("Failed to remove stop")?,
                KeyCode::Char('c') => app.clear_route().context("Failed to clear route")?,
                KeyCode::Char('u') => app.undo().context("Failed to undo")?,

                // Filters 1-6
                KeyCode::Char(c) if ('1'..='6').contains(&c) => {
                    let idx = c.to_digit(10).unwrap() as usize;
                    app.filters.toggle_by_index(idx);
                    app.update_filtered();
                }

                _ => {}
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::tempdir;

    fn create_test_db(path: &std::path::Path) -> Result<()> {
        let conn = rusqlite::Connection::open(path)?;

        conn.execute_batch(
            "CREATE TABLE route_waypoints (
                id INTEGER PRIMARY KEY,
                sector_km REAL,
                total_km REAL,
                sector_time TEXT,
                direction TEXT,
                description TEXT,
                lat REAL,
                lon REAL,
                elevation_m INTEGER
            );

            CREATE TABLE water_points (
                id INTEGER PRIMARY KEY,
                name TEXT,
                type TEXT,
                lat REAL,
                lon REAL,
                elevation_m REAL,
                status TEXT,
                off_route INTEGER,
                comment TEXT
            );

            CREATE TABLE huts (
                id INTEGER PRIMARY KEY,
                name TEXT,
                name_en TEXT,
                km REAL,
                region TEXT,
                lat REAL,
                lon REAL,
                phone TEXT,
                status TEXT
            );

            INSERT INTO route_waypoints (total_km, description, elevation_m)
            VALUES (0.0, 'вр. Ком - Start', 2016);

            INSERT INTO route_waypoints (total_km, description, elevation_m)
            VALUES (28.0, 'хижа Петрохан', 1450);

            INSERT INTO route_waypoints (total_km, description, elevation_m)
            VALUES (555.3, 'нос Емине - Black Sea', 0);

            INSERT INTO huts (name_en, km, phone, status)
            VALUES ('Petrohan', 28.0, '0888123456', 'working');
            ",
        )?;

        Ok(())
    }

    #[test]
    fn test_app_creation() -> Result<()> {
        let dir = tempdir()?;
        let db_path = dir.path().join("test.db");
        create_test_db(&db_path)?;

        let app = App::new(db_path)?;

        assert!(!app.all_waypoints.is_empty());
        // Route may have data from previous runs (loads from global config)
        assert!(app.filters.hut);

        Ok(())
    }

    #[test]
    fn test_filter_toggle() -> Result<()> {
        let dir = tempdir()?;
        let db_path = dir.path().join("test.db");
        create_test_db(&db_path)?;

        let mut app = App::new(db_path)?;
        let initial_count = app.filtered_waypoints.len();

        app.filters.toggle_by_index(1); // Toggle huts
        app.update_filtered();

        // Should have fewer waypoints with huts filtered out
        assert!(app.filtered_waypoints.len() <= initial_count);

        Ok(())
    }

    #[test]
    fn test_add_remove_route() -> Result<()> {
        let dir = tempdir()?;
        let db_path = dir.path().join("test.db");
        create_test_db(&db_path)?;

        // Create route file location in temp dir
        let route_dir = dir.path().join("kom-emine");
        fs::create_dir_all(&route_dir)?;

        let mut app = App::new(db_path)?;

        // Move to hut waypoint (km > 0)
        while let Some(wp) = app.current_waypoint() {
            if wp.km > 0.0 {
                break;
            }
            app.cursor_down();
        }

        app.add_selected_to_route()?;
        assert_eq!(app.route.len(), 1);

        // Switch to route panel and remove
        app.switch_panel();
        app.route_state.select(Some(0));
        app.remove_selected_from_route()?;
        assert_eq!(app.route.len(), 0);

        Ok(())
    }
}
