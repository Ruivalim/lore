package main

import (
	"context"
	"errors"
	"os/exec"
	"strings"
	"testing"
	"time"

	"github.com/charmbracelet/bubbles/spinner"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/x/ansi"
)

type fakeLore struct {
	docs     []Doc
	cfg      ResearchConfig
	local    AskResult
	research AskResult
	askErr   error
	asks     []bool // research? de cada chamada

	review     ReviewInfo
	actionErr  error
	approved   []string
	rejected   [][2]string // id, motivo
	edited     []string
	actionPath string

	summary string // vai no front de todo Show
}

func (f *fakeLore) Review(context.Context, string) (ReviewInfo, error) { return f.review, nil }
func (f *fakeLore) Approve(_ context.Context, id string) (string, error) {
	f.approved = append(f.approved, id)
	return f.actionPath, f.actionErr
}
func (f *fakeLore) Reject(_ context.Context, id, reason string) (string, error) {
	f.rejected = append(f.rejected, [2]string{id, reason})
	return f.actionPath, f.actionErr
}
func (f *fakeLore) EditCmd(id string) *exec.Cmd {
	f.edited = append(f.edited, id)
	return exec.Command("true")
}

func (f *fakeLore) List(context.Context) ([]Doc, error) { return f.docs, nil }
func (f *fakeLore) Show(_ context.Context, id string) (DocDetail, error) {
	front := map[string]any{"id": id, "title": id}
	if f.summary != "" {
		front["summary"] = f.summary
	}
	for _, d := range f.docs {
		if d.ID == id {
			front["status"] = d.Status
		}
	}
	return DocDetail{Front: front, Body: "# " + id + "\n\ncorpo"}, nil
}
func (f *fakeLore) Research(context.Context) (ResearchConfig, error) { return f.cfg, nil }
func (f *fakeLore) Ask(_ context.Context, _ string, research bool) (AskResult, error) {
	f.asks = append(f.asks, research)
	if f.askErr != nil {
		return AskResult{}, f.askErr
	}
	if research {
		return f.research, nil
	}
	return f.local, nil
}

// plain tira a cor: o Glamour colore palavra por palavra.
func plain(s string) string { return ansi.Strip(s) }

func boolp(b bool) *bool { return &b }

func newTestModel(f *fakeLore) Model {
	m := NewModel(f, "/repo", "dark")
	m = step(m, tea.WindowSizeMsg{Width: 120, Height: 40})
	m = step(m, configMsg{cfg: f.cfg})
	return m
}

func step(m Model, msg tea.Msg) Model {
	next, _ := m.Update(msg)
	return next.(Model)
}

// run aplica msg e executa o comando devolvido, como o runtime faria.
// Comandos de tick e batch não são seguidos: o teste manda os ticks.
func run(m Model, msg tea.Msg) (Model, tea.Msg) {
	next, cmd := m.Update(msg)
	m = next.(Model)
	if cmd == nil {
		return m, nil
	}
	return m, cmd()
}

func key(s string) tea.KeyMsg {
	switch s {
	case "enter":
		return tea.KeyMsg{Type: tea.KeyEnter}
	case "esc":
		return tea.KeyMsg{Type: tea.KeyEsc}
	}
	return tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune(s)}
}

// ask digita a pergunta e devolve o modelo com a resposta local aplicada.
func ask(t *testing.T, m Model, q string) Model {
	t.Helper()
	m = step(m, key("a"))
	for _, r := range q {
		m = step(m, key(string(r)))
	}
	m, msg := run(m, key("enter"))
	if m.state != askLocal {
		t.Fatalf("depois do enter, estado = %v, queria askLocal", m.state)
	}
	am, ok := msg.(askMsg)
	if !ok {
		t.Fatalf("enter não disparou ask, veio %T", msg)
	}
	return step(m, am)
}

func insufficient() AskResult {
	return AskResult{Coverage: "insufficient", Text: "A base não contém uma resposta confiável.\n"}
}

func TestCountdownRunsResearchWhenNobodyTouches(t *testing.T) {
	f := &fakeLore{
		cfg:      ResearchConfig{Enabled: true, ConfirmTimeout: 5},
		local:    insufficient(),
		research: AskResult{Coverage: "insufficient", Research: &Research{OK: true, Answer: "é Ulan Bator"}},
	}
	m := ask(t, newTestModel(f), "capital da mongolia")
	if m.state != askCountdown || m.remaining != 5 {
		t.Fatalf("estado %v restante %d, queria contagem de 5", m.state, m.remaining)
	}
	seq := m.askSeq
	for i := 0; i < 4; i++ {
		m = step(m, tickMsg{seq: seq})
	}
	if m.state != askCountdown || m.remaining != 1 {
		t.Fatalf("depois de 4 ticks: estado %v restante %d", m.state, m.remaining)
	}
	m, msg := run(m, tickMsg{seq: seq})
	if m.state != askResearch {
		t.Fatalf("contagem zerou mas estado = %v", m.state)
	}
	m = step(m, msg)
	if m.state != askIdle || len(f.asks) != 2 || !f.asks[1] {
		t.Fatalf("pesquisa não rodou: estado %v asks %v", m.state, f.asks)
	}
	if !strings.Contains(plain(m.view.View()), "Ulan Bator") {
		t.Fatalf("resposta da pesquisa não aparece:\n%s", m.view.View())
	}
}

func TestEnterDuringCountdownResearchesNow(t *testing.T) {
	f := &fakeLore{cfg: ResearchConfig{Enabled: true, ConfirmTimeout: 5}, local: insufficient(),
		research: AskResult{Research: &Research{OK: true, Answer: "x"}}}
	m := ask(t, newTestModel(f), "q")
	m, _ = run(m, key("enter"))
	if m.state != askResearch {
		t.Fatalf("enter na contagem: estado %v", m.state)
	}
}

func TestEscCancelsAndLateTickIsIgnored(t *testing.T) {
	f := &fakeLore{cfg: ResearchConfig{Enabled: true, ConfirmTimeout: 2}, local: insufficient()}
	m := ask(t, newTestModel(f), "q")
	oldSeq := m.askSeq
	m = step(m, key("esc"))
	if m.state != askIdle {
		t.Fatalf("esc não cancelou: %v", m.state)
	}
	for i := 0; i < 5; i++ {
		m = step(m, tickMsg{seq: oldSeq})
	}
	if m.state != askIdle || len(f.asks) != 1 {
		t.Fatalf("tick antigo disparou pesquisa: estado %v asks %v", m.state, f.asks)
	}
}

func TestOtherKeyPausesCountdown(t *testing.T) {
	f := &fakeLore{cfg: ResearchConfig{Enabled: true, ConfirmTimeout: 1}, local: insufficient()}
	m := ask(t, newTestModel(f), "q")
	m = step(m, key("x"))
	for i := 0; i < 10; i++ {
		m = step(m, tickMsg{seq: m.askSeq})
	}
	if m.state != askCountdown || !m.paused {
		t.Fatalf("pausa não segurou: estado %v pausado %v", m.state, m.paused)
	}
	m = step(m, key("n"))
	if m.state != askIdle || len(f.asks) != 1 {
		t.Fatalf("n depois da pausa: estado %v asks %v", m.state, f.asks)
	}
}

func TestZeroTimeoutWaitsForDecision(t *testing.T) {
	f := &fakeLore{cfg: ResearchConfig{Enabled: true, ConfirmTimeout: 0}, local: insufficient()}
	m := ask(t, newTestModel(f), "q")
	if !m.paused {
		t.Fatal("timeout 0 deveria esperar decisão, não contar")
	}
	m = step(m, tickMsg{seq: m.askSeq})
	if m.state != askCountdown {
		t.Fatalf("estado %v", m.state)
	}
}

func TestNoConfirmationSkipsCountdown(t *testing.T) {
	f := &fakeLore{cfg: ResearchConfig{Enabled: true, RequireConfirmation: boolp(false)},
		local: insufficient()}
	m := ask(t, newTestModel(f), "q")
	if m.state != askResearch {
		t.Fatalf("require_confirmation=false: estado %v, queria pesquisa direta", m.state)
	}
}

func TestResearchDisabledStopsAtLocalAnswer(t *testing.T) {
	f := &fakeLore{cfg: ResearchConfig{Enabled: false}, local: insufficient()}
	m := ask(t, newTestModel(f), "q")
	if m.state != askIdle {
		t.Fatalf("pesquisa desligada mas estado %v", m.state)
	}
	if !strings.Contains(plain(m.view.View()), "pesquisa externa desligada") {
		t.Fatalf("faltou aviso:\n%s", m.view.View())
	}
	m = step(m, key("p"))
	if m.state != askIdle {
		t.Fatal("p não pode pesquisar com research desligado")
	}
}

func TestSufficientAnswerNeverResearches(t *testing.T) {
	f := &fakeLore{cfg: ResearchConfig{Enabled: true, ConfirmTimeout: 5},
		local: AskResult{Coverage: "sufficient", Text: "use git log"}}
	m := ask(t, newTestModel(f), "q")
	if m.state != askIdle || len(f.asks) != 1 {
		t.Fatalf("estado %v asks %v", m.state, f.asks)
	}
}

func TestAskErrorShowsBanner(t *testing.T) {
	f := &fakeLore{cfg: ResearchConfig{Enabled: true}, askErr: errors.New("índice ausente")}
	m := ask(t, newTestModel(f), "q")
	if m.state != askIdle || !strings.Contains(plain(m.View()), "índice ausente") {
		t.Fatalf("erro não apareceu; estado %v", m.state)
	}
}

func TestStaleAnswerAfterNewQuestionIgnored(t *testing.T) {
	f := &fakeLore{cfg: ResearchConfig{Enabled: true, ConfirmTimeout: 5}, local: insufficient()}
	m := newTestModel(f)
	m = step(m, key("a"))
	m = step(m, key("x"))
	m, first := run(m, key("enter"))
	m = step(m, key("y"))
	m, _ = run(m, key("enter")) // segunda pergunta antes da primeira voltar
	m = step(m, first)
	if m.answer != nil {
		t.Fatal("resposta da primeira pergunta foi aplicada depois da segunda")
	}
}

func TestEmptyQuestionDoesNothing(t *testing.T) {
	f := &fakeLore{}
	m := newTestModel(f)
	m = step(m, key("a"))
	m = step(m, key(" "))
	m, msg := run(m, key("enter"))
	if msg != nil || m.state != askIdle {
		t.Fatalf("pergunta vazia disparou algo: %T %v", msg, m.state)
	}
}

func TestNewDraftGetsSelectedAfterResearch(t *testing.T) {
	f := &fakeLore{
		cfg:   ResearchConfig{Enabled: true, RequireConfirmation: boolp(false)},
		local: insufficient(),
		research: AskResult{Research: &Research{OK: true, Answer: "a",
			DraftPath: "/repo/drafts/nova.md"}},
		docs: []Doc{{ID: "velha", Path: "knowledge/velha.md"}, {ID: "nova", Path: "drafts/nova.md"}},
	}
	m := ask(t, newTestModel(f), "q")
	res, _ := f.Ask(context.Background(), "q", true)
	m, reload := run(m, askMsg{seq: m.askSeq, research: true, result: res})
	docs, ok := reload.(docsMsg)
	if !ok {
		t.Fatalf("pesquisa com rascunho não recarregou a lista: %T", reload)
	}
	m = step(m, docs)
	if sel := m.list.SelectedItem().(item); sel.doc.ID != "nova" {
		t.Fatalf("selecionado %q, queria o rascunho novo", sel.doc.ID)
	}
}

func TestDropTitle(t *testing.T) {
	if got := dropTitle("# Oi\n\ncorpo", "Oi"); got != "corpo" {
		t.Fatalf("got %q", got)
	}
	if got := dropTitle("# Outro\n\ncorpo", "Oi"); !strings.HasPrefix(got, "# Outro") {
		t.Fatalf("tirou título diferente: %q", got)
	}
	if got := dropTitle("corpo", ""); got != "corpo" {
		t.Fatalf("got %q", got)
	}
}

func TestStripDraftNotice(t *testing.T) {
	in := "Resposta externa, ainda não verificada.\nRascunho salvo em:\n  /x/y.md\n\nresposta"
	if got := stripDraftNotice(in); got != "resposta" {
		t.Fatalf("got %q", got)
	}
	if got := stripDraftNotice("outra coisa"); got != "outra coisa" {
		t.Fatalf("got %q", got)
	}
}

func TestTinyWindowDoesNotPanic(t *testing.T) {
	f := &fakeLore{docs: []Doc{{ID: "a", Title: strings.Repeat("título longo ", 20)}}}
	m := newTestModel(f)
	m = step(m, docsMsg{docs: f.docs})
	for _, size := range [][2]int{{1, 1}, {10, 5}, {30, 8}, {300, 100}} {
		m = step(m, tea.WindowSizeMsg{Width: size[0], Height: size[1]})
		_ = m.View()
	}
}

// drain executa o comando e devolve as mensagens ao modelo, como o runtime.
// Comando que não volta em 50ms é timer (cursor, spinner, status) e fica de fora.
func drain(t *testing.T, m Model, cmd tea.Cmd, depth int) Model {
	t.Helper()
	if cmd == nil || depth > 8 {
		return m
	}
	done := make(chan tea.Msg, 1)
	go func() { done <- cmd() }()
	var msg tea.Msg
	select {
	case msg = <-done:
	case <-time.After(50 * time.Millisecond):
		return m
	}
	if batch, ok := msg.(tea.BatchMsg); ok {
		for _, c := range batch {
			m = drain(t, m, c, depth+1)
		}
		return m
	}
	switch msg.(type) {
	case nil, spinner.TickMsg, tickMsg:
		return m
	}
	next, c := m.Update(msg)
	return drain(t, next.(Model), c, depth+1)
}

func TestListFilterAppliesThroughUpdate(t *testing.T) {
	f := &fakeLore{docs: []Doc{
		{ID: "commits", Title: "Como eu vejo as mensagens dos ultimos commits"},
		{ID: "como-descompacta-um-tar", Title: "Como descompacta um tar"},
		{ID: "sunshine", Title: "Porta default do sunshine"},
	}}
	m := newTestModel(f)
	m = step(m, docsMsg{docs: f.docs})
	for _, k := range []string{"/", "t", "a", "r"} {
		next, cmd := m.Update(key(k))
		m = drain(t, next.(Model), cmd, 0)
	}
	next, cmd := m.Update(key("enter"))
	m = drain(t, next.(Model), cmd, 0)
	visible := m.list.VisibleItems()
	if len(visible) != 1 || visible[0].(item).doc.ID != "como-descompacta-um-tar" {
		ids := []string{}
		for _, v := range visible {
			ids = append(ids, v.(item).doc.ID)
		}
		t.Fatalf("filtro tar mostra %v", ids)
	}
	if m.docID != "como-descompacta-um-tar" {
		t.Fatalf("seleção não acompanhou o filtro: %q", m.docID)
	}
}

func TestShortAnswerByDefaultAndFTogglesFull(t *testing.T) {
	f := &fakeLore{local: AskResult{Coverage: "sufficient",
		Short: "CURTA direta", Text: "COMPLETA longa"}}
	m := ask(t, newTestModel(f), "q")
	m = step(m, key("esc")) // sai da caixa de pergunta, como para o d
	view := plain(m.View())
	if !strings.Contains(view, "CURTA direta") || strings.Contains(view, "COMPLETA longa") {
		t.Fatalf("esperava só a curta:\n%s", view)
	}
	if !strings.Contains(view, "resposta completa") {
		t.Fatalf("help sem o atalho f:\n%s", view)
	}
	m = step(m, key("f"))
	view = plain(m.View())
	if !strings.Contains(view, "COMPLETA longa") || strings.Contains(view, "CURTA direta") {
		t.Fatalf("f não mostrou a completa:\n%s", view)
	}
	m = step(m, key("f"))
	if !strings.Contains(plain(m.View()), "CURTA direta") {
		t.Fatal("segundo f não voltou para a curta")
	}
}

func TestWithoutShortShowsFullAndFIsInert(t *testing.T) {
	f := &fakeLore{local: AskResult{Coverage: "sufficient", Text: "SÓ completa"}}
	m := ask(t, newTestModel(f), "q")
	m = step(m, key("esc"))
	m = step(m, key("f"))
	view := plain(m.View())
	if !strings.Contains(view, "SÓ completa") {
		t.Fatalf("sem curta tem que mostrar a completa:\n%s", view)
	}
	if strings.Contains(view, "resposta curta") || strings.Contains(view, "resposta completa") {
		t.Fatalf("atalho f não devia aparecer sem curta:\n%s", view)
	}
}

func TestNewAnswerStartsShortAgain(t *testing.T) {
	f := &fakeLore{local: AskResult{Coverage: "sufficient", Short: "CURTA", Text: "COMPLETA"}}
	m := ask(t, newTestModel(f), "q1")
	m = step(m, key("esc"))
	m = step(m, key("f"))
	m = ask(t, m, "q2")
	if !strings.Contains(plain(m.View()), "CURTA") {
		t.Fatal("resposta nova devia abrir na curta")
	}
}

func TestResearchSummaryIsTheShortAnswer(t *testing.T) {
	f := &fakeLore{local: AskResult{Coverage: "sufficient", Research: &Research{
		OK: true, Summary: "RESUMO da pesquisa", Answer: "PESQUISA completa"}}}
	m := ask(t, newTestModel(f), "q")
	m = step(m, key("esc"))
	view := plain(m.View())
	if !strings.Contains(view, "RESUMO da pesquisa") || strings.Contains(view, "PESQUISA completa") {
		t.Fatalf("pesquisa devia abrir no resumo:\n%s", view)
	}
	m = step(m, key("f"))
	if !strings.Contains(plain(m.View()), "PESQUISA completa") {
		t.Fatal("f não mostrou a pesquisa completa")
	}
}

func TestFailedResearchHasNoShortToggle(t *testing.T) {
	a := AskResult{Research: &Research{OK: false, Summary: "x", Error: "falhou"}}
	if a.HasShort() {
		t.Fatal("pesquisa que falhou não tem curta")
	}
}

func TestDocViewShowsSummary(t *testing.T) {
	f := &fakeLore{docs: []Doc{{ID: "doc-um", Title: "doc-um", Status: "verified", Valid: true}},
		summary: "Resumo revisado do documento"}
	m := newTestModel(f)
	m, msg := run(m, docsMsg{docs: f.docs})
	for msg != nil {
		var next tea.Msg
		m, next = run(m, msg)
		msg = next
	}
	if !strings.Contains(plain(m.View()), "Resumo revisado do documento") {
		t.Fatalf("leitor sem o summary:\n%s", plain(m.View()))
	}
}
