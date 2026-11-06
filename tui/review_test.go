package main

import (
	"errors"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
)

func reviewFixture() *fakeLore {
	return &fakeLore{
		docs: []Doc{
			{ID: "rasc", Title: "Rascunho bom", Status: "draft", Path: "drafts/rasc.md"},
			{ID: "ok", Title: "Já verificado", Status: "verified", Path: "knowledge/ok.md"},
		},
		review:     ReviewInfo{Valid: true, PossibleConflicts: []string{"conflita com ok"}},
		actionPath: "/repo/knowledge/rasc.md",
	}
}

// loaded devolve o modelo com a lista carregada e o rascunho selecionado.
func loaded(t *testing.T, f *fakeLore) Model {
	t.Helper()
	m := newTestModel(f)
	next, cmd := m.Update(docsMsg{docs: f.docs})
	return drain(t, next.(Model), cmd, 0)
}

func press(t *testing.T, m Model, keys ...string) (Model, tea.Cmd) {
	t.Helper()
	var cmd tea.Cmd
	for _, k := range keys {
		var next tea.Model
		next, cmd = m.Update(key(k))
		m = next.(Model)
	}
	return m, cmd
}

func TestStatusFilterCycles(t *testing.T) {
	m := loaded(t, reviewFixture())
	ids := func() []string {
		var out []string
		for _, it := range m.list.Items() {
			out = append(out, it.(item).doc.ID)
		}
		return out
	}
	if len(ids()) != 2 {
		t.Fatalf("todos: %v", ids())
	}
	m, _ = press(t, m, "v")
	if got := ids(); len(got) != 1 || got[0] != "rasc" {
		t.Fatalf("rascunhos: %v", got)
	}
	if !strings.Contains(plain(m.listStatus()), "1 rascunho") || strings.Contains(plain(m.listStatus()), "1 rascunhos") {
		t.Fatalf("status: %q", plain(m.listStatus()))
	}
	m, _ = press(t, m, "v")
	if got := ids(); len(got) != 1 || got[0] != "ok" {
		t.Fatalf("verificados: %v", got)
	}
	m, _ = press(t, m, "v")
	if len(ids()) != 2 {
		t.Fatalf("voltou para todos? %v", ids())
	}
}

func TestDraftShowsReviewBlock(t *testing.T) {
	m := loaded(t, reviewFixture())
	view := plain(m.view.View())
	if !strings.Contains(view, "Antes de aprovar") || !strings.Contains(view, "conflita com ok") {
		t.Fatalf("bloco de revisão ausente:\n%s", view)
	}
	m, cmd := press(t, m, "j") // desce para o verificado
	m = drain(t, m, cmd, 0)
	if strings.Contains(plain(m.view.View()), "Antes de aprovar") {
		t.Fatal("verificado não devia mostrar bloco de revisão")
	}
}

func TestApproveNeedsExplicitConfirmation(t *testing.T) {
	f := reviewFixture()
	m := loaded(t, f)
	m, _ = press(t, m, "A")
	if m.reviewMode != reviewConfirmApprove {
		t.Fatal("A não pediu confirmação")
	}
	// tecla qualquer, inclusive A de novo, não confirma
	m, _ = press(t, m, "x", "A", "j")
	if m.reviewMode != reviewConfirmApprove || len(f.approved) != 0 {
		t.Fatalf("tecla solta decidiu: modo %v aprovados %v", m.reviewMode, f.approved)
	}
	m, _ = press(t, m, "esc")
	if m.reviewMode != reviewNone || len(f.approved) != 0 {
		t.Fatal("esc não cancelou")
	}
	m, _ = press(t, m, "A")
	next, cmd := m.Update(key("enter"))
	m = next.(Model)
	if m.busy == "" {
		t.Fatal("sem indicação de trabalho em andamento")
	}
	m = drain(t, m, cmd, 0)
	if len(f.approved) != 1 || f.approved[0] != "rasc" {
		t.Fatalf("aprovados %v", f.approved)
	}
	if m.busy != "" || !strings.Contains(m.notice, "aprovado: Rascunho bom → knowledge/rasc.md") {
		t.Fatalf("busy %q notice %q", m.busy, m.notice)
	}
}

func TestApproveOnlyDrafts(t *testing.T) {
	f := reviewFixture()
	m := loaded(t, f)
	m, cmd := press(t, m, "j")
	m = drain(t, m, cmd, 0)
	m, _ = press(t, m, "A")
	if m.reviewMode != reviewNone || !strings.Contains(m.notice, "só rascunho") {
		t.Fatalf("modo %v notice %q", m.reviewMode, m.notice)
	}
	m, _ = press(t, m, "R")
	if m.reviewMode != reviewNone {
		t.Fatal("R abriu motivo num verificado")
	}
}

func TestApproveErrorIsNotSuccess(t *testing.T) {
	f := reviewFixture()
	f.actionErr = errors.New("documento inválido: falta sources")
	m := loaded(t, f)
	m, _ = press(t, m, "A")
	next, cmd := m.Update(key("enter"))
	m = drain(t, next.(Model), cmd, 0)
	if m.notice != "" || !strings.Contains(m.err, "falta sources") || m.busy != "" {
		t.Fatalf("notice %q err %q busy %q", m.notice, m.err, m.busy)
	}
}

func TestRejectAsksReasonAndKeysDontLeak(t *testing.T) {
	f := reviewFixture()
	f.actionPath = "/repo/archive/rasc.md"
	m := loaded(t, f)
	m, _ = press(t, m, "R")
	if m.reviewMode != reviewReason {
		t.Fatal("R não pediu motivo")
	}
	// enter vazio não rejeita
	m, _ = press(t, m, "enter")
	if len(f.rejected) != 0 || m.reviewMode != reviewReason {
		t.Fatal("rejeitou sem motivo")
	}
	// letras de atalho viram texto, não comando
	m, _ = press(t, m, "A", "v", "e", "q", " ", "r", "u", "i", "m")
	if len(f.approved) != 0 || len(f.edited) != 0 || m.statusFilter != showAll {
		t.Fatal("atalho disparou enquanto digitava o motivo")
	}
	next, cmd := m.Update(key("enter"))
	m = drain(t, next.(Model), cmd, 0)
	if len(f.rejected) != 1 || f.rejected[0] != [2]string{"rasc", "Aveq ruim"} {
		t.Fatalf("rejeitados %v", f.rejected)
	}
	if !strings.Contains(m.notice, "rejeitado") {
		t.Fatalf("notice %q", m.notice)
	}
}

func TestRejectEscCancels(t *testing.T) {
	f := reviewFixture()
	m := loaded(t, f)
	m, _ = press(t, m, "R", "x", "esc")
	if m.reviewMode != reviewNone || len(f.rejected) != 0 {
		t.Fatal("esc não cancelou rejeição")
	}
}

func TestEditOpensEditorForSelected(t *testing.T) {
	f := reviewFixture()
	m := loaded(t, f)
	_, cmd := press(t, m, "e")
	if cmd == nil || len(f.edited) != 1 || f.edited[0] != "rasc" {
		t.Fatalf("edit: cmd %v editados %v", cmd != nil, f.edited)
	}
}

func TestStaleReviewIgnored(t *testing.T) {
	m := loaded(t, reviewFixture())
	m = step(m, reviewMsg{id: "outro", info: ReviewInfo{PossibleConflicts: []string{"FANTASMA"}}})
	if strings.Contains(plain(m.view.View()), "FANTASMA") {
		t.Fatal("review de outro documento foi aplicado")
	}
}

func TestAutoApprovedCanBeConfirmedWithA(t *testing.T) {
	f := reviewFixture()
	f.docs = append(f.docs, Doc{ID: "auto", Title: "Entrou sozinho", Status: "verified",
		ReviewedBy: "auto", Path: "knowledge/auto.md"})
	m := loaded(t, f)
	m, cmd := press(t, m, "j", "j")
	m = drain(t, m, cmd, 0)
	if !strings.Contains(plain(m.View()), "confirmar revisão") {
		t.Fatalf("help sem confirmar revisão:\n%s", plain(m.View()))
	}
	m, _ = press(t, m, "A")
	if m.reviewMode != reviewConfirmApprove || !strings.Contains(plain(m.View()), "Entrou sem revisão humana") {
		t.Fatalf("A não pediu confirmação de revisão: modo %v", m.reviewMode)
	}
	next, cmd := m.Update(key("enter"))
	drain(t, next.(Model), cmd, 0)
	if len(f.approved) != 1 || f.approved[0] != "auto" {
		t.Fatalf("aprovados %v", f.approved)
	}
	// R continua só para rascunho
	m, _ = press(t, m, "esc", "R")
	if m.reviewMode != reviewNone {
		t.Fatal("R abriu motivo num verificado")
	}
}
