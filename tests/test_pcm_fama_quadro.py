"""As OS da FAMA no Quadro da semana (Levi, 11/11/2026: o cliente cria a OS na FAMA e ela aparece para o programador; "a
ideia é não ficarmos criando e editando e sim acompanhando"). Fase 1, SOMBRA: o Quadro mostra, nada muda na programação.

O que estes testes seguram: quais OS entram na semana (as abertas no dia da previsão; a aberta de antes da segunda vai na
segunda, "atrasada", num bloco recolhido; em mobilização e em execução, "em andamento"; as outras situações e a previsão
depois do domingo, não); a OS sem usina ligada vira aviso, não cartão; a sem data prevista também; os cartões da FAMA vêm
depois das tarefas oficiais, com o mesmo teto do Quadro; os filtros valem para elas (o responsável da usina sem tarefa
pela volta do cadastro) e as listas contam as OS da FAMA à parte; o "livro da FAMA gravado em" e o aviso da leitura
parada; a etiqueta de repetição só na preventiva do Fracttal da usina com preventiva da FAMA na semana, dita no rótulo
do cartão; a semana que acabou fica sem a FAMA; e a tela. O caminho de produção (a cópia por trás, sem ler o banco no
pedido) está em `tests/test_pcm_fama_copia.py`. A FAMA e o banco são de mentira: nenhum teste vai à rede."""
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from nexus.pcm import fama_os as FO
from nexus.pcm import fama_quadro as FQ
from nexus.pcm import quadro as Q
from test_pcm_quadro import _r

RAIZ = Path(__file__).resolve().parents[1]
BRT = timezone(timedelta(hours=-3))
TITULO_SIGILOSO = "Inversor parado no bloco norte"     # o título vem cifrado no livro: só a tela o mostra
AGORA = datetime(2026, 10, 7, 12, 0, tzinfo=BRT)
LIDO = "2026-10-07T10:40:00-03:00"                      # o batimento da carga, 1h20 antes de AGORA
REPETICAO = "A FAMA também tem preventiva desta usina nesta semana"


def _semana():
    """A W41 (segunda 05/10 a domingo 11/10/2026): duas usinas do Fracttal (a 1 com corretiva e MPM, a 2 com MPM)."""
    rows = [_r(1, "Segunda-feira", "08:00"),
            _r(2, "Terça-feira", "09:00", tarefa="[Grid Co.] - MPM - Cabine", tipo="MPM"),
            _r(3, "Quarta-feira", "10:00", tarefa="[Grid Co.] - MPM - Trafo", tipo="MPM", equipe="RN Sul 01",
               usina="Cliente B - Usina 2 - RN", cliente="Cliente B", responsavel="Pessoa B"),
            _r(4, "Quinta-feira", "11:00")]
    return {"week": "2026-W41", "label": "Semana 41", "rows": rows, "pendentes": [],
            "dates": {"seg": "05/10", "ter": "06/10", "qua": "07/10", "qui": "08/10", "sex": "09/10"}}


# a usina 3 não tem tarefa do Fracttal na semana: a equipe, o cliente e o responsável saem do cadastro (o responsável,
# o gestor de contrato da ficha, escrito no cadastro de outro jeito que na semana)
CADASTRO = {10: {"nomes": ["Cliente A - Usina 1 - SP"], "nome": "Usina 1", "cliente": "Cliente A", "equipe": "SP Leste 02",
                 "responsavel": "Pessoa A"},
            20: {"nomes": ["Cliente B - Usina 2 - RN"], "nome": "Usina 2", "cliente": "Cliente B", "equipe": "RN Sul 01",
                 "responsavel": "Pessoa B"},
            30: {"nomes": ["Cliente C - Usina 3 - MG"], "nome": "Usina 3", "cliente": "Cliente C", "equipe": "MG Sul 01",
                 "responsavel": "PESSOA  A"}}


def _f(i, usina, status, tipo="Corrective", prevista=20261006, severidade="Routine", titulo="Tarefa da FAMA"):
    return {"fama_os_id": i, "usina_id": usina, "status": status, "tipo": tipo, "severidade": severidade,
            "data_id_prevista": prevista, "data_id_criacao": 20260901, "titulo": titulo}


LINHAS = [_f(101, 10, "created", severidade="Critical", titulo=TITULO_SIGILOSO),     # terça
          _f(102, 10, "planned", tipo="Preventive/Predictive", prevista=20260928),    # antes da segunda: atrasada
          _f(103, 20, "under execution", tipo="Modules cleaning", prevista=20261008, severidade="Urgent"),
          _f(104, None, "created", prevista=20261007),                                # sem usina ligada
          _f(105, 10, "closed"),                                                      # fechada: não entra
          _f(106, 10, "created", prevista=20261020),                                  # depois do domingo
          _f(107, 30, "paused", tipo="Vegetation control", prevista=20261010, severidade="Non-Urgent"),   # sábado
          _f(108, 20, "created", prevista=None),                                      # sem data prevista
          _f(109, 99, "created")]                                                     # usina fora do cadastro


def _fama(hoje=date(2026, 10, 7), linhas=LINHAS, gerado_em=LIDO):
    return FQ.da_semana(linhas, _semana(), CADASTRO, hoje, gerado_em=gerado_em, agora=AGORA)


def _quadro(filtros=None, hoje=date(2026, 10, 7), linhas=LINHAS, todos=False, gerado_em=LIDO):
    sem, fama = _semana(), _fama(hoje, linhas, gerado_em)
    sem = FQ.marcar_repeticao(sem, fama)
    q = Q.montar(sem, [], filtros or {}, todos=todos, outras_opcoes=fama["linhas"])
    FQ.no_quadro(q, sem, fama, filtros or {}, todos=todos)
    return q


def _cartoes_fama(q):
    """{dia: [FAMA-<id>]}, as do dia e as atrasadas do bloco da segunda."""
    out = {c["id"]: [f["num"] for f in (c.get("fama") or []) + (c.get("fama_atrasadas") or [])] for c in q["colunas"]}
    return {d: v for d, v in out.items() if v}


# ── a porta única no teste e o cadastro ──────────────────────────────────────────────────────────────────────────
def test_a_porta_unica_no_teste_devolve_copias_das_linhas_dadas_e_o_batimento():
    """No teste a porta não vai ao banco: devolve cópias das linhas da configuração e o batimento dela. A leitura do livro
    de verdade (a parte A) está em tests/test_pcm_fama_juncao.py."""
    assert FO._linhas_fama({"TESTING": True}).linhas == []
    linha = {"fama_os_id": 1}
    lido = FO._linhas_fama({"TESTING": True, "NEXUS_FAMA_LINHAS_TESTE": [linha], "NEXUS_FAMA_GERADO_EM_TESTE": LIDO})
    assert lido.linhas == [linha] and lido.linhas[0] is not linha       # uma cópia: a tela não muda o dado de ninguém
    assert lido.gerado_em == LIDO


def test_vocabulario_da_fama():
    assert [FO.situacao(s) for s in ("created", "Planned", "paused", "under mobilization", "Under Execution",
                                      "under review", "executed", "approved", "closed", "", None)] == \
        ["aberta"] * 3 + ["andamento"] * 2 + [None] * 6
    assert FO.numero(101) == "FAMA-101" and FO.numero("101.0") == "FAMA-101"
    assert FO.data_de(20261006) == date(2026, 10, 6) and FO.data_de("2026-10-06") == date(2026, 10, 6)
    assert FO.data_de(None) is None and FO.data_de("") is None and FO.data_de(20261399) is None


def test_usinas_do_cadastro_pelo_de_para_do_fracttal_com_o_gestor_de_contrato():
    usinas = [{"usina_id": "10", "nome": "Usina 1", "cliente_id": 1, "equipe_id": 5, "gestor_contrato_id": "9.0"},
              {"usina_id": 11, "nome": "Usina velha", "excluido": "Sim"}]
    de_para = [{"usina_id": 10, "sistema": FO.SISTEMA_FRACTTAL, "chave_externa": "(sem Classificação 1) Usina 1"},
               {"usina_id": 10, "sistema": FO.SISTEMA_FRACTTAL, "chave_externa": "Cliente A -  Usina 1 - SP"},
               {"usina_id": 10, "sistema": "Outro sistema", "chave_externa": "U1"},
               {"usina_id": 11, "sistema": FO.SISTEMA_FRACTTAL, "chave_externa": "Usina velha"}]
    cad = FO.usinas_do_cadastro(usinas, de_para, [{"equipe_id": 5, "nome": "SP Leste 02"}],
                                [{"cliente_id": 1, "nome": "Cliente A"}], gestores={9: "Pessoa A"})
    assert cad == {10: {"nomes": ["Cliente A - Usina 1 - SP", "(sem Classificação 1) Usina 1"], "nome": "Usina 1",
                        "cliente": "Cliente A", "equipe": "SP Leste 02", "gestor_id": 9, "responsavel": "Pessoa A"}}


# ── as OS da semana ──────────────────────────────────────────────────────────────────────────────────────────────
def test_entram_as_abertas_no_dia_da_previsao_e_a_atrasada_no_bloco_da_segunda():
    q = _quadro()
    assert _cartoes_fama(q) == {"seg": ["FAMA-102"], "ter": ["FAMA-101"], "qui": ["FAMA-103"], "sab": ["FAMA-107"]}
    seg = q["colunas"][0]
    assert seg["fama"] == [] and [f["num"] for f in seg["fama_atrasadas"]] == ["FAMA-102"]
    assert seg["fama_atrasadas_n"] == 1
    # o sábado não tinha tarefa do Fracttal: a coluna aparece pela FAMA, na ordem dos dias
    assert [c["id"] for c in q["colunas"]] == ["seg", "ter", "qua", "qui", "sab"]
    sab = q["colunas"][-1]
    assert (sab["nome"], sab["data"], sab["n"], sab["cartoes"]) == ("Sábado", "10/10", 0, [])
    f = {f["num"]: f for c in q["colunas"] for f in (c.get("fama") or []) + (c.get("fama_atrasadas") or [])}
    assert (f["FAMA-102"]["marca"], f["FAMA-102"]["marcat"], f["FAMA-102"]["prev"]) == ("Atrasada", "critico", "28/09")
    assert (f["FAMA-103"]["marca"], f["FAMA-103"]["st"]) == ("Em andamento", "Em execução")
    assert f["FAMA-101"]["marca"] == "" and f["FAMA-107"]["st"] == "Pausada"
    # a OS sem usina ligada (ou com a usina fora do cadastro) e a sem data prevista viram aviso, não cartão
    assert (q["fama"]["sem_usina"], q["fama"]["sem_data"], q["fama"]["total_semana"]) == (2, 1, 4)


def test_o_teto_de_cartoes_vale_para_a_fama_e_ela_vem_depois_das_tarefas(monkeypatch):
    """Revisão de 11/11/2026, item 3: o mesmo teto do Quadro (40 por coluna; aqui 2), com o "+N"; as atrasadas num bloco
    recolhido da segunda; os cartões da FAMA depois das tarefas oficiais, nunca por cima."""
    monkeypatch.setattr(Q, "TETO_CARTOES", 2)
    linhas = (LINHAS + [_f(200 + i, 10, "created", prevista=20261006) for i in range(3)]
              + [_f(300 + i, 20, "planned", prevista=20260920 + i) for i in range(3)])
    q = _quadro(linhas=linhas)
    seg, ter = q["colunas"][0], q["colunas"][1]
    assert (len(ter["fama"]), ter["fama_ocultos"]) == (2, 2)                 # 4 na terça: 2 à vista e "+2"
    assert (len(seg["fama_atrasadas"]), seg["fama_atrasadas_n"], seg["fama_atrasadas_ocultas"]) == (2, 4, 2)
    assert [f["num"] for f in seg["fama_atrasadas"]] == ["FAMA-300", "FAMA-301"]      # a mais velha primeiro
    q = _quadro(linhas=linhas, todos=True)                                  # "mostrar todas"
    assert (len(q["colunas"][1]["fama"]), q["colunas"][1]["fama_ocultos"]) == (4, 0)
    assert len(q["colunas"][0]["fama_atrasadas"]) == 4


def test_o_cartao_mostra_numero_usina_tipo_severidade_previsao_status_e_titulo():
    f = next(f for c in _quadro()["colunas"] for f in c.get("fama") or [] if f["num"] == "FAMA-101")
    assert {k: f[k] for k in ("num", "st", "tp", "sev", "sevt", "uc", "t", "prev", "tc")} == {
        "num": "FAMA-101", "st": "Criada", "tp": "Corretiva", "sev": "Crítica", "sevt": "critico", "uc": "Usina 1 - SP",
        "t": TITULO_SIGILOSO, "prev": "06/10", "tc": "corretiva"}
    # a usina sem tarefa do Fracttal na semana sai pelo nome do de-para
    g = next(f for c in _quadro()["colunas"] for f in c.get("fama") or [] if f["num"] == "FAMA-107")
    assert (g["uc"], g["tp"], g["sev"]) == ("Usina 3 - MG", "Controle de vegetação", "Não urgente")


def test_as_os_da_fama_nao_contam_nas_tarefas_nem_nas_horas_do_dia():
    sem = _semana()
    sem_fama = Q.montar(sem, [], {})
    q = _quadro()
    assert [(c["id"], c["n"], c["horas"]) for c in q["colunas"] if c["id"] != "sab"] == \
        [(c["id"], c["n"], c["horas"]) for c in sem_fama["colunas"]]
    assert (q["total"], q["horas"]) == (sem_fama["total"], sem_fama["horas"])
    assert all("FAMA" not in it["os"] for it in q["itens"])            # nenhuma janela de reprogramar para elas


def test_os_filtros_do_quadro_valem_para_as_os_da_fama():
    assert _cartoes_fama(_quadro({"equipe": "RN Sul 01"})) == {"qui": ["FAMA-103"]}      # a equipe da usina na semana
    assert _cartoes_fama(_quadro({"cliente": "Cliente C"})) == {"sab": ["FAMA-107"]}     # sem tarefa: a do cadastro
    assert _cartoes_fama(_quadro({"tipo": "Corretiva"})) == {"ter": ["FAMA-101"]}
    assert _cartoes_fama(_quadro({"estado": "Em progresso"})) == {"qui": ["FAMA-103"]}
    assert _cartoes_fama(_quadro({"estado": "Pausada|Não iniciada"})) == {"seg": ["FAMA-102"], "ter": ["FAMA-101"],
                                                                          "sab": ["FAMA-107"]}
    assert _cartoes_fama(_quadro({"turno": "Manhã"})) == {}             # a FAMA não tem hora: "Sem horário"
    assert _cartoes_fama(_quadro({"q": "inversor parado"})) == {"ter": ["FAMA-101"]}
    assert _cartoes_fama(_quadro({"q": "fama-107"})) == {"sab": ["FAMA-107"]}
    q = _quadro({"equipe": "RN Sul 01"})
    assert (q["fama"]["total"], q["fama"]["total_semana"]) == (1, 4)


def test_o_gestor_ve_a_os_da_fama_da_usina_sem_tarefa_na_semana():
    """Revisão de 11/11/2026, item 5: a usina 3 não tem tarefa do Fracttal na semana; o responsável dela vem do cadastro
    (o gestor de contrato), escrito como a semana escreve o mesmo nome, e a OS não some no filtro do gestor."""
    assert _cartoes_fama(_quadro({"resp": "Pessoa A"})) == {"seg": ["FAMA-102"], "ter": ["FAMA-101"], "sab": ["FAMA-107"]}
    assert _cartoes_fama(_quadro({"resp": "Pessoa B"})) == {"qui": ["FAMA-103"]}


def test_as_listas_dos_filtros_contam_as_os_da_fama_a_parte():
    """Revisão de 11/11/2026, item 6: o número de cada opção é o das tarefas; as OS da FAMA têm a conta delas."""
    q = _quadro()
    tipos = dict(q["opcoes"]["tipo"])
    assert (tipos["Corretiva"], tipos["MPM"]) == (2, 2)                     # só as tarefas do Fracttal
    assert tipos["Limpeza de módulos"] == 0 and tipos["Controle de vegetação"] == 0
    assert q["opcoes_fora"]["tipo"] == {"Corretiva": 1, "Preventiva/Preditiva": 1, "Limpeza de módulos": 1,
                                        "Controle de vegetação": 1}
    assert q["opcoes_fora"]["resp"] == {"Pessoa A": 3, "Pessoa B": 1}
    # sem a FAMA, as listas são as de sempre (a ordem e a conta)
    assert Q.montar(_semana(), [], {})["opcoes"] == Q.opcoes(_semana()["rows"], {})


def test_a_etiqueta_de_repeticao_so_na_preventiva_do_fracttal_da_usina_com_preventiva_da_fama():
    q = _quadro()
    marcadas = {k["os"] for c in q["colunas"] for k in c["cartoes"] if k.get("frep")}
    # a MPM da usina 1 (a FAMA tem preventiva dela na semana); não a corretiva da mesma usina, nem a MPM da usina 2
    # (lá a FAMA tem limpeza de módulos, que não é preventiva)
    assert marcadas == {"2"}
    assert [it["os"] for it in q["itens"] if it.get("frep")] == ["2"]
    # a semana que entrou não muda (ela é a cópia em memória do arquivo do App)
    sem = _semana()
    FQ.marcar_repeticao(sem, _fama())
    assert not any(r.get("fama_rep") for r in sem["rows"])
    # sem preventiva da FAMA na semana, ninguém marca
    so_corretiva = [l for l in LINHAS if l["fama_os_id"] != 102]
    assert not any(r.get("fama_rep") for r in FQ.marcar_repeticao(_semana(), _fama(linhas=so_corretiva))["rows"])


def test_o_quadro_diz_quando_o_livro_da_fama_foi_gravado_e_avisa_a_leitura_parada():
    """Revisão de 11/11/2026, item 4: o batimento da carga (o `gerado_em` da aba `atualizacao`) é a última gravação
    do livro (re-revisão, item 4: "gravado em", não "lidas em": a carga lê de hora em hora e só regrava quando a FAMA
    muda ou uma vez por dia); com mais de 26 h, a leitura da FAMA parou e o Quadro avisa."""
    q = _quadro()
    assert (q["fama"]["gravado_em"], q["fama"]["velho"]) == ("07/10 10:40", False)
    q = _quadro(gerado_em="2026-10-06T09:59:00-03:00")                    # 26 h e 1 min antes de AGORA
    assert (q["fama"]["gravado_em"], q["fama"]["velho"]) == ("06/10 09:59", True)
    assert _quadro(gerado_em=None)["fama"]["velho"] is True                 # sem batimento: não se sabe, avisa
    assert FO.velho("2026-10-06T10:01:00-03:00", AGORA) is False and FO.velho("lixo", AGORA) is True


def test_a_semana_que_acabou_fica_sem_a_fama():
    """A situação da FAMA é a de agora: aplicada a uma semana passada, ela diria o que não aconteceu naquela semana."""
    fama = _fama(hoje=date(2026, 10, 12))
    assert not fama["ativa"] and fama["linhas"] == []
    assert _cartoes_fama(_quadro(hoje=date(2026, 10, 12))) == {}
    # o domingo ainda é da semana
    assert _fama(hoje=date(2026, 10, 11))["ativa"]


def test_os_textos_dizem_que_a_porta_le_o_livro_da_parte_a():
    """Revisão de 11/11/2026, item 8: depois da junção, nenhum texto diz mais que o leitor da parte A pode faltar na
    máquina (a porta lê o livro no banco)."""
    velhos = ("nexus/dados/fama.py na máquina", "sem a parte A nesta máquina", "está nesta máquina?")
    for arq in ("nexus/pcm/CLAUDE.md", "nexus/pcm/fama_quadro.py", "nexus/pcm/fama_motor.py", "nexus/pcm/fama_os.py"):
        texto = (RAIZ / arq).read_text(encoding="utf-8").replace("`", "")
        assert not any(v in texto for v in velhos), arq


# ── a tela ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _tela(app, logado, tmp_path, monkeypatch, url="/t/pcm/quadro?semana=2026-W41", **cfg):
    monkeypatch.setattr(Q, "hoje", lambda: date(2026, 10, 7))
    banco = tmp_path / "banco_dados.json"
    banco.write_text(json.dumps({"geradoEm": "2026-10-07T12:00:00Z", "semana_ativa": "2026-W41",
                                 "semanas": [_semana()]}), encoding="utf-8")
    app.config.update(NEXUS_PCM_FONTE=str(banco), NEXUS_PCM_TRABALHO=str(tmp_path / "trab"), **cfg)
    r = logado.get(url)
    assert r.status_code == 200
    return r.get_data(as_text=True)


def _agora_menos(horas: float) -> str:
    return (datetime.now(BRT) - timedelta(hours=horas)).isoformat(timespec="seconds")


def _com_fama(**k):
    return {"NEXUS_FAMA_LINHAS_TESTE": LINHAS, "NEXUS_FAMA_CADASTRO_TESTE": CADASTRO,
            "NEXUS_FAMA_GERADO_EM_TESTE": _agora_menos(1), **k}


def test_tela_quadro_com_as_os_da_fama(app, logado, tmp_path, monkeypatch):
    html = _tela(app, logado, tmp_path, monkeypatch, **_com_fama())
    # os quatro cartões da FAMA, só de leitura (sem a janela de reprogramar), com a marca FAMA
    assert html.count('class="q-cartao q-fama') == 4 and html.count('class="q-fama-marca">FAMA<') == 4
    for num in ("FAMA-101", "FAMA-102", "FAMA-103", "FAMA-107"):
        assert num in html
    assert "FAMA-105" not in html and "FAMA-106" not in html
    assert html.count("data-cartao=") == 4                               # os do Fracttal, como antes
    assert TITULO_SIGILOSO in html and "Atrasada" in html and "Em andamento" in html and "Sábado" in html
    # as atrasadas num bloco recolhido da segunda, depois das tarefas oficiais
    seg = html.split('aria-label="Segunda 05/10"', 1)[1].split("</section>", 1)[0]
    assert '<details class="q-fama-atrasadas">' in seg and "<details class=\"q-fama-atrasadas\" open" not in seg
    resumo = seg.split('<details class="q-fama-atrasadas">', 1)[1].split("</summary>", 1)[0]
    assert '<b class="gc-num">1</b>' in resumo and "OS da FAMA atrasada" in resumo
    assert seg.index("data-cartao=") < seg.index("q-fama-atrasadas")
    ter = html.split('aria-label="Terça 06/10"', 1)[1].split("</section>", 1)[0]
    assert ter.index("data-cartao=") < ter.index('class="q-cartao q-fama')    # a FAMA depois das tarefas
    # o aviso das sem usina, com o caminho da ligação; o das sem data prevista
    assert "2 OS da FAMA sem usina ligada" in html and "/t/base/ligacoes" in html and "Base → Ligações" in html
    assert "1 OS da FAMA sem data prevista" in html
    # a etiqueta de repetição numa preventiva só
    assert html.count('class="q-c-frep"') == 1
    dados = json.loads(html.split('id="q-dados">', 1)[1].split("</script>", 1)[0])
    assert [i["os"] for i in dados["itens"] if i.get("frep")] == ["2"]
    assert TITULO_SIGILOSO not in json.dumps(dados, ensure_ascii=False)  # o título não vai para os dados da página
    # a explicação no "!" do título (nada solto na tela), e a conta do topo com as OS da FAMA e a gravação do livro
    topo = html.split('class="q-barra"', 1)[0]
    caixa = topo.split('class="gc-explica"', 1)[1].split("</details>", 1)[0]
    assert "OS da FAMA" in caixa and "Atrasada" in caixa and "FAMA também" in caixa
    assert "4</b> OS da FAMA · livro da FAMA gravado em " in html and "lidas em" not in html
    assert "leitura da FAMA parou" not in html
    # a conta da FAMA à parte na lista do filtro de tipo
    assert '<span>Limpeza de módulos</span><small class="gc-num">0</small><small class="q-ms-fama">+1 FAMA</small>' in html


def test_a_etiqueta_de_repeticao_e_dita_no_rotulo_do_cartao():
    """Revisão de 11/11/2026, item 7: a frase vai no aria-label do cartão (o leitor de tela lê o rótulo do botão), e o
    texto escondido sai (ele escapava da rolagem do quadro e alargava a página a 375 px)."""
    html = (RAIZ / "nexus" / "templates" / "pcm" / "quadro.html").read_text(encoding="utf-8")
    assert "inv-so-leitor" not in html
    assert "{% if k.frep %}. " + REPETICAO + "{% endif %}" in html


def test_tela_a_frase_da_repeticao_no_rotulo_do_cartao(app, logado, tmp_path, monkeypatch):
    html = _tela(app, logado, tmp_path, monkeypatch, **_com_fama())
    assert f'aria-label="Abrir a OS 2: [Grid Co.] - MPM - Cabine. {REPETICAO}"' in html
    assert 'aria-label="Abrir a OS 1: Tarefa"' in html


def test_tela_diz_quando_o_livro_da_fama_foi_gravado_e_o_exclama_diz_quando_ele_e_regravado(app, logado, tmp_path,
                                                                                          monkeypatch):
    """Re-revisão de 11/11/2026, item 4: a hora da tela é a da última gravação do livro (o batimento), e a carga só
    regrava o livro quando a FAMA muda ou uma vez por dia: "lidas em" parecia dizer que a FAMA não era lida havia
    horas. O "!" diz por quê, e o aviso das 26 h continua."""
    gravado = (datetime.now(BRT) - timedelta(hours=5)).replace(second=0, microsecond=0)
    html = _tela(app, logado, tmp_path, monkeypatch,
                 **_com_fama(NEXUS_FAMA_GERADO_EM_TESTE=gravado.isoformat(timespec="seconds")))
    assert f"OS da FAMA · livro da FAMA gravado em {gravado.strftime('%d/%m %H:%M')}<" in html
    assert "lidas em" not in html and "leitura da FAMA parou" not in html          # 5 h: sem o aviso
    caixa = html.split('class="q-barra"', 1)[0].split('class="gc-explica"', 1)[1].split("</details>", 1)[0]
    explica = " ".join(caixa.split())
    assert "só é regravado quando a FAMA muda ou uma vez por dia" in explica and "26 h" in explica


def test_a_conta_do_topo_quebra_a_linha_quando_nao_cabe():
    """Com o "livro da FAMA gravado em" (re-revisão de 11/11/2026, item 4), a conta presa numa linha (nowrap) alargava o
    quadro de 641 a 673 px e com o menu ao lado, e a página rolava de lado (medido no navegador com o filtro do
    responsável: "N de M tarefas · ... · N de M OS da FAMA · livro da FAMA gravado em ..."). Ela quebra só quando não
    cabe."""
    css = (RAIZ / "nexus" / "static" / "pcm.css").read_text(encoding="utf-8")
    assert "nowrap" not in re.search(r"^\.q-conta\{([^}]*)\}", css, re.M).group(1)


def test_tela_avisa_a_leitura_da_fama_parada(app, logado, tmp_path, monkeypatch):
    html = _tela(app, logado, tmp_path, monkeypatch, **_com_fama(NEXUS_FAMA_GERADO_EM_TESTE=_agora_menos(30)))
    texto = " ".join(html.split())
    assert "A leitura da FAMA parou: o que aparece pode estar velho (livro da FAMA gravado em " in texto


def test_tela_quadro_sem_a_fama_fica_como_era(app, logado, tmp_path, monkeypatch):
    html = _tela(app, logado, tmp_path, monkeypatch)
    assert "FAMA" not in html and "q-fama" not in html and html.count("data-cartao=") == 4


def test_tela_quadro_com_a_leitura_da_fama_que_falha(app, logado, tmp_path, monkeypatch):
    def falha(cfg):
        raise RuntimeError("banco fora do ar")
    monkeypatch.setattr(FO, "_linhas_fama", falha)
    html = _tela(app, logado, tmp_path, monkeypatch)
    assert "As OS da FAMA não abriram agora (RuntimeError)" in html and "banco fora do ar" not in html
    assert "q-fama-marca" not in html and html.count("data-cartao=") == 4
