package main

import (
	"context"
	"fmt"
	"io"
	"math"
	"path/filepath"
	"strings"
	"time"

	"github.com/charmbracelet/bubbles/list"
	"github.com/charmbracelet/bubbles/spinner"
	"github.com/charmbracelet/bubbles/textinput"
	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/glamour"
	"github.com/charmbracelet/lipgloss"
)

type focus int

const (
	focusList focus = iota
	focusView
	focusAsk
)

// askState é a máquina da pergunta: local → (contagem) → pesquisa externa.
type askState int

const (
	askIdle askState = iota
	askLocal
	askCountdown
	askResearch
)

type (
	docsMsg struct {
		docs []Doc
		err  error
		// selecionar este caminho absoluto depois de recarregar (rascunho novo)
		selectPath string
	}
	docMsg struct {
		id     string
		detail DocDetail
		err    error
	}
	configMsg struct {
		cfg ResearchConfig
		err error
	}
	askMsg struct {
		seq      int
		research bool
		result   AskResult
		err      error
	}
	tickMsg struct{ seq int }
)

type item struct{ doc Doc }

func (i item) FilterValue() string {
	return i.doc.Title + " " + i.doc.ID + " " + strings.Join(i.doc.Tags, " ")
}

type delegate struct{}

func (delegate) Height() int                         { return 2 }
func (delegate) Spacing() int                        { return 1 }
func (delegate) Update(tea.Msg, *list.Model) tea.Cmd { return nil }

func (delegate) Render(w io.Writer, m list.Model, index int, it list.Item) {
	doc := it.(item).doc
	width := m.Width() - 2
	if width < 8 {
		return
	}
	title := doc.Title
	if title == "" {
		title = doc.ID
	}
	title = truncate(title, width)
	meta := truncate(doc.Status+" · "+doc.Type+" · "+doc.ID, width-2)
	dot := lipgloss.NewStyle().Foreground(statusColor(doc.Status)).Render("●")
	bar := "  "
	tStyle := textStyle
	if index == m.Index() {
		bar = accentStyle.Render("▌ ")
		tStyle = titleStyle.Foreground(colAccent)
	}
	fmt.Fprintf(w, "%s%s\n%s%s %s", bar, tStyle.Render(title), bar, dot, mutedStyle.Render(meta))
}

func truncate(s string, width int) string {
	if width <= 1 {
		return ""
	}
	if lipgloss.Width(s) <= width {
		return s
	}
	runes := []rune(s)
	for len(runes) > 0 && lipgloss.Width(string(runes))+1 > width {
		runes = runes[:len(runes)-1]
	}
	return string(runes) + "…"
}

type Model struct {
	lore  Lore
	root  string
	style string

	width, height int
	focus         focus

	list    list.Model
	view    viewport.Model
	input   textinput.Model
	spinner spinner.Model

	docs     []Doc
	research ResearchConfig
	err      string

	// painel da direita: documento ou resposta
	showingAnswer bool
	docID         string
	docDetail     *DocDetail
	answer        *AskResult
	fullAnswer    bool // false: resposta curta quando houver

	state     askState
	question  string
	askSeq    int
	remaining int
	paused    bool
	cancel    context.CancelFunc

	renderer      *glamour.TermRenderer
	rendererWidth int

	// revisão de rascunhos (review.go)
	statusFilter statusFilter
	reviewMode   reviewMode
	reason       textinput.Model
	review       *ReviewInfo
	notice       string
	busy         string
}

func NewModel(l Lore, root, glamourStyle string) Model {
	lst := list.New(nil, delegate{}, 30, 10)
	lst.SetShowTitle(false)
	lst.SetShowHelp(false)
	lst.SetShowStatusBar(false) // a do Bubbles diz "filtered"; listStatus faz em pt
	lst.SetFilteringEnabled(true)
	lst.Filter = filterTerms
	lst.DisableQuitKeybindings()
	lst.FilterInput.Prompt = "filtro: "
	lst.FilterInput.PromptStyle = accentStyle
	lst.Styles.NoItems = mutedStyle.Padding(0, 2)

	in := textinput.New()
	in.Prompt = "❯ "
	in.PromptStyle = accentStyle
	in.Placeholder = "pergunte à base (a para focar, enter envia)"
	in.CharLimit = 500

	sp := spinner.New(spinner.WithSpinner(spinner.MiniDot))
	sp.Style = accentStyle

	return Model{
		lore:    l,
		root:    root,
		style:   glamourStyle,
		list:    lst,
		view:    viewport.New(40, 10),
		input:   in,
		spinner: sp,
		reason:  newReasonInput(),
	}
}

func (m Model) Init() tea.Cmd {
	return tea.Batch(m.loadDocs(""), m.loadConfig(), m.spinner.Tick)
}

func (m Model) loadDocs(selectPath string) tea.Cmd {
	l := m.lore
	return func() tea.Msg {
		docs, err := l.List(context.Background())
		return docsMsg{docs: docs, err: err, selectPath: selectPath}
	}
}

func (m Model) loadConfig() tea.Cmd {
	l := m.lore
	return func() tea.Msg {
		cfg, err := l.Research(context.Background())
		return configMsg{cfg: cfg, err: err}
	}
}

func (m Model) loadDoc(id string) tea.Cmd {
	l := m.lore
	return func() tea.Msg {
		detail, err := l.Show(context.Background(), id)
		return docMsg{id: id, detail: detail, err: err}
	}
}

func (m *Model) runAsk(research bool) tea.Cmd {
	if m.cancel != nil {
		m.cancel()
	}
	ctx, cancel := context.WithCancel(context.Background())
	m.cancel = cancel
	m.askSeq++
	seq, q, l := m.askSeq, m.question, m.lore
	if research {
		m.state = askResearch
	} else {
		m.state = askLocal
	}
	return func() tea.Msg {
		res, err := l.Ask(ctx, q, research)
		return askMsg{seq: seq, research: research, result: res, err: err}
	}
}

func tick(seq int) tea.Cmd {
	return tea.Tick(time.Second, func(time.Time) tea.Msg { return tickMsg{seq: seq} })
}

func (m *Model) stopAsk() {
	if m.cancel != nil {
		m.cancel()
		m.cancel = nil
	}
	m.askSeq++ // descarta resposta que ainda estiver a caminho
	m.state = askIdle
	m.paused = false
}

func (m *Model) startCountdown() tea.Cmd {
	m.state = askCountdown
	m.remaining = int(math.Ceil(m.research.ConfirmTimeout))
	m.paused = m.remaining <= 0 // 0 na config: espera a decisão
	return tick(m.askSeq)
}

func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	next, cmd := m.update(msg)
	nm := next.(Model)
	// A faixa de aviso aparece e some: a altura do corpo muda junto.
	if nm.width > 0 {
		nm.layout()
	}
	return nm, cmd
}

func (m Model) update(msg tea.Msg) (tea.Model, tea.Cmd) {
	if nm, cmd, ok := m.updateReview(msg); ok {
		return nm, cmd
	}
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width, m.height = msg.Width, msg.Height
		m.layout()
		m.refreshView()
		return m, nil

	case spinner.TickMsg:
		var cmd tea.Cmd
		m.spinner, cmd = m.spinner.Update(msg)
		return m, cmd

	case docsMsg:
		if msg.err != nil {
			m.err = msg.err.Error()
			return m, nil
		}
		m.docs = msg.docs
		cmd := m.applyItems(msg.selectPath)
		if !m.showingAnswer {
			return m, tea.Batch(cmd, m.selectionChanged())
		}
		return m, cmd

	case configMsg:
		if msg.err != nil {
			m.err = "config: " + msg.err.Error()
			return m, nil
		}
		m.research = msg.cfg
		return m, nil

	case docMsg:
		if msg.id != m.docID {
			return m, nil
		}
		if msg.err != nil {
			m.err = msg.err.Error()
			m.docDetail = nil
		} else {
			d := msg.detail
			m.docDetail = &d
		}
		if !m.showingAnswer {
			m.refreshView()
			m.view.GotoTop()
		}
		return m, nil

	case askMsg:
		if msg.seq != m.askSeq {
			return m, nil
		}
		m.cancel = nil
		if msg.err != nil {
			m.state = askIdle
			m.err = msg.err.Error()
			return m, nil
		}
		res := msg.result
		m.answer = &res
		m.fullAnswer = false
		m.showingAnswer = true
		m.refreshView()
		m.view.GotoTop()
		if !msg.research && res.NeedsResearch() && m.research.Enabled {
			if !m.research.Confirm() {
				return m, m.runAsk(true)
			}
			return m, m.startCountdown()
		}
		m.state = askIdle
		if msg.research && res.Research != nil && res.Research.DraftPath != "" {
			return m, m.loadDocs(res.Research.DraftPath)
		}
		return m, nil

	case tickMsg:
		if msg.seq != m.askSeq || m.state != askCountdown || m.paused {
			return m, nil
		}
		m.remaining--
		if m.remaining <= 0 {
			return m, m.runAsk(true)
		}
		return m, tick(m.askSeq)

	case tea.KeyMsg:
		return m.handleKey(msg)
	}
	// Resto vai para a lista: o filtro dela chega assíncrono (FilterMatchesMsg).
	var cmd tea.Cmd
	m.list, cmd = m.list.Update(msg)
	return m, tea.Batch(cmd, m.selectionChanged())
}

func (m Model) handleKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	key := msg.String()
	if key == "ctrl+c" {
		m.stopAsk()
		return m, tea.Quit
	}
	// Aviso e erro somem na próxima tecla: já foram vistos.
	m.notice, m.err = "", ""
	if m.reviewMode != reviewNone {
		nm, cmd, _ := m.handleReviewKey(msg)
		return nm, cmd
	}

	// Durante a contagem o teclado decide; qualquer outra tecla pausa.
	if m.state == askCountdown {
		switch key {
		case "enter", "s", "y":
			return m, m.runAsk(true)
		case "esc", "n":
			m.stopAsk()
			return m, nil
		default:
			m.paused = true
			return m, nil
		}
	}
	if key == "esc" && (m.state == askLocal || m.state == askResearch) {
		m.stopAsk()
		m.err = "pergunta cancelada"
		return m, nil
	}

	if m.focus == focusAsk {
		switch key {
		case "esc":
			m.input.Blur()
			m.focus = focusList
			return m, nil
		case "tab":
			m.input.Blur()
			m.focus = focusList
			return m, nil
		case "enter":
			q := strings.TrimSpace(m.input.Value())
			if q == "" {
				return m, nil
			}
			m.question = q
			m.input.SetValue("")
			return m, m.runAsk(false)
		}
		var cmd tea.Cmd
		m.input, cmd = m.input.Update(msg)
		return m, cmd
	}

	if m.list.SettingFilter() {
		var cmd tea.Cmd
		m.list, cmd = m.list.Update(msg)
		return m, tea.Batch(cmd, m.selectionChanged())
	}

	if nm, cmd, ok := m.handleReviewKey(msg); ok {
		return nm, cmd
	}

	switch key {
	case "q":
		m.stopAsk()
		return m, tea.Quit
	case "a", "?":
		m.focus = focusAsk
		return m, m.input.Focus()
	case "tab":
		if m.focus == focusList {
			m.focus = focusView
		} else {
			m.focus = focusAsk
			return m, m.input.Focus()
		}
		return m, nil
	case "r":
		return m, tea.Batch(m.loadDocs(""), m.loadConfig())
	case "p":
		if m.question != "" && m.research.Enabled && m.state == askIdle {
			m.err = ""
			return m, m.runAsk(true)
		}
		return m, nil
	case "f":
		if m.showingAnswer && m.answer != nil && m.answer.HasShort() {
			m.fullAnswer = !m.fullAnswer
			m.refreshView()
			m.view.GotoTop()
		}
		return m, nil
	case "d":
		if m.showingAnswer {
			m.showingAnswer = false
			m.refreshView()
			m.view.GotoTop()
		} else if m.answer != nil {
			m.showingAnswer = true
			m.refreshView()
			m.view.GotoTop()
		}
		return m, nil
	case "enter":
		if m.focus == focusList {
			m.focus = focusView
			m.showingAnswer = false
			m.refreshView()
			return m, nil
		}
	case "esc":
		if m.focus == focusView {
			m.focus = focusList
			return m, nil
		}
	}

	if m.focus == focusView {
		var cmd tea.Cmd
		m.view, cmd = m.view.Update(msg)
		return m, cmd
	}
	var cmd tea.Cmd
	m.list, cmd = m.list.Update(msg)
	return m, tea.Batch(cmd, m.selectionChanged())
}

// selectionChanged carrega o documento selecionado quando ele muda.
func (m *Model) selectionChanged() tea.Cmd {
	sel, ok := m.list.SelectedItem().(item)
	if !ok || sel.doc.ID == m.docID {
		return nil
	}
	m.docID = sel.doc.ID
	m.docDetail = nil
	m.review = nil
	m.showingAnswer = false
	m.refreshView()
	if sel.doc.Status == "draft" {
		return tea.Batch(m.loadDoc(sel.doc.ID), m.loadReview(sel.doc.ID))
	}
	return m.loadDoc(sel.doc.ID)
}

// Geometria: cabeçalho 1, entrada 3, ajuda 1, faixa de aviso 3 quando houver.
func (m *Model) bodyHeight() int {
	h := m.height - 1 - 3 - 1
	if m.banner() != "" {
		h -= lipgloss.Height(m.banner())
	}
	return max(h, 4)
}

func (m *Model) leftWidth() int {
	return min(max(m.width*36/100, 28), 56)
}

func (m *Model) layout() {
	bh := m.bodyHeight()
	lw := m.leftWidth()
	m.list.SetSize(lw-4, bh-4) // 2 linhas para listStatus
	m.view.Width = m.width - lw - 4
	m.view.Height = bh - 2
	m.input.Width = m.width - 8
}

func (m *Model) markdown(src string) string {
	width := max(m.view.Width-1, 20)
	if m.renderer == nil || m.rendererWidth != width {
		r, err := glamour.NewTermRenderer(
			glamour.WithStandardStyle(m.style),
			glamour.WithWordWrap(width),
		)
		if err != nil {
			return src
		}
		m.renderer, m.rendererWidth = r, width
	}
	out, err := m.renderer.Render(src)
	if err != nil {
		return src
	}
	return strings.Trim(out, "\n")
}

// pick escolhe a curta ou a completa conforme fullAnswer. Sem curta, completa.
func (m Model) pick(short, full string) string {
	if m.fullAnswer || strings.TrimSpace(short) == "" {
		return full
	}
	return short
}

func (m *Model) refreshView() {
	if m.width == 0 {
		return
	}
	var b strings.Builder
	switch {
	case m.showingAnswer && m.answer != nil:
		a := m.answer
		b.WriteString(accentStyle.Render("Pergunta") + "\n")
		b.WriteString(titleStyle.Render(m.question) + "\n\n")
		b.WriteString(badge("cobertura: "+a.Coverage, coverageColor(a.Coverage)) + "\n")
		if a.Research != nil {
			r := a.Research
			switch {
			case r.Blocked != "":
				b.WriteString("\n" + errorStyle.Render("Pesquisa bloqueada: ") + r.Blocked + "\n")
			case !r.OK:
				b.WriteString("\n" + errorStyle.Render("Pesquisa falhou: ") + r.Error + "\n")
			default:
				b.WriteString(badge("resposta da IA, ainda não verificada", colYellow) + "\n")
				if r.DraftPath != "" {
					rel, err := filepath.Rel(m.root, r.DraftPath)
					if err != nil {
						rel = r.DraftPath
					}
					b.WriteString(mutedStyle.Render("rascunho: "+rel) + "\n")
				}
				b.WriteString("\n" + m.markdown(m.pick(r.Summary, stripDraftNotice(r.Answer))) + "\n")
			}
			for _, d := range r.Discarded {
				b.WriteString(mutedStyle.Render("descartada: "+d) + "\n")
			}
		} else {
			b.WriteString("\n" + m.markdown(m.pick(a.Short, a.Text)) + "\n")
		}
		if a.Research == nil && a.NeedsResearch() && !m.research.Enabled {
			b.WriteString("\n" + mutedStyle.Render("pesquisa externa desligada (research.enabled = false)"))
		}
	case m.docDetail != nil:
		d := m.docDetail
		title, _ := d.Front["title"].(string)
		status, _ := d.Front["status"].(string)
		typ, _ := d.Front["type"].(string)
		b.WriteString(titleStyle.Render(title) + "\n")
		b.WriteString(badge(status, statusColor(status)) + mutedStyle.Render("  "+typ))
		if updated := fmt.Sprint(d.Front["updated_at"]); updated != "" && updated != "<nil>" {
			b.WriteString(mutedStyle.Render("  ·  atualizado " + updated))
		}
		b.WriteString("\n")
		if tags, ok := d.Front["tags"].([]any); ok && len(tags) > 0 {
			parts := make([]string, len(tags))
			for i, t := range tags {
				parts[i] = "#" + fmt.Sprint(t)
			}
			b.WriteString(keyStyle.Render(strings.Join(parts, " ")) + "\n")
		}
		rel, err := filepath.Rel(m.root, d.Path)
		if err != nil {
			rel = d.Path
		}
		b.WriteString(mutedStyle.Render(rel) + "\n\n")
		if summary, _ := d.Front["summary"].(string); strings.TrimSpace(summary) != "" {
			b.WriteString(m.markdown("> "+strings.TrimSpace(summary)) + "\n\n")
		}
		if status == "draft" {
			b.WriteString(m.reviewBlock())
		}
		b.WriteString(m.markdown(dropTitle(d.Body, title)))
	case m.docID != "":
		b.WriteString(mutedStyle.Render("carregando…"))
	default:
		b.WriteString(mutedStyle.Render("nenhum documento selecionado"))
	}
	// Glamour já quebra o Markdown; isto cobre o resto (erros, caminhos).
	m.view.SetContent(lipgloss.NewStyle().Width(m.view.Width).Render(b.String()))
}

// dropTitle tira o "# Título" do começo do corpo quando repete o cabeçalho.
func dropTitle(body, title string) string {
	trimmed := strings.TrimLeft(body, "\n")
	first, rest, _ := strings.Cut(trimmed, "\n")
	if title != "" && strings.TrimSpace(strings.TrimPrefix(first, "# ")) == strings.TrimSpace(title) &&
		strings.HasPrefix(first, "# ") {
		return strings.TrimLeft(rest, "\n")
	}
	return body
}

// stripDraftNotice tira o cabeçalho que o CLI imprime antes da resposta,
// porque o TUI já mostra aviso e caminho do rascunho do jeito dele.
func stripDraftNotice(s string) string {
	const head = "Resposta externa, ainda não verificada.\n"
	if !strings.HasPrefix(s, head) {
		return s
	}
	rest := strings.TrimPrefix(s, head)
	if strings.HasPrefix(rest, "Rascunho salvo em:\n") {
		lines := strings.SplitN(rest, "\n", 3)
		if len(lines) == 3 {
			rest = lines[2]
		}
	}
	return strings.TrimLeft(rest, "\n")
}

func (m Model) banner() string {
	width := max(m.width-2, 10)
	switch m.state {
	case askLocal:
		return bannerStyle.BorderForeground(colAccent).Width(width).Render(
			m.spinner.View() + " procurando na base: " + truncate(m.question, width-30) +
				mutedStyle.Render("   esc cancela"))
	case askResearch:
		return bannerStyle.BorderForeground(colAccent).Width(width).Render(
			m.spinner.View() + " pesquisando na web e perguntando à IA…" +
				mutedStyle.Render("   esc cancela"))
	case askCountdown:
		lead := "A base não sabe responder isso."
		if m.answer != nil && m.answer.Coverage == "partial" {
			lead = "A base só cobre parte disso."
		}
		var action string
		if m.paused {
			action = "Pesquisar com IA? " + keyStyle.Render("enter") + " sim · " +
				keyStyle.Render("esc") + " não"
		} else {
			action = "Pesquisando com IA em " +
				accentStyle.Render(fmt.Sprintf("%ds", m.remaining)) + mutedStyle.Render("   ") +
				keyStyle.Render("enter") + " agora · " + keyStyle.Render("esc") +
				" cancela · outra tecla pausa"
		}
		return bannerStyle.Width(width).Render(lead + " " + action)
	}
	if rb := m.reviewBanner(width); rb != "" {
		return rb
	}
	if m.err != "" {
		return bannerStyle.BorderForeground(colRed).Width(width).Render(
			errorStyle.Render("erro: ") + m.err)
	}
	return ""
}

func (m Model) View() string {
	if m.width == 0 {
		return ""
	}
	counts := map[string]int{}
	for _, d := range m.docs {
		counts[d.Status]++
	}
	stats := fmt.Sprintf("%d docs · %d verificados · %d rascunhos", len(m.docs),
		counts["verified"], counts["draft"])
	header := brandStyle.Render("lore") + " " + headerStyle.Render(truncate(m.root, m.width/2)) +
		"  " + mutedStyle.Render(stats)

	bh := m.bodyHeight()
	lw := m.leftWidth()
	left := paneStyle
	right := paneStyle
	if m.focus == focusList {
		left = paneFocusStyle
	}
	if m.focus == focusView {
		right = paneFocusStyle
	}
	leftPane := left.Width(lw - 2).Height(bh - 2).Render(m.listStatus() + "\n\n" + m.list.View())
	rightPane := right.Width(m.width - lw - 2).Height(bh - 2).Render(m.view.View())
	body := lipgloss.JoinHorizontal(lipgloss.Top, leftPane, rightPane)

	ask := paneStyle
	if m.focus == focusAsk {
		ask = paneFocusStyle
	}
	askBox := ask.Width(m.width - 2).Render(m.input.View())

	help := m.helpLine()
	parts := []string{header, body}
	if b := m.banner(); b != "" {
		parts = append(parts, b)
	}
	parts = append(parts, askBox, help)
	return lipgloss.JoinVertical(lipgloss.Left, parts...)
}

func (m Model) listStatus() string {
	total := len(m.list.Items())
	shown := len(m.list.VisibleItems())
	noun := "documentos"
	if total == 1 {
		noun = "documento"
	}
	text := fmt.Sprintf("%d %s", total, noun)
	if m.statusFilter != showAll {
		text = fmt.Sprintf("%d %s", total, m.statusFilter.label())
	}
	if m.list.FilterState() != list.Unfiltered {
		text = fmt.Sprintf("“%s” · %d de %d", m.list.FilterValue(), shown, total)
	}
	return mutedStyle.Render(" " + truncate(text, m.leftWidth()-6))
}

func (m Model) helpLine() string {
	pairs := [][2]string{{"a", "perguntar"}, {"/", "filtrar"},
		{"v", "ver " + ((m.statusFilter + 1) % 3).label()}, {"e", "editar"}, {"tab", "foco"},
		{"r", "recarregar"}, {"q", "sair"}}
	if doc, ok := m.selectedDoc(); ok && doc.Status == "draft" {
		pairs = append([][2]string{{"A", "aprovar"}, {"R", "rejeitar"}}, pairs...)
	}
	if m.answer != nil && m.research.Enabled && m.state == askIdle {
		pairs = append([][2]string{{"p", "pesquisar com IA"}}, pairs...)
	}
	if m.showingAnswer && m.answer != nil && m.answer.HasShort() {
		label := "resposta completa"
		if m.fullAnswer {
			label = "resposta curta"
		}
		pairs = append([][2]string{{"f", label}}, pairs...)
	}
	if m.answer != nil {
		label := "ver resposta"
		if m.showingAnswer {
			label = "ver documento"
		}
		pairs = append([][2]string{{"d", label}}, pairs...)
	}
	if m.focus == focusAsk {
		pairs = [][2]string{{"enter", "perguntar"}, {"esc", "voltar"}}
	}
	parts := make([]string, len(pairs))
	for i, p := range pairs {
		parts[i] = keyStyle.Render(p[0]) + " " + mutedStyle.Render(p[1])
	}
	return " " + truncate(strings.Join(parts, mutedStyle.Render("  ·  ")), m.width-2)
}
