"""O coletor da torre Campo · App: Fracttal (só leitura, devagar) -> nota da régua do App -> API do PG (Levi, 04/10/2026:
"pode gravar na API do PG e ligar as telas").

O Fracttal e a API do PG são falsos, nos formatos medidos em 04/10. A cota do Fracttal é da empresa inteira e o App
vive dela: o que se prova aqui é que o coletor só pede o que falta e para no primeiro 429.
"""
import json
import re
from datetime import datetime

import pytest
import requests
from pg_falso import ApiPGFalsa

from nexus.cadastro.cifra import Cofre, gerar_chave
from nexus.campo import banco_campo, coletor, fracttal

CHAVE = gerar_chave()
GPS = " · GPS -5.123456,-42.654321 · 2026-10-02T14:33:12.000Z"


def _w(folio, id_wt, fim="2026-10-03T14:00:00.000000+00:00", tecnico="Técnico Um", note="", status=2, id_p=7):
    """Uma tarefa da fila de verificação como o REST devolve em work_orders?id_status_work_order=2."""
    return {"id_work_orders_tasks": id_wt, "id_work_order": int(folio) * 10, "wo_folio": str(folio),
            "description": f"Tarefa {id_wt}", "final_date": fim, "initial_date": "2026-10-03T13:00:00.000+00:00",
            "review_date": fim, "duration": 1800, "real_duration": 2700, "id_status_work_order": status,
            "id_status_work_order_task": 3, "personnel_description": tecnico, "id_personnel": id_p,
            "groups_1_description": "SP 01", "groups_2_description": "SP Interior",
            "items_log_description": "Usina A > Inversor 1", "code": "USA-INV1", "rating": 4,
            "tasks_log_task_type_main": "Preventiva", "priorities_description": "Alta", "note": note,
            "wo_final_date": None}


def _sub(id_wt, i, valor="1", tipo=4, req=True):
    return {"id_work_orders_tasks_form_items": id_wt * 100 + i, "id_work_order_task": id_wt,
            "description": f"Item {i}", "id_task_form_item_type": tipo, "value": valor, "is_required": req,
            "order_number": i}


def _foto(id_wt, texto="Painel limpo" + GPS, valor="https://s3/.ot/1/Painel-limpo-a1b2c3d4.jpg"):
    return {"id_work_order_task": id_wt, "description": texto, "type": 1, "value": valor}


class FracttalDoColetor:
    """REST do Fracttal: a fila e as aprovadas em páginas de 100 (start=) e, por OS, tarefas, subtarefas e anexos."""

    def __init__(self, fila, ordens, recusar_apos=None, aprovadas=None):
        self.fila, self.ordens, self.recusar_apos, self.pedidos = fila, ordens, recusar_apos, []
        self.aprovadas = aprovadas if aprovadas is not None else []

    def __call__(self, path):
        self.pedidos.append(path)
        if self.recusar_apos is not None and len(self.pedidos) > self.recusar_apos:
            raise fracttal.Recusado("o Fracttal recusou por excesso de pedidos (HTTP 429)")
        ini = int(re.search(r"start=(\d+)", path).group(1)) if "start=" in path else 0
        if path.startswith("work_orders?id_status_work_order=2"):
            return {"data": self.fila[ini:ini + 100]}
        if path.startswith("work_orders?id_status_work_order=3"):
            return {"data": self.aprovadas[ini:ini + 100]}
        o = self.ordens[re.search(r"folio=(\d+)", path).group(1)]
        chave = ("tarefas" if path.startswith("work_orders?wo_folio=") else
                 "subtarefas" if path.startswith("work_orders_subtasks/") else "anexos")
        return {"data": o[chave][ini:ini + 100]}

    def de(self, prefixo):
        return [p for p in self.pedidos if p.startswith(prefixo)]


def _config(chave=CHAVE):
    c = {"GRIDCO_DB_API": "http://pg.falso", "GRIDCO_SQL_TOKEN": "token-de-teste"}
    if chave:
        c["NEXUS_CHAVE_CADASTRO"] = chave
    return c


@pytest.fixture
def campo():
    """Duas OS na fila: a 15377 fechada pelo App (fotos com GPS e hora) e a 15380 fechada fora dele."""
    fila = [_w(15377, 501), _w(15380, 601, fim="2026-10-03T10:00:00.000000+00:00", tecnico="Técnico Dois", id_p=8)]
    ordens = {"15377": {"tarefas": [fila[0]], "subtarefas": [_sub(501, 1), _sub(501, 2)], "anexos": [_foto(501)]},
              "15380": {"tarefas": [fila[1]], "subtarefas": [_sub(601, 1)],
                        "anexos": [_foto(601, texto="", valor="https://s3/.ot/2/IMG_2031.jpg")]}}
    fx = FracttalDoColetor(fila, ordens)
    fracttal.usar_fornecedor(fx)
    yield fx, ApiPGFalsa()
    fracttal.usar_fornecedor(None)


DIA_UTIL = datetime(2026, 10, 5, 13, 0, tzinfo=coletor.timezone.utc)      # segunda, 10h em Brasília


def _rodar(api, **kw):
    # de dia, por padrão: o 429 encerra a rodada (de madrugada ele espera e repete, testado à parte)
    kw.setdefault("pausa_s", 0)
    kw.setdefault("agora", DIA_UTIL)
    # o relógio parado na hora do `agora`: com o relógio de verdade, a rodada "de madrugada" rodada de dia parava no
    # 1º pedido (virou o dia), e dois testes só passavam à noite (05/10/2026, 09:50)
    agora = kw["agora"]
    kw.setdefault("relogio", lambda: agora)
    kw.setdefault("espera_429_s", 0)
    return coletor.rodar(_config(kw.pop("chave", CHAVE)), sessao=api, **kw)


def test_primeira_rodada_grava_a_fila_com_a_nota(campo):
    fx, api = campo
    r = _rodar(api)
    linhas = {l["id_tarefa"]: l for l in banco_campo.ler("http://pg.falso", api).values()}
    assert r["gravadas"] == r["conferidas"] == 2 and not r["parou"]
    app = linhas[501]
    # painel do App: subtarefas 25 + 1 foto de 3 (6,7) + descrição 10 + assinatura 10 + observação 0 + GPS 20
    assert app["pelo_app"] and app["nota"] == 72 and app["gps_fotos"] and app["n_fotos"] == 1
    assert app["nota_placar"] == 100 and app["pontos_placar"] == 40
    assert app["os"] == "15377" and app["dur_prev_min"] == 30 and app["dur_real_min"] == 45 and app["status_os"] == 2
    assert app["fim"] == "2026-10-03T14:00:00" and app["regua"] == coletor.regras_app.CODIGO_APP
    # fechada fora do App: sem a marca das fotos do App, não há o que julgar, e as subtarefas nem são pedidas
    fora = linhas[601]
    assert fora["pelo_app"] is False and fora["nota"] is None
    assert fx.de("work_orders_subtasks/") == ["work_orders_subtasks/?folio=15377&limit=100&start=0"]


NOTA_RONDA = ("Ronda 2026-10-03 · Usina B · qualidade 87% · duração real 34 min (08:00 às 08:34) — "
              "Computador: Ligado; CFTV: Desligado; Sujidade da vala de drenagem: Limpa")


def _ronda_fx(fx):
    fx.fila.append(_w(15390, 701, note=NOTA_RONDA))
    fx.ordens["15390"] = {"tarefas": [fx.fila[-1]],
                          "subtarefas": [{"id_work_order_task": 701, "description": "Resumo da ronda",
                                          "value": NOTA_RONDA, "id_task_form_item_type": 1, "is_required": False},
                                         {"id_work_order_task": 701, "description": "Pendências e ocorrências",
                                          "value": "PENDÊNCIAS — trackers com desvio: 2 de 30 respondidos | ACHADOS — "
                                                   "Pragas: 2 pontos", "id_task_form_item_type": 1,
                                          "is_required": False}],
                          "anexos": [_foto(701), _foto(701, texto="Pragas · 2026-10-03T08:20:00.000Z")]}


def test_ronda_vai_ao_banco_como_informacao_de_ronda(campo):
    # Levi, 05/10: "esses dados de ronda têm sim que ir para a API, guardados como informação de ronda, salvando o
    # número da OS e todas essas informações"
    fx, api = campo
    _ronda_fx(fx)
    _rodar(api)
    l = banco_campo.ler("http://pg.falso", api)[701]
    assert l["ronda"] and l["pelo_app"] and l["nota"] == 87
    assert (l["ronda_dia"], l["ronda_usina"], l["ronda_duracao_min"], l["ronda_hora_ini"], l["ronda_hora_fim"]) == (
        "2026-10-03", "Usina B", 34, "08:00", "08:34")
    assert l["ronda_respostas"].startswith("Computador: Ligado; CFTV: Desligado")
    assert "trackers com desvio: 2 de 30" in l["ronda_pendencias"] and "Pragas: 2 pontos" in l["ronda_pendencias"]
    assert l["n_fotos"] == 2 and l["gps_fotos"] and l["ronda_lida"]
    aba = banco_campo.ler_rondas("http://pg.falso", api)
    assert [(r["os"], r["qualidade"], r["duracao_real_min"]) for r in aba] == [("15390", 87, 34)]
    assert set(aba[0]) == {a for a, _ in banco_campo.COLUNAS_RONDAS}


def test_ronda_gravada_so_com_a_nota_e_relida_uma_vez(campo):
    fx, api = campo
    _ronda_fx(fx)
    _rodar(api)
    antiga = banco_campo.ler("http://pg.falso", api)
    antiga[701].update(ronda_respostas=None, ronda_pendencias=None, ronda_lida=None)       # como antes de 05/10
    banco_campo.gravar(list(antiga.values()), banco_campo.resumo(list(antiga.values()), "x"), base="http://pg.falso",
                       token="t", sessao=api)
    _rodar(api)
    assert banco_campo.ler("http://pg.falso", api)[701]["ronda_lida"]
    antes = len(fx.pedidos)
    _rodar(api)
    assert not [p for p in fx.pedidos[antes:] if "15390" in p]     # já lida: não pede de novo


def test_segunda_rodada_so_le_a_fila(campo):
    fx, api = campo
    _rodar(api)
    antes = len(fx.pedidos)
    r = _rodar(api)
    assert fx.pedidos[antes:] == ["work_orders?id_status_work_order=2&limit=100&start=0&sort=final_date",
                                  "work_orders?id_status_work_order=3&limit=100&start=0&sort=final_date:desc"]
    assert r["notas"] == 0 and r["gravadas"] == 0 and api.syncs == 1     # nada mudou: não regrava


def test_tarefa_fechada_de_novo_vira_devolvida(campo):
    fx, api = campo
    _rodar(api)
    fx.fila[0] = _w(15377, 501, fim="2026-10-04T09:00:00.000000+00:00")
    fx.ordens["15377"]["tarefas"] = [fx.fila[0]]
    _rodar(api)
    l = banco_campo.ler("http://pg.falso", api)[501]
    assert l["devolvida"] and l["fim"] == "2026-10-04T09:00:00"


def test_os_que_saiu_da_fila_atualiza_o_status(campo):
    fx, api = campo
    _rodar(api)
    aprovada = dict(fx.fila[0], id_status_work_order=3, wo_final_date="2026-10-04T11:00:00.000000+00:00")
    devolvida = dict(fx.fila[1], id_status_work_order=1)
    fx.ordens["15377"]["tarefas"], fx.ordens["15380"]["tarefas"] = [aprovada], [devolvida]
    fx.fila.clear()
    r = _rodar(api)
    linhas = banco_campo.ler("http://pg.falso", api)
    assert r["saidas"] == 2
    assert linhas[501]["status_os"] == 3 and linhas[501]["aprovacao"] == "2026-10-04T11:00:00"
    assert linhas[601]["status_os"] == 1 and linhas[601]["devolvida"]


def test_para_no_primeiro_429_e_grava_o_que_ja_calculou(campo):
    fx, api = campo
    fx.recusar_apos = 4                    # fila, aprovadas, anexos e subtarefas da 15377; o 5º leva 429
    r = _rodar(api)
    linhas = banco_campo.ler("http://pg.falso", api)
    assert r["parou"] and "429" in r["parou_por"] and not r["completa"]
    assert linhas[501]["nota"] == 72 and 601 not in linhas


def test_fila_lida_pela_metade_nao_vira_saida(campo):
    fx, api = campo
    _rodar(api)
    fx.fila[:0] = [_w(20000 + i, 9000 + i) for i in range(100)]   # a fila passa de uma página
    fx.recusar_apos = len(fx.pedidos) + 1                          # a 2ª página leva 429
    r = _rodar(api)
    assert r["parou"] and r["saidas"] == 0
    assert banco_campo.ler("http://pg.falso", api)[601]["status_os"] == 2


def test_limite_de_ordens_por_rodada_comeca_pela_mais_recente(campo):
    fx, api = campo
    r = _rodar(api, max_os=1)
    linhas = banco_campo.ler("http://pg.falso", api)
    assert r["notas"] == 1 and list(linhas) == [501]


def test_nome_do_tecnico_vai_cifrado(campo):
    fx, api = campo
    _rodar(api)
    bruto = api.linhas(banco_campo.WORKBOOK, banco_campo.ABA)
    assert "Técnico Um" not in repr(bruto)
    l = banco_campo.ler("http://pg.falso", api)[501]
    assert l["tecnico_id"] == 7
    assert Cofre(CHAVE).decifrar(l["tecnico_cifrado"], coletor.contexto_do_tecnico(501)) == "Técnico Um"


def test_nome_cifrado_nao_muda_se_o_tecnico_nao_mudou(campo):
    fx, api = campo
    _rodar(api)
    antes = banco_campo.ler("http://pg.falso", api)[501]["tecnico_cifrado"]
    _rodar(api)
    assert banco_campo.ler("http://pg.falso", api)[501]["tecnico_cifrado"] == antes


def test_sem_a_chave_vai_so_o_id(campo):
    fx, api = campo
    _rodar(api, chave=None)
    l = banco_campo.ler("http://pg.falso", api)[501]
    assert l["tecnico_cifrado"] is None and l["tecnico_id"] == 7


def test_banco_que_perde_linha_e_acusado(campo):
    fx, _ = campo
    r = _rodar(ApiPGFalsa(perder=1))
    assert r["erro"] and "não devolveu" in r["erro"]


def test_api_que_devolve_texto_e_lida_igual(campo):
    fx, _ = campo
    api = ApiPGFalsa(como_texto=True)
    r = _rodar(api)
    assert r["conferidas"] == 2
    assert banco_campo.ler("http://pg.falso", api)[501]["nota"] == 72


def test_workbook_criado_uma_vez_e_gravado_com_token(campo):
    fx, api = campo
    _rodar(api)
    _rodar(api)
    assert api.criacoes == 1 and "Bearer token-de-teste" in api.tokens


def test_sem_token_calcula_mas_nao_grava(campo):
    fx, api = campo
    c = _config()
    del c["GRIDCO_SQL_TOKEN"]
    r = coletor.rodar(c, sessao=api, pausa_s=0)
    assert r["gravadas"] == 0 and "GRIDCO_SQL_TOKEN" in r["erro"] and api.syncs == 0


def test_hora_do_fracttal_vira_utc():
    assert coletor.utc("2026-10-03T11:00:00.000-03:00") == "2026-10-03T14:00:00"
    assert coletor.utc("2026-10-03T14:00:00Z") == "2026-10-03T14:00:00"
    assert coletor.utc(None) is None and coletor.utc("lixo") is None


@pytest.mark.parametrize("anexos,esperado", [
    ([_foto(1)], True),                                                         # desc · GPS · hora
    ([_foto(1, texto="2026-10-02T14:33:12.000Z", valor="x")], True),             # só a hora (foto sem GPS)
    ([_foto(1, texto="", valor="https://s3/.ot/9/OS15377-foto2-0123456789ab.jpg")], True),   # nome que o App dá
    ([_foto(1, texto="foto do painel", valor="https://s3/IMG_2031.jpg")], False),
    ([], False)])
def test_marca_das_fotos_do_app(anexos, esperado):
    assert coletor.pelo_app(anexos) is esperado


def _cobertura(api):
    return banco_campo.ler_tudo("http://pg.falso", api)[1]


def test_cobertura_completa_so_com_tudo_calculado(campo):
    fx, api = campo
    r = _rodar(api, max_os=1)
    assert not r["completa"] and r["pendentes"] == 1 and _cobertura(api)["completa"] == "não"
    r = _rodar(api, max_os=1)
    assert r["completa"] and r["pendentes"] == 0 and _cobertura(api)["completa"] == "sim"


def test_aprovadas_da_janela_entram_e_a_leitura_para_no_piso(campo):
    fx, api = campo
    agora = datetime(2026, 10, 4, 23, 0, tzinfo=coletor.timezone.utc)
    dentro = _w(15200, 801, fim="2026-09-20T10:00:00.000000+00:00", status=3)
    fora = _w(14000, 802, fim="2026-06-01T10:00:00.000000+00:00", status=3)
    fx.aprovadas = [dentro] + [dict(fora, id_work_orders_tasks=900 + i) for i in range(100)] + [
        _w(13000, 803, fim="2026-05-01T10:00:00.000000+00:00", status=3)]
    fx.ordens["15200"] = {"tarefas": [dentro], "subtarefas": [_sub(801, 1)], "anexos": [_foto(801)]}
    r = _rodar(api, agora=agora)
    linhas = banco_campo.ler("http://pg.falso", api)
    assert r["aprovadas"] == 1 and linhas[801]["status_os"] == 3 and linhas[801]["nota"] is not None
    assert 802 not in linhas and 803 not in linhas
    # a 1ª página mistura uma do período com 99 antigas: a mais nova dela ainda é de 20/09, então lê a 2ª; a 2ª é toda
    # anterior ao piso e a leitura para ali
    assert len(fx.de("work_orders?id_status_work_order=3")) == 2


def test_carga_longa_grava_no_meio(campo):
    fx, api = campo
    r = _rodar(api, gravar_a_cada=1)
    assert api.syncs == 2 and r["completa"]          # depois da 1ª OS e no fim


@pytest.mark.parametrize("ultimo,quando,esperado", [
    ({"pendentes": 9000}, datetime(2026, 10, 4, 23, 0, tzinfo=coletor.timezone.utc), 60),        # domingo à noite
    ({"pendentes": 9000}, datetime(2026, 10, 5, 13, 0, tzinfo=coletor.timezone.utc), 1800),      # segunda, 10h
    ({"pendentes": 9000, "parou": True}, datetime(2026, 10, 4, 23, 0, tzinfo=coletor.timezone.utc), 300),
    ({"pendentes": 9000, "parou": True}, datetime(2026, 10, 5, 13, 0, tzinfo=coletor.timezone.utc), 1800),
    ({"pendentes": 9000, "erro": "x"}, datetime(2026, 10, 4, 23, 0, tzinfo=coletor.timezone.utc), 120),
    ({"erro": "x"}, datetime(2026, 10, 5, 13, 0, tzinfo=coletor.timezone.utc), 1800),
    ({"pendentes": 0}, datetime(2026, 10, 4, 23, 0, tzinfo=coletor.timezone.utc), 1800),
    (None, datetime(2026, 10, 4, 23, 0, tzinfo=coletor.timezone.utc), 1800)])
def test_de_madrugada_a_carga_emenda_as_rodadas(ultimo, quando, esperado):
    assert coletor.espera_s(ultimo, 30, quando) == esperado


def test_rodada_da_madrugada_para_quando_comeca_o_horario_de_campo(campo):
    fx, api = campo
    noite = datetime(2026, 10, 5, 8, 59, tzinfo=coletor.timezone.utc)        # segunda, 05:59 em Brasília
    dia = datetime(2026, 10, 5, 9, 1, tzinfo=coletor.timezone.utc)           # 06:01
    horas = iter([noite, dia, dia])
    r = coletor.rodar(_config(), sessao=api, pausa_s=0, agora=noite, relogio=lambda: next(horas))
    assert r["virou_dia"] and r["notas"] == 1 and r["pendentes"] == 1 and not r["completa"]



class FracttalQueRecusaUmaVez(FracttalDoColetor):
    """Recusa (429) só o pedido de número `recusar_no` e responde todos os outros."""

    def __init__(self, base, recusar_no):
        super().__init__(base.fila, base.ordens, aprovadas=base.aprovadas)
        self.recusar_no = recusar_no

    def __call__(self, path):
        if len(self.pedidos) + 1 == self.recusar_no:
            self.pedidos.append(path)
            raise fracttal.Recusado("o Fracttal recusou por excesso de pedidos (HTTP 429)")
        return super().__call__(path)


def test_de_madrugada_o_429_espera_e_repete_o_mesmo_pedido(campo):
    fx, api = campo
    uma = FracttalQueRecusaUmaVez(fx, recusar_no=3)          # o 3º pedido (anexos da 15377) leva um 429
    fracttal.usar_fornecedor(uma)
    noite = datetime(2026, 10, 5, 3, 0, tzinfo=coletor.timezone.utc)           # domingo, 00h em Brasília
    r = _rodar(api, agora=noite)
    assert not r["parou"] and r["esperas_429"] == 1 and r["completa"]
    assert uma.pedidos[2] == uma.pedidos[3]                    # repetiu o mesmo pedido, sem reler a fila


def test_de_dia_o_429_encerra_a_rodada(campo):
    fx, api = campo
    fracttal.usar_fornecedor(FracttalQueRecusaUmaVez(fx, recusar_no=3))
    r = _rodar(api)
    assert r["parou"] and r["esperas_429"] == 0 and not r["completa"]



def test_endereco_da_usina_nao_vai_ao_banco(campo):
    # o items_log_description do Fracttal traz o endereço da usina; no cadastro do Nexus endereço é sensível (05/10)
    fx, api = campo
    fx.fila[0]["items_log_description"] = ("Thopen - Indaiatuba 1 - SP Estrada IDT 150, S/N Indaiatuba São Paulo "
                                           "Brasil { THPN-IND100 }")
    _rodar(api)
    assert "Estrada" not in repr(api.linhas(banco_campo.WORKBOOK, banco_campo.ABA))
    assert banco_campo.ler("http://pg.falso", api)[501]["ativo"] == "SP 01 · USA-INV1"


def test_linha_antiga_com_endereco_e_reescrita_sem_ele(campo):
    fx, api = campo
    _rodar(api)
    antiga = banco_campo.ler("http://pg.falso", api)
    antiga[501]["ativo"] = "Usina A Estrada X, S/N { USA-INV1 }"         # como a 1ª carga gravou
    banco_campo.gravar(list(antiga.values()), banco_campo.resumo(list(antiga.values()), "x"), base="http://pg.falso",
                       token="t", sessao=api)
    _rodar(api)
    assert banco_campo.ler("http://pg.falso", api)[501]["ativo"] == "SP 01 · USA-INV1"



def _cadastro(api, pessoas, de_para):
    """O cadastro_nexus no banco falso: as pessoas com o nome cifrado, como o Nexus publica (banco/pessoas/<id>)."""
    cofre = Cofre(CHAVE)
    cab_p = ["pessoa_id", "vinculo", "cargo", "excluido", "sensivel_cifrado"]
    api._id("cadastro_nexus", "pessoas")["linhas"] = [
        {"headers": cab_p, "values": [pid, "CLT", "Técnico", "não",
                                      cofre.cifrar(json.dumps({"nome": nome}), f"banco/pessoas/{pid}")]}
        for pid, nome in pessoas]
    cab_d = ["usina_id", "sistema", "chave_externa", "casou_por"]
    api._id("cadastro_nexus", "de_para")["linhas"] = [
        {"headers": cab_d, "values": [uid, "Fracttal · Classificação 1", chave, "código"]} for uid, chave in de_para]


def test_liga_usina_e_pessoa_ao_cadastro_por_id(campo):
    # Levi, 05/10: "pode ligar ao usina_id e pessoa_id do cadastro"
    fx, api = campo
    _cadastro(api, [(17, "Técnico Um"), (18, "Outro Nome")], [(41, "SP 01")])
    r = _rodar(api)
    l = banco_campo.ler("http://pg.falso", api)
    assert (l[501]["usina_id"], l[501]["pessoa_id"]) == (41, 17)
    assert l[601]["pessoa_id"] is None                       # "Técnico Dois" não tem ficha: sem ID, à vista
    atu = banco_campo.ler_tudo("http://pg.falso", api)[1]
    assert int(atu["sem_pessoa_id"]) == 1 and int(atu["sem_usina_id"]) == 0 and r["gravadas"] == 2


def test_homonimo_nao_liga(campo):
    fx, api = campo
    _cadastro(api, [(17, "Técnico Um"), (99, "TECNICO  UM")], [(41, "SP 01")])
    _rodar(api)
    assert banco_campo.ler("http://pg.falso", api)[501]["pessoa_id"] is None


def test_cadastro_fora_do_ar_mantem_o_id_que_ja_estava(campo, monkeypatch):
    fx, api = campo
    _cadastro(api, [(17, "Técnico Um")], [(41, "SP 01")])
    _rodar(api)

    def fora_do_ar(*_a, **_k):
        raise requests.ConnectionError("sem rota")
    monkeypatch.setattr(coletor.ligacao_cadastro, "mapas", fora_do_ar)
    fx.fila[0]["rating"] = 5                                    # algo muda no Fracttal: a linha é regravada
    _rodar(api)
    l = banco_campo.ler("http://pg.falso", api)[501]
    assert l["rating"] == 5 and (l["usina_id"], l["pessoa_id"]) == (41, 17)



def test_hifen_sem_espaco_e_a_mesma_usina():
    m = {"usina": {coletor.ligacao_cadastro._norm("Thopen - Coração 1 - SC"): 7}, "pessoa": {}}
    assert coletor.ligacao_cadastro.usina_id(m, "Thopen - Coração 1- SC") == 7



def test_codigo_do_app_vira_pessoa_id():
    # o App (v226) manda a pessoa como HMAC do e-mail; o Nexus calcula o mesmo código para o e-mail do cadastro
    import hashlib as _h
    import hmac as _hm
    api = ApiPGFalsa()
    cofre = Cofre(CHAVE)
    api._id("cadastro_nexus", "pessoas")["linhas"] = [
        {"headers": ["pessoa_id", "excluido", "sensivel_cifrado"],
         "values": [17, "não", cofre.cifrar(json.dumps({"nome": "Ana", "email": "Ana@X.com"}), "banco/pessoas/17")]},
        {"headers": ["pessoa_id", "excluido", "sensivel_cifrado"],
         "values": [18, "não", cofre.cifrar(json.dumps({"nome": "Beto", "email": "beto@x.com"}), "banco/pessoas/18")]}]
    m = coletor.ligacao_cadastro.mapas({"GRIDCO_DB_API": "http://pg.falso", "NEXUS_CHAVE_CADASTRO": CHAVE,
                                        "NEXUS_PESSOA_HMAC": "k"}, api)
    do_app = _hm.new(b"k", b"ana@x.com", _h.sha256).hexdigest()[:24]          # o _pessoa_hmac do function_app.py
    assert coletor.ligacao_cadastro.pessoa_id_do_codigo(m, do_app) == 17
    assert coletor.ligacao_cadastro.pessoa_id_do_codigo(m, do_app + ";outro") == 17
    sem = coletor.ligacao_cadastro.mapas({"GRIDCO_DB_API": "http://pg.falso", "NEXUS_CHAVE_CADASTRO": CHAVE}, api)
    assert sem["hmac"] == {} and coletor.ligacao_cadastro.pessoa_id_do_codigo(sem, do_app) is None


@pytest.mark.parametrize("quando,roda", [
    (datetime(2026, 10, 5, 13, 30, tzinfo=coletor.timezone.utc), False),   # segunda, 10h30 em Brasília
    (datetime(2026, 10, 5, 22, 0, tzinfo=coletor.timezone.utc), True),     # segunda, 19h
    (datetime(2026, 10, 4, 15, 0, tzinfo=coletor.timezone.utc), True)])    # domingo, 12h
def test_no_horario_de_campo_o_coletor_nao_roda(quando, roda):
    # 05/10: a cota do Fracttal esgotada de manhã fez a OS 15423 não aparecer para o técnico no App
    assert coletor.deve_rodar(quando) is roda
