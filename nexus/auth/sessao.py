"""Quem está na sessão: o e-mail, como o portão guardou (`session["usuario"]`).

Até 08/11/2026 eram cinco cópias iguais (Acessos, Pessoas e setores, Equipamentos das usinas, a casca e o setor de cada
tela); o mapa do desembaraço as juntou aqui.
"""
from flask import session


def email_da_sessao() -> str:
    """O e-mail de quem entrou, sem espaço nas pontas e em minúsculas; vazio sem sessão de pessoa (a senha de
    administrador não tem e-mail)."""
    u = session.get("usuario")
    return str(u.get("email") or "").strip().lower() if isinstance(u, dict) else ""
