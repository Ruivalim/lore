package main

import (
	"context"
	"fmt"
	"path/filepath"
	"strings"

	"github.com/charmbracelet/bubbles/list"
	"github.com/charmbracelet/bubbles/textinput"
	tea "github.com/charmbracelet/bubbletea"
)

// statusFilter recorta a lista por status, antes do filtro de texto.
type statusFilter int

const (
	showAll statusFilter = iota
	showDrafts
	showVerified
)

func (f statusFilter) label() string {
	switch f {
	case showDrafts:
		return "rascunhos"
	case showVerified:
		return "verificados"
	}
	return "todos"
}

func (f statusFilter) match(d Doc) bool {
	switch f {
	case showDrafts:
		return d.Status == "draft"
	case showVerified:
		return d.Status == "verified"
	}
	return true
}

// reviewMode: aprovar pede confirmação, rejeitar pede motivo.
type reviewMode int

const (
	reviewNone reviewMode = iota
	reviewConfirmApprove
	reviewReason
)

type (
	reviewMsg struct {
		id   string
		info ReviewInfo
		err  error
	}
	actionMsg struct {
		verb  string // "aprovado" ou "rejeitado"
		title string
		path  string
		err   error
	}
	editDoneMsg struct {
		id  string
		err error
	}
)

func newReasonInput() textinput.Model {
	in := textinput.New()
	in.Prompt = "motivo: "
	in.PromptStyle = accentStyle
	in.Placeholder = "por que rejeitar (fica registrado no documento)"
	in.CharLimit = 300
	return in
}

func (m Model) selectedDoc() (Doc, bool) {
	sel, ok := m.list.SelectedItem().(item)
	return sel.doc, ok
}

func (m Model) loadReview(id string) tea.Cmd {
	l := m.lore
	return func() tea.Msg {
		info, err := l.Review(context.Background(), id)
		return reviewMsg{id: id, info: info, err: err}
	}
}

// applyItems monta a lista a partir de m.docs e do recorte de status.
// selectPath (absoluto) escolhe um documento específico, se ele estiver lá.
func (m *Model) applyItems(selectPath string) tea.Cmd {
	var items []list.Item
	selected := -1
	for _, d := range m.docs {
		if !m.statusFilter.match(d) {
			continue
		}
		if selectPath != "" && filepath.Join(m.root, d.Path) == filepath.Clean(selectPath) {
			selected = len(items)
		}
		items = append(items, item{doc: d})
	}
	cmd := m.list.SetItems(items)
	if selected >= 0 {
		m.list.ResetFilter()
		m.list.Select(selected)
	}
	return cmd
}

// handleReviewKey cuida das teclas enquanto confirma aprovação ou digita o
// motivo da rejeição. Devolve handled=false quando a tecla não é dele.
func (m Model) handleReviewKey(msg tea.KeyMsg) (Model, tea.Cmd, bool) {
	key := msg.String()
	switch m.reviewMode {
	case reviewConfirmApprove:
		switch key {
		case "enter", "s", "y":
			m.reviewMode = reviewNone
			return m, m.approve(), true
		case "esc", "n":
			m.reviewMode = reviewNone
		}
		return m, nil, true // outras teclas não fazem nada: decisão explícita
	case reviewReason:
		switch key {
		case "esc":
			m.reviewMode = reviewNone
			m.reason.Blur()
			return m, nil, true
		case "enter":
			reason := strings.TrimSpace(m.reason.Value())
			if reason == "" {
				return m, nil, true
			}
			m.reviewMode = reviewNone
			m.reason.Blur()
			return m, m.reject(reason), true
		}
		var cmd tea.Cmd
		m.reason, cmd = m.reason.Update(msg)
		return m, cmd, true
	}

	doc, ok := m.selectedDoc()
	switch key {
	case "v":
		m.statusFilter = (m.statusFilter + 1) % 3
		cmd := m.applyItems("")
		return m, tea.Batch(cmd, m.selectionChanged()), true
	case "A":
		if !ok {
			return m, nil, true
		}
		if doc.Status != "draft" && !doc.NeedsConfirmation() {
			m.notice = "só rascunho pode ser aprovado (este é " + doc.Status + ")"
			return m, nil, true
		}
		m.reviewMode = reviewConfirmApprove
		return m, nil, true
	case "R":
		if !ok {
			return m, nil, true
		}
		if doc.Status != "draft" {
			m.notice = "só rascunho pode ser rejeitado (este é " + doc.Status + ")"
			return m, nil, true
		}
		m.reviewMode = reviewReason
		m.reason.SetValue("")
		return m, m.reason.Focus(), true
	case "e":
		if !ok {
			return m, nil, true
		}
		id := doc.ID
		return m, tea.ExecProcess(m.lore.EditCmd(id), func(err error) tea.Msg {
			return editDoneMsg{id: id, err: err}
		}), true
	}
	return m, nil, false
}

func (m *Model) approve() tea.Cmd {
	doc, ok := m.selectedDoc()
	if !ok {
		return nil
	}
	m.busy = "aprovando e reindexando…"
	l := m.lore
	return func() tea.Msg {
		path, err := l.Approve(context.Background(), doc.ID)
		return actionMsg{verb: "aprovado", title: doc.Title, path: path, err: err}
	}
}

func (m *Model) reject(reason string) tea.Cmd {
	doc, ok := m.selectedDoc()
	if !ok {
		return nil
	}
	m.busy = "rejeitando…"
	l := m.lore
	return func() tea.Msg {
		path, err := l.Reject(context.Background(), doc.ID, reason)
		return actionMsg{verb: "rejeitado", title: doc.Title, path: path, err: err}
	}
}

// updateReview trata as mensagens da revisão; handled=false se não é dela.
func (m Model) updateReview(msg tea.Msg) (Model, tea.Cmd, bool) {
	switch msg := msg.(type) {
	case reviewMsg:
		if msg.id != m.docID {
			return m, nil, true
		}
		if msg.err != nil {
			m.review = nil
			m.err = "review: " + msg.err.Error()
		} else {
			info := msg.info
			m.review = &info
		}
		if !m.showingAnswer {
			m.refreshView()
		}
		return m, nil, true
	case actionMsg:
		m.busy = ""
		if msg.err != nil {
			m.err = msg.err.Error()
			return m, nil, true
		}
		rel, err := filepath.Rel(m.root, msg.path)
		if err != nil {
			rel = msg.path
		}
		m.notice = fmt.Sprintf("%s: %s → %s", msg.verb, msg.title, rel)
		m.docID = "" // força recarregar o documento no caminho novo
		return m, m.loadDocs(msg.path), true
	case editDoneMsg:
		if msg.err != nil {
			m.err = "edição: " + msg.err.Error()
		}
		m.docID = ""
		doc, _ := m.selectedDoc()
		return m, m.loadDocs(filepath.Join(m.root, doc.Path)), true
	}
	return m, nil, false
}

// reviewBlock aparece no topo de um rascunho: o que conferir antes de aprovar.
func (m Model) reviewBlock() string {
	r := m.review
	if r == nil {
		return mutedStyle.Render("conferindo rascunho…") + "\n\n"
	}
	var b strings.Builder
	b.WriteString(accentStyle.Render("Antes de aprovar") + "\n")
	if !r.Valid {
		b.WriteString(errorStyle.Render("inválido: ") + strings.Join(r.Errors, "; ") + "\n")
	}
	if len(r.PossibleConflicts) > 0 {
		b.WriteString(badge(fmt.Sprintf("%d possível conflito com a base", len(r.PossibleConflicts)), colOrange) + "\n")
		for _, c := range r.PossibleConflicts {
			b.WriteString("  ? " + c + "\n")
		}
	} else {
		b.WriteString(badge("sem conflito aparente com a base", colGreen) + "\n")
	}
	if n := len(r.UnsourcedClaims); n > 0 {
		b.WriteString(mutedStyle.Render(fmt.Sprintf("%d trechos sem fonte explícita (heurística, confira os principais):", n)) + "\n")
		for _, c := range r.UnsourcedClaims[:min(n, 3)] {
			b.WriteString(mutedStyle.Render("  · "+truncate(c, max(m.view.Width-6, 20))) + "\n")
		}
	}
	b.WriteString(keyStyle.Render("A") + mutedStyle.Render(" aprova · ") + keyStyle.Render("R") +
		mutedStyle.Render(" rejeita · ") + keyStyle.Render("e") + mutedStyle.Render(" edita") + "\n\n")
	return b.String()
}

func (m Model) reviewBanner(width int) string {
	switch m.reviewMode {
	case reviewConfirmApprove:
		doc, _ := m.selectedDoc()
		question := "Aprovar “" + truncate(doc.Title, width/2) + "”? Vira verificado e passa a responder perguntas.  "
		if doc.NeedsConfirmation() {
			question = "Confirmar a revisão de “" + truncate(doc.Title, width/2) + "”? Entrou sem revisão humana.  "
		}
		return bannerStyle.BorderForeground(colGreen).Width(width).Render(
			question +
				keyStyle.Render("enter") + " aprova · " + keyStyle.Render("esc") + " cancela")
	case reviewReason:
		return bannerStyle.BorderForeground(colRed).Width(width).Render(
			m.reason.View() + mutedStyle.Render("   enter rejeita · esc cancela"))
	}
	if m.busy != "" {
		return bannerStyle.BorderForeground(colAccent).Width(width).Render(m.spinner.View() + " " + m.busy)
	}
	if m.notice != "" {
		return bannerStyle.BorderForeground(colGreen).Width(width).Render(m.notice)
	}
	return ""
}
