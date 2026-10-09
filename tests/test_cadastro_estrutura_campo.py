"""A estrutura de O&M de 10/2026 no cadastro (Levi, 08/10/2026: "pode adaptar, deixa as vagas preparadas"): a região de
campo com o Supervisor de Campo e o Coordenador (vazio = vaga, nunca erro), o código e a região da equipe, os vínculos
novos, a RESPONSÁVEL O&M com a região no lugar da pessoa (vira vaga, não pessoa), a publicação no banco sem nome em claro
e a carga única do CSV da estrutura (nome exato, sem acento/caixa/espaço, e o resto "fora", sem chutar).
Planilha e CSV sintéticos; pessoas fictícias."""
import io
import json
import re

import openpyxl
import pytest

from nexus import create_app
from nexus.cadastro import banco as B
from nexus.cadastro import estrutura_campo as E
from nexus.cadastro.armazem import ArmazemLocal
from nexus.cadastro.cifra import Cofre, gerar_chave
from nexus.cadastro.esquema import VINCULOS, rotulo_lista
from nexus.cadastro.importar import eh_rotulo_de_regiao, ler_xlsx, montar
from nexus.cadastro.servico import Carga, Servico

from conftest import SENHA_TESTE
from test_cadastro_importar import _xlsx
from test_cadastro_telas import _FormularioDoNavegador

LISTAS = {"status_usina": ["OPERAÇÃO", "A MOBILIZAR"], "uf": ["SP", "CE"], "cargos": ["Técnico O&M"],
          "status_contratacao": ["Ativo", "Desligado"],
          "vinculo": ["Colaborador de campo", "Supervisor", "Gestor de contrato"]}


def _carga():
    """Três equipes (uma com espaço a mais no nome), uma excluída, e quatro pessoas: um técnico, a futura supervisora
    de campo, o coordenador e a gestora de contrato (com o vínculo antigo "Gestor de contrato")."""
    return Carga(entidades={
        "equipes": [{"id": "1", "ordem": 1, "valores": {"nome": "SP Norte 01"}},
                    {"id": "2", "ordem": 2, "valores": {"nome": "CE  Leste 01"}},
                    {"id": "3", "ordem": 3, "valores": {"nome": "PR Oeste 03"}},
                    {"id": "4", "ordem": 4, "valores": {"nome": "MS Sul 01"}}],
        "pessoas": [{"id": "1", "ordem": 1, "valores": {"nome": "Fulano de Tal Tecnico", "vinculo": "Colaborador de campo",
                                                        "cargo": "Técnico O&M", "equipe": "1", "status": "Ativo"}},
                    {"id": "2", "ordem": 2, "valores": {"nome": "Supervisora Exemplo Teste", "vinculo": "Supervisor",
                                                        "email": "supervisora@exemplo.test"}},
                    {"id": "3", "ordem": 3, "valores": {"nome": "Coordenador Exemplo Teste", "vinculo": "Supervisor"}},
                    {"id": "4", "ordem": 4, "valores": {"nome": "Gestora Exemplo Teste", "vinculo": "Gestor de contrato"}}],
        "clientes": [{"id": "1", "ordem": 1, "valores": {"nome": "Thopen"}}],
        "usinas": [{"id": "1", "ordem": 1, "valores": {"nome": "Altair", "status": "OPERAÇÃO", "equipe": "1",
                                                       "cliente": "1", "gestor_contrato": "4", "id_bd": "UFV-1"}},
                   {"id": "2", "ordem": 2, "valores": {"nome": "Crateús", "status": "OPERAÇÃO", "equipe": "2",
                                                       "cliente": "1", "id_bd": "UFV-2"}},
                   {"id": "3", "ordem": 3, "valores": {"nome": "Nova", "status": "A MOBILIZAR", "equipe": "2",
                                                       "cliente": "1", "id_bd": "UFV-3"}},
                   {"id": "4", "ordem": 4, "valores": {"nome": "Sem Região", "status": "OPERAÇÃO", "equipe": "4",
                                                       "cliente": "1", "id_bd": "UFV-4"}}]},
        listas=LISTAS)


@pytest.fixture
def srv(tmp_path):
    s = Servico(ArmazemLocal(tmp_path / "c.json"), Cofre(gerar_chave()))
    s.aplicar_carga(_carga())
    return s


CSV = ("regiao_campo;base_regiao;codigo_equipe;equipe;base_equipe\n"
       "Sudeste 03;São José do Rio Preto/SP;E-31;SP Norte 01;Altair\n"
       "Nordeste 01;Fortaleza/CE;E-05;CE Leste 01;Limoeiro do Norte\n"
       "Sul 01;Maringá/PR;E-25;PR Oeste 03;Mandaguaçu\n"
       "Sul 01;Maringá/PR;E-40;PR Oeste 02;Paranavaí\n")


# ── 1. a dimensão: região de campo, vaga, vínculos ────────────────────────────────────────────────────────────────
def test_vinculos_novos_e_o_rotulo_do_gestor_sem_mudar_o_valor_gravado():
    assert {"Supervisor de Campo", "Coordenador de Campo", "Gestor de contrato", "Supervisor"} <= set(VINCULOS)
    assert rotulo_lista("vinculo", "Gestor de contrato") == "Gestor de contrato (Supervisor PM)"
    assert rotulo_lista("vinculo", "Supervisor") == "Supervisor (legado)"
    assert rotulo_lista("vinculo", "Supervisor de Campo") == "Supervisor de Campo"


def test_regiao_nasce_com_as_vagas_e_a_vaga_nao_e_pendencia(srv):
    r = srv.criar("regioes_campo", {"nome": "Nordeste 02", "base": "Caruaru/PE"}, quem="teste")
    assert r.ok and r.registro.id == "1"
    reg = srv.registro("regioes_campo", "1")
    assert reg.valores["supervisor_campo"] is None and reg.valores["coordenador_campo"] is None
    assert not [p for p in srv.pendencias() if p["entidade"] == "regioes_campo"]       # vaga não é erro
    # a equipe aponta para a região; a pessoa da região tem de existir no cadastro
    assert srv.salvar("equipes", "1", {"regiao_campo": "1", "codigo": "E-31"}, srv.registro("equipes", "1").versao,
                      quem="teste").ok
    assert not srv.salvar("regioes_campo", "1", {"supervisor_campo": "99"}, reg.versao, quem="teste").ok
    # código de equipe é único
    res = srv.salvar("equipes", "2", {"codigo": "e-31"}, srv.registro("equipes", "2").versao, quem="teste")
    assert not res.ok and "Já existe" in res.erros["codigo"]


# ── telas do cadastro ─────────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def app_cad(tmp_path):
    app = create_app({"NEXUS_SECRET_KEY": "k", "NEXUS_SENHA_ADMIN": SENHA_TESTE, "NEXUS_CHAVE_CADASTRO": gerar_chave(),
                      "NEXUS_ARMAZEM_LOCAL": str(tmp_path / "cad.json")})
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    from nexus.cadastro.telas import servico
    with app.app_context():
        s = servico()
        s.aplicar_carga(_carga())
        s.criar("regioes_campo", {"nome": "Nordeste 01", "base": "Fortaleza/CE"}, quem="teste")
        s.criar("regioes_campo", {"nome": "Sudeste 03", "base": "São José do Rio Preto/SP",
                                  "supervisor_campo": "2", "coordenador_campo": "3"}, quem="teste")
        s.salvar("equipes", "2", {"regiao_campo": "1", "codigo": "E-05"}, s.registro("equipes", "2").versao, quem="t")
        s.salvar("equipes", "1", {"regiao_campo": "2", "codigo": "E-31"}, s.registro("equipes", "1").versao, quem="t")
    return app


@pytest.fixture
def cli(app_cad):
    c = app_cad.test_client()
    assert c.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    return c


def _h(r):
    return r.get_data(as_text=True)


def test_menu_e_lista_das_regioes_com_a_vaga_como_vaga(cli):
    html = _h(cli.get("/t/base/regioes-campo"))
    assert "Regiões de campo" in html and "Nordeste 01" in html and "Sudeste 03" in html
    linha = re.search(r"<tr[^>]*>\s*<td class=\"id\">1</td>.*?</tr>", html, re.S).group(0)
    # a vaga aparece como vaga (tracejado azul de informação), não como aviso nem como crítico
    assert linha.count('<span class="cad-vaga">Vaga</span>') == 2 and "cad-chip--critico" not in linha
    assert "cad-com-aviso" not in linha
    linha2 = re.search(r"<tr[^>]*>\s*<td class=\"id\">2</td>.*?</tr>", html, re.S).group(0)
    assert "Supervisora Teste" in linha2 and "Coordenador Teste" in linha2 and "cad-vaga" not in linha2
    # equipes e usinas em operação da região; a nota das equipes com usina em operação sem região
    assert ">1<" in linha and "1 equipe com usina em operação ainda sem região de campo (1 usina em operação)" in html


def test_ficha_da_regiao_mostra_a_vaga_as_equipes_e_salva_a_pessoa(cli, app_cad):
    html = _h(cli.get("/t/base/regiao-campo/1"))
    assert '<option value="" selected>Vaga</option>' in html                         # o vazio da caixa diz "Vaga"
    assert 'class="cad-vaga"' in html and "Equipes da região" in html and "E-05 · CE  Leste 01" in html
    # na caixa, quem é Supervisor de Campo vem primeiro; o rótulo novo do gestor; o "Supervisor" antigo, legado
    assert 'label="Supervisor (legado)"' in html and 'label="Gestor de contrato (Supervisor PM)"' in html
    form = _FormularioDoNavegador(html).campos
    form["supervisor_campo"] = "2"
    assert cli.post("/t/base/regiao-campo/1", data=form).status_code == 302
    with app_cad.app_context():
        from nexus.cadastro.telas import servico
        assert servico().registro("regioes_campo", "1").valores["supervisor_campo"] == "2"
    assert "Supervisora Teste" in _h(cli.get("/t/base/regioes-campo"))


def test_abrir_e_salvar_sem_mexer_nao_muda_a_regiao_nem_a_equipe(cli, app_cad):
    from nexus.cadastro.telas import servico
    with app_cad.app_context():
        antes = {("regioes_campo", "1"): servico().registro("regioes_campo", "1").versao,
                 ("equipes", "2"): servico().registro("equipes", "2").versao}
    for url in ("/t/base/regiao-campo/1", "/t/base/equipe/2"):
        assert cli.post(url, data=_FormularioDoNavegador(_h(cli.get(url))).campos).status_code == 302
    with app_cad.app_context():
        servico()._cache = None
        assert {k: servico().registro(*k).versao for k in antes} == antes


def test_nova_regiao_pela_tela(cli):
    r = cli.post("/t/base/regiao-campo/nova", data={"nome": "Norte-01", "base": "Mãe do Rio/PA"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/t/base/regiao-campo/3")
    assert cli.post("/t/base/regiao-campo/nova", data={"nome": "norte-01"}).status_code == 422     # nome único


def test_equipe_tem_codigo_e_regiao_e_o_filtro_por_regiao(cli):
    html = _h(cli.get("/t/base/equipe/2"))
    assert 'name="codigo"' in html and 'value="E-05"' in html and 'name="regiao_campo"' in html
    assert "Supervisor de Campo" in html and 'class="cad-vaga"' in html               # a região dele está vaga
    assert "SP Norte 01" in _h(cli.get("/t/base/equipes?regiao_campo=2"))
    assert "SP Norte 01" not in _h(cli.get("/t/base/equipes?regiao_campo=1"))
    assert "Região de campo: Sudeste 03" in _h(cli.get("/t/base/usina/1"))


def test_pessoa_mostra_o_vinculo_com_o_rotulo_novo(cli):
    html = _h(cli.get("/t/pessoas/colaboradores"))
    assert "Gestor de contrato (Supervisor PM)" in html and "Supervisor (legado)" in html
    ficha = _h(cli.get("/t/pessoas/colaborador/4"))
    assert '<option value="Gestor de contrato" selected>Gestor de contrato (Supervisor PM)</option>' in ficha


# ── 3. RESPONSÁVEL O&M com a região no lugar da pessoa ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("texto", ["NE · Fortaleza-CE e Teresina-PI", "Sul · Maringá-PR", "SE · Leste de SP",
                                   "SE — Oeste de SP", "Nordeste 02", "Norte-01", "Centro Oeste 01"])
def test_rotulo_de_regiao(texto):
    assert eh_rotulo_de_regiao(texto)


@pytest.mark.parametrize("texto", ["Carla Souza", "Sergio Exemplo", "Nelson Exemplo", "Davi Rocha", "", None,
                                   "Sul América Energia"])
def test_nome_de_pessoa_nao_e_rotulo_de_regiao(texto):
    assert not eh_rotulo_de_regiao(texto)
    assert eh_rotulo_de_regiao("Região Exemplo", regioes=["Região Exemplo"])     # o nome de uma região do cadastro


VAGA_NE = ["Crateús", "CRT100", "OPERAÇÃO", "Thopen", 2, None, None, None, None, "Crateús", None, "Brasil", "CE", None,
           "CE Leste 01", "Nordeste", "Davi Rocha", "NE · Fortaleza-CE e Teresina-PI", None, None, "UFV-20"]
# (o Gestor de Contrato com a região também não vira pessoa: fica o texto, à vista na Qualidade do cadastro)
VAGA_SE = ["Batatais 2", None, "A MOBILIZAR", "Thopen", 1, None, None, None, None, "Batatais", None, "Brasil", "SP",
           None, "SP Leste 01", "Sudeste", "SE · Leste de SP", "SE — Oeste de SP", None, None, "UFV-21"]


def test_regiao_na_responsavel_om_vira_vaga_e_nao_pessoa(tmp_path):
    srv = Servico(ArmazemLocal(tmp_path / "c.json"), Cofre(gerar_chave()))
    p = montar(ler_xlsx(_xlsx(extra=[VAGA_NE, VAGA_SE])), srv, arquivo="BD_Operacoes.xlsx")
    nomes = {x["valores"].get("nome") for x in p.carga.entidades["pessoas"]}
    assert not {n for n in nomes if "·" in str(n) or "Oeste" in str(n)}              # nenhuma pessoa "região"
    us = {u["valores"]["id_bd"]: u["valores"] for u in p.carga.entidades["usinas"]}
    assert us["UFV-20"]["responsavel_om"] is None and us["UFV-20"]["responsavel_om_vaga"] == "NE · Fortaleza-CE e Teresina-PI"
    assert us["UFV-21"]["responsavel_om_vaga"] == "SE — Oeste de SP"
    from nexus.cadastro.tipos import Legado
    assert us["UFV-21"]["gestor_contrato"] == Legado("SE · Leste de SP")
    assert us["UFV-10"]["responsavel_om"] and us["UFV-10"]["responsavel_om_vaga"] is None     # pessoa continua pessoa
    assert p.vagas == [{"rotulo": "NE · Fortaleza-CE e Teresina-PI", "usinas": 1, "tinham_pessoa": 0},
                       {"rotulo": "SE — Oeste de SP", "usinas": 1, "tinham_pessoa": 0}]
    assert any("2 usina(s) com a região no lugar da pessoa" in a for a in p.avisos)
    # aplicada: a usina fica sem responsável, com a vaga anotada; a pessoa que estava sai e a prévia conta isso
    srv.aplicar_carga(p.carga)
    u = next(r for r in srv.registros("usinas") if r.valores.get("id_bd") == "UFV-20")
    assert u.valores["responsavel_om"] is None and u.valores["responsavel_om_vaga"].startswith("NE ·")
    carla = next(r.id for r in srv.registros("pessoas") if r.valores.get("nome") == "Carla Souza")
    srv.salvar("usinas", u.id, {"responsavel_om": carla}, u.versao, quem="teste")
    p2 = montar(ler_xlsx(_xlsx(extra=[VAGA_NE, VAGA_SE])), srv, arquivo="BD_Operacoes.xlsx")
    assert p2.vagas[0] == {"rotulo": "NE · Fortaleza-CE e Teresina-PI", "usinas": 1, "tinham_pessoa": 1}


def test_previa_mostra_as_vagas(cli):
    r = cli.post("/t/base/importar", data={"arquivo": (io.BytesIO(_xlsx(extra=[VAGA_NE])), "BD_Operacoes.xlsx")},
                 content_type="multipart/form-data")
    html = _h(r)
    assert r.status_code == 200 and "Vagas de Supervisor de Campo" in html
    assert "<td>NE · Fortaleza-CE e Teresina-PI</td>" in html
    # e a usina, aplicada, mostra "Vaga · <região>" na coluna Responsável O&amp;M
    token = re.search(r'name="token" value="([^"]+)"', html).group(1)
    assert cli.post("/t/base/importar/aplicar", data={"token": token}).status_code == 302
    assert '<span class="cad-vaga">Vaga · NE · Fortaleza-CE e Teresina-PI</span>' in _h(cli.get("/t/base/registro-mestre"))


def test_importar_nao_apaga_o_codigo_nem_a_regiao_da_equipe(app_cad):
    from nexus.cadastro.telas import servico
    with app_cad.app_context():
        s = servico()
        eq = next(e for e in s.registros("equipes") if e.valores["nome"] == "SP Norte 01")
        s.salvar("equipes", eq.id, {"nome": "SP Leste 01"}, eq.versao, quem="t")      # o nome que a planilha traz
        s.aplicar_carga(montar(ler_xlsx(_xlsx()), s, arquivo="BD.xlsx").carga)
        eq = s.registro("equipes", eq.id)
        assert (eq.valores["codigo"], eq.valores["regiao_campo"]) == ("E-31", "2")


def test_supervisor_digitado_com_a_regiao_nao_vira_legado():
    from nexus.cadastro import importar as I
    abas = ler_xlsx(_xlsx())
    pes = abas["Relação Geral Colaboradores"]
    i = pes.indice("Supervisor")
    pes.linhas[0][i] = I.Celula("NE · Fortaleza-CE e Teresina-PI", None)
    p = montar(abas, None, arquivo="x.xlsx")
    ana = next(x for x in p.carga.entidades["pessoas"] if x["valores"]["nome"] == "Ana Maria Lima")
    assert ana["valores"]["supervisor"] is None


def test_pcm_auxiliar_escreve_a_regiao_da_vaga(srv):
    from nexus.pcm import auxiliar
    u = srv.registro("usinas", "2")
    srv.salvar("usinas", "2", {"responsavel_om_vaga": "NE · Fortaleza-CE e Teresina-PI"}, u.versao, quem="t")
    linha = next(l for l in auxiliar.linhas(srv) if l["OPERAÇÃO"] == "Crateús")
    assert linha["RESPONSÁVEL O&M"] == "NE · Fortaleza-CE e Teresina-PI"


# ── 4. no banco: a aba nova e as colunas novas, pessoa só por ID ──────────────────────────────────────────────────
def _tab(t, aba):
    cab, linhas = t[aba]
    return [dict(zip(cab, l)) for l in linhas]


def test_banco_tem_a_regiao_com_a_vaga_e_nenhum_nome_em_claro(srv):
    srv.criar("regioes_campo", {"nome": "Sudeste 03", "base": "São José do Rio Preto/SP", "supervisor_campo": "2"},
              quem="t")
    srv.criar("regioes_campo", {"nome": "Nordeste 01", "base": "Fortaleza/CE"}, quem="t")
    srv.salvar("equipes", "1", {"regiao_campo": "1", "codigo": "E-31"}, srv.registro("equipes", "1").versao, quem="t")
    u = srv.registro("usinas", "2")
    srv.salvar("usinas", "2", {"responsavel_om_vaga": "NE · Fortaleza-CE e Teresina-PI"}, u.versao, quem="t")
    cofre = srv.cofre
    t = B.montar(srv, cofre)
    regs = {r["regiao_campo_id"]: r for r in _tab(t, "regioes_campo")}
    assert regs[1]["nome"] == "Sudeste 03" and regs[1]["supervisor_campo_id"] == 2
    assert (regs[1]["supervisor_campo_vaga"], regs[1]["coordenador_campo_vaga"]) == ("não", "sim")
    assert (regs[2]["supervisor_campo_vaga"], regs[2]["supervisor_campo_id"]) == ("sim", None)
    assert [regs[1]["ordem"], regs[2]["ordem"]] == [1, 2]
    # as colunas novas das abas que já existiam vão no FIM (depois do sensivel_cifrado)
    cab_eq, cab_us = t["equipes"][0], t["usinas"][0]
    assert cab_eq[-3:] == [B.COL_CIFRA, "codigo", "regiao_campo_id"] and cab_us[-2:] == [B.COL_CIFRA, "responsavel_om_vaga"]
    eq = {e["equipe_id"]: e for e in _tab(t, "equipes")}
    assert (eq[1]["codigo"], eq[1]["regiao_campo_id"], eq[2]["regiao_campo_id"]) == ("E-31", 1, None)
    assert {u["usina_id"]: u["responsavel_om_vaga"] for u in _tab(t, "usinas")}[2] == "NE · Fortaleza-CE e Teresina-PI"
    # o inner join fecha: toda região apontada existe; toda pessoa apontada pela região existe
    assert {e["regiao_campo_id"] for e in eq.values()} - {None} <= set(regs)
    assert {r["supervisor_campo_id"] for r in regs.values()} - {None} <= {p["pessoa_id"] for p in _tab(t, "pessoas")}
    # nenhum nome de pessoa em claro em lugar nenhum; o da supervisora só cifrado na ficha dela
    tudo = json.dumps({k: v for k, v in t.items()}, ensure_ascii=False, default=str)
    for nome in ("Supervisora Exemplo Teste", "Coordenador Exemplo Teste", "Gestora Exemplo Teste", "supervisora@exemplo"):
        assert nome not in tudo, nome
    p2 = next(p for p in _tab(t, "pessoas") if p["pessoa_id"] == 2)
    assert json.loads(cofre.decifrar(p2[B.COL_CIFRA], "banco/pessoas/2"))["nome"] == "Supervisora Exemplo Teste"
    at = _tab(t, "atualizacao")[0]
    assert B.CAB_ATUALIZACAO[-1] == "regioes_campo" and at["regioes_campo"] == 2


# ── 2. a carga única do CSV da estrutura ─────────────────────────────────────────────────────────────────────────
def test_csv_e_conferido():
    assert len(E.ler_csv("﻿" + CSV)) == 4
    with pytest.raises(E.EstruturaErro, match="faltam colunas"):
        E.ler_csv("regiao;equipe\nA;B\n")
    with pytest.raises(E.EstruturaErro, match="equipe repetido"):
        E.ler_csv(CSV + "Sul 01;Maringá/PR;E-41;PR Oeste 03;X\n")
    with pytest.raises(E.EstruturaErro, match="mais de uma base"):
        E.ler_csv(CSV + "Sul 01;Curitiba/PR;E-41;PR Sul 09;X\n")


def test_plano_casa_pelo_nome_e_o_resto_fica_fora_sem_chutar(srv):
    plano = E.planejar(srv, E.ler_csv(CSV))
    assert [(r["nome"], r["id"]) for r in plano.regioes] == [("Sudeste 03", None), ("Nordeste 01", None), ("Sul 01", None)]
    casadas = {c["codigo"]: (c["equipe_id"], c["como"]) for c in plano.casadas}
    assert casadas == {"E-31": ("1", "exato"), "E-05": ("2", "normalizado"), "E-25": ("3", "exato")}
    assert [(f["codigo"], f["motivo"]) for f in plano.fora] == [("E-40", "nenhuma equipe do cadastro com esse nome")]
    # usinas em OPERAÇÃO pela equipe: a "Nova" (a mobilizar) não conta; a da MS Sul 01 fica sem região
    assert plano.usinas_por_regiao == {"Sudeste 03": 1, "Nordeste 01": 1, "Sul 01": 0, E.SEM_REGIAO: 1}
    assert plano.vinculos_faltando == ["Supervisor de Campo", "Coordenador de Campo"]


def test_ambiguo_excluido_e_codigo_de_outra_equipe_ficam_fora(tmp_path):
    srv = Servico(ArmazemLocal(tmp_path / "c.json"), Cofre(gerar_chave()))
    srv.aplicar_carga(Carga(entidades={"equipes": [
        {"id": "1", "ordem": 1, "valores": {"nome": "SP Norte 01"}},
        {"id": "2", "ordem": 2, "valores": {"nome": "SP  NORTE 01 "}},       # o mesmo nome sem espaço/caixa: ambíguo
        {"id": "3", "ordem": 3, "valores": {"nome": "PR Oeste 03", "codigo": "E-05"}},
        {"id": "4", "ordem": 4, "valores": {"nome": "CE Leste 01"}}]}, listas=LISTAS))
    srv.aplicar_carga(Carga(entidades={"equipes": [                           # a 4 sai da planilha: fica excluída
        {"id": "1", "ordem": 1, "valores": {"nome": "SP Norte 01"}},
        {"id": "2", "ordem": 2, "valores": {"nome": "SP  NORTE 01 "}},
        {"id": "3", "ordem": 3, "valores": {"nome": "PR Oeste 03", "codigo": "E-05"}}]}, listas=None))
    csv = ("regiao_campo;base_regiao;codigo_equipe;equipe;base_equipe\n"
           "Sudeste 03;X/SP;E-31;sp norte 01;A\nNordeste 01;Y/CE;E-05;CE Leste 01;B\nSul 01;Z/PR;E-06;PR Oeste 03;C\n")
    plano = E.planejar(srv, E.ler_csv(csv))
    fora = {f["codigo"]: f["motivo"] for f in plano.fora}
    assert fora["E-31"] == "2 equipes do cadastro com esse nome (normalizado)"
    assert fora["E-05"] == "só uma equipe EXCLUÍDA do cadastro tem esse nome"
    # a PR Oeste 03 já tem o código E-05; o CSV dá E-06: casa e TROCA (o relatório mostra a troca)
    assert [(c["codigo"], c["muda"]["codigo"]) for c in plano.casadas] == [("E-06", ("E-05", "E-06"))]


def test_aplicar_grava_confere_e_rodar_de_novo_nao_muda_nada(srv):
    plano = E.planejar(srv, E.ler_csv(CSV))
    antes = E.foto(srv)
    res = E.aplicar(srv, plano)
    assert res["erros"] == [] and res["equipes_gravadas"] == 3 and set(res["regioes"]) == {"Sudeste 03", "Nordeste 01",
                                                                                            "Sul 01"}
    assert E.conferir(srv, plano, antes) == []
    regs = {r.titulo: r for r in srv.registros("regioes_campo")}
    assert [r.titulo for r in srv.registros("regioes_campo")] == ["Sudeste 03", "Nordeste 01", "Sul 01"]   # ordem do CSV
    assert regs["Sul 01"].valores["base"] == "Maringá/PR" and regs["Sul 01"].valores["supervisor_campo"] is None
    eq = srv.registro("equipes", "2")
    assert (eq.valores["codigo"], srv.titulo_de("regioes_campo", eq.valores["regiao_campo"])) == ("E-05", "Nordeste 01")
    assert {"Supervisor de Campo", "Coordenador de Campo"} <= set(srv.listas()["vinculo"])
    assert srv.auditoria(1)[0]["quem"] == E.QUEM
    # o supervisor posto depois fica; a 2ª rodada reaproveita as regiões e não grava nada
    r = regs["Sudeste 03"]
    srv.salvar("regioes_campo", r.id, {"supervisor_campo": "2"}, r.versao, quem="tela")
    foto = E.foto(srv)
    plano2 = E.planejar(srv, E.ler_csv(CSV))
    assert all(x["id"] for x in plano2.regioes) and all(not c["muda"] for c in plano2.casadas)
    assert E.aplicar(srv, plano2)["equipes_gravadas"] == 0
    assert E.foto(srv) == foto


def test_conferir_acusa_usina_mexida(srv):
    plano = E.planejar(srv, E.ler_csv(CSV))
    antes = E.foto(srv)
    E.aplicar(srv, plano)
    u = srv.registro("usinas", "1")
    srv.salvar("usinas", "1", {"nome": "Altair X"}, u.versao, quem="t")
    assert any(p.startswith("usinas mudou") for p in E.conferir(srv, plano, antes))


def test_ferramenta_ensaio_nao_grava(tmp_path, monkeypatch, capsys):
    import ferramentas.importar_estrutura_campo as F
    chave = gerar_chave()
    arq = tmp_path / "c.json"
    s = Servico(ArmazemLocal(arq), Cofre(chave))
    s.aplicar_carga(_carga())
    marca = arq.stat().st_mtime_ns
    (tmp_path / "e.csv").write_text(CSV, encoding="utf-8")
    monkeypatch.setattr(F, "ler_ambiente", lambda: {"NEXUS_CHAVE_CADASTRO": chave, "NEXUS_ARMAZEM_LOCAL": str(arq)})
    monkeypatch.setattr("sys.argv", ["x", str(tmp_path / "e.csv")])
    F.main()
    saida = capsys.readouterr().out
    assert "ENSAIO: nada gravado" in saida and "casaram 3" in saida and "FORA: E-40 PR Oeste 02" in saida
    assert arq.stat().st_mtime_ns == marca and not (tmp_path / "backups").exists()
    monkeypatch.setattr("sys.argv", ["x", str(tmp_path / "e.csv"), "--aplicar"])
    F.main()
    saida = capsys.readouterr().out
    assert "conferido:" in saida and list((tmp_path / "backups").glob("c_*_antes_estrutura_campo.json"))
