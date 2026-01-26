//! UI rendering for Kom-Emine TUI

use crate::app::{ActivePanel, App, InputMode};
use crate::db::{extract_name, Difficulty};
use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style, Stylize},
    symbols,
    text::{Line, Span},
    widgets::{Axis, Block, Borders, Chart, Clear, Dataset, GraphType, Paragraph, Row, Table, Wrap},
    Frame,
};

/// Main UI render function
pub fn render(frame: &mut Frame, app: &mut App) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),  // Header
            Constraint::Length(1),  // Filters
            Constraint::Length(10), // Elevation profile
            Constraint::Min(10),    // Main content
            Constraint::Length(3),  // Warnings/status
            Constraint::Length(1),  // Help hint / status
        ])
        .split(frame.area());

    render_header(frame, chunks[0]);
    render_filters(frame, chunks[1], app);
    render_elevation(frame, chunks[2], app);
    render_main(frame, chunks[3], app);
    render_warnings(frame, chunks[4], app);
    render_status_line(frame, chunks[5], app);

    if app.show_help {
        render_help_popup(frame);
    }
}

fn render_header(frame: &mut Frame, area: Rect) {
    let header = Paragraph::new(vec![
        Line::from(vec![Span::styled(
            "KOM-EMINE ROUTE PLANNER",
            Style::default().fg(Color::Cyan).bold(),
        )]),
        Line::from(vec![Span::styled(
            "555 km | Kom Peak -> Cape Emine | Bulgaria's E3 Trail",
            Style::default().fg(Color::DarkGray),
        )]),
    ])
    .block(
        Block::default()
            .borders(Borders::BOTTOM)
            .border_style(Style::default().fg(Color::DarkGray)),
    );

    frame.render_widget(header, area);
}

fn render_filters(frame: &mut Frame, area: Rect, app: &mut App) {
    let f = &app.filters;

    let filters = Line::from(vec![
        Span::raw(" Filters: "),
        filter_span("1:Hut", f.hut),
        Span::raw(" "),
        filter_span("2:Shelter", f.shelter),
        Span::raw(" "),
        filter_span("3:Village", f.village),
        Span::raw(" "),
        filter_span("4:Town", f.town),
        Span::raw(" "),
        filter_span("5:Resort", f.resort),
        Span::raw(" "),
        filter_span("6:Finish", f.finish),
    ]);

    frame.render_widget(Paragraph::new(filters), area);
}

fn filter_span(label: &str, enabled: bool) -> Span {
    if enabled {
        Span::styled(label, Style::default().fg(Color::Green))
    } else {
        Span::styled(label, Style::default().fg(Color::DarkGray))
    }
}

fn render_elevation(frame: &mut Frame, area: Rect, app: &App) {
    if app.elevation_profile.is_empty() {
        let block = Block::default()
            .title(" Elevation ")
            .borders(Borders::ALL)
            .border_style(Style::default().fg(Color::DarkGray));
        frame.render_widget(block, area);
        return;
    }

    // Convert elevation data to chart points
    let data: Vec<(f64, f64)> = app
        .elevation_profile
        .iter()
        .map(|p| (p.km, p.elevation as f64))
        .collect();

    // Route stop km markers for overlay
    let stop_kms: Vec<f64> = app.route.iter().map(|s| s.km).collect();

    // Find max km from data
    let max_km = data.last().map(|(km, _)| *km).unwrap_or(555.0);

    // Create vertical line markers for each route stop
    // Each stop gets points from bottom to its elevation to draw a vertical line
    let mut stop_lines: Vec<Vec<(f64, f64)>> = Vec::new();
    for &km in &stop_kms {
        // Find elevation at this km
        if let Some(elev) = app
            .elevation_profile
            .iter()
            .min_by(|a, b| (a.km - km).abs().partial_cmp(&(b.km - km).abs()).unwrap())
            .map(|p| p.elevation as f64)
        {
            // Create vertical line from 0 to elevation
            stop_lines.push(vec![(km, 0.0), (km, elev)]);
        }
    }

    // Build datasets - elevation profile first
    let mut datasets = vec![
        Dataset::default()
            .name("Elevation")
            .marker(symbols::Marker::Braille)
            .graph_type(GraphType::Line)
            .style(Style::default().fg(Color::Green))
            .data(&data),
    ];

    // Add each stop as a vertical line dataset
    for line in &stop_lines {
        datasets.push(
            Dataset::default()
                .marker(symbols::Marker::Braille)
                .graph_type(GraphType::Line)
                .style(Style::default().fg(Color::Cyan))
                .data(line),
        );
    }

    // X-axis labels
    let x_labels: Vec<Span> = vec![
        Span::raw("0"),
        Span::raw("50"),
        Span::raw("100"),
        Span::raw("150"),
        Span::raw("200"),
        Span::raw("250"),
        Span::raw("300"),
        Span::raw("350"),
        Span::raw("400"),
        Span::raw("450"),
        Span::raw("500"),
        Span::styled(format!("{:.0}km", max_km), Style::default().fg(Color::DarkGray)),
    ];

    // Y-axis labels - more granular for taller chart
    let y_labels: Vec<Span> = vec![
        Span::raw("0"),
        Span::raw("500"),
        Span::raw("1000"),
        Span::raw("1500"),
        Span::raw("2000"),
        Span::styled("2400m", Style::default().fg(Color::Yellow)),
    ];

    // Build title with stats
    let title = if stop_kms.is_empty() {
        format!(" Elevation | {}m - {}m ", app.elevation_min, app.elevation_max)
    } else {
        format!(
            " Elevation | {} stops | {}m - {}m ",
            stop_kms.len(),
            app.elevation_min,
            app.elevation_max
        )
    };

    let chart = Chart::new(datasets)
        .block(
            Block::default()
                .title(title)
                .borders(Borders::ALL)
                .border_style(Style::default().fg(Color::DarkGray)),
        )
        .x_axis(
            Axis::default()
                .labels(x_labels)
                .bounds([0.0, max_km])
                .style(Style::default().fg(Color::DarkGray)),
        )
        .y_axis(
            Axis::default()
                .labels(y_labels)
                .bounds([0.0, 2400.0])
                .style(Style::default().fg(Color::DarkGray)),
        );

    frame.render_widget(chart, area);
}

fn render_main(frame: &mut Frame, area: Rect, app: &mut App) {
    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(50), Constraint::Percentage(50)])
        .split(area);

    render_waypoints_panel(frame, chunks[0], app);
    render_route_panel(frame, chunks[1], app);
}

fn render_waypoints_panel(frame: &mut Frame, area: Rect, app: &mut App) {
    let is_active = app.active_panel == ActivePanel::Waypoints;
    let selected_kms = app.selected_kms();

    let title = format!(" Waypoints ({}) ", app.filtered_waypoints.len());
    let border_style = if is_active {
        Style::default().fg(Color::Cyan)
    } else {
        Style::default().fg(Color::DarkGray)
    };

    let block = Block::default()
        .title(title)
        .borders(Borders::ALL)
        .border_style(border_style);

    let header = Row::new(vec!["km", "Name", "Elev", "Type"])
        .style(Style::default().bold())
        .bottom_margin(1);

    let rows: Vec<Row> = app
        .filtered_waypoints
        .iter()
        .enumerate()
        .map(|(_, wp)| {
            let km_key = (wp.km * 10.0) as i64;
            let is_in_route = selected_kms.contains(&km_key);

            let name = extract_name(&wp.description);
            let elev = wp.elevation.map(|e| e.to_string()).unwrap_or("-".into());
            let type_label = wp
                .sleepable_type
                .as_ref()
                .map(|t| t.as_str())
                .unwrap_or("-");

            let style = if is_in_route {
                Style::default().fg(Color::Green).add_modifier(Modifier::BOLD)
            } else {
                Style::default()
            };

            Row::new(vec![
                format!("{:.1}", wp.km),
                name,
                elev,
                type_label.to_string(),
            ])
            .style(style)
        })
        .collect();

    let widths = [
        Constraint::Length(6),
        Constraint::Min(15),
        Constraint::Length(5),
        Constraint::Length(8),
    ];

    let highlight_style = if is_active {
        Style::default().bg(Color::Blue)
    } else {
        Style::default().bg(Color::DarkGray)
    };

    let table = Table::new(rows, widths)
        .header(header)
        .block(block)
        .row_highlight_style(highlight_style);

    frame.render_stateful_widget(table, area, &mut app.waypoint_state);

    // Show distance hint for current waypoint
    if is_active {
        if let Some(wp) = app.current_waypoint() {
            let dist = app.distance_from_prev(wp.km);
            let prev = app.prev_stop_name(wp.km);
            let hint = format!(" {:.1}km from {} ", dist, prev);

            let hint_area = Rect {
                x: area.x + 1,
                y: area.y + area.height - 1,
                width: hint.len().min(area.width as usize - 2) as u16,
                height: 1,
            };

            frame.render_widget(
                Paragraph::new(hint).style(Style::default().fg(Color::Yellow)),
                hint_area,
            );
        }
    }
}

fn render_route_panel(frame: &mut Frame, area: Rect, app: &mut App) {
    let is_active = app.active_panel == ActivePanel::Route;

    let title = format!(" Route ({} stops) ", app.route.len());
    let border_style = if is_active {
        Style::default().fg(Color::Cyan)
    } else {
        Style::default().fg(Color::DarkGray)
    };

    let block = Block::default()
        .title(title)
        .borders(Borders::ALL)
        .border_style(border_style);

    if app.route.is_empty() {
        let empty = Paragraph::new("Press Enter to add stops")
            .style(Style::default().fg(Color::DarkGray))
            .block(block);
        frame.render_widget(empty, area);
        return;
    }

    let header = Row::new(vec!["#", "Segment", "km", "hrs", "+m"])
        .style(Style::default().bold())
        .bottom_margin(1);

    let rows: Vec<Row> = app
        .route
        .iter()
        .enumerate()
        .map(|(i, stop)| {
            let start_name = if i == 0 {
                "Kom Peak".to_string()
            } else {
                extract_name(&app.route[i - 1].description)
            };
            let end_name = extract_name(&stop.description);

            let (dist, hrs, gain, diff) = stop
                .segment
                .as_ref()
                .map(|s| {
                    (
                        format!("{:.1}", s.distance_km),
                        format!("{:.1}", s.hours),
                        format!("+{}", s.elevation_gain),
                        s.difficulty,
                    )
                })
                .unwrap_or(("-".into(), "-".into(), "-".into(), Difficulty::Easy));

            let segment = format!("{} -> {}", truncate(&start_name, 8), truncate(&end_name, 8));

            let style = match diff {
                Difficulty::Hard => Style::default().fg(Color::Red),
                Difficulty::Moderate => Style::default().fg(Color::Yellow),
                Difficulty::Easy => Style::default(),
            };

            Row::new(vec![format!("{}", i + 1), segment, dist, hrs, gain]).style(style)
        })
        .collect();

    let widths = [
        Constraint::Length(2),
        Constraint::Min(18),
        Constraint::Length(5),
        Constraint::Length(5),
        Constraint::Length(6),
    ];

    let highlight_style = if is_active {
        Style::default().bg(Color::Blue)
    } else {
        Style::default().bg(Color::DarkGray)
    };

    let table = Table::new(rows, widths)
        .header(header)
        .block(block)
        .row_highlight_style(highlight_style);

    frame.render_stateful_widget(table, area, &mut app.route_state);

    // Render totals at bottom
    let (total_km, total_hrs, total_gain) = app.route_totals();
    let totals = format!(
        " Total: {:.1}km | {:.1}hrs | +{}m ",
        total_km, total_hrs, total_gain
    );

    let totals_area = Rect {
        x: area.x + 1,
        y: area.y + area.height - 1,
        width: totals.len().min(area.width as usize - 2) as u16,
        height: 1,
    };

    frame.render_widget(
        Paragraph::new(totals).style(Style::default().fg(Color::Cyan).bold()),
        totals_area,
    );
}

fn render_warnings(frame: &mut Frame, area: Rect, app: &mut App) {
    let block = Block::default()
        .title(" Warnings ")
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::DarkGray));

    if app.warnings.is_empty() {
        let ok = Paragraph::new(" No warnings")
            .style(Style::default().fg(Color::Green))
            .block(block);
        frame.render_widget(ok, area);
    } else {
        let text = app.warnings.join(" | ");
        let warnings = Paragraph::new(format!(" {}", text))
            .style(Style::default().fg(Color::Red))
            .block(block);
        frame.render_widget(warnings, area);
    }
}

fn render_status_line(frame: &mut Frame, area: Rect, app: &mut App) {
    // Search mode - show search input
    if app.input_mode == InputMode::Search {
        let search = Line::from(vec![
            Span::styled("/", Style::default().fg(Color::Yellow)),
            Span::raw(&app.search_query),
            Span::styled("_", Style::default().fg(Color::Yellow).add_modifier(Modifier::SLOW_BLINK)),
        ]);
        frame.render_widget(Paragraph::new(search), area);
        return;
    }

    // GotG mode - show waiting for g
    if app.input_mode == InputMode::GotG {
        let hint = Line::from(vec![
            Span::styled("g", Style::default().fg(Color::Yellow)),
            Span::raw(" (press g for top)"),
        ]);
        frame.render_widget(Paragraph::new(hint), area);
        return;
    }

    // Status message
    if let Some(msg) = &app.status_msg {
        let status = Line::from(vec![
            Span::styled(format!(" {}", msg), Style::default().fg(Color::Yellow)),
        ]);
        frame.render_widget(Paragraph::new(status), area);
        return;
    }

    // Default help hints
    let hint = Line::from(vec![
        Span::styled(" ?", Style::default().fg(Color::Cyan)),
        Span::raw(":help "),
        Span::styled("hjkl", Style::default().fg(Color::Cyan)),
        Span::raw(":nav "),
        Span::styled("Space", Style::default().fg(Color::Cyan)),
        Span::raw(":add "),
        Span::styled("d", Style::default().fg(Color::Cyan)),
        Span::raw(":del "),
        Span::styled("/", Style::default().fg(Color::Cyan)),
        Span::raw(":search "),
        Span::styled("u", Style::default().fg(Color::Cyan)),
        Span::raw(":undo "),
        Span::styled("q", Style::default().fg(Color::Cyan)),
        Span::raw(":quit"),
    ]);
    frame.render_widget(Paragraph::new(hint), area);
}

fn render_help_popup(frame: &mut Frame) {
    let area = centered_rect(65, 80, frame.area());

    frame.render_widget(Clear, area);

    let help_text = vec![
        Line::from(""),
        Line::from(vec![Span::styled("Navigation (vim-style)", Style::default().bold())]),
        Line::from("  j/k             - Move down/up"),
        Line::from("  h/l             - Switch panel left/right"),
        Line::from("  gg/G            - Go to first/last"),
        Line::from("  Ctrl+d/Ctrl+u   - Half page down/up"),
        Line::from("  PgDn/PgUp       - Full page down/up"),
        Line::from("  Tab             - Toggle panel"),
        Line::from(""),
        Line::from(vec![Span::styled("Search", Style::default().bold())]),
        Line::from("  /               - Search forward"),
        Line::from("  n/N             - Next/previous match"),
        Line::from(""),
        Line::from(vec![Span::styled("Actions", Style::default().bold())]),
        Line::from("  Space/Enter     - Add stop to route"),
        Line::from("  d/x             - Remove stop from route"),
        Line::from("  c               - Clear entire route"),
        Line::from("  u               - Undo last change"),
        Line::from(""),
        Line::from(vec![Span::styled("Filters (1-6)", Style::default().bold())]),
        Line::from("  1-Huts  2-Shelters  3-Villages"),
        Line::from("  4-Towns 5-Resorts   6-Finish"),
        Line::from(""),
        Line::from(vec![Span::styled("Other", Style::default().bold())]),
        Line::from("  ?               - Toggle help"),
        Line::from("  q/Esc/Ctrl+c    - Quit"),
        Line::from(""),
        Line::from(vec![Span::styled(
            "Press any key to close",
            Style::default().fg(Color::DarkGray),
        )]),
    ];

    let help = Paragraph::new(help_text)
        .block(
            Block::default()
                .title(" Help ")
                .borders(Borders::ALL)
                .border_style(Style::default().fg(Color::Cyan)),
        )
        .wrap(Wrap { trim: false });

    frame.render_widget(help, area);
}

/// Helper to create centered rectangle
fn centered_rect(percent_x: u16, percent_y: u16, area: Rect) -> Rect {
    let popup_layout = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Percentage((100 - percent_y) / 2),
            Constraint::Percentage(percent_y),
            Constraint::Percentage((100 - percent_y) / 2),
        ])
        .split(area);

    Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage((100 - percent_x) / 2),
            Constraint::Percentage(percent_x),
            Constraint::Percentage((100 - percent_x) / 2),
        ])
        .split(popup_layout[1])[1]
}

/// Truncate string to max length
fn truncate(s: &str, max: usize) -> String {
    if s.chars().count() <= max {
        s.to_string()
    } else {
        s.chars().take(max).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_truncate() {
        assert_eq!(truncate("hello", 10), "hello");
        assert_eq!(truncate("hello world", 5), "hello");
        assert_eq!(truncate("", 5), "");
    }

    #[test]
    fn test_centered_rect() {
        let area = Rect::new(0, 0, 100, 50);
        let centered = centered_rect(50, 50, area);
        // Should be roughly centered
        assert!(centered.x > 0);
        assert!(centered.y > 0);
        assert!(centered.width < area.width);
        assert!(centered.height < area.height);
    }
}
