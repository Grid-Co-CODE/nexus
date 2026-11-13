"""Rondas, pedido do Levi de 08/10/2026 (Nexus > Campo App > Rondas): a tabela de registros sem Região, Início e Fim,
com a Duração ao lado da Data e o início e o fim no mouse; o botão Fotos na tabela; o indicador "Nunca tiveram ronda";
a "Sem ronda" no lugar da Cobertura; a Sujidade pela criticidade, com Status e Tipo; o Quem ronda com as pendentes de
cada técnico; e o Painel por região, equipe, cliente e supervisor (com a estrutura de O&M de 10/2026, o supervisor virou
a região de campo e o gestor de contrato). Desde 03/11/2026 (Rondas enxuta) o Painel, a Sujidade e o Quem ronda saíram
da tela e a Sem ronda é um filtro dos Registros: as contas deles seguem provadas aqui pelo visao. Banco falso
(pg_falso)."""
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
    # o menu do cabeçalho (Duração, Pendências, 03/11/2026) não é o título da coluna
    trecho = re.sub(r'<div class="rd-menu-caixa".*?</div>', "", trecho, flags=re.S)
    return [re.sub(r"<[^>]+>", "", t).replace("&shy;", "").strip() for t in re.findall(r"<th[^>]*>(.*?)</th>", trecho, re.S)]


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
    # a coluna Fotos saiu (03/11/2026): a linha abre a barra lateral com tudo da ronda, fotos inclusive
    assert _cabecalho(html, "cn-tab--rondas") == ["Data", "Duração", "Técnico", "Usina", "Equipe", "Tipo", "Qualidade",
                                                  "Veredito", "Pendências", "Trackers", "OS"]
    # 10:00Z às 11:00Z = 07:00 às 08:00 em Brasília; a dica vale no mouse e no foco do teclado (tabindex)
    assert 'class="cn-dur" tabindex="0" data-dica="Iniciou às 07:00 · terminou às 08:00 (Brasília)"' in html
    assert '<span class="cn-oculto">. Iniciou às 07:00 · terminou às 08:00 (Brasília)</span>' in html   # leitor de tela
    assert 'id="cn-dica-flut" hidden' in html
    # o CSV continua com tudo (início e fim inclusive): é a exportação, não a tela
    assert "Início;Fim" in logado.get("/t/campo/rondas?csv=1").get_data(as_text=True)


# ── 4 e 4.1: as fotos da ronda; desde 03/11/2026 na barra lateral, a mesma da tabela e do histórico da usina ──────
def test_botao_fotos_na_tabela_e_no_historico_com_o_mesmo_componente(banco, logado):
    html = logado.get("/t/campo/rondas").get_data(as_text=True)
    # a linha abre a barra lateral (03/11/2026: "Tira esse botão 'Fotos' ao clicar na linha já abre uma barra lateral");
    # as duas rondas da Altair têm OS 500, a de Brodowski não tem OS: a barra diz que as fotos ficam no App
    # (a caixa que amplia é a mesma da Zeladoria e da Segurança, que seguem com o botão: o script dele vem junto)
    assert 'class="cn-bt-fotos"' not in html and '<tr class="cn-fotos-linha"' not in html
    assert html.count('data-detalhe="/t/campo/rondas/usina/1/ronda?os=500&amp;data=') == 2
    assert html.count('class="cn-caixa-foto"') == 1 and "ArrowLeft" in html and 'id="rd-gaveta"' in html
    url = re.search(r'data-detalhe="(/t/campo/rondas/usina/1/ronda[^"]+)"', html).group(1).replace("&amp;", "&")
    det = logado.get(url).get_data(as_text=True)
    assert 'data-fotos-url="/t/campo/rondas/os/500/fotos"' in det and "<h2" in det and "Altair" in det
    brod = re.search(r'data-detalhe="(/t/campo/rondas/usina/2/ronda[^"]+)"', html).group(1).replace("&amp;", "&")
    assert "as fotos ficam só no App" in logado.get(brod).get_data(as_text=True)
    pag = logado.get("/t/campo/rondas/usina/1").get_data(as_text=True)
    assert 'data-detalhe="/t/campo/rondas/usina/1/ronda?os=500' in pag and pag.count('class="cn-caixa-foto"') == 1
    assert 'id="rd-gaveta"' in pag and 'class="cn-bt-fotos"' not in pag


# ── 5: quantas usinas nunca tiveram ronda, em todo o registro ────────────────────────────────────────────────────
def test_indicador_nunca_tiveram_ronda_conta_todo_o_registro(banco, logado):
    d = visao.rondas().dados
    assert d["registro_desde"] == _dia(3)
    k = visao.painel_rondas(d["todas"], d["cobertura"], 7, d["hoje"])["kpi"]
    assert k["nunca"] == 1                                     # Coração 1
    html = logado.get("/t/campo/rondas").get_data(as_text=True)
    desde = _dia(3)
    # desde 12/11/2026 (a revisão de desenho) o número não é mais um indicador da faixa: fica numa linha que leva à
    # Central de atenção (a tela dona do pendente), e a lista segue no "Mostrar" dos Filtros
    assert "<b>1</b> usina nunca teve ronda" in html and 'value="nunca"' in html
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
    # desde 03/11/2026 a Sem ronda é um filtro: a etiqueta diz qual, e o indicador fica marcado
    nunca = logado.get("/t/campo/rondas?aba=sem&cob=nunca").get_data(as_text=True)
    assert "Mostrar: <b>Nunca tiveram ronda</b>" in nunca and "<h2>Sem ronda</h2>" in nunca


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
    # a aba saiu da tela (Levi, 03/11/2026: "Esse 'sujidade e vegetação' também é redundante pois os registros já
    # mostram"): o endereço dela cai nos Registros
    html = logado.get("/t/campo/rondas?aba=sujidade").get_data(as_text=True)
    assert "<h2>Rondas diárias</h2>" in html and "Sujidade e vegetação</a>" not in html


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
    # a aba saiu (Levi, 03/11/2026: "Pode tirar quem ronda também! Menos é mais!"): o endereço cai nos Registros
    html = logado.get("/t/campo/rondas?aba=quem&cluster=SP+Norte").get_data(as_text=True)
    assert "<h2>Rondas diárias</h2>" in html and "Quem ronda" not in html and 'class="cn-equipe ' not in html


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
    # a aba saiu (Levi, 03/11/2026: "Tire o painel, ele não serve"): o endereço cai nos Registros
    html = logado.get("/t/campo/rondas?aba=painel").get_data(as_text=True)
    assert "<h2>Rondas diárias</h2>" in html and "Por região do Brasil" not in html
    # a equipe é um filtro da tela (desde 13/10/2026; desde 03/11/2026 no painel dos Filtros)
    sem = logado.get("/t/campo/rondas?aba=sem&equipe=SC+Oeste+01").get_data(as_text=True)
    assert '<option value="SC Oeste 01" selected>SC Oeste 01</option>' in sem and "Coração 1" in sem
    assert "Nenhuma usina mobilizada sem ronda" in logado.get("/t/campo/rondas?aba=sem&equipe=SP+Norte+01").get_data(as_text=True)


def test_indicadores_levam_a_aba_sem_ronda(banco, logado):
    html = logado.get("/t/campo/rondas").get_data(as_text=True)
    assert 'href="?cob=sem"' in html and 'value="atrasadas"' in html      # a atrasada: só no "Mostrar" (12/11/2026)
    # duas abas (03/11/2026): a Sem ronda virou o "Mostrar" dos Filtros
    abas = re.findall(r'<nav class="cn-abas" id="abas".*?</nav>', html, re.S)[0]
    assert re.findall(r">(Registros|Trackers)<", abas) == ["Registros", "Trackers"] and "Sem ronda" not in abas


# ── Revisão (08/10): a seta mostra a ordem do servidor, a pessoa ordena pelo nome e o veredito pela gravidade ───────
def test_ordem_inicial_marcada_pessoa_pelo_nome_veredito_pela_gravidade(banco, logado):
    html = logado.get("/t/campo/rondas").get_data(as_text=True)
    # a mais recente primeiro já vem do servidor: o 1º clique em Data tem de inverter, não repetir
    assert '<th data-primeiro="desc" aria-sort="descending">Data</th>' in html
    assert '<th class="rd-th" data-ordem-menu data-primeiro="desc"><details class="rd-menu"><summary>Duração' in html
    # a célula do técnico tem o avatar com as iniciais; ordenar pelo texto juntaria "FS" ao nome
    assert '<td class="cn-pessoa" data-ordem="Fulano Souza"><span class="cn-avatar">FS</span>' in html
    assert re.search(r'<td data-ordem="[0-3]"><span class="cn-selo cn-selo--', html)
    dur = logado.get("/t/campo/rondas?ind=duracao").get_data(as_text=True)
    assert '<th data-primeiro="desc">Data</th>' in dur
    assert '<th class="rd-th" data-ordem-menu data-primeiro="desc" aria-sort="descending"><details class="rd-menu">' in dur
    trk = logado.get("/t/campo/rondas?aba=trackers").get_data(as_text=True)
    assert '<th data-primeiro="desc" aria-sort="descending">Data</th><th>Técnico</th>' in trk
