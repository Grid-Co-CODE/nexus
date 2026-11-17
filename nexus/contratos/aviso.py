"""As contestações no aviso do topo (16/11/2026, Levi: "as contestações também devem notificar nas notificações lá de cima,
a que não é do OS Creator!"): a bandeja das demandas (`casca._sino_demandas`), ao lado do botão do OS Creator.

A regra (as escolhas do Levi no mesmo dia):
- **O que entra:** a contestação SEM RESPOSTA do setor (nenhuma atualização e não resolvida; `tratamento.situacoes`). Sai
  para o setor inteiro, ao mesmo tempo, na 1ª atualização de qualquer um dele ou quando alguém a resolve ("1ª resposta do
  setor"). Reaberta sem nenhuma atualização volta.
- **Quem recebe:** quem é do setor da contestação (Performance, COS, Zeladoria, pelo nome, como a tela) e abre a tela
  Contestações. O administrador recebe só a do setor dele ("Só a do setor dele"); o administrador sem um desses setores
  recebe as dos três (é quem coordena, e não tem "o dele"). A senha de administrador (sem pessoa) não tem aviso, como o
  resto da bandeja.

Nenhuma página espera o banco por causa dele: a cópia dos dois livros (`thopen_contestacoes` e o acompanhamento) dura 1
minuto e é relida por trás; sem cópia (o Nexus acabou de subir), a bandeja sai sem as contestações. Quem grava um evento
pela tela já o vê na cópia (`anotar`). Só o que vai em claro no banco é lido aqui (a usina, o dia, os itens, o evento):
nada se decifra para o aviso.
"""
import time
from datetime import datetime

from flask import current_app

from . import contestacoes as CT
from . import tratamento as TR

TTL_S = 60
_CACHE: dict = {}


def _ler() -> dict:
    from ..dados import conexao, livros
    base, sessao = conexao.banco()
    lido = {"linhas": livros.ler(base, sessao, CT.LIVRO, CT.ABA),
            "eventos": livros.ler(base, sessao, TR.LIVRO, TR.ABA), "lido_em": time.time()}
    _CACHE["copia"] = lido
    return lido


def copia() -> dict | None:
    """A cópia guardada, sem esperar o banco: velha, relê por trás; sem cópia, começa a leitura por trás e devolve None.
    Nos testes, lê na hora."""
    if current_app.config.get("TESTING"):
        try:
            return _ler()
        except Exception:        # noqa: BLE001 — banco fora no teste: a bandeja sai sem as contestações
            return None
    g = _CACHE.get("copia")
    if not g or time.time() - g["lido_em"] >= TTL_S:
        from ..auth import setor_telas as ST
        app = current_app._get_current_object()

        def reler():
            with app.app_context():
                _ler()
        ST._em_fundo("contestacoes_aviso", reler)
    return g


def anotar(evento: dict) -> None:
    """O evento que esta máquina acabou de gravar entra na cópia (a releitura de 1 minuto o traria de qualquer jeito)."""
    g = _CACHE.get("copia")
    if g is not None:
        g["eventos"] = list(g["eventos"]) + [evento]


def esquecer() -> None:
    _CACHE.clear()


def _dia_txt(x: dict) -> str:
    ini, fim = x.get("ini"), x.get("fim")
    if not ini:
        return ""
    return ini.strftime("%d/%m") + (f" a {fim.strftime('%d/%m')}" if fim and fim != ini else "")


def sem_resposta(setores: tuple, hoje=None) -> list[dict]:
    """As contestações sem resposta dos `setores`, a mais nova em cima: {"id", "setor", "usina", "dia", "itens",
    "dias"} (os dias desde que chegou). Sem cópia: vazio."""
    g = copia()
    if not g or not setores:
        return []
    sit = TR.situacoes(g["eventos"])
    hoje = hoje or datetime.now(CT._BRT).date()
    out = []
    for l in g["linhas"]:
        setor = str(l.get("setor") or "")
        if setor not in setores or sit.get(str(l.get("id")), "sem_resposta") != "sem_resposta":
            continue
        x = CT._linha(l, None)          # sem a chave: só o que vai em claro (a usina, o dia, os itens)
        out.append({"id": str(x["id"]), "setor": setor, "usina": x["usina"], "dia": _dia_txt(x), "itens": x["itens"],
                    "quando": x["quando"], "dias": (hoje - x["quando"].date()).days if x["quando"] else None})
    out.sort(key=lambda x: x["quando"] or datetime.min.replace(tzinfo=CT._BRT), reverse=True)
    return out
