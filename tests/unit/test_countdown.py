"""Contagem regressiva do ask: sem tecla segue, tecla decide, fora de TTY não assume."""

import io
import os
import pty
import threading
import time

from lore.countdown import confirm, decide


class FakeClock:
    """Relógio que anda um passo por chamada, para não esperar segundos reais."""

    def __init__(self, step=1.0):
        self.now = 0.0
        self.step = step

    def __call__(self):
        self.now += self.step
        return self.now


def _tty_pair():
    master, slave = pty.openpty()
    return master, os.fdopen(slave, "r", closefd=True)


def _type_later(master, data, delay=0.1):
    """Digita depois do prompt existir; setcbreak (TCSAFLUSH) pode descartar antes."""
    timer = threading.Timer(delay, lambda: os.write(master, data))
    timer.start()
    return timer


def test_decide_keys():
    assert decide("s") is True and decide("Y") is True and decide("\n") is True
    assert decide("n") is False and decide("\x1b") is False
    assert decide("x") is None


def test_no_key_until_timeout_says_yes():
    master, slave = _tty_pair()
    out = io.StringIO()
    try:
        assert confirm("Pesquisar?", 5, stdin=slave, stdout=out, clock=FakeClock()) is True
    finally:
        os.close(master)
        slave.close()
    assert "sem resposta, seguindo" in out.getvalue()


def test_real_timeout_is_short_and_says_yes():
    master, slave = _tty_pair()
    started = time.monotonic()
    try:
        assert confirm("Pesquisar?", 0.3, stdin=slave, stdout=io.StringIO()) is True
    finally:
        os.close(master)
        slave.close()
    assert time.monotonic() - started < 2


def test_n_without_enter_cancels():
    # cbreak: "n" decide sem Enter. Em modo canônico o select nem acordaria.
    master, slave = _tty_pair()
    timer = _type_later(master, b"n")
    try:
        assert confirm("Pesquisar?", 30, stdin=slave, stdout=io.StringIO()) is False
    finally:
        timer.join()
        os.close(master)
        slave.close()


def test_enter_confirms_immediately():
    master, slave = _tty_pair()
    timer = _type_later(master, b"\r")
    started = time.monotonic()
    try:
        assert confirm("Pesquisar?", 30, stdin=slave, stdout=io.StringIO()) is True
    finally:
        timer.join()
        os.close(master)
        slave.close()
    assert time.monotonic() - started < 2


def test_neutral_key_pauses_and_waits_past_timeout():
    master, slave = _tty_pair()
    first = _type_later(master, b"x", 0.05)
    # Responde "n" bem depois do prazo: se a pausa falhar, já teria dito sim.
    second = _type_later(master, b"n", 0.6)
    try:
        assert confirm("Pesquisar?", 0.3, stdin=slave, stdout=io.StringIO()) is False
    finally:
        first.join()
        second.join()
        os.close(master)
        slave.close()


def test_terminal_mode_restored():
    import termios

    master, slave = _tty_pair()
    before = termios.tcgetattr(slave.fileno())
    os.write(master, b"s")
    try:
        confirm("Pesquisar?", 5, stdin=slave, stdout=io.StringIO())
        assert termios.tcgetattr(slave.fileno()) == before
    finally:
        os.close(master)
        slave.close()


def test_not_tty_never_assumes_yes_on_eof():
    assert confirm("Pesquisar?", 5, stdin=io.StringIO(""), stdout=io.StringIO()) is False


def test_not_tty_reads_line():
    assert confirm("P?", 5, stdin=io.StringIO("\n"), stdout=io.StringIO()) is True
    assert confirm("P?", 5, stdin=io.StringIO("n\n"), stdout=io.StringIO()) is False


def test_zero_timeout_waits_for_line_even_in_tty():
    master, slave = _tty_pair()
    os.write(master, b"n\n")
    try:
        assert confirm("P?", 0, stdin=slave, stdout=io.StringIO()) is False
    finally:
        os.close(master)
        slave.close()

