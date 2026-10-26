"""O pulso laranja nas OS de Garantias paradas (Levi, 25/10/2026, pelo chat da Engenharia: "sabe o pulsar que temos no
quadro de equipe? passe instruções para o chat de Nexus (Chamados) implementar nas OSs de garantias porém quando a OS
ficar a partir de 5 dias sem comentário de atualização!").

A regra (`acomp_web.parada`): pulsa a OS ABERTA do quadro (Chegaram e Ticket aberto; nem finalizada, nem em verificação,
nem cancelada) com 5 x 24 h ou mais desde o último comentário de atualização: a última observação da tela (as do banco
da Gridco, inclusive a do ticket gravado) ou, na OS retroativa, a última data do histórico da nota. Sem comentário
nenhum, conta da abertura (a esquecida desde o início também pulsa). Sem conseguir ler as observações (o banco fora),
nada pulsa: não se chuta. O desenho é o do Quadro da equipe da Engenharia (`nexus/static/engenharia.css`,
`.kb-card--parada`), com os mesmos valores e os tokens nos dois temas do clone.

Nomes e números de mentira: o repositório é público."""
import datetime as dt
import re
import sys
from pathlib import Path

import pytest

from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

from os_web import acomp_web as aw  # noqa: E402

HOJE = dt.datetime(2026, 10, 25, 12, 0)
CSS = Path(ponte.RAIZ_CLONE) / "os_web" / "static" / "chamados.css"


def _linha(status=1, criada="2026-10-01T15:00:00", nota=""):
    return {"id": 1, "folio": "9103", "cliente": "Cliente Teste", "usina": "Usina Teste", "ativo": "Inversor 1.1",
            "tipo": "Inversor", "tipo_tarefa": "Administrativa", "note": nota,
            "descricao": "[Inversor 1.1] - Acompanhamento de chamado Marca", "status_id": status,
            "data": criada, "data_fim": "", "atribuido_a": "Analista Teste", "id_atribuido": None}


def _parada(ultima_obs="", ticket="", **kw) -> bool:
    return aw.cartao(_linha(**kw), ticket, ultima_obs, HOJE)["parada"]


def test_4_dias_e_23_h_sem_comentario_nao_pulsa():
    assert _parada("2026-10-20T13:00:00-03:00") is False


def test_5_dias_sem_comentario_pulsa():
    assert _parada("2026-10-20T12:00:00-03:00") is True


def test_vale_nas_duas_colunas_abertas():
    assert _parada("2026-10-10T12:00:00-03:00", ticket="SR 90000001") is True           # Ticket aberto


@pytest.mark.parametrize("status", [2, 3, 4])
def test_finalizada_em_verificacao_ou_cancelada_nao_pulsa(status):
    assert _parada("2026-09-01T12:00:00-03:00", status=status) is False


def test_sem_comentario_conta_da_abertura():
    # criada às 15:00 UTC (12:00 em Brasília): 5 dias exatos em 25/10 12:00
    assert _parada("", criada="2026-10-20T15:00:00") is True
    assert _parada("", criada="2026-10-21T15:00:00") is False


def test_na_retroativa_o_historico_da_nota_conta_como_comentario():
    nota = ("[CHAMADO] Acompanhamento — Huawei · Inversor\n"
            "Data da ocorrência / abertura do chamado: 21/08/2026\n"
            "Histórico (importado da Gestão de Chamados V02):\n21/08 - Chamado aberto\n22/10 - Cobrado o fabricante")
    assert _parada("", nota=nota, criada="2026-10-24T14:00:00") is False                 # 22/10: 3 dias
    assert _parada("", nota=nota.replace("22/10", "14/10"), criada="2026-10-24T14:00:00") is True


def test_sem_ler_as_observacoes_nada_pulsa():
    """O banco da Gridco fora: a OS sem comentário que conseguimos ler pareceria esquecida; não se chuta."""
    q = aw.montar_quadro([_linha(criada="2026-09-01T12:00:00")], {1: ""}, {}, HOJE, obs_lidas=False)
    assert [c["parada"] for c in q["colunas"]["chegou"]] == [False]
    q = aw.montar_quadro([_linha(criada="2026-09-01T12:00:00")], {1: ""}, {}, HOJE)
    assert [c["parada"] for c in q["colunas"]["chegou"]] == [True]


# ── a tela ─────────────────────────────────────────────────────────────────────────────────────────────────────────
JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira


@pytest.fixture
def cli(monkeypatch):
    pytest.importorskip("PyQt6")          # o clone importa o steps/ui.py do OS Creator ao montar a tela de Engenharia
    import api
    import chamados_obs_store as obs_store
    from os_web import criar_app, rotas
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()
    linhas = [dict(_linha(criada="2026-09-01T12:00:00"), id=1, folio="9103"),
              dict(_linha(criada="2026-09-01T12:00:00"), id=2, folio="9104")]
    monkeypatch.setattr(api, "_code_to_loc", lambda: {})
    monkeypatch.setattr(api, "list_chamados", lambda **k: [dict(l) for l in linhas])
    monkeypatch.setattr(api, "total_chamados", lambda de=None: 2)
    monkeypatch.setattr(api, "tickets_os3_em_massa", lambda ids: {i: "" for i in ids})
    monkeypatch.setattr(aw, "agora_brt", lambda: HOJE)
    estado = {"obs": {"9104": "2026-10-24T09:00:00-03:00"}, "erro": None}

    def ultima():
        if estado["erro"]:
            raise RuntimeError(estado["erro"])
        return dict(estado["obs"])
    monkeypatch.setattr(obs_store, "ultima_por_os", ultima)
    monkeypatch.setattr(obs_store, "finalizado_por_os", lambda: {})
    monkeypatch.setattr(obs_store, "listar", lambda forcar=False: [])
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Analista Teste", "email": "teste@exemplo.invalid", "perfil": ""}
    yield c, estado
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()


def _cartao(h, folio):
    return re.search(r'<a class="([^"]*)" href="/os/chamados/acompanhamento/%s"' % folio, h).group(1).split()


def test_o_cartao_parado_ganha_o_pulso_e_o_comentado_nao(cli):
    c, _ = cli
    h = c.get("/os/chamados/acompanhamento").get_data(as_text=True)
    assert "parada" in _cartao(h, "9103")                        # sem comentário desde 01/09
    assert "parada" not in _cartao(h, "9104")                    # comentada ontem


def test_banco_fora_nada_pulsa_e_a_tela_diz(cli):
    c, estado = cli
    estado["erro"] = "fora do ar"
    h = c.get("/os/chamados/acompanhamento?atualizar=1").get_data(as_text=True)
    assert "parada" not in _cartao(h, "9103") and "parada" not in _cartao(h, "9104")
    assert "o pulso das OS paradas fica desligado" in h


# ── o CSS: o mesmo pulso do Quadro da equipe da Engenharia ─────────────────────────────────────────────────────────
def test_o_pulso_e_o_da_engenharia_por_token():
    css = CSS.read_text(encoding="utf-8")
    regra = re.search(r"\.card\.parada::after\{([^}]*)\}", css)
    assert regra and "animation:ac-pulso 1.4s ease-in-out infinite alternate" in regra.group(1)
    assert re.findall(r"var\((--pulso-a\d+)\)", regra.group(1)) == [f"--pulso-a{n}" for n in (71, 43, 71, 57, 43, 28, 14)]
    assert "0 0 0 1.5px var(--pulso-a71),0 0 16px 3px var(--pulso-a43)" in regra.group(1)
    assert re.search(r"@keyframes ac-pulso\{from\{opacity:\.5\}to\{opacity:1\}\}", css)
    # a sombra igual à da Engenharia, valor por valor
    eng = Path("nexus/static/engenharia.css").read_text(encoding="utf-8")
    sombra = lambda t: re.sub(r"\s+", "", re.search(r"box-shadow:([^;]*);\s*animation", t).group(1))  # noqa: E731
    assert sombra(regra.group(1)) == sombra(re.search(r"\.kb-card--parada::after\{([^}]*)\}", eng).group(1))


def test_o_pulso_vale_mesmo_com_reduzir_movimento():
    css = CSS.read_text(encoding="utf-8")
    assert re.search(r"@media \(prefers-reduced-motion:reduce\)\{\.card\.parada::after\{animation:ac-pulso 1\.4s "
                     r"ease-in-out infinite alternate!important\}\}", css)


def test_os_tokens_do_pulso_nos_dois_temas_do_clone():
    css = CSS.read_text(encoding="utf-8")
    escuro = re.search(r":root\{([^}]*)\}", css).group(1)
    claro = re.search(r'html\[data-tema="claro"\]\{([^}]*)\}', css).group(1)
    for n in (71, 57, 43, 28, 14):
        assert "--pulso-a%d:rgba(255,143,60,.%d)" % (n, n) in escuro
        assert "--pulso-a%d:rgba(247,140,60,.%d)" % (n, n) in claro
