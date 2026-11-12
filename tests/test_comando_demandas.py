"""As demandas entre setores (12/11/2026, Levi: "os setores consigam conversar entre si sem ter que especificamente criar
um OS"; o desenho em docs/superpowers/specs/2026-11-12-demandas-entre-setores-design.md).

O que estes testes seguram: o prazo em dias úteis (sem fim de semana e feriado nacional), a pausa do "pedir informação",
a conclusão sozinha em 3 dias úteis, a vencida que avisa o setor; o livro `nexus_demandas` no catálogo antes da 1ª
gravação, com o texto e os nomes só cifrados; o papel e a vez de cada passo; a OS só da usina escolhida; e as telas
(a Caixa de entrada, a Nova demanda, os Temas do setor e o sininho). Banco falso do test_campo_visao; nomes fictícios."""
from datetime import date

from nexus.comando import demandas_regras as R


def _ev(evento, iso):
    return {"evento": evento, "registrado_em": iso}


ABRIU = {"registrado_em": "2026-11-11T13:00:00.000Z"}           # qua 11/11, 10:00 em Brasília


# ── a regra pura ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_prazo_pula_fim_de_semana_e_feriado():
    assert R.somar_dias_uteis(date(2026, 11, 13), 1) == date(2026, 11, 16)          # sexta + 1 = segunda
    assert R.somar_dias_uteis(date(2026, 11, 19), 1) == date(2026, 11, 23)          # 20/11 é feriado nacional
    assert R.dias_uteis_entre(date(2026, 11, 13), date(2026, 11, 16)) == 1
    assert R.dias_uteis_entre(date(2026, 11, 16), date(2026, 11, 13)) == -1


def test_situacoes_pelo_ultimo_evento():
    hoje = date(2026, 11, 12)
    assert R.estado(ABRIU, [], 2, hoje)["situacao"] == "nova"
    assert R.estado(ABRIU, [_ev("em_analise", "2026-11-11T15:00:00Z")], 2, hoje)["situacao"] == "em_analise"
    e = R.estado(ABRIU, [_ev("pediu_informacao", "2026-11-11T15:00:00Z")], 2, hoje)
    assert e["situacao"] == "aguardando" and e["pausada"] and not e["vencida"]
    passos = [_ev("em_analise", "2026-11-11T14:00:00Z"), _ev("respondeu", "2026-11-12T14:00:00Z")]
    assert R.estado(ABRIU, passos, 2, hoje)["situacao"] == "finalizada"
    devolvida = R.estado(ABRIU, passos + [_ev("devolveu", "2026-11-13T14:00:00Z")], 2, date(2026, 11, 13))
    assert devolvida["situacao"] == "devolvida" and devolvida["prazo"] == date(2026, 11, 17)      # 2 dias da devolução
    assert R.estado(ABRIU, passos + [_ev("concluiu", "2026-11-12T16:00:00Z")], 2, hoje)["situacao"] == "concluida"
    # o passo fora da vez não muda nada (concluir o que não foi respondido)
    assert R.estado(ABRIU, [_ev("concluiu", "2026-11-11T16:00:00Z")], 2, hoje)["situacao"] == "nova"


def test_a_pausa_empurra_o_prazo():
    assert R.estado(ABRIU, [], 2, date(2026, 11, 11))["prazo"] == date(2026, 11, 13)
    pausa = [_ev("pediu_informacao", "2026-11-12T14:00:00Z"), _ev("informou", "2026-11-16T14:00:00Z")]
    e = R.estado(ABRIU, pausa, 2, date(2026, 11, 16))
    assert e["situacao"] == "em_analise" and e["prazo"] == date(2026, 11, 17)      # sexta e segunda parados
    # com a pausa ainda aberta, o prazo anda junto até hoje
    aberta = R.estado(ABRIU, pausa[:1], 2, date(2026, 11, 16))
    assert aberta["pausada"] and aberta["prazo"] == date(2026, 11, 17) and not aberta["vencida"]


def test_vencida_e_conclusao_sozinha():
    e = R.estado(ABRIU, [_ev("em_analise", "2026-11-11T14:00:00Z")], 2, date(2026, 11, 16))
    assert e["vencida"] and e["dias_restantes"] == -1 and R.selo_do_prazo(e) == ("Vencida", "há 1 dia", "critico")
    assert R.selo_do_prazo(R.estado(ABRIU, [], 2, date(2026, 11, 13))) == ("Vence", "hoje", "critico")
    assert R.selo_do_prazo(R.estado(ABRIU, [], 2, date(2026, 11, 12))) == ("Falta", "1 dia", "alerta")
    respondida = [_ev("respondeu", "2026-11-10T14:00:00Z")]
    abriu_antes = {"registrado_em": "2026-11-09T13:00:00Z"}
    assert R.estado(abriu_antes, respondida, 2, date(2026, 11, 12))["situacao"] == "finalizada"
    s = R.estado(abriu_antes, respondida, 2, date(2026, 11, 13))
    assert s["situacao"] == "concluida" and s["sozinha"] and s["rotulo"] == "Concluída sozinha"


def _d(did, de, para, setor, estado):
    return {"demanda_id": did, "de_hmac": de, "para_hmac": para, "para_setor_id": setor, "titulo": did, "de_nome": de,
            "estado": estado}


def test_avisos_de_quem_pediu_de_quem_recebe_e_do_setor():
    hoje = date(2026, 11, 12)
    nova = R.estado(ABRIU, [], 5, hoje)
    falta1 = R.estado(ABRIU, [_ev("em_analise", "2026-11-11T14:00:00Z")], 2, hoje)
    vencida = R.estado({"registrado_em": "2026-11-05T13:00:00Z"}, [], 2, hoje)
    respondida = R.estado(ABRIU, [_ev("respondeu", "2026-11-12T12:00:00Z")], 2, hoje)
    aguardando = R.estado(ABRIU, [_ev("pediu_informacao", "2026-11-12T12:00:00Z")], 2, hoje)
    lista = [_d("d1", "ana", "eu", 2, nova), _d("d2", "ana", "eu", 2, falta1), _d("d3", "ana", "bia", 2, vencida),
             _d("d4", "eu", "ana", 7, respondida), _d("d5", "eu", "ana", 7, aguardando), _d("d6", "ana", "bia", 9, vencida)]
    meus = {a["demanda_id"]: a["tipo"] for a in R.avisos(lista, "eu", 2, hoje)}
    assert meus == {"d1": "nova", "d2": "prazo", "d3": "vencida", "d4": "respondida", "d5": "informacao"}
    assert [a["demanda_id"] for a in R.avisos(lista, "eu", 2, hoje)][0] == "d3"        # a vencida primeiro
    assert {a["demanda_id"] for a in R.avisos(lista, "outra", 3, hoje)} == set()
