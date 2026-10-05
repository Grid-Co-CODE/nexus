"""Quem é quem para as regras copiadas do App: o mesmo ident() do App, com o arquivo e a tabela lidos pelo Nexus.

O ident() do App mescla o identidades.json que vai no pacote dele com o cadastro da tabela, que vence e-mail a e-mail
(é o BD_Operações sincronizado). Aqui a mescla é a mesma; muda só de onde vem o arquivo:
NEXUS_CAMPO_IDENTIDADES (no servidor: dados/campo/identidades.json, FORA do git, porque tem nome e e-mail de gente) ou,
na máquina do Levi, o da pasta do App no SharePoint.

O cadastro mora, no App, na tabela dos TOKENS do Fracttal de cada pessoa (fracttaltokens), assim como as PT. O Nexus só
lê as partições liberadas (PARTICOES_LIBERADAS): tabela_dos_tokens() recusa as outras. Os tokens ("tok") nunca: quando
o dado do App vier para o banco do Nexus, essa partição não vem.
"""
import json
import re
from pathlib import Path

PASTA_DO_APP = (Path.home() / "OneDrive - GRID CO" / "Área de Trabalho" / "Grid Co_ - 4. O&M" / "11.Pré-Operação"
                / "6. PCM" / "09. Programação Semanal" / "App_Campo" / "middleware")
_ARQ = {"caminho": None, "mtime": None, "v": None}
VAZIO = {"porEmail": {}, "supervisoresScope": {}, "adminEmails": []}


def _caminho():
    from flask import current_app, has_app_context
    if not has_app_context():
        return None
    cfg = current_app.config
    valor = cfg.get("NEXUS_CAMPO_IDENTIDADES")
    if not valor and not cfg.get("TESTING"):
        from ..config import ler_ambiente
        valor = ler_ambiente().get("NEXUS_CAMPO_IDENTIDADES")
        if not valor and (PASTA_DO_APP / "identidades.json").exists():
            valor = str(PASTA_DO_APP / "identidades.json")
    return Path(valor) if valor else None


def _arquivo() -> dict:
    caminho = _caminho()
    if caminho is None or not caminho.exists():
        return dict(VAZIO)             # como no App: sem o arquivo, vale só a tabela
    mtime = caminho.stat().st_mtime
    if _ARQ["caminho"] != caminho or _ARQ["mtime"] != mtime:
        try:
            _ARQ.update(caminho=caminho, mtime=mtime, v=json.loads(caminho.read_text(encoding="utf-8")))
        except Exception:
            _ARQ.update(caminho=caminho, mtime=mtime, v=dict(VAZIO))
    return _ARQ["v"]


def ident(cadastro_tab) -> dict:
    """A mescla do ident() do App (function_app.py), linha a linha: o arquivo como base e a tabela por cima."""
    arq = _arquivo()
    tab = cadastro_tab()
    if not tab:
        return arq
    base = dict(arq)
    pe = dict(base.get("porEmail") or {})
    for em, p in tab.items():
        atual = dict(pe.get(em) or {})
        atual.update({k: v for k, v in (p or {}).items() if v not in (None, "", [])})
        pe[em] = atual
    base["porEmail"] = pe
    return base


# As partições da tabela dos tokens que o Nexus pode ler. Os tokens moram em "tok" (e o login em "state"): fechadas.
#   cadastro  o cadastro de pessoas (bd_operacoes) e o dono de cada usina (bd_responsaveis)
# A partição "pt" saiu em 05/10/2026: a tela de PT do Nexus lê o livro pt_app_campo do banco (nexus/campo/visao.py).
PARTICOES_LIBERADAS = ("cadastro",)


class _TabelaDosTokens:
    """Só leitura, e só nas partições liberadas: a dos tokens (`tok`) e a do login (`state`) nunca são pedidas."""

    def _da(self, pk):
        if pk not in PARTICOES_LIBERADAS:
            raise PermissionError(f"o Nexus não lê a partição {pk!r} da tabela dos tokens do Fracttal")
        from .tabelas import tabela
        return tabela("fracttaltokens", pk)

    def get_entity(self, pk, rk):
        return self._da(pk).get_entity(pk, rk)

    def query_entities(self, filtro, **kwargs):
        m = re.match(r"\s*PartitionKey eq '([^']*)'", filtro)
        if not m:
            raise PermissionError("consulta na tabela dos tokens sem partição fixa")
        return self._da(m.group(1)).query_entities(filtro, **kwargs)


def tabela_dos_tokens():
    return _TabelaDosTokens()
