"""YAML/front matter parsing sem dependências externas.

Suporta o subconjunto usado pelos documentos lore: escalares, listas de
escalares, listas de mapas simples e mapa de `sources`. Nada além disso.
Falha explícita em vez de adivinhar.
"""

from __future__ import annotations


class FrontMatterError(ValueError):
    pass


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _parse_scalar(raw: str):
    text = _strip_quotes(raw.strip())
    if text in ("null", "~", ""):
        return None
    if text in ("true", "True"):
        return True
    if text in ("false", "False"):
        return False
    try:
        return int(text)
    except ValueError:
        pass
    return text


def parse(text: str) -> dict:
    """Parseia bloco YAML simples em dict. Levanta FrontMatterError."""
    result: dict = {}
    lines = text.splitlines()
    i = 0
    n = len(lines)

    def indent_of(line: str) -> int:
        return len(line) - len(line.lstrip(" "))

    while i < n:
        line = lines[i]
        i += 1
        if not line.strip() or line.strip().startswith("#"):
            continue
        if "\t" in line[: indent_of(line)]:
            raise FrontMatterError(f"tab na indentação: {line!r}")
        if indent_of(line) != 0:
            raise FrontMatterError(f"chave fora do nível raiz: {line!r}")
        if ":" not in line:
            raise FrontMatterError(f"linha sem ':': {line!r}")
        key, _, rest = line.partition(":")
        key = key.strip()
        if not key or " " in key:
            raise FrontMatterError(f"chave inválida: {line!r}")
        if key in result:
            raise FrontMatterError(f"chave duplicada: {key}")
        rest = rest.strip()
        if rest == "[]":
            result[key] = []
            continue
        if rest:
            if rest.startswith(("[", "{")):
                raise FrontMatterError(f"flow style não suportado: {line!r}")
            result[key] = _parse_scalar(rest)
            continue
        # Bloco: lista ou mapa aninhado.
        items: list = []
        submap: dict | None = None
        base_indent: int | None = None
        while i < n:
            nxt = lines[i]
            if not nxt.strip() or nxt.strip().startswith("#"):
                i += 1
                continue
            ind = indent_of(nxt)
            if ind == 0:
                break
            if base_indent is None:
                base_indent = ind
            if ind != base_indent:
                raise FrontMatterError(f"indentação inconsistente: {nxt!r}")
            stripped = nxt.strip()
            if stripped.startswith("- "):
                if submap is not None:
                    raise FrontMatterError(
                        f"mistura de mapa e lista sob '{key}': {nxt!r}"
                    )
                payload = stripped[2:].strip()
                if not payload:
                    # Item de lista que é mapa em linhas seguintes.
                    i += 1
                    entry: dict = {}
                    while i < n:
                        sub = lines[i]
                        if not sub.strip() or sub.strip().startswith("#"):
                            i += 1
                            continue
                        if indent_of(sub) <= ind:
                            break
                        if ":" not in sub:
                            raise FrontMatterError(f"linha sem ':': {sub!r}")
                        sk, _, sv = sub.partition(":")
                        sk = sk.strip()
                        if not sk or " " in sk:
                            raise FrontMatterError(f"chave inválida: {sub!r}")
                        if sk in entry:
                            raise FrontMatterError(f"chave duplicada: {sk}")
                        entry[sk] = _parse_scalar(sv.strip())
                        i += 1
                    if not entry:
                        raise FrontMatterError(f"item vazio sob '{key}'")
                    items.append(entry)
                    continue
                if ":" in payload and not (
                    payload.startswith(("'", '"'))
                    or payload.startswith("http")
                ):
                    # Mapa inline numa linha de lista: "- kind: personal".
                    if submap is not None:
                        raise FrontMatterError(
                            f"mistura de mapa e lista sob '{key}'"
                        )
                    sk, _, sv = payload.partition(":")
                    sk = sk.strip()
                    if " " in sk or not sk:
                        items.append(_parse_scalar(payload))
                    else:
                        entry = {sk: _parse_scalar(sv.strip())}
                        # Continua coletando linhas "chave: valor" do item.
                        i += 1
                        while i < n:
                            sub = lines[i]
                            if not sub.strip() or sub.strip().startswith("#"):
                                i += 1
                                continue
                            if indent_of(sub) <= ind:
                                break
                            s = sub.strip()
                            if s.startswith("- ") or ":" not in s:
                                break
                            sk2, _, sv2 = s.partition(":")
                            sk2 = sk2.strip()
                            if " " in sk2 or not sk2:
                                break
                            if sk2 in entry:
                                raise FrontMatterError(
                                    f"chave duplicada: {sk2}"
                                )
                            entry[sk2] = _parse_scalar(sv2.strip())
                            i += 1
                        items.append(entry)
                    continue
                items.append(_parse_scalar(payload))
                i += 1
            elif ":" in stripped:
                if items:
                    raise FrontMatterError(
                        f"mistura de lista e mapa sob '{key}': {nxt!r}"
                    )
                if submap is None:
                    submap = {}
                sk, _, sv = stripped.partition(":")
                sk = sk.strip()
                if not sk or " " in sk:
                    raise FrontMatterError(f"chave inválida: {nxt!r}")
                if sk in submap:
                    raise FrontMatterError(f"chave duplicada: {sk}")
                if sv.strip():
                    submap[sk] = _parse_scalar(sv.strip())
                else:
                    raise FrontMatterError(
                        f"aninhamento triplo não suportado: {nxt!r}"
                    )
                i += 1
            else:
                raise FrontMatterError(f"linha inválida: {nxt!r}")
        if submap is not None:
            result[key] = submap
        else:
            result[key] = items
    return result


def split_front_matter(text: str) -> tuple[dict, str]:
    """Separa front matter de corpo. Levanta FrontMatterError."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise FrontMatterError("documento deve começar com '---'")
    end = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end = idx
            break
    if end is None:
        raise FrontMatterError("front matter sem fechamento '---'")
    front_raw = "".join(lines[1:end])
    body = "".join(lines[end + 1 :])
    try:
        front = parse(front_raw)
    except FrontMatterError as exc:
        raise FrontMatterError(f"front matter inválido: {exc}") from exc
    if not isinstance(front, dict):
        raise FrontMatterError("front matter deve ser um mapa")
    return front, body
