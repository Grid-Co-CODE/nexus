"""Os avisos de quem fez a solicitação (Levi, 11/11/2026: "As notificações do fracttal também deve mostrar quando uma
solicitação feita gera OS e deve chegar todas as notificações dessa OS!"): o "Sua solicitação gerou uma OS" das solicitações
lidas no Fracttal pelo REST (a aprovada direto no Fracttal também) e, da OS gerada, a ida para Em Verificação, a conclusão e
o cancelamento, com o motivo. O REST e a lista central de OS são de mentira; nomes, números e textos inventados."""
from collections import namedtuple
from datetime import datetime, timedelta, timezone

import pytest
from test_campo_visao import banco  # noqa: F401  (fixture: o banco falso)
from test_comando_avisos import _cliente_de, _sino, avisos_limpos  # noqa: F401
from test_comando_insights import PESSOA, limpo  # noqa: F401  (fixtures)

from nexus.comando import avisos as AV
from nexus.comando import solicitacoes_fracttal as SF

BRT = timezone(timedelta(hours=-3))
AGORA = datetime(2026, 11, 13, 10, 0, tzinfo=BRT)
EU, OUTRO = 501, 777
Rec = namedtuple("Rec", "id folio descricao atribuido_a status_id data_fim data")


def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


class Lista:
    def __init__(self, recs):
        self.por_id = {r.id: r for r in recs}
        self.versao, self.janela = 1, ("2026-10-28", "2026-11-13")

    def atual(self):
        return self

    def filtrar(self, *a, **k):
        return []


def _sol(codigo, wid, folio, conta=EU, email="", nome="Pessoa Exemplo", aprovador="Programador Exemplo"):
    return {"codigo": codigo, "id_account": conta, "email": email, "nome": nome, "wid": wid, "folio": folio,
            "aprovador": aprovador}


@pytest.fixture
def lista(monkeypatch):
    recs = [Rec(201, "19201", "Troca de fusível", "Técnico Exemplo", 1, "", _utc(AGORA - timedelta(days=1))),
            Rec(202, "19202", "Recomposição de String", "Técnico Exemplo", 3, _utc(AGORA - timedelta(hours=5)),
                _utc(AGORA - timedelta(days=1))),
            Rec(203, "19203", "Limpeza de módulos", "Técnico Exemplo", 4, "", _utc(AGORA - timedelta(days=1))),
            Rec(204, "19204", "Antiga", "Técnico Exemplo", 3, _utc(AGORA - timedelta(hours=5)),
                _utc(datetime(2026, 11, 9, 9, 0, tzinfo=BRT))),                      # criada antes de SEGUIR_DESDE
            Rec(205, "19205", "Inspeção", "Pessoa Exemplo", 2, _utc(AGORA - timedelta(hours=2)),
                _utc(AGORA - timedelta(days=1)))]                                    # executada por quem pediu
    l = Lista(recs)
    monkeypatch.setattr(AV, "_os_central", lambda: l)
    return l


def _ids(itens):
    return sorted(a["id"] for a in itens)


def test_a_solicitacao_que_virou_os_no_fracttal_avisa_quem_pediu(lista):
    rest = [_sol("4301", 201, "19201"), _sol("4302", 201, "19201", conta=OUTRO), _sol("4290", 204, "19204")]
    itens = AV.da_solicitacao(EU, "", ["Pessoa Exemplo"], [], rest, {}, AGORA)
    s = [a for a in itens if a["tipo"] == "solicitacao"]
    assert [(a["id"], a["titulo"], a["wid"], a["folio"]) for a in s] == [("S:4301", "Sua solicitação gerou uma OS", 201,
                                                                         "19201")]
    assert "Solicitação 4301" in s[0]["detalhe"] and "Programador Exemplo" in s[0]["detalhe"]
    assert "S:4290" not in _ids(itens)                                    # a OS criada antes de SEGUIR_DESDE não avisa


def test_a_os_da_solicitacao_concluida_e_cancelada_chega_a_quem_pediu(lista):
    rest = [_sol("4302", 202, "19202"), _sol("4303", 203, "19203"), _sol("4305", 205, "19205")]
    cancel = {203: {"motivo": "Duplicada", "visto": AGORA - timedelta(hours=1)}}
    itens = {a["id"]: a for a in AV.da_solicitacao(EU, "", ["Pessoa Exemplo"], [], rest, cancel, AGORA)}
    exe = [a for a in itens.values() if a["tipo"] == "execucao"]
    assert [a["titulo"] for a in exe] == ["OS 19202 da sua solicitação concluída pelo técnico"]
    assert "Concluída" in exe[0]["detalhe"] and "Solicitação 4302" in exe[0]["detalhe"]
    can = itens["C:203"]
    assert (can["tipo"], can["titulo"], can["status"]) == ("cancelada", "OS 19203 da sua solicitação foi cancelada",
                                                           "Cancelada")
    assert can["detalhe"].startswith("Motivo: Duplicada") and can["quando"] == AGORA - timedelta(hours=1)
    assert not any(a["wid"] == 205 and a["tipo"] == "execucao" for a in itens.values())   # quem pediu executou: não avisa


def test_a_cancelada_sem_o_motivo_lido_ainda_espera(lista):
    itens = AV.da_solicitacao(EU, "", [], [], [_sol("4303", 203, "19203")], {}, AGORA)
    assert "C:203" not in _ids(itens)


def test_a_aprovada_no_os_creator_tambem_e_acompanhada(lista):
    evento = {"id": "S:4310", "tipo": "solicitacao", "wid": 202, "folio": "19202", "quando": AGORA - timedelta(days=1)}
    itens = AV.da_solicitacao(EU, "", ["Pessoa Exemplo"], [evento], [], {}, AGORA)
    assert [a["titulo"] for a in itens] == ["OS 19202 da sua solicitação concluída pelo técnico"]
    velho = dict(evento, quando=datetime(2026, 11, 9, tzinfo=BRT))                     # aprovada antes de SEGUIR_DESDE
    assert AV.da_solicitacao(EU, "", [], [velho], [], {}, AGORA) == []


def test_quem_pediu_pela_conta_pelo_email_ou_pelo_nome_so_sem_a_conta(app, banco, limpo):  # noqa: F811
    rest = [_sol("1", 1, "1", conta=EU, nome="Outra Pessoa"), _sol("2", 2, "2", conta=OUTRO, email="eu@exemplo.test",
                                                                  nome="Outra Pessoa"),
            _sol("3", 3, "3", conta=OUTRO, nome="Pessoa Exemplo")]
    with app.app_context():                                               # o código do nome usa a chave do app
        assert [s["codigo"] for s in AV._minhas(rest, EU, "eu@exemplo.test", ["Pessoa Exemplo"])] == ["1", "2"]
        assert [s["codigo"] for s in AV._minhas(rest, None, "", ["PESSOA EXEMPLO"])] == ["3"]   # o nome, sem a conta


def test_o_mesmo_aviso_por_dois_caminhos_sai_uma_vez(lista, monkeypatch):
    evento_linha = {"evento": "gerou_os", "aviso_id": "S:4301", "destino_hmac": "", "registrado_em": _utc(AGORA)}
    monkeypatch.setattr(AV, "solicitacoes", lambda nomes, linhas, agora=None, cofre=None: [
        {"id": "S:4301", "tipo": "solicitacao", "wid": 201, "folio": "19201", "quando": AGORA - timedelta(days=1),
         "titulo": "Sua solicitação gerou uma OS", "detalhe": "pelo OS Creator"}])
    itens = AV.da_pessoa("Pessoa Exemplo", "", [evento_linha], AGORA, id_account=EU, rest=[_sol("4301", 201, "19201")])
    s = [a for a in itens if a["id"] == "S:4301"]
    assert len(s) == 1 and s[0]["detalhe"] == "pelo OS Creator"          # o da aprovação no OS Creator vale primeiro


def test_o_cancelado_marca_como_lido_com_o_tipo_dele():
    assert AV.AVISO_RE.fullmatch("C:203") and AV.TIPO_DO_PREFIXO["C"] == "cancelada"


# ── o leitor do REST ──
class Api:
    def __init__(self, paginas, status=None):
        self.paginas, self.pedidos, self.cancelamentos = paginas, [], []

    def _req(self, metodo, ep, params=None, **k):
        self.pedidos.append((metodo, ep, dict(params or {})))
        i = (params or {}).get("start", 0) // SF.LIMITE
        total = sum(len(p) for p in self.paginas)
        return {"data": self.paginas[i] if i < len(self.paginas) else [], "total": total}

    def cancelamento_da_os(self, folio):
        self.cancelamentos.append(folio)
        return {"motivo": "Duplicada", "nota": ""}


def _linha_rest(n, wid=None):
    return {"id_code": n, "id_account": EU, "requested_by": "Pessoa Exemplo", "email_requested_by": "Eu@Exemplo.test",
            "id_work_order": wid, "wo_folio": str(19000 + n) if wid else None,
            "requests_x_status_accounts_name": "Programador Exemplo"}


def test_o_leitor_pagina_e_guarda_so_as_que_viraram_os(monkeypatch):
    api = Api([[_linha_rest(i, 300 + i if i % 2 else None) for i in range(SF.LIMITE)], [_linha_rest(500, 900)]])
    monkeypatch.setattr(SF, "_clone", lambda nome: api)
    linhas = SF.ler_rest(AGORA)
    assert len(api.pedidos) == 2 and api.pedidos[1][2]["start"] == SF.LIMITE
    assert api.pedidos[0][:2] == ("GET", "work_requests") and api.pedidos[0][2]["since"] == "2026-10-14T00:00:00"
    assert len(linhas) == SF.LIMITE // 2 + 1 and all(l["wid"] for l in linhas)
    assert linhas[-1] == {"codigo": "500", "id_account": EU, "email": "eu@exemplo.test", "nome": "Pessoa Exemplo",
                          "wid": 900, "folio": "19500", "aprovador": "Programador Exemplo"}


def test_o_motivo_da_cancelada_e_lido_uma_vez(monkeypatch, lista):
    SF.limpar()
    api = Api([])
    oc = type("OC", (), {"atual": lambda self: lista})()
    monkeypatch.setattr(SF, "_clone", lambda nome: api if nome == "api" else oc)
    linhas = [SF.enxuta(_linha_rest(1, 203)), SF.enxuta(_linha_rest(2, 202))]
    SF._motivos(linhas)
    SF._motivos(linhas)
    assert api.cancelamentos == ["19001"] and SF._CANCEL[203]["motivo"] == "Duplicada"
    SF.limpar()


def test_o_leitor_nao_roda_nos_testes_sem_a_chave(app):
    with app.app_context():
        assert SF._ligado(app) is False
        app.config["NEXUS_SOLICITACOES_FRACTTAL"] = "1"
        assert SF._ligado(app) is True
        app.config.pop("NEXUS_SOLICITACOES_FRACTTAL")


class _Relogio(datetime):
    """O relógio dos avisos parado em AGORA (o sino lê `datetime.now`; com a hora real, o teste das 00h falhava)."""

    @classmethod
    def now(cls, tz=None):
        return AGORA


def test_o_sino_mostra_a_cancelada_com_o_selo(app, banco, limpo, avisos_limpos, monkeypatch):
    monkeypatch.setattr(AV, "datetime", _Relogio)
    agora = AGORA
    recs = [Rec(203, "19203", "Limpeza de módulos", "Técnico Exemplo", 4, "", _utc(agora - timedelta(hours=3)))]
    l = Lista(recs)
    monkeypatch.setattr(AV, "_os_central", lambda: l)
    monkeypatch.setattr(SF, "atuais", lambda app=None: (
        [_sol("4303", 203, "19203", conta=None, nome=PESSOA["nome"])],
        {203: {"motivo": "Duplicada", "visto": agora - timedelta(minutes=5)}}))
    sino = _sino(_cliente_de(app, PESSOA).get("/").get_data(as_text=True))
    assert "OS 19203 da sua solicitação foi cancelada" in sino and "Motivo: Duplicada" in sino
    assert 'sino-sev--critico">Cancelada' in sino or ">Cancelada<" in sino
