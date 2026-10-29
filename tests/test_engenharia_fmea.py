"""Engenharia: emitir FMEA e causa raiz de um ativo da Confiabilidade (Levi, 29/10/2026: "Tem que ter emitir FEMEA
emitir causa raiz do pcm.gridco.com.br use como referência e implemente"). A referência é o módulo Confiabilidade do
painel do PCM (as duas folhas, a biblioteca de modos de falha, o RPN e a matriz GUT); aqui o relatório emitido vai para
o banco (livro nexus_engenharia_relatorios), não para um arquivo do GitHub. Banco falso (tests/pg_falso.py); os nomes
são fictícios."""
import pytest

from nexus.engenharia import biblioteca_falhas as B


def _os(n, t, servico=False, nota=""):
    return {"os": str(n), "t": t, "nota": nota, "d": "20/10 08:00", "tipo": "Corretiva", "st": "Concluída",
            "servico": servico}


# ── a biblioteca de modos de falha (a camada 2 do painel do PCM) ─────────────────────────────────────────────────────
def test_biblioteca_casa_o_padrao_mais_frequente_nas_os_do_ativo():
    """3 strings sem corrente e 1 religamento é um problema de string, não o da OS mais recente (a regra do PCM)."""
    a = {"fam": "Inversor", "crit": "B", "os": [_os(4, "Religamento do inversor"), _os(3, "String 18 sem corrente"),
                                                _os(2, "Recomposição", nota="string com corrente nula"),
                                                _os(1, "String 4 sem corrente")]}
    p = B.pre(a)
    assert p["padrao"]["chave"] == "string_corrente" and p["n_padrao"] == 3
    assert p["fontes"] == "#3, #2, #1" and not p["so_servico"]
    assert p["tipo_falha"] == "eletrica" and p["sev"] == 5 and p["det"] == 4
    assert len(p["padrao"]["pq"]) == 5 and len(p["padrao"]["acoes"]) == 3


def test_biblioteca_sem_padrao_sugere_pela_criticidade_e_nao_preenche_o_resto():
    a = {"fam": "Cabine", "crit": "A", "os": [_os(1, "Troca de módulo quebrado"), _os(2, "Módulo trincado")]}
    p = B.pre(a)
    assert p["padrao"] is None and p["n_padrao"] == 0 and p["fontes"] == ""
    assert p["sev"] == 8 and p["det"] == 6 and p["tipo_falha"] == ""


def test_so_servico_vem_da_confiabilidade_e_nao_puxa_padrao():
    """O serviço registrado como corretiva (limpeza, ensaio) é a mesma marca da Confiabilidade, não um padrão novo."""
    a = {"fam": "Inversor", "crit": "B", "soServico": True,
         "os": [_os(1, "Limpeza do inversor", servico=True), _os(2, "Ensaio de isolamento", servico=True)]}
    p = B.pre(a)
    assert p["so_servico"] and p["padrao"] is None and p["n_servico"] == 2


def test_ocorrencia_vai_da_frequencia_em_30_dias_para_a_escala_de_1_a_10():
    assert [B.ocorrencia(n) for n in range(7)] == [2, 2, 4, 6, 8, 10, 10]


def test_funcao_do_equipamento_pela_familia():
    assert B.funcao("Inversor").startswith("Converter CC") and B.funcao("Desconhecida") == "—"


# ── o livro dos relatórios emitidos (nexus_engenharia_relatorios) ───────────────────────────────────────────────────
import json  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

import requests  # noqa: E402
from pg_falso import ApiPGFalsa  # noqa: E402

from nexus.cadastro.cifra import gerar_chave  # noqa: E402
from nexus.dados import catalogo, explica, livros  # noqa: E402
from nexus.dados.equipamento import equipamento_id  # noqa: E402
from nexus.engenharia import acompanhamento as AC  # noqa: E402
from nexus.engenharia import fmea as F  # noqa: E402

BRT = timezone(timedelta(hours=-3))
ANA = AC_ANA = {"email": "ana.lima@gridco.com.br", "nome": "Ana Lima"}
ATIVO = {"cod": "IBI200-INVR1.3", "nome": "Inversor 1.3", "usina": "Usina Teste 1", "cliente": "Cliente X",
         "usina_id": 1, "ligada_por": "de-para do Fracttal", "fam": "Inversor", "crit": "B", "circuito": "Bloco 1",
         "nivel": "critico", "nFalha": 4, "n7": 2, "n30": 5, "p90": 2, "mtbf": 310.0, "mttr": 6.5, "disp": 0.91,
         "soServico": False,
         "os": [_os(9, "String 18 sem corrente"), _os(8, "String 18 sem corrente"), _os(7, "Limpeza", servico=True)]}
FMEA_OK = {"modo_1": "String PV18 com corrente nula", "efeito_1": "Perda de geração", "causa_1": "Conector MC4",
           "sev": "5", "det": "4", "elaboracao": "Ana Lima", "acao_1": "Trocar conectores", "acao_prazo_1": "2026-11-10"}
RCA_OK = {"descricao": "A string zerou três vezes", "pq_1": "Zerou", "pq_5": "Sem termografia",
          "causa_raiz": "O plano não pede termografia", "tipo_falha": "eletrica", "g_1": "5", "u_1": "4", "t_1": "3",
          "acao_1": "Incluir termografia na MPT"}


@pytest.fixture
def banco(app):
    app.config.update(GRIDCO_DB_API="http://pg.falso", NEXUS_CHAVE_CADASTRO=gerar_chave(),
                      NEXUS_PESSOA_HMAC="hmac-teste", GRIDCO_SQL_TOKEN="tk")
    api = ApiPGFalsa()
    app.extensions["nexus_dados_sessao"] = api
    F.limpar()
    AC.limpar()
    with app.app_context():
        yield api
    F.limpar()
    AC.limpar()
    app.extensions.pop("nexus_dados_sessao", None)


def _rels():
    return F.relatorios(F.ler(forcar=True)["linhas"])


def test_catalogo_registra_o_livro_e_o_fato():
    l = catalogo.LIVRO_POR_NOME[F.LIVRO]
    assert l.abas == (F.ABA,) and l.so_cresce and not l.no_banco and catalogo.aba_segue_a_regra(F.ABA)
    f = catalogo.POR_ID["relatorio_falha"]
    assert f.area == "engenharia" and f.tipo == "transacao" and f.chave == ("id",)
    assert f.fontes == (f"{F.LIVRO} · {F.ABA}",)
    assert {m.coluna for m in f.medidas} == {"falhas_30d_qtd", "ocorrencia_nivel", "severidade_nivel",
                                            "deteccao_nivel", "rpn_pts"}
    assert "relatorio_falha" in explica.RESUMO and "relatorio_falha" in explica.PARA_QUE


def test_emitir_fmea_numera_grava_cifrado_e_le_de_volta(banco):
    r = F.emitir("fmea", ATIVO, FMEA_OK, ANA, pode=True, acompanhamento_id="ac1")
    ano = datetime.now(BRT).year
    assert r["numero"] == f"FMEA-{ano}-0001" and r["revisao"] == 0
    (l,) = banco.linhas(F.LIVRO, F.ABA)
    assert list(l) == list(F.CAB) and l["tipo"] == "fmea" and l["codigo_ativo"] == "IBI200-INVR1.3"
    assert l["equipamento_id"] == equipamento_id("IBI200-INVR1.3") and l["usina_id"] == 1
    assert l["acompanhamento_id"] == "ac1" and l["pessoa_hmac"] and l["padrao_biblioteca"] == "string_corrente"
    # a ocorrência é medida (4 falhas em 30 dias = 8) e o RPN é OCC x SEV x DET
    assert (l["falhas_30d_qtd"], l["ocorrencia_nivel"], l["severidade_nivel"], l["deteccao_nivel"], l["rpn_pts"]) == \
        (4, 8, 5, 4, 160)
    # a API do banco tem leitura aberta: nem quem, nem o texto da análise em claro
    claro = json.dumps(l, ensure_ascii=False, default=str).lower()
    assert "ana lima" not in claro and ANA["email"] not in claro and "conector" not in claro
    (rel,) = _rels()
    u = rel["ultima"]
    assert rel["numero"] == r["numero"] and u["autor"] == "Ana Lima" and u["rev_txt"] == "R00"
    assert u["campos"]["modo_1"] == "String PV18 com corrente nula" and u["campos"]["acao_prazo_1"] == "2026-11-10"
    assert u["ativo"]["nome"] == "Inversor 1.3" and [o["os"] for o in u["os"]] == ["9", "8", "7"]
    assert u["rpn"] == 160 and u["tipo_txt"] == "FMEA"


def test_numeracao_por_tipo_e_por_ano(banco):
    ano = datetime.now(BRT).year
    # um FMEA do ano passado no livro: o número do ano novo recomeça em 0001
    velho = {"id": "velho", "numero": f"FMEA-{ano - 1}-0007", "tipo": "fmea", "revisao": 0}
    banco.workbooks[F.LIVRO] = {"key": F.LIVRO}
    banco._id(F.LIVRO, F.ABA)["linhas"] = [{"headers": list(F.CAB), "values": [velho.get(c) for c in F.CAB]}]
    a = F.emitir("fmea", ATIVO, FMEA_OK, ANA, pode=True)
    b = F.emitir("fmea", ATIVO, FMEA_OK, ANA, pode=True)
    c = F.emitir("rca", ATIVO, RCA_OK, ANA, pode=True)
    assert (a["numero"], b["numero"], c["numero"]) == (f"FMEA-{ano}-0001", f"FMEA-{ano}-0002", f"RCA-{ano}-0001")
    assert c["rpn_pts"] is None and c["tipo_falha"] == "eletrica"


def test_nova_revisao_mantem_o_numero_e_sobe_a_revisao(banco):
    a = F.emitir("fmea", ATIVO, FMEA_OK, ANA, pode=True)
    b = F.emitir("fmea", ATIVO, dict(FMEA_OK, sev="7"), ANA, pode=True, de=a["numero"])
    assert b["numero"] == a["numero"] and b["revisao"] == 1 and b["rpn_pts"] == 8 * 7 * 4
    (rel,) = _rels()
    assert [x["rev_txt"] for x in rel["revisoes"]] == ["R00", "R01"] and rel["ultima"]["revisao"] == 1
    assert F.por_ativo(_rels())["IBI200-INVR1.3"][0]["numero"] == a["numero"]


@pytest.mark.parametrize("tipo, campos, usuario, pode, de, msg", [
    ("fmea", FMEA_OK, ANA, False, None, "Engenharia"),
    ("fmea", FMEA_OK, None, True, None, "login"),
    ("xyz", FMEA_OK, ANA, True, None, "tipo"),
    ("fmea", dict(FMEA_OK, modo_1=" "), ANA, True, None, "modo de falha"),
    ("rca", dict(RCA_OK, causa_raiz=""), ANA, True, None, "causa raiz"),
    ("fmea", dict(FMEA_OK, sev="11"), ANA, True, None, "Severidade"),
    ("rca", dict(RCA_OK, g_1="9"), ANA, True, None, "1 a 5"),
    ("rca", dict(RCA_OK, tipo_falha="magia"), ANA, True, None, "Tipo de falha"),
    ("fmea", dict(FMEA_OK, acao_prazo_1="10/11/2026"), ANA, True, None, "data"),
    ("fmea", dict(FMEA_OK, modo_1="x" * 301), ANA, True, None, "300"),
    ("fmea", FMEA_OK, ANA, True, "FMEA-2026-0099", "não achei o relatório"),
])
def test_recusas_nao_gravam(banco, tipo, campos, usuario, pode, de, msg):
    with pytest.raises(F.Recusada, match=msg):
        F.emitir(tipo, ATIVO, campos, usuario, pode=pode, de=de)
    assert banco.linhas(F.LIVRO, F.ABA) == []


def test_revisao_de_outro_tipo_ou_outro_ativo_e_recusada(banco):
    a = F.emitir("fmea", ATIVO, FMEA_OK, ANA, pode=True)
    with pytest.raises(F.Recusada, match="FMEA"):
        F.emitir("rca", ATIVO, RCA_OK, ANA, pode=True, de=a["numero"])
    with pytest.raises(F.Recusada, match="outro ativo"):
        F.emitir("fmea", dict(ATIVO, cod="OUTRO-INVR9"), FMEA_OK, ANA, pode=True, de=a["numero"])


def test_campo_que_a_folha_nao_tem_fica_fora(banco):
    F.emitir("fmea", ATIVO, dict(FMEA_OK, injetado="<script>"), ANA, pode=True)
    (rel,) = _rels()
    assert "injetado" not in rel["ultima"]["campos"]


def test_banco_fora_nao_grava_e_diz(banco, monkeypatch):
    monkeypatch.setattr(livros, "publicar", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("fora")))
    with pytest.raises(requests.ConnectionError):
        F.emitir("fmea", ATIVO, FMEA_OK, ANA, pode=True)
    assert banco.linhas(F.LIVRO, F.ABA) == []


# ── as telas: a folha, a emissão, o relatório, a lista e a gaveta ────────────────────────────────────────────────────
# a mesma Confiabilidade de prova do acompanhamento: sinal em IBI200-INVR1.3 (crítico, 4 falhas em 30 dias, aberto com
# Ana Lima), IBI200-TRK07 e IBI200-INV02; quem entra é do setor Engenharia
from test_engenharia_acompanhamento import SAME, _aid_de, _como, tela  # noqa: E402,F401

URL = "/t/engenharia/fmea"
FORM = {"tipo": "fmea", "cod": "IBI200-INVR1.3", "modo_1": "Inversor desliga sozinho", "efeito_1": "Geração a zero",
        "causa_1": "Proteção de isolamento", "sev": "7", "det": "5", "acao_1": "Medir o isolamento CC"}


def _emitir(cliente, **mudar):
    return cliente.post(f"{URL}/emitir", data=dict(FORM, **mudar), headers=SAME)


def test_folha_nova_do_fmea_traz_o_medido_e_as_sugestoes(tela, cliente):
    html = _como(cliente, AC_ANA).get(f"{URL}/novo?tipo=fmea&ativo=IBI200-INVR1.3").get_data(as_text=True)
    assert "FMEA: análise de modos de falha e efeitos" in html and "IBI200-INVR1.3" in html
    assert 'name="modo_1"' in html and 'name="sev"' in html and "Emitir" in html and "Imprimir / PDF" in html
    # a ocorrência é medida: 4 falhas em 30 dias = 8 na escala; quem elabora vem do login
    assert 'data-occ="8"' in html
    # quem elabora vem do login, sem o verde nem o selo da biblioteca (ela não sugeriu o nome)
    assert '<input class="eg-fo-in" name="elaboracao" value="Ana Lima"' in html
    assert "a numerar na emissão" in html


def test_folha_da_causa_raiz_tem_os_porques_e_a_matriz_gut(tela, cliente):
    html = _como(cliente, AC_ANA).get(f"{URL}/novo?tipo=rca&ativo=IBI200-INVR1.3").get_data(as_text=True)
    assert "Análise de causa raiz" in html and "Os cinco porquês" in html and 'name="pq_5"' in html
    assert 'name="causa_raiz"' in html and 'name="g_1"' in html and "Elétrica" in html


def test_emitir_pela_tela_grava_e_abre_o_relatorio(tela, cliente):
    _como(cliente, AC_ANA)
    r = _emitir(cliente)
    ano = datetime.now(BRT).year
    assert r.status_code == 303 and r.headers["Location"].endswith(f"{URL}/FMEA-{ano}-0001?emitido=1")
    (l,) = tela.linhas(F.LIVRO, F.ABA)
    assert l["acompanhamento_id"] == _aid_de("IBI200-INVR1.3") and l["rpn_pts"] == 8 * 7 * 5
    html = cliente.get(f"{URL}/FMEA-{ano}-0001?emitido=1").get_data(as_text=True)
    assert f"FMEA-{ano}-0001" in html and "R00" in html and "Inversor desliga sozinho" in html
    assert "Ana Lima" in html and "Nova revisão" in html and "280" in html and "emitido" in html.lower()


def test_recusa_volta_a_folha_com_o_que_foi_digitado(tela, cliente):
    r = _emitir(_como(cliente, AC_ANA), modo_1="")
    html = r.get_data(as_text=True)
    assert r.status_code == 400 and "modo de falha" in html and 'value="Geração a zero"' in html
    assert tela.linhas(F.LIVRO, F.ABA) == []


def test_nova_revisao_pela_tela(tela, cliente):
    _como(cliente, AC_ANA)
    _emitir(cliente)
    ano = datetime.now(BRT).year
    num = f"FMEA-{ano}-0001"
    html = cliente.get(f"{URL}/novo?de={num}").get_data(as_text=True)
    assert 'value="Inversor desliga sozinho"' in html and f'name="de" value="{num}"' in html
    r = _emitir(cliente, de=num, sev="9")
    assert r.status_code == 303 and r.headers["Location"].endswith(f"{URL}/{num}?emitido=1")
    ver = cliente.get(f"{URL}/{num}").get_data(as_text=True)
    assert "R01" in ver and f"{URL}/{num}?rev=0" in ver
    assert "R00" in cliente.get(f"{URL}/{num}?rev=0").get_data(as_text=True)


def test_lista_e_gaveta_mostram_os_relatorios(tela, cliente):
    _como(cliente, AC_ANA)
    _emitir(cliente)
    _emitir(cliente, tipo="rca", causa_raiz="Isolamento CC degradado", tipo_falha="eletrica")
    ano = datetime.now(BRT).year
    lista = cliente.get(URL).get_data(as_text=True)
    assert f"FMEA-{ano}-0001" in lista and f"RCA-{ano}-0001" in lista and "IBI200-INVR1.3" in lista
    assert "Causa raiz" in lista and "280" in lista
    so_rca = cliente.get(f"{URL}?tipo=rca").get_data(as_text=True)
    assert f"RCA-{ano}-0001" in so_rca and f"FMEA-{ano}-0001" not in so_rca
    gav = cliente.get("/t/engenharia/confiabilidade?aba=acompanhamento").get_data(as_text=True)
    assert "Emitir FMEA" in gav and "Emitir causa raiz" in gav and f"FMEA-{ano}-0001" in gav


def test_quem_nao_e_da_engenharia_le_e_nao_emite(tela, cliente, monkeypatch):
    from nexus.auth import setor_telas as ST
    _como(cliente, AC_ANA)
    _emitir(cliente)
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": {"engenharia/fmea", "engenharia/confiabilidade"},
                                               "setor": {"id": 2, "nome": "Performance"}, "erro": ""})
    ano = datetime.now(BRT).year
    assert cliente.get(f"{URL}/novo?tipo=fmea&ativo=IBI200-INVR1.3").status_code == 403
    assert _emitir(cliente).status_code == 403
    ver = cliente.get(f"{URL}/FMEA-{ano}-0001").get_data(as_text=True)
    assert "Inversor desliga sozinho" in ver and "Nova revisão" not in ver
    gav = cliente.get("/t/engenharia/confiabilidade?aba=acompanhamento").get_data(as_text=True)
    assert "Emitir FMEA" not in gav and f"FMEA-{ano}-0001" in gav
    assert len(tela.linhas(F.LIVRO, F.ABA)) == 1


def test_de_outro_site_nao_emite(tela, cliente):
    r = _como(cliente, AC_ANA).post(f"{URL}/emitir", data=FORM, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403 and tela.linhas(F.LIVRO, F.ABA) == []


def test_ativo_fora_da_confiabilidade_e_relatorio_que_nao_existe(tela, cliente):
    _como(cliente, AC_ANA)
    r = cliente.get(f"{URL}/novo?tipo=fmea&ativo=NAO-EXISTE-1")
    assert r.status_code == 404 and "não está na Confiabilidade" in r.get_data(as_text=True)
    assert cliente.get(f"{URL}/FMEA-2026-9999").status_code == 404


def test_a_engenharia_emite_sem_marcar_a_tela_em_acessos(app, monkeypatch):
    """Com o portão por setor ligado (o servidor), quem é da Engenharia só passa nas telas do setor: sem a tela FMEA ser
    dele, o Emitir da gaveta da Confiabilidade voltava 403 (o caso do Pegar da Mesa, 18/10/2026)."""
    from nexus.auth import setor_telas as ST
    monkeypatch.setattr(ST, "escolhas_de_dono", lambda: {})          # sem escolha na Central: vale o do código
    with app.app_context():
        telas = ST.das_do_setor({"id": 1, "nome": "Engenharia"})
        for caminho in ("/t/engenharia/fmea", "/t/engenharia/fmea/novo", "/t/engenharia/fmea/emitir",
                        "/t/engenharia/fmea/FMEA-2026-0001"):
            assert ST.pode(caminho, telas), caminho
        assert not ST.pode("/t/engenharia/fmea", ST.das_do_setor({"id": 3, "nome": "Performance"}))

