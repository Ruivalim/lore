package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os/exec"
	"strings"
	"syscall"
)

// Doc é uma linha de `lore list --json`.
type Doc struct {
	ID         string   `json:"id"`
	Title      string   `json:"title"`
	Type       string   `json:"type"`
	Status     string   `json:"status"`
	Tags       []string `json:"tags"`
	UpdatedAt  string   `json:"updated_at"`
	Path       string   `json:"path"`
	Valid      bool     `json:"valid"`
	ReviewedBy string   `json:"reviewed_by"`
}

// DocDetail vem de `lore show --json`.
type DocDetail struct {
	Front map[string]any `json:"front"`
	Body  string         `json:"body"`
	Path  string         `json:"path"`
}

// Research é o bloco "research" de `lore ask --json`.
type Research struct {
	OK        bool     `json:"ok"`
	Answer    string   `json:"answer"`
	Summary   string   `json:"summary"`
	DraftPath string   `json:"draft_path"`
	Blocked   string   `json:"blocked"`
	Error     string   `json:"error"`
	Discarded []string `json:"discarded"`
}

// NeedsConfirmation: entrou em verified pela política automática.
func (d Doc) NeedsConfirmation() bool {
	return d.Status == "verified" && d.ReviewedBy == "auto"
}

// HasShort diz se há resposta curta para alternar com a completa.
func (a AskResult) HasShort() bool {
	if a.Research != nil {
		return a.Research.OK && strings.TrimSpace(a.Research.Summary) != ""
	}
	return strings.TrimSpace(a.Short) != ""
}

// AskResult é a saída de `lore ask --json`.
type AskResult struct {
	Coverage   string    `json:"coverage"`
	Short      string    `json:"short"`
	Text       string    `json:"text"`
	Citations  []string  `json:"citations"`
	Gap        []string  `json:"gap"`
	Warning    string    `json:"warning"`
	Researched bool      `json:"researched"`
	Research   *Research `json:"research"`
}

// NeedsResearch diz se a base local não deu conta da pergunta.
func (a AskResult) NeedsResearch() bool {
	return a.Coverage == "insufficient" || a.Coverage == "partial"
}

// ResearchConfig é o pedaço de `lore config --json` que o TUI usa.
type ResearchConfig struct {
	Enabled             bool    `json:"enabled"`
	RequireConfirmation *bool   `json:"require_confirmation"`
	ConfirmTimeout      float64 `json:"confirm_timeout"`
}

// Confirm reproduz o default do Python: sem a chave, pede confirmação.
func (c ResearchConfig) Confirm() bool {
	return c.RequireConfirmation == nil || *c.RequireConfirmation
}

// ReviewInfo é o que `lore review <id> --json` aponta num rascunho.
type ReviewInfo struct {
	Valid             bool     `json:"valid"`
	Errors            []string `json:"errors"`
	UnsourcedClaims   []string `json:"unsourced_claims"`
	PossibleConflicts []string `json:"possible_conflicts"`
}

// Lore é tudo que o TUI pede ao CLI Python. Interface para os testes.
type Lore interface {
	List(ctx context.Context) ([]Doc, error)
	Show(ctx context.Context, id string) (DocDetail, error)
	Research(ctx context.Context) (ResearchConfig, error)
	Ask(ctx context.Context, question string, research bool) (AskResult, error)
	Review(ctx context.Context, id string) (ReviewInfo, error)
	// Approve e Reject devolvem o caminho novo do documento.
	Approve(ctx context.Context, id string) (string, error)
	Reject(ctx context.Context, id, reason string) (string, error)
	// EditCmd é interativo (abre $EDITOR), por isso devolve o comando.
	EditCmd(id string) *exec.Cmd
}

// ExecLore chama o binário `lore` e lê o JSON da saída.
type ExecLore struct {
	Bin  string
	Root string
}

func (l ExecLore) run(ctx context.Context, out any, args ...string) error {
	full := append([]string{"--root", l.Root, "--json"}, args...)
	cmd := exec.CommandContext(ctx, l.Bin, full...)
	// Cancelar mata o grupo todo: o lore chama claude/pi como filhos, e
	// matar só o Python deixaria o agente rodando órfão e gastando.
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	cmd.Cancel = func() error { return syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL) }
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	runErr := cmd.Run()
	if ctx.Err() != nil {
		return ctx.Err()
	}
	return decode(stdout.Bytes(), stderr.String(), runErr, out)
}

// decode separa três casos: JSON de erro do lore, JSON útil (mesmo com
// código != 0, como pesquisa que falhou) e saída que nem JSON é.
func decode(stdout []byte, stderr string, runErr error, out any) error {
	var head struct {
		OK    *bool  `json:"ok"`
		Error string `json:"error"`
	}
	if err := json.Unmarshal(stdout, &head); err != nil || head.OK == nil {
		detail := strings.TrimSpace(stderr)
		if detail == "" {
			detail = strings.TrimSpace(string(stdout))
		}
		if runErr != nil {
			return fmt.Errorf("lore falhou (%v): %s", runErr, firstLine(detail))
		}
		return fmt.Errorf("resposta do lore não é JSON: %s", firstLine(detail))
	}
	if !*head.OK && head.Error != "" {
		// KeyError do Python chega como "'id não encontrado: x'".
		return errors.New(strings.Trim(head.Error, "'"))
	}
	if err := json.Unmarshal(stdout, out); err != nil {
		return fmt.Errorf("JSON inesperado do lore: %w", err)
	}
	return nil
}

func firstLine(s string) string {
	if s == "" {
		return "(sem saída)"
	}
	line, _, _ := strings.Cut(s, "\n")
	return line
}

func (l ExecLore) List(ctx context.Context) ([]Doc, error) {
	var out struct {
		Docs []Doc `json:"docs"`
	}
	err := l.run(ctx, &out, "list")
	return out.Docs, err
}

func (l ExecLore) Show(ctx context.Context, id string) (DocDetail, error) {
	var out DocDetail
	err := l.run(ctx, &out, "show", id)
	return out, err
}

func (l ExecLore) Research(ctx context.Context) (ResearchConfig, error) {
	var out struct {
		Config struct {
			Research ResearchConfig `json:"research"`
		} `json:"config"`
	}
	err := l.run(ctx, &out, "config")
	return out.Config.Research, err
}

func (l ExecLore) Ask(ctx context.Context, question string, research bool) (AskResult, error) {
	var out AskResult
	flag := "--local-only"
	if research {
		flag = "--yes"
	}
	err := l.run(ctx, &out, "ask", flag, "--", question)
	return out, err
}

func (l ExecLore) Review(ctx context.Context, id string) (ReviewInfo, error) {
	var out ReviewInfo
	err := l.run(ctx, &out, "review", "--", id)
	return out, err
}

type pathOut struct {
	Path string `json:"path"`
}

// Aprovar e rejeitar exigem --human no CLI: aqui quem apertou a tecla e
// confirmou foi a pessoa, é exatamente o caso.
func (l ExecLore) Approve(ctx context.Context, id string) (string, error) {
	var out pathOut
	err := l.run(ctx, &out, "approve", "--human", "--", id)
	return out.Path, err
}

func (l ExecLore) Reject(ctx context.Context, id, reason string) (string, error) {
	var out pathOut
	err := l.run(ctx, &out, "reject", "--human", "--reason", reason, "--", id)
	return out.Path, err
}

func (l ExecLore) EditCmd(id string) *exec.Cmd {
	return exec.Command(l.Bin, "--root", l.Root, "edit", "--", id)
}
