// lore-tui: navegar na base e perguntar. Chamado por `lore ask` sem pergunta.
package main

import (
	"flag"
	"fmt"
	"os"
	"os/exec"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

func main() {
	root := flag.String("root", "", "raiz do repositório lore")
	bin := flag.String("lore", "lore", "binário do CLI lore")
	flag.Parse()

	lorePath, err := exec.LookPath(*bin)
	if err != nil {
		fmt.Fprintf(os.Stderr, "lore-tui: CLI lore não encontrado (%s)\n", *bin)
		os.Exit(1)
	}
	// Decide o tema antes do Bubble Tea assumir o terminal: a consulta de cor
	// de fundo não funciona depois.
	style := "light"
	if lipgloss.HasDarkBackground() {
		style = "dark"
	}
	model := NewModel(ExecLore{Bin: lorePath, Root: *root}, *root, style)
	if _, err := tea.NewProgram(model, tea.WithAltScreen()).Run(); err != nil {
		fmt.Fprintf(os.Stderr, "lore-tui: %v\n", err)
		os.Exit(1)
	}
}
