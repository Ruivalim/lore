package main

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// fakeBin escreve um `lore` de mentira em shell e devolve o caminho.
func fakeBin(t *testing.T, script string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "lore")
	if err := os.WriteFile(path, []byte("#!/bin/sh\n"+script), 0o755); err != nil {
		t.Fatal(err)
	}
	return path
}

func TestAskPassesQuestionSafely(t *testing.T) {
	argsFile := filepath.Join(t.TempDir(), "args")
	bin := fakeBin(t, `printf '%s\n' "$@" > `+argsFile+`
echo '{"ok": true, "coverage": "sufficient", "text": "oi"}'`)
	l := ExecLore{Bin: bin, Root: "/r"}
	res, err := l.Ask(context.Background(), "--yes e se começar com traço?", false)
	if err != nil || res.Text != "oi" {
		t.Fatalf("res %+v err %v", res, err)
	}
	raw, _ := os.ReadFile(argsFile)
	got := strings.Split(strings.TrimSpace(string(raw)), "\n")
	want := []string{"--root", "/r", "--json", "ask", "--local-only", "--", "--yes e se começar com traço?"}
	if strings.Join(got, "|") != strings.Join(want, "|") {
		t.Fatalf("args\n got %q\nwant %q", got, want)
	}
}

func TestResearchFlagUsesYes(t *testing.T) {
	bin := fakeBin(t, `case "$*" in *"--yes"*) echo '{"ok": true, "coverage":"insufficient","research":{"ok":true,"answer":"web"}}';; *) exit 9;; esac`)
	res, err := ExecLore{Bin: bin}.Ask(context.Background(), "q", true)
	if err != nil || res.Research == nil || res.Research.Answer != "web" {
		t.Fatalf("res %+v err %v", res, err)
	}
}

func TestErrorJSONBecomesError(t *testing.T) {
	bin := fakeBin(t, `echo '{"ok": false, "error": "id não encontrado: x"}'; exit 1`)
	_, err := ExecLore{Bin: bin}.Show(context.Background(), "x")
	if err == nil || err.Error() != "id não encontrado: x" {
		t.Fatalf("err %v", err)
	}
}

func TestUsefulJSONWithNonZeroExitIsKept(t *testing.T) {
	// ask sai com 1 quando a pesquisa falha, mas o JSON traz o motivo.
	bin := fakeBin(t, `echo '{"ok": false, "coverage": "insufficient", "research": {"ok": false, "error": "busca web falhou"}}'; exit 1`)
	res, err := ExecLore{Bin: bin}.Ask(context.Background(), "q", true)
	if err != nil || res.Research == nil || res.Research.Error != "busca web falhou" {
		t.Fatalf("res %+v err %v", res, err)
	}
}

func TestGarbageOutputReportsStderr(t *testing.T) {
	bin := fakeBin(t, `echo 'Traceback (most recent call last):' >&2; echo boom >&2; exit 2`)
	_, err := ExecLore{Bin: bin}.List(context.Background())
	if err == nil || !strings.Contains(err.Error(), "Traceback") {
		t.Fatalf("err %v", err)
	}
}

func TestNonJSONSuccessIsError(t *testing.T) {
	bin := fakeBin(t, `echo 'olá, não sou JSON'`)
	_, err := ExecLore{Bin: bin}.List(context.Background())
	if err == nil || !strings.Contains(err.Error(), "não é JSON") {
		t.Fatalf("err %v", err)
	}
}

func TestMissingBinary(t *testing.T) {
	_, err := ExecLore{Bin: "/nao/existe/lore"}.List(context.Background())
	if err == nil {
		t.Fatal("binário inexistente sem erro")
	}
}

func TestCancelKillsSlowProcess(t *testing.T) {
	bin := fakeBin(t, `exec sleep 30`)
	ctx, cancel := context.WithCancel(context.Background())
	go func() { time.Sleep(100 * time.Millisecond); cancel() }()
	started := time.Now()
	_, err := ExecLore{Bin: bin}.Ask(ctx, "q", true)
	if err != context.Canceled {
		t.Fatalf("err %v, queria context.Canceled", err)
	}
	if time.Since(started) > 5*time.Second {
		t.Fatal("cancelamento não matou o processo")
	}
}

func TestResearchConfigDefaultsToConfirm(t *testing.T) {
	bin := fakeBin(t, `echo '{"ok": true, "config": {"research": {"enabled": true}}}'`)
	cfg, err := ExecLore{Bin: bin}.Research(context.Background())
	if err != nil || !cfg.Enabled || !cfg.Confirm() {
		t.Fatalf("cfg %+v err %v", cfg, err)
	}
}
