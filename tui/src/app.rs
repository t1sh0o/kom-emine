//! Application state and logic

use crate::db::{extract_name, Database, ElevationPoint, SegmentStats, SleepableType, Waypoint};
use anyhow::Result;
use ratatui::widgets::TableState;
use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::fs;
use std::path::PathBuf;

/// Active panel in the UI
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum ActivePanel {
    #[default]
    Waypoints,
    Route,
}

/// Input mode
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum InputMode {
    #[default]
    Normal,
    Search,
    GotG, // waiting for second 'g' in gg
}

/// Search direction
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum SearchDirection {
    #[default]
    Forward,
    Backward,
}

/// Filter state for waypoint types
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Filters {
    pub hut: bool,
    pub shelter: bool,
    pub village: bool,
    pub town: bool,
    pub resort: bool,
    pub finish: bool,
}

impl Default for Filters {
    fn default() -> Self {
        Self {
            hut: true,
            shelter: true,
            village: true,
            town: true,
            resort: true,
            finish: true,
        }
    }
}

impl Filters {
    pub fn is_enabled(&self, t: &SleepableType) -> bool {
        match t {
            SleepableType::Hut => self.hut,
            SleepableType::Shelter => self.shelter,
            SleepableType::Village => self.village,
            SleepableType::Town => self.town,
            SleepableType::Resort => self.resort,
            SleepableType::Finish => self.finish,
        }
    }

    pub fn toggle(&mut self, t: SleepableType) {
        match t {
            SleepableType::Hut => self.hut = !self.hut,
            SleepableType::Shelter => self.shelter = !self.shelter,
            SleepableType::Village => self.village = !self.village,
            SleepableType::Town => self.town = !self.town,
            SleepableType::Resort => self.resort = !self.resort,
            SleepableType::Finish => self.finish = !self.finish,
        }
    }

    /// Toggle filter by index 1-6
    pub fn toggle_by_index(&mut self, idx: usize) {
        match idx {
            1 => self.hut = !self.hut,
            2 => self.shelter = !self.shelter,
            3 => self.village = !self.village,
            4 => self.town = !self.town,
            5 => self.resort = !self.resort,
            6 => self.finish = !self.finish,
            _ => {}
        }
    }

    /// Get status string for display
    pub fn status(&self) -> String {
        let mut parts = Vec::new();
        if self.hut {
            parts.push("H");
        }
        if self.shelter {
            parts.push("S");
        }
        if self.village {
            parts.push("V");
        }
        if self.town {
            parts.push("T");
        }
        if self.resort {
            parts.push("R");
        }
        if self.finish {
            parts.push("F");
        }
        parts.join("")
    }
}

/// Selected route stop
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RouteStop {
    pub km: f64,
    pub description: String,
    #[serde(skip)]
    pub segment: Option<SegmentStats>,
}

/// Persisted route data
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
struct SavedRoute {
    stops: Vec<f64>,
}

/// Application state
pub struct App {
    pub db: Database,
    pub all_waypoints: Vec<Waypoint>,
    pub filtered_waypoints: Vec<Waypoint>,
    pub route: Vec<RouteStop>,
    pub filters: Filters,
    pub active_panel: ActivePanel,
    pub waypoint_state: TableState,
    pub route_state: TableState,
    pub show_help: bool,
    pub warnings: Vec<String>,
    route_path: PathBuf,
    // Vim features
    pub input_mode: InputMode,
    pub search_query: String,
    pub search_direction: SearchDirection,
    undo_stack: Vec<Vec<RouteStop>>,
    pub status_msg: Option<String>,
    // Elevation profile
    pub elevation_profile: Vec<ElevationPoint>,
    pub elevation_min: i32,
    pub elevation_max: i32,
}

impl App {
    pub fn new(db_path: PathBuf) -> Result<Self> {
        let db = Database::open(&db_path)?;
        let all_waypoints = db.get_sleepable_waypoints()?;

        // Load elevation profile (sample ~500 points for display)
        let elevation_profile = db.get_elevation_profile(500).unwrap_or_default();
        let (elevation_min, elevation_max) = db.get_elevation_range().unwrap_or((0, 2500));

        let route_path = Self::get_route_path();

        let mut waypoint_state = TableState::default();
        waypoint_state.select(Some(0));

        let mut app = Self {
            db,
            all_waypoints,
            filtered_waypoints: Vec::new(),
            route: Vec::new(),
            filters: Filters::default(),
            active_panel: ActivePanel::default(),
            waypoint_state,
            route_state: TableState::default(),
            show_help: false,
            warnings: Vec::new(),
            route_path,
            input_mode: InputMode::default(),
            search_query: String::new(),
            search_direction: SearchDirection::default(),
            undo_stack: Vec::new(),
            status_msg: None,
            elevation_profile,
            elevation_min,
            elevation_max,
        };

        app.update_filtered();
        app.load_route()?;

        Ok(app)
    }

    fn get_route_path() -> PathBuf {
        dirs::data_local_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join("kom-emine")
            .join("route.json")
    }

    /// Update filtered waypoints list
    pub fn update_filtered(&mut self) {
        self.filtered_waypoints = self
            .all_waypoints
            .iter()
            .filter(|w| {
                w.sleepable_type
                    .as_ref()
                    .is_some_and(|t| self.filters.is_enabled(t))
            })
            .cloned()
            .collect();

        // Clamp cursor
        let current = self.waypoint_state.selected().unwrap_or(0);
        if !self.filtered_waypoints.is_empty() && current >= self.filtered_waypoints.len() {
            self.waypoint_state.select(Some(self.filtered_waypoints.len() - 1));
        } else if self.filtered_waypoints.is_empty() {
            self.waypoint_state.select(None);
        } else if self.waypoint_state.selected().is_none() {
            self.waypoint_state.select(Some(0));
        }
    }

    /// Load saved route from disk
    fn load_route(&mut self) -> Result<()> {
        if self.route_path.exists() {
            let content = fs::read_to_string(&self.route_path)?;
            let saved: SavedRoute = serde_json::from_str(&content)?;

            for km in saved.stops {
                if let Some(wp) = self.all_waypoints.iter().find(|w| (w.km - km).abs() < 0.01) {
                    self.route.push(RouteStop {
                        km: wp.km,
                        description: wp.description.clone(),
                        segment: None,
                    });
                }
            }

            self.route.sort_by(|a, b| a.km.partial_cmp(&b.km).unwrap());
            self.update_segments()?;
        }
        Ok(())
    }

    /// Save route to disk
    fn save_route(&self) -> Result<()> {
        if let Some(parent) = self.route_path.parent() {
            fs::create_dir_all(parent)?;
        }

        let saved = SavedRoute {
            stops: self.route.iter().map(|s| s.km).collect(),
        };

        let content = serde_json::to_string_pretty(&saved)?;
        fs::write(&self.route_path, content)?;
        Ok(())
    }

    /// Update segment stats for all route stops
    fn update_segments(&mut self) -> Result<()> {
        for i in 0..self.route.len() {
            let start = if i == 0 { 0.0 } else { self.route[i - 1].km };
            let end = self.route[i].km;

            if end > start {
                let stats = self.db.get_segment_stats(start, end)?;
                self.route[i].segment = Some(stats);
            }
        }

        self.update_warnings();
        Ok(())
    }

    /// Update warnings based on route
    fn update_warnings(&mut self) {
        self.warnings.clear();

        for (i, stop) in self.route.iter().enumerate() {
            if let Some(seg) = &stop.segment {
                if seg.distance_km > 60.0 {
                    self.warnings
                        .push(format!("Day {}: {:.0}km > 60km", i + 1, seg.distance_km));
                }
                if seg.hours > 12.0 {
                    self.warnings
                        .push(format!("Day {}: {:.1}h > 12h", i + 1, seg.hours));
                }
                if seg.water_count < 2 {
                    self.warnings
                        .push(format!("Day {}: low water ({})", i + 1, seg.water_count));
                }
            }
        }
    }

    /// Add waypoint at cursor to route
    pub fn add_selected_to_route(&mut self) -> Result<()> {
        let cursor = self.waypoint_state.selected().unwrap_or(0);

        // Clone needed data to avoid borrow issues
        let (km, description) = match self.filtered_waypoints.get(cursor) {
            Some(wp) => (wp.km, wp.description.clone()),
            None => return Ok(()),
        };

        // Skip if already in route
        if self.route.iter().any(|s| (s.km - km).abs() < 0.01) {
            self.status_msg = Some("Already in route".to_string());
            return Ok(());
        }

        self.save_undo();
        self.route.push(RouteStop {
            km,
            description: description.clone(),
            segment: None,
        });

        self.route.sort_by(|a, b| a.km.partial_cmp(&b.km).unwrap());
        self.update_segments()?;
        self.save_route()?;

        // Select newly added item in route
        if let Some(idx) = self.route.iter().position(|s| (s.km - km).abs() < 0.01) {
            self.route_state.select(Some(idx));
        }
        self.status_msg = Some(format!("Added: {}", extract_name(&description)));
        Ok(())
    }

    /// Remove stop at cursor from route
    pub fn remove_selected_from_route(&mut self) -> Result<()> {
        let cursor = self.route_state.selected().unwrap_or(0);
        if !self.route.is_empty() && cursor < self.route.len() {
            self.save_undo();
            let removed = self.route.remove(cursor);
            self.status_msg = Some(format!("Removed: {}", extract_name(&removed.description)));

            if self.route.is_empty() {
                self.route_state.select(None);
            } else if cursor >= self.route.len() {
                self.route_state.select(Some(self.route.len() - 1));
            }

            self.update_segments()?;
            self.save_route()?;
        }
        Ok(())
    }

    /// Clear entire route
    pub fn clear_route(&mut self) -> Result<()> {
        if !self.route.is_empty() {
            self.save_undo();
            self.route.clear();
            self.route_state.select(None);
            self.warnings.clear();
            self.save_route()?;
            self.status_msg = Some("Route cleared".to_string());
        }
        Ok(())
    }

    /// Move cursor up in active panel
    pub fn cursor_up(&mut self) {
        match self.active_panel {
            ActivePanel::Waypoints => {
                let i = self.waypoint_state.selected().unwrap_or(0);
                if i > 0 {
                    self.waypoint_state.select(Some(i - 1));
                }
            }
            ActivePanel::Route => {
                let i = self.route_state.selected().unwrap_or(0);
                if i > 0 {
                    self.route_state.select(Some(i - 1));
                }
            }
        }
    }

    /// Move cursor down in active panel
    pub fn cursor_down(&mut self) {
        match self.active_panel {
            ActivePanel::Waypoints => {
                let i = self.waypoint_state.selected().unwrap_or(0);
                if !self.filtered_waypoints.is_empty() && i < self.filtered_waypoints.len() - 1 {
                    self.waypoint_state.select(Some(i + 1));
                }
            }
            ActivePanel::Route => {
                let i = self.route_state.selected().unwrap_or(0);
                if !self.route.is_empty() && i < self.route.len() - 1 {
                    self.route_state.select(Some(i + 1));
                }
            }
        }
    }

    /// Page up (10 items)
    pub fn page_up(&mut self) {
        match self.active_panel {
            ActivePanel::Waypoints => {
                let i = self.waypoint_state.selected().unwrap_or(0);
                self.waypoint_state.select(Some(i.saturating_sub(10)));
            }
            ActivePanel::Route => {
                let i = self.route_state.selected().unwrap_or(0);
                self.route_state.select(Some(i.saturating_sub(10)));
            }
        }
    }

    /// Page down (10 items)
    pub fn page_down(&mut self) {
        match self.active_panel {
            ActivePanel::Waypoints => {
                let i = self.waypoint_state.selected().unwrap_or(0);
                let max = self.filtered_waypoints.len().saturating_sub(1);
                self.waypoint_state.select(Some((i + 10).min(max)));
            }
            ActivePanel::Route => {
                let i = self.route_state.selected().unwrap_or(0);
                let max = self.route.len().saturating_sub(1);
                self.route_state.select(Some((i + 10).min(max)));
            }
        }
    }

    /// Switch active panel
    pub fn switch_panel(&mut self) {
        self.active_panel = match self.active_panel {
            ActivePanel::Waypoints => ActivePanel::Route,
            ActivePanel::Route => ActivePanel::Waypoints,
        };
    }

    /// Go to panel left (waypoints)
    pub fn panel_left(&mut self) {
        self.active_panel = ActivePanel::Waypoints;
    }

    /// Go to panel right (route)
    pub fn panel_right(&mut self) {
        self.active_panel = ActivePanel::Route;
    }

    /// Go to first item (gg)
    pub fn goto_first(&mut self) {
        match self.active_panel {
            ActivePanel::Waypoints => {
                if !self.filtered_waypoints.is_empty() {
                    self.waypoint_state.select(Some(0));
                }
            }
            ActivePanel::Route => {
                if !self.route.is_empty() {
                    self.route_state.select(Some(0));
                }
            }
        }
    }

    /// Go to last item (G)
    pub fn goto_last(&mut self) {
        match self.active_panel {
            ActivePanel::Waypoints => {
                if !self.filtered_waypoints.is_empty() {
                    self.waypoint_state.select(Some(self.filtered_waypoints.len() - 1));
                }
            }
            ActivePanel::Route => {
                if !self.route.is_empty() {
                    self.route_state.select(Some(self.route.len() - 1));
                }
            }
        }
    }

    /// Half page up (Ctrl+u)
    pub fn half_page_up(&mut self) {
        match self.active_panel {
            ActivePanel::Waypoints => {
                let i = self.waypoint_state.selected().unwrap_or(0);
                self.waypoint_state.select(Some(i.saturating_sub(15)));
            }
            ActivePanel::Route => {
                let i = self.route_state.selected().unwrap_or(0);
                self.route_state.select(Some(i.saturating_sub(15)));
            }
        }
    }

    /// Half page down (Ctrl+d)
    pub fn half_page_down(&mut self) {
        match self.active_panel {
            ActivePanel::Waypoints => {
                let i = self.waypoint_state.selected().unwrap_or(0);
                let max = self.filtered_waypoints.len().saturating_sub(1);
                self.waypoint_state.select(Some((i + 15).min(max)));
            }
            ActivePanel::Route => {
                let i = self.route_state.selected().unwrap_or(0);
                let max = self.route.len().saturating_sub(1);
                self.route_state.select(Some((i + 15).min(max)));
            }
        }
    }

    /// Start search mode
    pub fn start_search(&mut self, direction: SearchDirection) {
        self.input_mode = InputMode::Search;
        self.search_direction = direction;
        self.search_query.clear();
        self.status_msg = None;
    }

    /// Add char to search query
    pub fn search_push(&mut self, c: char) {
        self.search_query.push(c);
    }

    /// Remove char from search query
    pub fn search_pop(&mut self) {
        self.search_query.pop();
    }

    /// Execute search and go to first match
    pub fn search_execute(&mut self) {
        if self.search_query.is_empty() {
            self.input_mode = InputMode::Normal;
            return;
        }

        let query = self.search_query.to_lowercase();
        let current = self.waypoint_state.selected().unwrap_or(0);

        let matches: Vec<usize> = self
            .filtered_waypoints
            .iter()
            .enumerate()
            .filter(|(_, wp)| {
                wp.description.to_lowercase().contains(&query)
                    || extract_name(&wp.description).to_lowercase().contains(&query)
            })
            .map(|(i, _)| i)
            .collect();

        if matches.is_empty() {
            self.status_msg = Some(format!("Pattern not found: {}", self.search_query));
            self.input_mode = InputMode::Normal;
            return;
        }

        // Find next match based on direction
        let next = match self.search_direction {
            SearchDirection::Forward => matches.iter().find(|&&i| i > current).or(matches.first()),
            SearchDirection::Backward => {
                matches.iter().rev().find(|&&i| i < current).or(matches.last())
            }
        };

        if let Some(&idx) = next {
            self.waypoint_state.select(Some(idx));
            self.active_panel = ActivePanel::Waypoints;
            self.status_msg = Some(format!("/{} [{}/{}]", self.search_query,
                matches.iter().position(|&i| i == idx).unwrap_or(0) + 1,
                matches.len()));
        }

        self.input_mode = InputMode::Normal;
    }

    /// Go to next search match (n)
    pub fn search_next(&mut self) {
        if self.search_query.is_empty() {
            return;
        }
        // Temporarily switch direction for this search
        let orig_dir = self.search_direction;
        self.search_direction = SearchDirection::Forward;
        self.search_execute();
        self.search_direction = orig_dir;
    }

    /// Go to previous search match (N)
    pub fn search_prev(&mut self) {
        if self.search_query.is_empty() {
            return;
        }
        let orig_dir = self.search_direction;
        self.search_direction = SearchDirection::Backward;
        self.search_execute();
        self.search_direction = orig_dir;
    }

    /// Cancel search
    pub fn search_cancel(&mut self) {
        self.input_mode = InputMode::Normal;
        self.search_query.clear();
    }

    /// Save state for undo before modifying route
    fn save_undo(&mut self) {
        self.undo_stack.push(self.route.clone());
        // Keep max 50 undo levels
        if self.undo_stack.len() > 50 {
            self.undo_stack.remove(0);
        }
    }

    /// Undo last route change
    pub fn undo(&mut self) -> Result<()> {
        if let Some(prev_route) = self.undo_stack.pop() {
            self.route = prev_route;
            self.update_segments()?;
            self.save_route()?;
            self.status_msg = Some("Undo".to_string());

            // Fix route cursor
            if self.route.is_empty() {
                self.route_state.select(None);
            } else {
                let cursor = self.route_state.selected().unwrap_or(0);
                if cursor >= self.route.len() {
                    self.route_state.select(Some(self.route.len() - 1));
                }
            }
        } else {
            self.status_msg = Some("Nothing to undo".to_string());
        }
        Ok(())
    }

    /// Get km of selected items in route (for highlighting in waypoints list)
    pub fn selected_kms(&self) -> HashSet<i64> {
        self.route
            .iter()
            .map(|s| (s.km * 10.0) as i64) // Use fixed precision for comparison
            .collect()
    }

    /// Get currently selected waypoint
    pub fn current_waypoint(&self) -> Option<&Waypoint> {
        self.waypoint_state
            .selected()
            .and_then(|i| self.filtered_waypoints.get(i))
    }

    /// Get route totals
    pub fn route_totals(&self) -> (f64, f64, i32) {
        let mut total_km = 0.0;
        let mut total_hrs = 0.0;
        let mut total_gain = 0;

        for stop in &self.route {
            if let Some(seg) = &stop.segment {
                total_km += seg.distance_km;
                total_hrs += seg.hours;
                total_gain += seg.elevation_gain;
            }
        }

        (total_km, total_hrs, total_gain)
    }

    /// Get distance from previous stop for a waypoint
    pub fn distance_from_prev(&self, wp_km: f64) -> f64 {
        let prev_km = self
            .route
            .iter()
            .filter(|s| s.km < wp_km)
            .map(|s| s.km)
            .max_by(|a, b| a.partial_cmp(b).unwrap())
            .unwrap_or(0.0);

        wp_km - prev_km
    }

    /// Get name of previous stop
    pub fn prev_stop_name(&self, wp_km: f64) -> String {
        self.route
            .iter()
            .filter(|s| s.km < wp_km)
            .max_by(|a, b| a.km.partial_cmp(&b.km).unwrap())
            .map(|s| extract_name(&s.description))
            .unwrap_or_else(|| "Kom Peak".to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_filters_default() {
        let f = Filters::default();
        assert!(f.hut);
        assert!(f.shelter);
        assert!(f.village);
        assert!(f.town);
        assert!(f.resort);
        assert!(f.finish);
    }

    #[test]
    fn test_filters_toggle() {
        let mut f = Filters::default();
        f.toggle(SleepableType::Hut);
        assert!(!f.hut);
        f.toggle(SleepableType::Hut);
        assert!(f.hut);
    }

    #[test]
    fn test_filters_toggle_by_index() {
        let mut f = Filters::default();
        f.toggle_by_index(1); // Hut
        assert!(!f.hut);
        f.toggle_by_index(2); // Shelter
        assert!(!f.shelter);
    }

    #[test]
    fn test_filters_status() {
        let f = Filters::default();
        assert_eq!(f.status(), "HSVTRF");

        let mut f2 = Filters::default();
        f2.hut = false;
        f2.town = false;
        assert_eq!(f2.status(), "SVRF");
    }

    #[test]
    fn test_active_panel_switch() {
        let mut panel = ActivePanel::Waypoints;
        panel = match panel {
            ActivePanel::Waypoints => ActivePanel::Route,
            ActivePanel::Route => ActivePanel::Waypoints,
        };
        assert_eq!(panel, ActivePanel::Route);
    }
}
