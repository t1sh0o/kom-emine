//! Database access for Kom-Emine route planner

use anyhow::Result;
use rusqlite::{params, Connection};
use std::path::Path;

/// Route waypoint from PDF data
#[derive(Debug, Clone)]
pub struct Waypoint {
    pub id: i64,
    pub km: f64,
    pub sector_km: Option<f64>,
    pub sector_time: Option<String>,
    pub description: String,
    pub lat: Option<f64>,
    pub lon: Option<f64>,
    pub elevation: Option<i32>,
    pub sleepable_type: Option<SleepableType>,
}

/// Type of accommodation
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SleepableType {
    Hut,
    Shelter,
    Village,
    Town,
    Resort,
    Finish,
}

impl SleepableType {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Hut => "hut",
            Self::Shelter => "shelter",
            Self::Village => "village",
            Self::Town => "town",
            Self::Resort => "resort",
            Self::Finish => "finish",
        }
    }

    pub fn label(&self) -> &'static str {
        match self {
            Self::Hut => "Hut",
            Self::Shelter => "Shelter",
            Self::Village => "Village",
            Self::Town => "Town",
            Self::Resort => "Resort",
            Self::Finish => "Finish",
        }
    }
}

/// Segment statistics
#[derive(Debug, Clone, Default)]
pub struct SegmentStats {
    pub start_km: f64,
    pub end_km: f64,
    pub distance_km: f64,
    pub hours: f64,
    pub elevation_gain: i32,
    pub water_count: i32,
    pub terrain: String,
    pub difficulty: Difficulty,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub enum Difficulty {
    #[default]
    Easy,
    Moderate,
    Hard,
}

impl Difficulty {
    pub fn label(&self) -> &'static str {
        match self {
            Self::Easy => "easy",
            Self::Moderate => "moderate",
            Self::Hard => "HARD",
        }
    }
}

/// Hut information
#[derive(Debug, Clone)]
pub struct Hut {
    pub name: String,
    pub name_en: String,
    pub km: f64,
    pub phone: Option<String>,
    pub region: String,
}

/// Elevation profile point
#[derive(Debug, Clone)]
pub struct ElevationPoint {
    pub km: f64,
    pub elevation: i32,
}

/// Database connection wrapper
pub struct Database {
    conn: Connection,
}

impl Database {
    pub fn open<P: AsRef<Path>>(path: P) -> Result<Self> {
        let conn = Connection::open(path)?;
        Ok(Self { conn })
    }

    /// Get all route waypoints
    pub fn get_waypoints(&self) -> Result<Vec<Waypoint>> {
        let mut stmt = self.conn.prepare(
            "SELECT id, total_km, sector_km, sector_time, description, lat, lon, elevation_m
             FROM route_waypoints ORDER BY total_km",
        )?;

        let waypoints = stmt
            .query_map([], |row| {
                let desc: String = row.get(4)?;
                let sleepable_type = parse_sleepable_type(&desc);

                Ok(Waypoint {
                    id: row.get(0)?,
                    km: row.get(1)?,
                    sector_km: row.get(2)?,
                    sector_time: row.get(3)?,
                    description: desc,
                    lat: row.get(5)?,
                    lon: row.get(6)?,
                    elevation: row.get(7)?,
                    sleepable_type,
                })
            })?
            .filter_map(|r| r.ok())
            .collect();

        Ok(waypoints)
    }

    /// Get sleepable waypoints only
    pub fn get_sleepable_waypoints(&self) -> Result<Vec<Waypoint>> {
        let all = self.get_waypoints()?;
        Ok(all
            .into_iter()
            .filter(|w| w.sleepable_type.is_some())
            .collect())
    }

    /// Get segment statistics between two km markers
    pub fn get_segment_stats(&self, start_km: f64, end_km: f64) -> Result<SegmentStats> {
        // Calculate hours from sector times
        let mut stmt = self.conn.prepare(
            "SELECT sector_time, elevation_m FROM route_waypoints
             WHERE total_km > ? AND total_km <= ?",
        )?;

        let rows: Vec<(Option<String>, Option<i32>)> = stmt
            .query_map(params![start_km, end_km], |row| {
                Ok((row.get(0)?, row.get(1)?))
            })?
            .filter_map(|r| r.ok())
            .collect();

        let mut total_mins = 0;
        for (time, _) in &rows {
            if let Some(t) = time {
                let parts: Vec<&str> = t.split(':').collect();
                if parts.len() == 2 {
                    if let (Ok(h), Ok(m)) = (parts[0].parse::<i32>(), parts[1].parse::<i32>()) {
                        total_mins += h * 60 + m;
                    }
                }
            }
        }

        // Calculate elevation gain
        let mut gain = 0;
        let mut prev_elev: Option<i32> = None;
        for (_, elev) in &rows {
            if let Some(e) = elev {
                if let Some(p) = prev_elev {
                    if *e > p {
                        gain += e - p;
                    }
                }
                prev_elev = Some(*e);
            }
        }

        // Count water sources in range
        let water_count: i32 = self
            .conn
            .query_row(
                "SELECT COUNT(*) FROM water_points WHERE type='water' AND status='ok'
             AND lon BETWEEN (SELECT MIN(lon) FROM route_waypoints WHERE total_km BETWEEN ?1 AND ?2)
             AND (SELECT MAX(lon) FROM route_waypoints WHERE total_km BETWEEN ?1 AND ?2)",
                params![start_km, end_km],
                |row| row.get(0),
            )
            .unwrap_or(0);

        let distance = end_km - start_km;
        let hours = total_mins as f64 / 60.0;
        let terrain = get_terrain_name((start_km + end_km) / 2.0);

        // Determine difficulty
        let difficulty = if hours > 12.0 || gain > 1500 || distance > 55.0 {
            Difficulty::Hard
        } else if hours > 8.0 || gain > 900 || distance > 40.0 {
            Difficulty::Moderate
        } else {
            Difficulty::Easy
        };

        Ok(SegmentStats {
            start_km,
            end_km,
            distance_km: distance,
            hours,
            elevation_gain: gain,
            water_count,
            terrain,
            difficulty,
        })
    }

    /// Get all working huts
    pub fn get_huts(&self) -> Result<Vec<Hut>> {
        let mut stmt = self.conn.prepare(
            "SELECT name, name_en, km, phone, region FROM huts
             WHERE status='working' ORDER BY km",
        )?;

        let huts = stmt
            .query_map([], |row| {
                Ok(Hut {
                    name: row.get(0)?,
                    name_en: row.get(1)?,
                    km: row.get(2)?,
                    phone: row.get(3)?,
                    region: row.get(4)?,
                })
            })?
            .filter_map(|r| r.ok())
            .collect();

        Ok(huts)
    }

    /// Get elevation profile (sampled for display)
    pub fn get_elevation_profile(&self, sample_count: usize) -> Result<Vec<ElevationPoint>> {
        // Get total count
        let total: i64 = self
            .conn
            .query_row("SELECT COUNT(*) FROM track_profile", [], |row| row.get(0))?;

        if total == 0 {
            return Ok(Vec::new());
        }

        // Sample every Nth point
        let step = (total as usize / sample_count).max(1);

        let mut stmt = self.conn.prepare(
            "SELECT km, elevation FROM track_profile WHERE id % ?1 = 0 ORDER BY km",
        )?;

        let points = stmt
            .query_map([step as i64], |row| {
                Ok(ElevationPoint {
                    km: row.get(0)?,
                    elevation: row.get(1)?,
                })
            })?
            .filter_map(|r| r.ok())
            .collect();

        Ok(points)
    }

    /// Get min/max elevation
    pub fn get_elevation_range(&self) -> Result<(i32, i32)> {
        let (min, max): (i32, i32) = self.conn.query_row(
            "SELECT MIN(elevation), MAX(elevation) FROM track_profile",
            [],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )?;
        Ok((min, max))
    }
}

/// Parse sleepable type from Bulgarian description
fn parse_sleepable_type(desc: &str) -> Option<SleepableType> {
    let desc_lower = desc.to_lowercase();

    // Hut patterns
    if desc_lower.contains("хижа") || desc_lower.contains("х.") || desc_lower.contains("горски дом")
    {
        return Some(SleepableType::Hut);
    }

    // Shelter patterns
    if desc_lower.contains("заслон") || desc_lower.contains("т.с.") {
        return Some(SleepableType::Shelter);
    }

    // Village patterns
    if desc_lower.contains("с.") || desc_lower.contains("село") {
        return Some(SleepableType::Village);
    }

    // Town patterns
    if desc_lower.contains("гр.") || desc_lower.contains("град") || desc_lower.contains("център")
    {
        return Some(SleepableType::Town);
    }

    // Resort patterns
    if desc_lower.contains("курорт") || desc_lower.contains("хотел") || desc_lower.contains("вила")
    {
        return Some(SleepableType::Resort);
    }

    // Finish
    if desc_lower.contains("черно море") || desc_lower.contains("нос емине") {
        return Some(SleepableType::Finish);
    }

    None
}

/// Get terrain name for km marker
fn get_terrain_name(km: f64) -> String {
    if km < 105.0 {
        "Western".to_string()
    } else if km < 175.0 {
        "Central-alpine".to_string()
    } else if km < 245.0 {
        "Botev area".to_string()
    } else if km < 330.0 {
        "Central East".to_string()
    } else {
        "Eastern/Coast".to_string()
    }
}

/// Extract short name from description
pub fn extract_name(desc: &str) -> String {
    if desc.is_empty() {
        return "-".to_string();
    }

    // Try to extract meaningful name part after Bulgarian prefixes
    let prefixes = [
        "х.",
        "хижа",
        "заслон",
        "т.с.",
        "с.",
        "гр.",
        "курорт",
        "хотел",
        "вила",
    ];

    for prefix in prefixes {
        if let Some(idx) = desc.to_lowercase().find(prefix) {
            let after = &desc[idx + prefix.len()..];
            let name: String = after
                .trim_start_matches(|c: char| c == ' ' || c == '"' || c == '"' || c == '„')
                .chars()
                .take_while(|c| *c != '"' && *c != '"' && *c != ',' && *c != '-' && *c != '/' && *c != '\n')
                .collect();
            let trimmed = name.trim();
            if !trimmed.is_empty() {
                return trimmed.chars().take(25).collect();
            }
        }
    }

    // Fallback: first 25 chars
    desc.chars().take(25).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_sleepable_type() {
        assert_eq!(
            parse_sleepable_type("хижа Добрила"),
            Some(SleepableType::Hut)
        );
        assert_eq!(
            parse_sleepable_type("х. Козя Стена"),
            Some(SleepableType::Hut)
        );
        assert_eq!(
            parse_sleepable_type("заслон Хазим"),
            Some(SleepableType::Shelter)
        );
        assert_eq!(
            parse_sleepable_type("с. Козичино"),
            Some(SleepableType::Village)
        );
        assert_eq!(parse_sleepable_type("гр. Котел"), Some(SleepableType::Town));
        assert_eq!(
            parse_sleepable_type("вила Ральо"),
            Some(SleepableType::Resort)
        );
        assert_eq!(
            parse_sleepable_type("нос Емине"),
            Some(SleepableType::Finish)
        );
        assert_eq!(parse_sleepable_type("просто точка"), None);
    }

    #[test]
    fn test_extract_name() {
        assert_eq!(extract_name("хижа Добрила/junction"), "Добрила");
        assert_eq!(extract_name(""), "-");
    }

    #[test]
    fn test_terrain_name() {
        assert_eq!(get_terrain_name(50.0), "Western");
        assert_eq!(get_terrain_name(150.0), "Central-alpine");
        assert_eq!(get_terrain_name(200.0), "Botev area");
        assert_eq!(get_terrain_name(300.0), "Central East");
        assert_eq!(get_terrain_name(400.0), "Eastern/Coast");
    }

    #[test]
    fn test_difficulty_label() {
        assert_eq!(Difficulty::Easy.label(), "easy");
        assert_eq!(Difficulty::Moderate.label(), "moderate");
        assert_eq!(Difficulty::Hard.label(), "HARD");
    }
}
