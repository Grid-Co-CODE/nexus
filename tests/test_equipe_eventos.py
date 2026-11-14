"""Os eventos do dia do Mapa de equipe (10/11/2026; `nexus/campo/equipe/eventos.py`). Pedido do Levi pela sessão Nexus
Field, com a imagem do quadro de eventos do COS: "Quero que apareça tipo ocorrências: Algo nesse estilo".

Os eventos saem dos pontos do dia, pelas réguas que já existem (nenhum número novo): a usina é o raio de 1 km
(`RAIO_USINA_KM`), a saída da usina é o ÚLTIMO ponto nela e a chegada o 1º ponto na outra (a regra dos deslocamentos),
"sem sinal" é 30 min sem ponto, e "andando" é o que o próprio celular diz (`mov`). Sem dado não se inventa: "saiu de
casa" não existe (seria dedução), é "saiu de <cidade>"; e "para <usina>" e "chegada prevista" ficam para quando houver
o destino (a programação do PCM ou a OS).

Coordenadas, usinas e pessoas inventadas; nada vai à rede."""
from datetime import datetime, timedelta, timezone

from nexus.campo.equipe import eventos as EV

AGORA = datetime(2026, 11, 10, 15, 0, tzinfo=timezone.utc)      # 12:00 em Brasília
USINAS = {"7": (-16.612345, -49.187654, "GO"), "8": (-17.334571, -48.712389, "GO")}
NOMES = {"7": "Usina Alfa Teste", "8": "Usina Bravo Teste"}
CASA = (-16.567381, -49.187643)                 # parado fora de usina, 5 km da Alfa
NA_A = (-16.605173, -49.187654)                 # 0,8 km da Alfa
ESTRADA = (-16.981237, -48.954321)
NA_B = (-17.331873, -48.712311)                 # na Bravo


def _p(hora, minuto, lugar, mov=False):
    inst = datetime(2026, 11, 10, hora + 3, minuto, tzinfo=timezone.utc)      # hora de Brasília
    return {"pessoa_id": 1, "instante": inst.strftime("%Y-%m-%dT%H:%M:%SZ"), "lat": lugar[0], "lon": lugar[1],
            "mov": mov}


def _as(hora, minuto):
    return datetime(2026, 11, 10, hora + 3, minuto, tzinfo=timezone.utc)


def _cidade(lat, lon):
    return "Cidade Um Teste" if (lat, lon) == CASA else None


def _eventos(pontos, estado=None, agora=AGORA):
    return EV.do_tecnico(1, pontos, USINAS, NOMES, agora, estado=estado or {}, cidade=_cidade)


def test_o_dia_de_um_tecnico_vira_eventos_com_a_regra_dos_deslocamentos():
    pontos = [_p(6, 40, CASA), _p(6, 50, CASA), _p(7, 0, ESTRADA, mov=True), _p(7, 30, NA_A),
              _p(9, 0, NA_A), _p(9, 10, ESTRADA, mov=True), _p(9, 20, ESTRADA), _p(9, 30, ESTRADA, mov=True),
              _p(10, 5, NA_B)]
    ev = _eventos(pontos, agora=_as(10, 10))
    assert [(e["tipo"], e["hora"], e["texto"]) for e in ev] == [
        ("inicio", "06:40", "primeira posição do dia, em Cidade Um Teste"),
        ("saiu", "06:50", "saiu de Cidade Um Teste"),
        ("chegou", "07:30", "chegou na Usina Alfa Teste, depois de 40 min de deslocamento"),
        ("saiu", "09:00", "saiu da Usina Alfa Teste"),
        ("chegou", "10:05", "chegou na Usina Bravo Teste, depois de 1 h 05 de deslocamento"),
    ]
    # a parada no meio da estrada (09:20, fora de usina) não vira evento: ela está no percurso
    assert [e["rotulo"] for e in ev] == ["Início do dia", "Deslocamento", "Na usina", "Deslocamento", "Na usina"]
    assert [e["tom"] for e in ev] == ["neutro", "info", "ok", "info", "ok"]
    assert ev[2]["usina_id"] == "7" and ev[1]["usina_id"] is None
    # o formato que outra tela (o videowall do COS) pode ler: só texto, hora e ids, nenhuma coordenada
    assert all(set(e) == {"instante", "hora", "pessoa_id", "tipo", "texto", "rotulo", "tom", "usina_id",
                          "destino_usina_id", "destino", "chegada_prevista"} for e in ev)
    assert not any(str(c) in repr(ev) for c in (*CASA, *NA_A, *ESTRADA, *NA_B))


def test_quem_comeca_na_usina_nao_sai_de_cidade_nenhuma():
    ev = _eventos([_p(6, 30, NA_A), _p(8, 0, NA_A)], agora=_as(8, 10))
    assert [(e["tipo"], e["texto"]) for e in ev] == [("inicio", "primeira posição do dia, na Usina Alfa Teste")]


def test_sem_a_cidade_o_texto_diz_fora_de_usina_e_nao_inventa():
    """A cidade sai da malha do IBGE no disco; sem ela, "fora de usina", nunca "casa"."""
    ev = EV.do_tecnico(1, [_p(6, 40, CASA), _p(7, 0, ESTRADA, mov=True)], USINAS, NOMES, _as(7, 10), estado={},
                       cidade=lambda lat, lon: None)
    assert [e["texto"] for e in ev] == ["primeira posição do dia, fora de usina", "saiu de um ponto fora de usina"]
    assert "casa" not in repr(ev)


def test_sem_sinal_e_sem_permissao_entram_como_eventos_do_dia():
    """O sem sinal entra na hora em que virou sem sinal (o último ponto + 30 min) e diz desde quando; o sem permissão,
    na hora em que o celular avisou, se foi hoje."""
    ev = _eventos([_p(6, 30, NA_A), _p(11, 0, NA_A)])            # último ponto às 11:00; agora 12:00
    (s,) = [e for e in ev if e["tipo"] == "sem_sinal"]
    assert (s["hora"], s["texto"], s["rotulo"], s["tom"]) == ("11:30", "sem sinal desde 11:00", "Sem sinal", "alerta")
    ev = _eventos([_p(6, 30, NA_A), _p(11, 50, NA_A)], estado={"permissao": "sem", "desde": AGORA - timedelta(hours=1)})
    (s,) = [e for e in ev if e["tipo"] == "sem_permissao"]
    assert (s["hora"], s["texto"], s["tom"]) == ("11:00", "sem permissão no celular", "critico")
    assert not [e for e in ev if e["tipo"] == "sem_sinal"]                 # 10 min: ainda com sinal
    # o aviso de ontem não é evento de hoje
    ev = _eventos([_p(6, 30, NA_A)], estado={"permissao": "sem", "desde": AGORA - timedelta(days=1)})
    assert not [e for e in ev if e["tipo"] == "sem_permissao"]


def test_os_eventos_da_equipe_vem_do_mais_novo_ao_mais_velho_com_o_resumo():
    ev = EV.da_equipe({1: [_p(6, 40, CASA), _p(7, 0, ESTRADA, mov=True), _p(7, 30, NA_A)],
                       2: [{**_p(7, 45, NA_B), "pessoa_id": 2}]},
                      USINAS, NOMES, _as(7, 55), estados={}, cidade=_cidade)
    assert [(e["pessoa_id"], e["hora"], e["tipo"]) for e in ev] == [
        (2, "07:45", "inicio"), (1, "07:30", "chegou"), (1, "06:40", "saiu"), (1, "06:40", "inicio")]
    assert EV.resumo(ev) == "1 deslocamento · 1 chegada · 2 inícios do dia"
    assert EV.resumo([]) == ""


def test_so_a_saida_do_lugar_do_inicio_vira_saiu_de_cidade():
    """O "saiu de <cidade>" é a saída do lugar onde o dia começou (os pontos parados do início). Quem começa o dia já
    andando não tem esse lugar: a parada fora de usina no meio do caminho não vira saída."""
    ev = _eventos([_p(6, 40, ESTRADA, mov=True), _p(7, 0, CASA), _p(7, 10, ESTRADA, mov=True)], agora=_as(7, 15))
    assert [e["tipo"] for e in ev] == ["inicio"]
    # e quem começa parado sai uma vez só: a 2ª parada fora de usina também não vira saída
    ev = _eventos([_p(6, 40, CASA), _p(7, 0, ESTRADA, mov=True), _p(7, 5, ESTRADA), _p(7, 10, ESTRADA, mov=True)],
                  agora=_as(7, 15))
    assert [e["tipo"] for e in ev] == ["inicio", "saiu"]


# ── o destino pela programação do PCM (10/11/2026, Levi: "Pode subir o destino do técnico") ────────────────────────
# os blocos de hoje da equipe do técnico, na ordem da hora (o que `equipe_tela._programa_do_dia` monta do
# banco_dados.json do PCM): a usina (o id pelo de-para do Fracttal), a hora de início e se a tarefa já foi feita
PROG = [{"usina_id": "7", "usina": "Usina Alfa Teste", "h_ini": "07:10", "feita": False},
        {"usina_id": "8", "usina": "Usina Bravo Teste", "h_ini": "13:12", "feita": False}]


def _eta(saida, de, usina):
    from nexus.campo.equipe.deslocamentos import haversine_km
    horas = haversine_km(*de, *USINAS[usina][:2]) / 70.0 * 1.2
    return (saida + timedelta(hours=horas)).astimezone(timezone(timedelta(hours=-3))).strftime("%H:%M")


def test_a_saida_leva_o_destino_da_programacao_e_a_chegada_prevista_pela_regua_do_pcm():
    """O destino é o próximo bloco da programação de hoje da equipe do técnico que ainda não foi feito, numa usina
    diferente da que ele deixa; a chegada prevista é a régua do motor do PCM (a distância em linha reta / 70 km/h x
    1,2), da hora e do ponto da saída. A chegada diz a hora programada da usina."""
    pontos = [_p(6, 40, CASA), _p(6, 50, CASA), _p(7, 0, ESTRADA, mov=True), _p(7, 30, NA_A), _p(9, 0, NA_A),
              _p(9, 10, ESTRADA, mov=True), _p(10, 5, NA_B)]
    ev = EV.do_tecnico(1, pontos, USINAS, NOMES, _as(10, 10), estado={}, cidade=_cidade, programa=PROG)
    saidas = [e for e in ev if e["tipo"] == "saiu"]
    assert saidas[0]["texto"] == ("saiu de Cidade Um Teste para Usina Alfa Teste; chegada prevista "
                                  + _eta(_as(6, 50), CASA, "7"))
    assert saidas[1]["texto"] == ("saiu da Usina Alfa Teste para Usina Bravo Teste; chegada prevista "
                                  + _eta(_as(9, 0), NA_A, "8"))
    assert [e["destino_usina_id"] for e in saidas] == ["7", "8"] and all(e["chegada_prevista"] for e in saidas)
    assert [e["destino"] for e in saidas] == ["Usina Alfa Teste", "Usina Bravo Teste"]
    chegadas = [e["texto"] for e in ev if e["tipo"] == "chegou"]
    assert chegadas == ["chegou na Usina Alfa Teste, depois de 40 min de deslocamento; programada às 07:10",
                        "chegou na Usina Bravo Teste, depois de 1 h 05 de deslocamento; programada às 13:12"]


def test_o_destino_pula_o_bloco_feito_e_sem_programacao_nao_ha_destino():
    pontos = [_p(6, 40, CASA), _p(7, 0, ESTRADA, mov=True)]
    feita = [{**PROG[0], "feita": True}, PROG[1]]
    (s,) = [e for e in EV.do_tecnico(1, pontos, USINAS, NOMES, _as(7, 10), estado={}, cidade=_cidade, programa=feita)
            if e["tipo"] == "saiu"]
    assert s["texto"].startswith("saiu de Cidade Um Teste para Usina Bravo Teste; chegada prevista ")
    # sem programação (a equipe sem bloco hoje, o arquivo do PCM fora do ar): a saída sem destino, nada inventado
    (s,) = [e for e in EV.do_tecnico(1, pontos, USINAS, NOMES, _as(7, 10), estado={}, cidade=_cidade)
            if e["tipo"] == "saiu"]
    assert s["texto"] == "saiu de Cidade Um Teste" and s["destino_usina_id"] is None and s["chegada_prevista"] is None
    # a usina do bloco sem coordenada no cadastro (ou sem de-para): o destino pelo nome, sem a chegada prevista
    sem = [{"usina_id": None, "usina": "Usina Sem Ligacao", "h_ini": "08:00", "feita": False}]
    (s,) = [e for e in EV.do_tecnico(1, pontos, USINAS, NOMES, _as(7, 10), estado={}, cidade=_cidade, programa=sem)
            if e["tipo"] == "saiu"]
    assert s["texto"] == "saiu de Cidade Um Teste para Usina Sem Ligacao" and s["chegada_prevista"] is None


def test_a_regua_da_chegada_prevista_e_a_do_motor_do_pcm():
    """Uma régua só: a velocidade e o fator de rota são os do motor do PCM (`programacao_v7.py`, cópia idêntica do
    repositório do PCM, que não se importa aqui por ser o script do motor). Mudou lá, este teste avisa."""
    import re
    from pathlib import Path
    motor = (Path(__file__).resolve().parent.parent / "nexus" / "pcm" / "motor" / "programacao_v7.py").read_text(
        encoding="utf-8")
    kmh = float(re.search(r"^TRAVEL_KMH\s*=\s*([\d.]+)", motor, flags=re.M).group(1))
    fator = float(re.search(r"^TRAVEL_FACTOR\s*=\s*([\d.]+)", motor, flags=re.M).group(1))
    assert (EV.VELOCIDADE_KMH, EV.FATOR_ROTA) == (kmh, fator)


# ── o percurso contado por usina (11/11/2026) ────────────────────────────────────────────────────────────────────────
def _percurso(pontos):
    return [(i["tipo"], i["de"], i["ate"], i["texto"]) for i in EV.do_percurso(pontos, USINAS, NOMES, cidade=_cidade)]


def test_o_percurso_conta_o_dia_por_usina_com_a_regra_dos_eventos():
    """Levi, 11/11/2026: "O percurso do técnico deve ser mais generalista por exemplo 'Chegou na UFV X', 'Saiu da Usina X',
    'Chegou na UFV X'". A lista do Ver percurso deixa de ser ponto a ponto ("em deslocamento", "parado") e conta o que
    aconteceu, pela MESMA regra dos eventos do dia: a usina é o raio de 1 km, a saída é o último ponto nela, a chegada o
    1º ponto na outra. A parada fora de usina no meio do caminho fica (com a cidade, quando há), o trecho andando fica
    implícito, e a saída diz quanto tempo ficou na usina."""
    pontos = [_p(6, 40, CASA), _p(6, 50, CASA), _p(7, 0, ESTRADA, mov=True), _p(7, 30, NA_A),
              _p(9, 0, NA_A), _p(9, 10, ESTRADA, mov=True), _p(9, 20, ESTRADA), _p(9, 25, ESTRADA),
              _p(9, 30, ESTRADA, mov=True), _p(10, 5, NA_B)]
    # a linha do tempo (Levi, 13/11/2026: "Tá com muito texto. Eu queria mais essa visão de linha do tempo mesmo [...]
    # Entrou, saiu, voltou"): o texto é o que aconteceu e onde; o tempo vai num detalhe curto
    assert _percurso(pontos) == [
        ("cidade", "06:40", "06:50", "Em Cidade Um Teste"),
        ("chegou", "07:30", "07:30", "Entrou na Usina Alfa Teste"),
        ("saiu", "09:00", "09:00", "Saiu da Usina Alfa Teste"),
        ("parado", "09:20", "09:25", "Parado fora de usina"),
        ("chegou", "10:05", "10:05", "Entrou na Usina Bravo Teste"),
    ]
    itens = EV.do_percurso(pontos, USINAS, NOMES, cidade=_cidade)
    assert [(i["acao"], i["lugar"], i["detalhe"], i["repete"]) for i in itens] == [
        ("Em", "Cidade Um Teste", "", False),
        ("Entrou", "Usina Alfa Teste", "40 min de deslocamento", False),
        ("Saiu", "Usina Alfa Teste", "1 h 30 na usina", True),            # o lugar da linha de cima: a tela não repete
        ("Parado", "fora de usina", "", False),
        ("Entrou", "Usina Bravo Teste", "1 h 05 de deslocamento", False),
    ]


def test_o_percurso_chama_de_ufv_a_usina_sem_ufv_no_nome_e_fecha_no_ultimo_ponto():
    """O nome do cadastro em geral não diz "UFV" ("Altair", "Ipixuna 1 e 2"): o texto diz "Entrou na UFV Altair". O
    nome que já diz UFV ou Usina fica como está. Começar na usina é "Começou na UFV X"; o período que termina
    andando fecha com "Terminou em deslocamento"; a parada fora de usina diz a cidade."""
    nomes = {"7": "Altair Teste", "8": "UFV Bravo Teste"}
    pontos = [_p(8, 0, NA_A), _p(8, 30, NA_A), _p(8, 40, ESTRADA, mov=True), _p(9, 0, CASA), _p(9, 5, CASA),
              _p(9, 10, ESTRADA, mov=True), _p(10, 0, NA_B), _p(10, 30, NA_B), _p(10, 40, ESTRADA, mov=True)]
    itens = [(i["tipo"], i["de"], i["ate"], i["texto"])
             for i in EV.do_percurso(pontos, USINAS, nomes, cidade=_cidade)]
    assert itens == [
        ("inicio", "08:00", "08:00", "Começou na UFV Altair Teste"),
        ("saiu", "08:30", "08:30", "Saiu da UFV Altair Teste"),
        ("cidade", "09:00", "09:05", "Em Cidade Um Teste"),
        ("chegou", "10:00", "10:00", "Entrou na UFV Bravo Teste"),
        ("saiu", "10:30", "10:30", "Saiu da UFV Bravo Teste"),
        ("ultimo", "10:40", "10:40", "Terminou em deslocamento"),
    ]
    # cada linha só com tipo, horas, o texto em partes e a usina: nenhuma coordenada
    assert all(set(i) == {"tipo", "de", "ate", "texto", "acao", "lugar", "detalhe", "repete", "usina_id"}
               for i in EV.do_percurso(pontos, USINAS, nomes))


def test_o_percurso_de_mais_de_um_dia_leva_a_data_e_sem_ponto_e_vazio():
    pontos = [_p(8, 0, NA_A), {**_p(8, 0, NA_B), "instante": "2026-11-11T12:00:00Z"}]
    itens = EV.do_percurso(pontos, USINAS, NOMES)
    # quem sai já no 1º ponto não ganha a "Primeira posição" no mesmo minuto: a saída diz de onde ele partiu
    assert [(i["de"], i["texto"], i["detalhe"]) for i in itens] == [
        ("10/11 08:00", "Saiu da Usina Alfa Teste", ""),
        ("11/11 09:00", "Entrou na Usina Bravo Teste", "25 h 00 de deslocamento")]
    assert EV.do_percurso([], USINAS, NOMES) == []


def test_quem_fica_na_cidade_o_dia_todo_tem_uma_linha_so():
    """Levi, 12/11/2026, com a imagem da lista repetindo "Parado em Guaratinguetá" dez vezes: "deixa bem simples e
    direto, 'Em Guaratinguetá' se ele ficou o dia todo vai aparecer só isso o dia todo!". As paradas seguidas na mesma
    cidade, sem usina no meio, viram UMA linha "Em <cidade>" do primeiro ao último ponto dela; o andar dentro da cidade
    não quebra a linha, e o começo e o fim andando também entram nela quando o ponto é da mesma cidade."""
    pontos = [_p(8, 8, CASA), _p(8, 15, CASA), _p(8, 20, ESTRADA, mov=True), _p(8, 42, CASA), _p(8, 50, ESTRADA, mov=True),
              _p(9, 0, CASA), _p(9, 10, CASA, mov=True)]
    assert _percurso(pontos) == [("cidade", "08:08", "09:10", "Em Cidade Um Teste")]
    # andando no começo e no fim, num ponto sem cidade: a primeira e a última posição em deslocamento
    pontos = [_p(8, 0, ESTRADA, mov=True), _p(8, 10, CASA), _p(8, 20, CASA), _p(8, 30, ESTRADA, mov=True)]
    assert _percurso(pontos) == [
        ("inicio", "08:00", "08:00", "Começou em deslocamento"), ("cidade", "08:10", "08:20", "Em Cidade Um Teste"),
        ("ultimo", "08:30", "08:30", "Terminou em deslocamento")]


def test_quem_sai_e_volta_a_mesma_usina_voltou():
    """Levi, 13/11/2026, com a lista da Matões 200 ("Chegou na UFV Matões 200, depois de 14 min de deslocamento", "Saiu
    da UFV Matões 200, depois de 22 min na usina"...): "Entrou, saiu, voltou, entendeu? Eu acho que não tem necessidade
    de muito texto". Quem volta à usina de onde acabou de sair VOLTOU, e o detalhe diz quanto tempo ficou fora."""
    pontos = [_p(7, 18, CASA), _p(7, 20, NA_A), _p(10, 44, NA_A), _p(10, 50, ESTRADA, mov=True), _p(10, 58, NA_A),
              _p(11, 20, NA_A), _p(11, 22, ESTRADA, mov=True), _p(11, 24, NA_A), _p(11, 30, NA_A)]
    itens = EV.do_percurso(pontos, USINAS, NOMES, cidade=_cidade)
    assert [(i["de"], i["acao"], i["detalhe"], i["repete"]) for i in itens] == [
        ("07:18", "Em", "", False),
        ("07:20", "Entrou", "2 min de deslocamento", False),
        ("10:44", "Saiu", "3 h 24 na usina", True),
        ("10:58", "Voltou", "14 min fora", True),
        ("11:20", "Saiu", "22 min na usina", True),
        ("11:24", "Voltou", "4 min fora", True),
    ]
    assert itens[3]["texto"] == "Voltou à Usina Alfa Teste"

