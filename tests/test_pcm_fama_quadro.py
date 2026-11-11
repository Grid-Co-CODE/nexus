"""As OS da FAMA no Quadro da semana (Levi, 11/11/2026: o cliente cria a OS na FAMA e ela aparece para o programador; "a
ideia é não ficarmos criando e editando e sim acompanhando"). Fase 1, SOMBRA: o Quadro mostra, nada muda na programação.

O que estes testes seguram: a porta única (`fama_os._linhas_fama`: sem o leitor da parte A, nenhuma linha); quais OS entram
na semana (as abertas no dia da previsão; a aberta de antes da segunda vai na segunda, "atrasada"; em mobilização e em
execução, "em andamento"; as outras situações e a previsão depois do domingo, não); a OS sem usina ligada vira aviso, não
cartão; a sem data prevista também; os filtros do Quadro valem para elas; a etiqueta de repetição só na preventiva do
Fracttal da usina com preventiva da FAMA na semana; a semana que acabou fica sem a FAMA; e a tela (cartão só de leitura,
o aviso, o "!", a contagem das tarefas que não muda). A FAMA e o banco são de mentira: nenhum teste vai à rede."""
import json
import re
from datetime import date
from pathlib import Path

from nexus.pcm import fama_os as FO
from nexus.pcm import fama_quadro as FQ
from nexus.pcm import quadro as Q
from test_pcm_quadro import _r

TITULO_SIGILOSO = "Inversor parado no bloco norte"     # o título vem cifrado no livro: só a tela o mostra


def _semana():
    """A W41 (segunda 05/10 a domingo 11/10/2026): duas usinas do Fracttal (a 1 com corretiva e MPM, a 2 com MPM)."""
    rows = [_r(1, "Segunda-feira", "08:00"),
            _r(2, "Terça-feira", "09:00", tarefa="[Grid Co.] - MPM - Cabine", tipo="MPM"),
            _r(3, "Quarta-feira", "10:00", tarefa="[Grid Co.] - MPM - Trafo", tipo="MPM", equipe="RN Sul 01",
               usina="Cliente B - Usina 2 - RN", cliente="Cliente B", responsavel="Pessoa B"),
            _r(4, "Quinta-feira", "11:00")]
    return {"week": "2026-W41", "label": "Semana 41", "rows": rows, "pendentes": [],
            "dates": {"seg": "05/10", "ter": "06/10", "qua": "07/10", "qui": "08/10", "sex": "09/10"}}


CADASTRO = {10: {"nomes": ["Cliente A - Usina 1 - SP"], "nome": "Usina 1", "cliente": "Cliente A", "equipe": "SP Leste 02"},
            20: {"nomes": ["Cliente B - Usina 2 - RN"], "nome": "Usina 2", "cliente": "Cliente B", "equipe": "RN Sul 01"},
            30: {"nomes": ["Cliente C - Usina 3 - MG"], "nome": "Usina 3", "cliente": "Cliente C", "equipe": "MG Sul 01"}}


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


def _fama(hoje=date(2026, 10, 7), linhas=LINHAS):
    return FQ.da_semana(linhas, _semana(), CADASTRO, hoje)


def _quadro(filtros=None, hoje=date(2026, 10, 7)):
    sem, fama = _semana(), _fama(hoje)
    sem = FQ.marcar_repeticao(sem, fama)
    q = Q.montar(sem, [], filtros or {}, outras_opcoes=fama["linhas"])
    FQ.no_quadro(q, sem, fama, filtros or {})
    return q


def _cartoes_fama(q):
    return {c["id"]: [f["num"] for f in c.get("fama") or []] for c in q["colunas"] if c.get("fama")}


# ── a porta única ────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_porta_unica_no_teste_devolve_copias_das_linhas_dadas():
    """No teste a porta não vai ao banco: devolve cópias das linhas da configuração. A leitura do livro de verdade (a parte
    A) está em tests/test_pcm_fama_juncao.py."""
    assert FO._linhas_fama({"TESTING": True}) == []
    linha = {"fama_os_id": 1}
    lidas = FO._linhas_fama({"TESTING": True, "NEXUS_FAMA_LINHAS_TESTE": [linha]})
    assert lidas == [linha] and lidas[0] is not linha                 # uma cópia: a tela não muda o dado de ninguém


def test_vocabulario_da_fama():
    assert [FO.situacao(s) for s in ("created", "Planned", "paused", "under mobilization", "Under Execution",
                                      "under review", "executed", "approved", "closed", "", None)] == \
        ["aberta"] * 3 + ["andamento"] * 2 + [None] * 6
    assert FO.numero(101) == "FAMA-101" and FO.numero("101.0") == "FAMA-101"
    assert FO.data_de(20261006) == date(2026, 10, 6) and FO.data_de("2026-10-06") == date(2026, 10, 6)
    assert FO.data_de(None) is None and FO.data_de("") is None and FO.data_de(20261399) is None


def test_usinas_do_cadastro_pelo_de_para_do_fracttal():
    usinas = [{"usina_id": "10", "nome": "Usina 1", "cliente_id": 1, "equipe_id": 5},
              {"usina_id": 11, "nome": "Usina velha", "excluido": "Sim"}]
    de_para = [{"usina_id": 10, "sistema": FO.SISTEMA_FRACTTAL, "chave_externa": "(sem Classificação 1) Usina 1"},
               {"usina_id": 10, "sistema": FO.SISTEMA_FRACTTAL, "chave_externa": "Cliente A -  Usina 1 - SP"},
               {"usina_id": 10, "sistema": "Outro sistema", "chave_externa": "U1"},
               {"usina_id": 11, "sistema": FO.SISTEMA_FRACTTAL, "chave_externa": "Usina velha"}]
    cad = FO.usinas_do_cadastro(usinas, de_para, [{"equipe_id": 5, "nome": "SP Leste 02"}],
                                [{"cliente_id": 1, "nome": "Cliente A"}])
    assert cad == {10: {"nomes": ["Cliente A - Usina 1 - SP", "(sem Classificação 1) Usina 1"], "nome": "Usina 1",
                        "cliente": "Cliente A", "equipe": "SP Leste 02"}}


# ── as OS da semana ──────────────────────────────────────────────────────────────────────────────────────────────
def test_entram_as_abertas_no_dia_da_previsao_e_a_atrasada_na_segunda():
    q = _quadro()
    assert _cartoes_fama(q) == {"seg": ["FAMA-102"], "ter": ["FAMA-101"], "qui": ["FAMA-103"], "sab": ["FAMA-107"]}
    # o sábado não tinha tarefa do Fracttal: a coluna aparece pela FAMA, na ordem dos dias
    assert [c["id"] for c in q["colunas"]] == ["seg", "ter", "qua", "qui", "sab"]
    sab = q["colunas"][-1]
    assert (sab["nome"], sab["data"], sab["n"], sab["cartoes"]) == ("Sábado", "10/10", 0, [])
    f = {f["num"]: f for c in q["colunas"] for f in c.get("fama") or []}
    assert (f["FAMA-102"]["marca"], f["FAMA-102"]["marcat"], f["FAMA-102"]["prev"]) == ("Atrasada", "critico", "28/09")
    assert (f["FAMA-103"]["marca"], f["FAMA-103"]["st"]) == ("Em andamento", "Em execução")
    assert f["FAMA-101"]["marca"] == "" and f["FAMA-107"]["st"] == "Pausada"
    # a OS sem usina ligada (ou com a usina fora do cadastro) e a sem data prevista viram aviso, não cartão
    assert (q["fama"]["sem_usina"], q["fama"]["sem_data"], q["fama"]["total_semana"]) == (2, 1, 4)


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
    assert _cartoes_fama(_quadro({"resp": "Pessoa A"})) == {"seg": ["FAMA-102"], "ter": ["FAMA-101"]}
    assert _cartoes_fama(_quadro({"tipo": "Corretiva"})) == {"ter": ["FAMA-101"]}
    assert _cartoes_fama(_quadro({"estado": "Em progresso"})) == {"qui": ["FAMA-103"]}
    assert _cartoes_fama(_quadro({"estado": "Pausada|Não iniciada"})) == {"seg": ["FAMA-102"], "ter": ["FAMA-101"],
                                                                          "sab": ["FAMA-107"]}
    assert _cartoes_fama(_quadro({"turno": "Manhã"})) == {}             # a FAMA não tem hora: "Sem horário"
    assert _cartoes_fama(_quadro({"q": "inversor parado"})) == {"ter": ["FAMA-101"]}
    assert _cartoes_fama(_quadro({"q": "fama-107"})) == {"sab": ["FAMA-107"]}
    q = _quadro({"equipe": "RN Sul 01"})
    assert (q["fama"]["total"], q["fama"]["total_semana"]) == (1, 4)
    # os tipos da FAMA entram na lista do filtro, contados; a corretiva soma com a do Fracttal
    tipos = dict(_quadro()["opcoes"]["tipo"])
    assert tipos["Limpeza de módulos"] == 1 and tipos["Controle de vegetação"] == 1 and tipos["Preventiva/Preditiva"] == 1
    assert tipos["Corretiva"] == 3


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


def test_a_semana_que_acabou_fica_sem_a_fama():
    """A situação da FAMA é a de agora: aplicada a uma semana passada, ela diria o que não aconteceu naquela semana."""
    fama = _fama(hoje=date(2026, 10, 12))
    assert not fama["ativa"] and fama["linhas"] == []
    assert _cartoes_fama(_quadro(hoje=date(2026, 10, 12))) == {}
    # o domingo ainda é da semana
    assert _fama(hoje=date(2026, 10, 11))["ativa"]


# ── a tela ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _tela(app, logado, tmp_path, monkeypatch, **cfg):
    monkeypatch.setattr(Q, "hoje", lambda: date(2026, 10, 7))
    banco = tmp_path / "banco_dados.json"
    banco.write_text(json.dumps({"geradoEm": "2026-10-07T12:00:00Z", "semana_ativa": "2026-W41",
                                 "semanas": [_semana()]}), encoding="utf-8")
    app.config.update(NEXUS_PCM_FONTE=str(banco), NEXUS_PCM_TRABALHO=str(tmp_path / "trab"), **cfg)
    r = logado.get("/t/pcm/quadro?semana=2026-W41")
    assert r.status_code == 200
    return r.get_data(as_text=True)


def test_tela_quadro_com_as_os_da_fama(app, logado, tmp_path, monkeypatch):
    html = _tela(app, logado, tmp_path, monkeypatch, NEXUS_FAMA_LINHAS_TESTE=LINHAS, NEXUS_FAMA_CADASTRO_TESTE=CADASTRO)
    # os quatro cartões da FAMA, só de leitura (sem a janela de reprogramar), com a marca FAMA
    assert html.count('class="q-cartao q-fama') == 4 and html.count('class="q-fama-marca">FAMA<') == 4
    for num in ("FAMA-101", "FAMA-102", "FAMA-103", "FAMA-107"):
        assert num in html
    assert "FAMA-105" not in html and "FAMA-106" not in html
    assert html.count("data-cartao=") == 4                               # os do Fracttal, como antes
    assert TITULO_SIGILOSO in html and "Atrasada" in html and "Em andamento" in html and "Sábado" in html
    # o aviso das sem usina, com o caminho da ligação; o das sem data prevista
    assert "2 OS da FAMA sem usina ligada" in html and "/t/base/ligacoes" in html and "Base → Ligações" in html
    assert "1 OS da FAMA sem data prevista" in html
    # a etiqueta de repetição numa preventiva só, com a frase inteira para quem lê pelo leitor de tela
    assert html.count('class="q-c-frep"') == 1
    assert "a FAMA também tem preventiva desta usina nesta semana" in html
    dados = json.loads(html.split('id="q-dados">', 1)[1].split("</script>", 1)[0])
    assert [i["os"] for i in dados["itens"] if i.get("frep")] == ["2"]
    assert TITULO_SIGILOSO not in json.dumps(dados, ensure_ascii=False)  # o título não vai para os dados da página
    # a explicação no "!" do título (nada solto na tela), e a conta do topo com as OS da FAMA
    topo = html.split('class="q-barra"', 1)[0]
    caixa = topo.split('class="gc-explica"', 1)[1].split("</details>", 1)[0]
    assert "OS da FAMA" in caixa and "Atrasada" in caixa and "FAMA também" in caixa
    assert "4</b> OS da FAMA" in html


def test_a_etiqueta_de_repeticao_prende_o_texto_do_leitor_de_tela():
    """Prova no navegador de 11/11/2026, a 375 px: o texto do leitor de tela da etiqueta "FAMA também" (`inv-so-leitor`,
    absoluto) escapava da rolagem do quadro, porque nenhum ancestral do cartão é posicionado, e alargava a página de 375
    para 708 px. A etiqueta é o bloco que o prende."""
    css = (Path(__file__).resolve().parents[1] / "nexus" / "static" / "pcm.css").read_text(encoding="utf-8")
    regra = re.search(r"\.q-c-frep\{([^}]*)\}", css)
    assert regra and "position:relative" in regra.group(1)


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
