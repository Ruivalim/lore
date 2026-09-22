---
id: wireguard-split-dns
title: Split DNS com WireGuard e systemd-resolved
type: howto
status: verified
tags:
  - linux
  - networking
  - wireguard
  - dns
created_at: 2026-05-01
updated_at: 2026-05-02
verified_at: 2026-05-02
review_after: 2027-05-02
sources:
  - kind: personal
    description: Verificado no homelab em 2026-05-02
---

# Split DNS com WireGuard e systemd-resolved

## Quando usar

Quando o túnel deve resolver só domínios internos.

## Procedimento

Use uma rota de DNS por domínio no perfil do túnel e confirme que o
resolved recebeu a interface correta.

```ini
[Interface]
DNS = 10.0.0.53
```

## Verificação

Rode `resolvectl status wg0` e confira o servidor listado.

## Limitações

Não cobre NetworkManager; só systemd-resolved.
