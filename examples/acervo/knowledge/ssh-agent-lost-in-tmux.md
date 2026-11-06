---
id: ssh-agent-lost-in-tmux
title: SSH agent lost after reattaching tmux
summary: Point `SSH_AUTH_SOCK` at a stable symlink that `~/.ssh/rc` refreshes on every login, so old tmux panes keep working.
type: troubleshooting
status: verified
reviewed_by: human
tags:
  - ssh
  - tmux
created_at: 2026-08-03
updated_at: 2026-08-03
verified_at: 2026-08-03
review_after: 2027-08-03
sources:
  - kind: personal
    description: reproduced and fixed on two machines
---

# SSH agent lost after reattaching tmux

## Symptom

`git push` inside an old tmux pane fails with `Could not open a connection to
your authentication agent` after reconnecting over SSH.

## Cause

Each SSH login gets a new agent socket path, and panes created earlier still
hold the old `SSH_AUTH_SOCK` value.

## Fix

Keep a stable symlink and refresh it on login in `~/.ssh/rc`:

```sh
if [ -S "$SSH_AUTH_SOCK" ]; then
  ln -sf "$SSH_AUTH_SOCK" ~/.ssh/agent.sock
fi
```

Then set `SSH_AUTH_SOCK=~/.ssh/agent.sock` in the tmux environment.
