"""Rondas, pedido do Levi de 08/10/2026 (Nexus > Campo App > Rondas): a tabela de registros sem Região, Início e Fim,
com a Duração ao lado da Data e o início e o fim no mouse; o botão Fotos na tabela; o indicador "Nunca tiveram ronda";
a aba "Sem ronda" no lugar da Cobertura; a Sujidade pela criticidade, com Status e Tipo; o Quem ronda com as pendentes
de cada técnico e em blocos; e o Painel por região, equipe, cliente e supervisor (com a estrutura de O&M de 10/2026, o
supervisor virou a região de campo e o gestor de contrato). Banco falso (pg_falso)."""
import json
import pathlib
import re

from test_campo_visao import CHAVE_CADASTRO, _aba, _dia, _fech, _ronda, banco  # noqa: F401  (fixture)

from nexus.cadastro.cifra import Cofre
from nexus.campo import aprovacao, ronda_checklist, visao


def _cabecalho(html, marca):
    """Os títulos das colunas da 1ª tabela depois de `marca`, como a pessoa lê: sem o hífen invisível (&shy;) que deixa
    "Sombreamento" quebrar linha para a tabela da Sujidade caber a 1366 px."""
    trecho = html.split(marca, 1)[1].split("</thead>", 1)[0]
    return [re.sub(r"<[^>]+>", "", t).replace("&shy;", "").strip() for t in re.findall(r"<th[^>]*>(.*?)</th>", trecho)]


def _rondas_do_banco(banco, *extras):
    """As três rondas do banco falso (Altair há 1 e 3 dias, Brodowski há 2 dias sem OS) e mais as pedidas."""
    _aba(banco, "rondas_app_campo", "OS de ronda", [
        _ronda(_dia(1), Falhas="ronda longa pendente; item sem foto de evidência"),
        _ronda(_dia(3), Falhas="ronda longa pendente"),
        _ronda(_dia(2), usina="Thopen - Brodowski 1 - SP", ativo="THPN-BWK100", OS=None,
               **{"Situação da OS": "Não criada — Fracttal: Conecte"}), *extras])
    visao.limpar()


def _sem_fracttal(monkeypatch, respostas=None):
    """A aba Sujidade nunca lê o Fracttal no teste: respostas prontas e as releituras desligadas."""
    monkeypatch.setattr(ronda_checklist, "respostas", lambda: respostas or {})
    monkeypatch.setattr(ronda_checklist, "pedir_releitura", lambda app=None: None)
    monkeypatch.setattr(ronda_checklist, "estado", lambda: {"lendo": False, "erro": "", "lidas": True, "fila": True})
    monkeypatch.setattr(aprovacao, "_pedir_releitura", lambda: None)


# ── 1, 2 e 3: Registros sem Região, Início e Fim; Duração ao lado da Data, com o início e o fim no mouse ───────────
def test_registros_sem_regiao_inicio_fim_e_a_duracao_ao_lado_da_data(banco, logado):
    html = logado.get("/t/campo/rondas").get_data(as_text=True)
    assert _cabecalho(html, "cn-tab--rondas") == ["Data", "Duração", "Técnico", "Usina", "Equipe", "Tipo", "Qualidade",
                                                  "Veredito", "Pendências", "Trackers", "OS", "Fotos"]
    # 10:00Z às 11:00Z = 07:00 às 08:00 em Brasília; a dica vale no mouse e no foco do teclado (tabindex)
    assert 'class="cn-dur" tabindex="0" data-dica="Iniciou às 07:00 · terminou às 08:00 (Brasília)"' in html
    assert '<span class="cn-oculto">. Iniciou às 07:00 · terminou às 08:00 (Brasília)</span>' in html   # leitor de tela
    assert 'id="cn-dica-flut" hidden' in html
    # o CSV continua com tudo (início e fim inclusive): é a exportação, não a tela
    assert "Início;Fim" in logado.get("/t/campo/rondas?csv=1").get_data(as_text=True)


# ── 4 e 4.1: o botão Fotos na tabela, o mesmo componente do histórico da usina ───────────────────────────────────
def test_botao_fotos_na_tabela_e_no_historico_com_o_mesmo_componente(banco, logado):
    html = logado.get("/t/campo/rondas").get_data(as_text=True)
    # as duas rondas da Altair têm OS 500; a de Brodowski não tem OS: sem botão, com o porquê
    assert html.count('data-url="/t/campo/rondas/os/500/fotos"') == 2
    assert html.count('<tr class="cn-fotos-linha" hidden><td colspan="12"></td></tr>') == 2
    assert 'title="Ronda sem OS no Fracttal: as fotos ficam só no App">—<' in html
    assert html.count('class="cn-caixa-foto"') == 1 and "ArrowLeft" in html and "Escape" in html
    pag = logado.get("/t/campo/rondas/usina/1").get_data(as_text=True)
    assert 'data-url="/t/campo/rondas/os/500/fotos"' in pag and pag.count('class="cn-caixa-foto"') == 1


# ── 5: quantas usinas nunca tiveram ronda, em todo o registro ────────────────────────────────────────────────────
def test_indicador_nunca_tiveram_ronda_conta_todo_o_registro(banco, logado):
    d = visao.rondas().dados
    assert d["registro_desde"] == _dia(3)
    k = visao.painel_rondas(d["todas"], d["cobertura"], 7, d["hoje"])["kpi"]
    assert k["nunca"] == 1                                     # Coração 1
    html = logado.get("/t/campo/rondas").get_data(as_text=True)
    desde = _dia(3)
    assert "Nunca tiveram ronda" in html and 'href="?aba=sem&amp;cob=nunca"' in html
    assert f"desde {desde[8:10]}/{desde[5:7]}/{desde[:4]}, rondas avulsas" in html          # o title diz desde quando
    # uma ronda de 40 dias atrás: fora dos 30 dias, mas no registro; Coração 1 deixa de ser "nunca" e segue sem ronda
    _rondas_do_banco(banco, _ronda(_dia(40), usina="Coração Fracttal", ativo="THPN-COR100"))
    d = visao.rondas().dados
    assert d["registro_desde"] == _dia(40)
    assert visao.painel_rondas(d["todas"], d["cobertura"], 30, d["hoje"])["kpi"]["nunca"] == 0
    sem = logado.get("/t/campo/rondas?aba=sem").get_data(as_text=True)
    assert "Coração 1" in sem and ">40 d<" in sem
    assert "Nenhuma usina mobilizada sem ronda" in logado.get("/t/campo/rondas?aba=sem&cob=nunca").get_data(as_text=True)


# ── 6: a aba "Sem ronda" no lugar da Cobertura ─────────────────────────────────────────────────────────────────────
def _pessoas_com_nome():
    cofre = Cofre(CHAVE_CADASTRO)

    def p(pid, vinculo, equipe, status, sup, nome):
        return {"pessoa_id": pid, "vinculo": vinculo, "cargo": "Técnico O&M", "equipe_id": equipe, "status": status,
                "supervisor_id": sup, "excluido": "não",
                "sensivel_cifrado": cofre.cifrar(json.dumps({"nome": nome, "nome_padrao": nome}), f"banco/pessoas/{pid}")}
    campo = "Colaborador de campo"
    return [p(1, campo, 10, "Ativo", 90, "Fulana Teste Lima"), p(2, campo, 10, None, 90, "Ciclano Prova Rocha"),
            p(3, campo, 10, "Desligado", 90, "Desligado Fora Teste"), p(4, campo, 20, "Ativo", 91, "Beltrana Exemplo Dias"),
            p(90, "Supervisor", None, None, None, "Beltrano Supervisor"), p(91, "Supervisor", None, None, None, "Ciclano Chefe")]


def test_aba_sem_ronda_com_tecnicos_regiao_gestor_e_ultima_os(banco, logado):
    _aba(banco, "cadastro_nexus", "pessoas", _pessoas_com_nome())
    # Coração 1 sem ronda; duas OS fechadas pelo App nela (ligadas pelo código do ativo): a última é a 15001
    _aba(banco, "fechamentos_app_campo", "Fechamentos", [
        _fech(5, 90),
        _fech(30, 88, Usina="Outro · Coração Fracttal", OS="15001", **{"Código do ativo": "THPN-COR100-INVR2",
                                                                       "Tipo da OS": "Corretiva"}),
        _fech(200, 70, Usina="Outro · Coração Fracttal", OS="14000", **{"Código do ativo": "THPN-COR100-INVR2"})])
    visao.limpar()
    cob = {c["usina"]: c for c in visao.rondas().dados["cobertura"]}
    assert cob["Coração 1"]["tecnicos"] == ["Beltrana Dias"] and cob["Coração 1"]["ultima_os"]["os"] == "15001"
    assert cob["Altair"]["tecnicos"] == ["Ciclano Rocha", "Fulana Lima"]          # o desligado fica fora
    assert cob["Altair"]["ultima_os"]["tecnico"] == "Técnico Silva" and cob["Brodowski 1"]["ultima_os"] is None
    html = logado.get("/t/campo/rondas?aba=sem").get_data(as_text=True)
    assert _cabecalho(html, "<h2>Sem ronda</h2>") == ["Usina", "Equipe", "Técnicos", "Região de campo",
                                                      "Gestor de contrato", "Última OS na usina", "Última ronda"]
    tabela = html.split("<h2>Sem ronda</h2>", 1)[1].split("</table>", 1)[0]
    assert "Coração 1" in tabela and "Beltrana Dias" in tabela and "Ciclano Chefe" in tabela      # o gestor da usina
    assert 'Sul 01<span class="det">Supervisor de Campo: <span class="cn-vaga">vaga</span></span>' in tabela
    assert "15001" in tabela and "Corretiva · Técnico Silva" in tabela and ">nunca<" in tabela
    assert "Altair" not in tabela and "Brodowski 1" not in tabela                     # tiveram ronda nos 30 dias
    assert "Cobertura</a>" not in html                                                # a aba Cobertura saiu
    # o endereço antigo (aba=cobertura) cai na aba nova; há 7 dias ou mais e nunca são filtros dela
    assert "<h2>Sem ronda</h2>" in logado.get("/t/campo/rondas?aba=cobertura").get_data(as_text=True)
    assert 'aria-current="page">Nunca tiveram ronda <b>1</b>' in logado.get("/t/campo/rondas?aba=sem&cob=nunca").get_data(as_text=True)


# ── 7, 7.1 e 7.2: Sujidade e vegetação pela criticidade, com Status e Tipo, sem fundo e sem botões de filtro ───────
def test_nota_de_criticidade_e_as_palavras_do_status():
    assert visao.criticidade({}) == (0, [])
    assert visao.criticidade({"sujidade": 3, "vegetacao": 2}) == (1, [])                     # 3 só desempata
    assert visao.criticidade({"vegetacao": 5, "vala": "Obstruída"}) == (
        9, [("Vegetação muito alta", "critico"), ("Vala obstruída", "critico")])
    assert visao.criticidade({"sujidade": 5}) == (5, [("Sujidade muito alta", "critico")])
    # tudo no 4 (3 + 3) passa à frente da vala só obstruída (4); a "suja" da ronda avulsa é a obstruída
    assert visao.criticidade({"sujidade": 4, "vegetacao": 4})[0] == 6 > visao.criticidade({"vala": "Suja"})[0] == 4
    p, itens = visao.criticidade({"vegetacao": 4, "vala": "Parcial", "sensores_sujos": ["IPOA", "GHI"]})
    assert p == 3 + 2 + 4 and itens == [("Vegetação alta", "alerta"), ("Vala parcial", "alerta"),
                                        ("Sensor sujo (IPOA, GHI)", "alerta")]
    # o sombreamento entra no Status mas não pesa; "Não" não é sombreamento
    assert visao.criticidade({"sombreamento": "Não"}) == (0, [])
    assert visao.criticidade({"sombreamento": "árvore na fileira 3"}) == (0, [("Sombreamento", "info")])


def test_sujidade_do_mais_critico_com_status_tipo_e_so_a_cor_da_fonte(banco, logado, monkeypatch):
    # Altair (OS 500): sujidade 5 = 5 pontos; Brodowski (sem OS, carga única): vegetação 4, sujidade 3, vala obstruída
    # e IPOA sujo = 3 + 1 + 4 + 2 = 10 pontos -> vem primeiro, embora a leitura da Altair seja mais recente
    _aba(banco, "nexus_rondas_checklist", "fato_checklist_ronda", [
        {"ronda_id": "x", "data_id": 1, "usina_id": 2, "inicio": f"{_dia(2)}T10:00:00.000Z", "sujidade": 3,
         "vegetacao": 4, "vala": "Obstruída", "ipoa_sujo": 1, "ghi_sujo": None, "albedo_sujo": 0}])
    visao.limpar()
    resp = {"500": {"sujidade": 5, "vegetacao": 2, "vala": "Limpa", "sensores_sujos": []}}
    _sem_fracttal(monkeypatch, resp)
    d = visao.rondas().dados
    s = visao.sujidade_vegetacao(d["todas"], d["cobertura"], resp, 30, d["hoje"])
    assert [(x["usina"], x["pontos"]) for x in s["linhas"]] == [("Brodowski 1", 10), ("Altair", 5)]
    html = logado.get("/t/campo/rondas?aba=sujidade").get_data(as_text=True)
    assert _cabecalho(html, "cn-painel-barra") == ["Data", "Técnico", "Usina", "Equipe", "Região", "Tipo", "Sujidade",
                                                   "Vegetação", "Sombreamento", "Vala", "Sensores", "OS", "Status"]
    corpo = html.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    assert corpo.index("Brodowski 1") < corpo.index("Altair")
    assert "Vegetação alta" in corpo and "Vala obstruída" in corpo and "Sensor sujo (IPOA)" in corpo
    assert "Sujidade muito alta" in corpo and "Sudeste" in corpo                       # região do Brasil pela UF
    assert '<td data-ordem="4"><span class="cn-t-critico">Obstruída</span></td>' in corpo   # a vala, pela cor da fonte
    assert corpo.count('<span class="cn-tipo">curta</span>') == 2 and 'class="det">ronda' not in corpo   # Tipo: coluna
    # o número só com a cor da fonte (sem o fundo do cn-nivel) e o status ordenado do mais crítico
    assert 'class="cn-nivel-txt cn-nivel-txt--5">5<' in corpo and 'class="cn-nivel ' not in corpo
    assert 'aria-sort="descending">Status' in html and 'data-ordem="10"' in corpo
    # sem os botões de filtro (Sujidade alta, Vegetação alta...): ordenar é clicar no cabeçalho
    assert "?aba=sujidade&amp;sv=" not in html and 'class="cn-ordenavel"' in html
    assert html.count("table.cn-ordenavel") == 1                                         # o script de ordenar, uma vez


# ── 8 e 8.1: Quem ronda com as pendentes de cada técnico, em blocos ───────────────────────────────────────────────
def test_quem_ronda_mostra_quais_sao_as_pendentes_e_abre_em_blocos(banco, logado):
    d = visao.rondas().dados
    cl = {c["cluster"]: c for c in visao.painel_rondas(d["todas"], d["cobertura"], 30, d["hoje"])["clusters"]}
    sp, sc = cl["SP Norte"], cl["SC Oeste"]
    # cobertura do cluster = usinas com ronda no período ÷ usinas (a conta do indicador)
    assert (sp["cobertas"], sp["cobertura_pct"], sc["cobertas"], sc["cobertura_pct"]) == (2, 100, 0, 0)
    pend = sp["pessoas"][0]["pendentes_usinas"]
    assert [(p["usina"], p["status"], p["cor"]) for p in pend] == [("Altair", "Ronda longa pendente", "alerta")]
    assert pend[0]["obs"].startswith("O App pede a ronda longa (última ronda em")
    assert [(p["usina"], p["status"]) for p in sc["pendentes_usinas"]] == [("Coração 1", "Nunca teve ronda")]
    assert [p["usina"] for p in sp["pendentes_usinas"]] == ["Altair"]          # só as do cluster
    blocos = logado.get("/t/campo/rondas?aba=quem").get_data(as_text=True)
    assert blocos.count('class="cn-equipe cn-equipe--') == 2 and 'aria-current="page">Blocos<' in blocos
    assert 'href="?aba=quem&amp;cluster=SP+Norte#abas"' in blocos and ">100%<" in blocos
    tabela = logado.get("/t/campo/rondas?aba=quem&ver=tabela").get_data(as_text=True)
    assert 'class="cn-equipe ' not in tabela and "Quem ronda, por cluster" in tabela and 'aria-current="page">Tabela<' in tabela
    pessoas = logado.get("/t/campo/rondas?aba=quem&cluster=SP+Norte").get_data(as_text=True)
    assert '<tr class="cn-linha" tabindex="0" aria-expanded="false"' in pessoas
    detalhe = pessoas.split('<tr class="cn-detalhe" hidden>', 1)[1].split("</tr>", 1)[0]
    assert "Ronda longa pendente" in detalhe and '/t/campo/rondas/usina/1"' in detalhe and "Altair" in detalhe
    assert "Ver a usina pendente de ronda do cluster" in pessoas


# ── 9: o Painel, quem está melhor por região, equipe, cliente, região de campo e gestor de contrato ────────────────
def test_painel_compara_regiao_equipe_cliente_regiao_de_campo_e_gestor(banco, logado):
    d = visao.rondas().dados
    p = visao.painel_rondas(d["todas"], d["cobertura"], 30, d["hoje"])
    c = visao.comparativos(p["periodo"], d["cobertura"])
    # "Região de campo" e "Gestor de contrato" no lugar de "Supervisor" (estrutura de O&M de 10/2026)
    assert set(c) == {"regiao_br", "equipe", "cliente", "regiao_campo", "gestor"}
    rc = {a["nome"]: a for a in c["regiao_campo"]}
    assert (rc["Sudeste 03"]["usinas"], rc["Sudeste 03"]["indice"], rc["Sudeste 03"]["sub"]) == (
        2, 94, "Supervisor de Campo: Supervisora Campo")
    assert rc["Sul 01"]["sub"] == "Supervisor de Campo: vaga"
    assert [a["nome"] for a in c["gestor"]] == ["Beltrano Supervisor", "Ciclano Chefe"]
    eq = c["equipe"]
    # SP Norte 01: 2 de 2 com ronda, nota 90 -> índice 0,6 × 90 + 0,4 × 100 = 94; SC Oeste 01 sem ronda: sem índice
    assert [(a["nome"], a["indice"], a["cobertura_pct"], a["nota"], a["rondas"], a["dur_media"]) for a in eq] == [
        ("SP Norte 01", 94, 100, 90, 3, 60), ("SC Oeste 01", None, 0, None, 0, None)]
    assert eq[0]["base_pequena"] and [a["nome"] for a in c["regiao_br"]] == ["Sudeste", "Sul"]
    html = logado.get("/t/campo/rondas?aba=painel").get_data(as_text=True)
    for titulo in ("Por região do Brasil", "Por equipe", "Por cliente", "Por região de campo", "Por gestor de contrato"):
        assert titulo in html, titulo
    assert "Por supervisor" not in html
    assert html.count('class="cn-ordenavel"') == 5 and "base pequena" in html
    for link in ('href="?equipe=SP+Norte+01"', 'href="?regiao=Sudeste"', 'href="?cliente=Thopen"',
                 'href="?regiao_campo=Sudeste+03"', 'href="?gestor=Beltrano+Supervisor"'):
        assert link in html, link
    assert '<span class="det">Supervisor de Campo: vaga</span>' in html
    # o clique leva à tabela filtrada; a equipe vira um filtro da tela, com o × para tirar
    sem = logado.get("/t/campo/rondas?aba=sem&equipe=SC+Oeste+01").get_data(as_text=True)
    assert "Equipe: SC Oeste 01" in sem and "Coração 1" in sem
    assert "Nenhuma usina mobilizada sem ronda" in logado.get("/t/campo/rondas?aba=sem&equipe=SP+Norte+01").get_data(as_text=True)


def test_indicadores_levam_a_aba_sem_ronda(banco, logado):
    html = logado.get("/t/campo/rondas").get_data(as_text=True)
    assert 'href="?aba=sem"' in html and 'href="?aba=sem&amp;cob=atrasadas"' in html
    assert [a for a in re.findall(r'<nav class="cn-abas" id="abas".*?</nav>', html, re.S)[0].split("</a>") if "href" in a][3].endswith("Sem ronda<i>1</i>")


# ── Revisão (08/10): a seta mostra a ordem do servidor, a pessoa ordena pelo nome e o veredito pela gravidade ───────
def test_ordem_inicial_marcada_pessoa_pelo_nome_veredito_pela_gravidade(banco, logado):
    html = logado.get("/t/campo/rondas").get_data(as_text=True)
    # a mais recente primeiro já vem do servidor: o 1º clique em Data tem de inverter, não repetir
    assert '<th data-primeiro="desc" aria-sort="descending">Data</th><th data-primeiro="desc">Duração</th>' in html
    # a célula do técnico tem o avatar com as iniciais; ordenar pelo texto juntaria "FS" ao nome
    assert '<td class="cn-pessoa" data-ordem="Fulano Souza"><span class="cn-avatar">FS</span>' in html
    assert re.search(r'<td data-ordem="[0-3]"><span class="cn-selo cn-selo--', html)
    dur = logado.get("/t/campo/rondas?ind=duracao").get_data(as_text=True)
    assert '<th data-primeiro="desc">Data</th><th data-primeiro="desc" aria-sort="descending">Duração</th>' in dur
    trk = logado.get("/t/campo/rondas?aba=trackers").get_data(as_text=True)
    assert '<th data-primeiro="desc" aria-sort="descending">Data</th><th>Técnico</th>' in trk


def test_destaque_do_painel_com_base_pequena_e_titulo_dos_blocos(banco, logado):
    # no banco falso todo grupo (região, equipe, cliente, região de campo e gestor) tem menos de 3 usinas: há índice,
    # mas só de base pequena
    html = logado.get("/t/campo/rondas?aba=painel").get_data(as_text=True)
    destaques = html.split('<div class="cn-rank-destaques">', 1)[1].split('<div class="cn-rank-grade">', 1)[0]
    assert destaques.count("só grupos de base pequena (menos de 3 usinas)") == 5 and "sem índice no período" not in destaques
    blocos = logado.get("/t/campo/rondas?aba=quem").get_data(as_text=True)
    assert 'title="1 técnico rondou neste cluster no período"' in blocos
    assert 'title="0 técnicos rondaram neste cluster no período"' in blocos
    # lado a lado só quando cada tabela de 620 px cabe; no celular, uma coluna sem rolar a página
    css = (pathlib.Path(__file__).resolve().parents[1] / "nexus" / "static" / "campo.css").read_text(encoding="utf-8")
    assert ".cn-rank-grade{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(640px,100%),1fr))" in css
