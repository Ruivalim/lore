# Contributing

Thanks for taking the time. A few things keep lore easy to change.

## Setup

```sh
make setup   # .venv with lore editable and dev tools
make install # lore on your PATH, editable, via pipx
make check   # what CI runs: ruff, go vet, gofmt, pytest, go test, builds
```

Python 3.11+ and Go (version in `tui/go.mod`) are needed.

## Changes

- New behavior comes with tests that cover what actually breaks: invalid
  input, a CLI that exits 0 on failure, a network error, a value at the limit.
  The happy path alone does not count.
- If a test fails, the code is wrong until proven otherwise. If the test was
  wrong, say why in the commit.
- A new config option goes in `src/lore/config.example.toml` with its default
  and a comment. That file is the source of the defaults, and a test fails if
  code reads a key that is not there.
- Runtime dependencies stay minimal (today only PyYAML). Open an issue before
  adding one.
- The trust model is the product: nothing becomes `verified` without a human
  or a review policy the user turned on, and nothing leaves the machine
  without research being enabled. Changes that weaken this need a strong case.

## Commits

Short subject in the style of the log (`area: what changed`), body explaining
why when it is not obvious.
