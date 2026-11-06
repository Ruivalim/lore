---
id: wireguard-split-dns
title: Split DNS over WireGuard with systemd-resolved
summary: Give the tunnel interface its own DNS server and a routing domain (`~corp.internal`) so only internal names go through the VPN.
type: howto
status: verified
reviewed_by: human
tags:
  - linux
  - networking
  - wireguard
  - dns
created_at: 2026-09-14
updated_at: 2026-09-20
verified_at: 2026-09-20
review_after: 2027-03-20
sources:
  - url: https://www.freedesktop.org/software/systemd/man/latest/resolvectl.html
    title: resolvectl(1)
    accessed_at: 2026-09-20
  - kind: personal
    description: tested on the home lab tunnel
---

# Split DNS over WireGuard with systemd-resolved

## When to use

When the tunnel should resolve only internal domains and everything else keeps
using the local resolver.

## Procedure

Point the tunnel interface at the internal DNS server and mark the internal
domain as a routing domain with the `~` prefix:

```sh
resolvectl dns wg0 10.8.0.1
resolvectl domain wg0 '~corp.internal'
```

## Verification

`resolvectl query git.corp.internal` should report `wg0` as the link used.
