"""Os Avisos das OS em três linhas e o aviso da OS pausada (Levi, 22/11/2026: "OS número, traço, e aí o que aconteceu, se ela
foi concluída, se ela foi pausada [...] executada a [técnico] em verificação. E aí o ativo [...] vira uma terceira linha. E eu
também quero que tenha, ao lado de concluída pelo técnico, a data e a hora que aconteceu"). A lista central e o livro do Fora
da programação são de mentira; nomes, números e textos inventados."""
from collections import namedtuple
from datetime import datetime, timedelta, timezone

import pytest
from test_campo_visao import banco  # noqa: F401  (fixture: o banco falso)
from test_comando_avisos import _ListaFalsa, _cliente_de, _sino, avisos_limpos  # noqa: F401  (fixture)
from test_comando_insights import PESSOA, limpo  # noqa: F401  (fixtures)

from nexus.comando import avisos as AV
from nexus.pcm import motivos as M

Reg = namedtuple("Reg", "id folio descricao atribuido_a status_id data_fim ativo")
BRT = timezone(timedelta(hours=-3))
ITEM = "a1b2c3d4e5f60718"


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")     # como o livro dos motivos grava (UTC, com o Z)


def test_as_tres_linhas_saem_do_ativo_e_da_descricao():
    # o OS Creator escreve "[Ativo] - Atividade": o ativo vai para o começo da 3ª linha, sem o colchete
    assert AV._ativo_e_atividade("", "[Inversor 1.1] - Inspecionar o inversor") == ("Inversor 1.1", "Inspecionar o inversor")
    assert AV._ativo_e_atividade("Inversor 2.2", "[Inversor 2.2] - Troca") == ("Inversor 2.2", "Troca")
    assert AV._ativo_e_atividade("String Box 3", "Trocar o fusível") == ("String Box 3", "Trocar o fusível")
    t = AV.tres_linhas("Concluída pelo técnico", [["Executada por Técnico Um", ""], AV._status("Em Verificação"), ["", ""]],
                       "", "[Inversor 1.1] - Inspecionar", "OS 16507")
    assert t == {"os_txt": "OS 16507", "acao": "Concluída pelo técnico", "ativo": "Inversor 1.1", "atividade": "Inspecionar",
                 "l2": [["Executada por Técnico Um", ""], ["Em verificação", "alerta"]]}
    assert AV._status("Concluída") == ["Concluída", "ok"] and AV._status("") == []


@pytest.fixture
def pausa(monkeypatch):
    """A OS 16490, criada pela pessoa, pausada há 1 hora pelo técnico no App; o livro dos motivos de mentira."""
    agora = datetime.now(BRT)
    l = _ListaFalsa([Reg(301, "16490", "[Tracker 12] - Ajustar o motor do rastreador", "Técnico Um", 1, "", "Tracker 12")])
    monkeypatch.setattr(AV, "_os_central", lambda: l)
    marca = {"item_id": ITEM, "os": 16490, "tarefa": "[Tracker 12] - Ajustar o motor do rastreador",
             "motivo": "Aguardando peça", "quem_motivo": "Técnico Um", "origem_motivo": "app",
             "desde": _iso(agora - timedelta(hours=1))}
    vig = {ITEM: marca}
    monkeypatch.setattr(M, "copia", lambda cfg: {"lido_em": 1})
    monkeypatch.setattr(M, "vigentes", lambda cfg, est: vig)
    monkeypatch.setattr(AV, "PAUSAS_DESDE", (agora - timedelta(days=3)).strftime("%Y-%m-%d"))
    return marca


def test_a_os_que_eu_criei_pausada_pelo_tecnico_vira_aviso(app, pausa, avisos_limpos, monkeypatch):
    cfg = {"x": 1}
    itens = AV.pausadas(cfg, "Fulana de Teste")
    assert len(itens) == 1
    a = itens[0]
    assert a["id"] == f"P:{ITEM}:" + pausa["desde"].replace("-", "").replace("T", "").replace(":", "")[:12]
    assert AV.AVISO_RE.fullmatch(a["id"]) and AV.TIPO_DO_PREFIXO["P"] == "pausada" and a["tipo"] == "pausada"
    assert (a["os_txt"], a["acao"], a["ativo"], a["atividade"]) == ("OS 16490", "Pausada pelo técnico", "Tracker 12",
                                                                    "Ajustar o motor do rastreador")
    assert a["l2"] == [["Técnico Um", ""], ["Motivo: Aguardando peça", ""]] and a["wid"] == 301
    # pelo PCM, o título diz
    AV.limpar()
    pausa["origem_motivo"] = "pcm"
    assert AV.pausadas(cfg, "Fulana de Teste")[0]["acao"] == "Pausada pelo PCM"


def test_a_pausa_de_antes_a_minha_e_sem_o_livro_nao_avisam(app, pausa, avisos_limpos, monkeypatch):
    cfg = {"x": 1}
    # a pausa de antes de PAUSAS_DESDE (sem enxurrada na 1ª leitura depois de subir)
    monkeypatch.setattr(AV, "PAUSAS_DESDE", (datetime.now(BRT) + timedelta(days=1)).strftime("%Y-%m-%d"))
    assert AV.pausadas(cfg, "Fulana de Teste") == []
    monkeypatch.setattr(AV, "PAUSAS_DESDE", "2026-01-01")
    AV.limpar()
    # a pausa que a própria pessoa pôs
    pausa["quem_motivo"] = "Fulana de Teste"
    assert AV.pausadas(cfg, "Fulana de Teste") == []
    # a OS que não é da pessoa (a lista não a traz), o livro fora e a lista que não responde
    AV.limpar()
    pausa["quem_motivo"], pausa["os"] = "Técnico Um", 99999          # o livro guarda o nº da OS como número
    assert AV.pausadas(cfg, "Fulana de Teste") == []
    monkeypatch.setattr(M, "copia", lambda cfg: None)
    assert AV.pausadas(cfg, "Fulana de Teste") == [] and AV.pausadas(None, "Fulana de Teste") == []
    assert AV.pausadas(cfg, "Pessoa Homônima") == []


def test_o_sino_mostra_a_pausada_e_a_hora_ao_lado(app, banco, limpo, pausa, avisos_limpos):
    sino = _sino(_cliente_de(app, PESSOA).get("/").get_data(as_text=True))
    assert "ph-pause-circle" in sino and '<b class="nt-os">OS 16490</b> — Pausada pelo técnico' in sino
    assert "Técnico Um · Motivo: Aguardando peça" in sino
    assert '<span class="nt-l3"><b>Tracker 12</b> — Ajustar o motor do rastreador</span>' in sino
    hora = datetime.fromisoformat(pausa["desde"].replace("Z", "+00:00")).astimezone(BRT)
    assert f'<span class="nt-hora">{hora.strftime("%d/%m · %H:%M")}</span>' in sino
    assert "A OS pausada" in _cliente_de(app, PESSOA).get("/").get_data(as_text=True)
