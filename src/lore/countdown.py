"""Confirmação com contagem regressiva: sem interação, segue sozinho."""

from __future__ import annotations

import os
import select
import sys
import termios
import time
import tty

YES_KEYS = ("s", "y", "\r", "\n")
NO_KEYS = ("n", "q", "\x1b", "\x03", "\x04")


def decide(key: str) -> bool | None:
    """Tecla → True (sim), False (não) ou None (tecla neutra)."""
    key = key.lower()
    if key in YES_KEYS:
        return True
    if key in NO_KEYS:
        return False
    return None


def confirm(prompt: str, timeout: float, stdin=None, stdout=None,
            clock=time.monotonic) -> bool:
    """Pergunta S/n. Em TTY, conta `timeout` segundos e assume sim se ninguém
    tocar no teclado. Tecla neutra pausa a contagem e espera s/n. Fora de TTY
    (pipe, CI) nunca assume nada: lê uma linha, EOF vale não."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    if timeout <= 0 or not _is_tty(stdin):
        return _confirm_line(prompt, stdin, stdout)
    fd = stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        return _countdown(prompt, timeout, fd, stdout, clock)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        stdout.write("\n")
        stdout.flush()


def _is_tty(stream) -> bool:
    try:
        return stream.isatty()
    except (AttributeError, ValueError):
        return False


def _confirm_line(prompt: str, stdin, stdout) -> bool:
    stdout.write(f"{prompt} [S/n] ")
    stdout.flush()
    line = stdin.readline()
    if not line:
        return False
    return line.strip().lower() in ("", "s", "y")


def _countdown(prompt: str, timeout: float, fd: int, stdout, clock) -> bool:
    deadline = clock() + timeout
    paused = False
    while True:
        remaining = deadline - clock()
        if not paused and remaining <= 0:
            stdout.write(f"\r\x1b[K{prompt} [S/n] sem resposta, seguindo")
            return True
        hint = "s/n" if paused else f"{max(1, int(remaining + 0.999))}s"
        stdout.write(f"\r\x1b[K{prompt} [S/n] ({hint}) ")
        stdout.flush()
        wait = None if paused else min(0.25, max(remaining, 0))
        ready, _, _ = select.select([fd], [], [], wait)
        if not ready:
            continue
        key = os.read(fd, 1).decode("utf-8", "replace")
        if not key:
            return False
        answer = decide(key)
        if answer is not None:
            return answer
        paused = True
