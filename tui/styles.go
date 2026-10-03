package main

import "github.com/charmbracelet/lipgloss"

var (
	colAccent = lipgloss.AdaptiveColor{Light: "#5A3FD1", Dark: "#A48BFF"}
	colMuted  = lipgloss.AdaptiveColor{Light: "#6B6B76", Dark: "#8B8B96"}
	colBorder = lipgloss.AdaptiveColor{Light: "#C9C9D3", Dark: "#3A3A46"}
	colText   = lipgloss.AdaptiveColor{Light: "#1E1E24", Dark: "#E6E6EE"}
	colGreen  = lipgloss.AdaptiveColor{Light: "#1F7A3D", Dark: "#6BD68E"}
	colYellow = lipgloss.AdaptiveColor{Light: "#8A6100", Dark: "#F2C66D"}
	colOrange = lipgloss.AdaptiveColor{Light: "#A64B00", Dark: "#FF9F5A"}
	colRed    = lipgloss.AdaptiveColor{Light: "#B3261E", Dark: "#FF7A70"}

	brandStyle = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#FFFFFF")).
			Background(colAccent).Padding(0, 1)
	headerStyle = lipgloss.NewStyle().Foreground(colMuted)
	mutedStyle  = lipgloss.NewStyle().Foreground(colMuted)
	textStyle   = lipgloss.NewStyle().Foreground(colText)
	titleStyle  = lipgloss.NewStyle().Bold(true).Foreground(colText)
	accentStyle = lipgloss.NewStyle().Foreground(colAccent).Bold(true)
	errorStyle  = lipgloss.NewStyle().Foreground(colRed).Bold(true)
	keyStyle    = lipgloss.NewStyle().Foreground(colAccent)

	paneStyle = lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).
			BorderForeground(colBorder).Padding(0, 1)
	paneFocusStyle = paneStyle.BorderForeground(colAccent)

	bannerStyle = lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).
			BorderForeground(colYellow).Padding(0, 1)
)

func statusColor(status string) lipgloss.TerminalColor {
	switch status {
	case "verified":
		return colGreen
	case "draft":
		return colYellow
	case "stale":
		return colOrange
	case "rejected":
		return colRed
	default:
		return colMuted
	}
}

func coverageColor(coverage string) lipgloss.TerminalColor {
	switch coverage {
	case "sufficient":
		return colGreen
	case "stale", "partial":
		return colYellow
	case "conflicting":
		return colOrange
	default:
		return colRed
	}
}

func badge(text string, color lipgloss.TerminalColor) string {
	return lipgloss.NewStyle().Foreground(color).Bold(true).Render("● " + text)
}
