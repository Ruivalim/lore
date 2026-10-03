package main

import "testing"

func indexes(term string, targets []string) []int {
	var out []int
	for _, r := range filterTerms(term, targets) {
		out = append(out, r.Index)
	}
	return out
}

func TestFilterNeedsWholeWords(t *testing.T) {
	targets := []string{
		"Como eu vejo as mensagens dos ultimos commits? como-eu-vejo pesquisa-externa",
		"Como descompacta um tar como-descompacta-um-tar",
		"Porta default do sunshine porta-default",
	}
	if got := indexes("tar", targets); len(got) != 1 || got[0] != 1 {
		t.Fatalf("tar casou %v, queria só [1]", got)
	}
}

func TestFilterIgnoresCaseAndAccent(t *testing.T) {
	targets := []string{"Descompactação de arquivos", "outra coisa"}
	if got := indexes("DESCOMPACTACAO", targets); len(got) != 1 || got[0] != 0 {
		t.Fatalf("got %v", got)
	}
	if got := indexes("açã", []string{"descompactacao"}); len(got) != 1 {
		t.Fatalf("acento no termo: got %v", got)
	}
}

func TestFilterAllWordsRequired(t *testing.T) {
	targets := []string{"git log mensagens", "git stash"}
	if got := indexes("git log", targets); len(got) != 1 || got[0] != 0 {
		t.Fatalf("got %v", got)
	}
}

func TestFilterTitleMatchRanksFirst(t *testing.T) {
	targets := []string{"Porta do sunshine tags: keyring", "Keyring trancado no gnome"}
	if got := indexes("keyring", targets); len(got) != 2 || got[0] != 1 {
		t.Fatalf("got %v, queria título com keyring primeiro", got)
	}
}

func TestFilterEmptyKeepsAll(t *testing.T) {
	if got := indexes("   ", []string{"a", "b"}); len(got) != 2 {
		t.Fatalf("got %v", got)
	}
}
