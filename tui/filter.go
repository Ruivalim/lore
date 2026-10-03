package main

import (
	"sort"
	"strings"
	"unicode"

	"github.com/charmbracelet/bubbles/list"
	"golang.org/x/text/unicode/norm"
)

// fold baixa caixa e tira acento: "Descompactação" casa com "descompactacao".
func fold(s string) string {
	var b strings.Builder
	for _, r := range norm.NFD.String(strings.ToLower(s)) {
		if !unicode.Is(unicode.Mn, r) {
			b.WriteRune(r)
		}
	}
	return b.String()
}

// filterTerms troca o fuzzy padrão do Bubbles, que com texto longo casa
// quase tudo. Cada palavra digitada precisa aparecer inteira; quem tem as
// palavras no começo do alvo (o título) sobe.
func filterTerms(term string, targets []string) []list.Rank {
	words := strings.Fields(fold(term))
	if len(words) == 0 {
		ranks := make([]list.Rank, len(targets))
		for i := range targets {
			ranks[i] = list.Rank{Index: i}
		}
		return ranks
	}
	type scored struct {
		rank  list.Rank
		score int
	}
	var hits []scored
	for i, target := range targets {
		hay := fold(target)
		score, ok := 0, true
		for _, w := range words {
			pos := strings.Index(hay, w)
			if pos < 0 {
				ok = false
				break
			}
			score += pos
		}
		if ok {
			hits = append(hits, scored{list.Rank{Index: i}, score})
		}
	}
	sort.SliceStable(hits, func(a, b int) bool { return hits[a].score < hits[b].score })
	ranks := make([]list.Rank, len(hits))
	for i, h := range hits {
		ranks[i] = h.rank
	}
	return ranks
}
