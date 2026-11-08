"""Texto comparável: sem acento, sem caixa e com espaço único.

Até 08/11/2026 eram 11 cópias iguais (`_norm`, `_sem_acento`, `norm`) no cadastro, no Campo, nos fatos, na Engenharia,
no PCM e na Performance; o mapa do desembaraço as juntou aqui. As variantes que não são iguais (a que tira o espaço do
hífen, a que usa `casefold`, a que não põe em minúsculas) ficaram onde estavam, porque comparam de outro jeito. Ficam de
fora também o motor do PCM (roda num subprocesso) e o clone do OS Creator (importado também como pacote solto).
"""
import unicodedata


def sem_acento(s) -> str:
    """'  Coração   1 ' -> 'coracao 1'. Vazio para None."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())
