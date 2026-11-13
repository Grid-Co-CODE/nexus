"""Tela Base → Ligações (nexus/cadastro/ligacoes.py + telas_ligacoes.py): buraco à vista e corrigido na própria tela."""
import json
from urllib.parse import parse_qs, urlparse

import pytest

from nexus import create_app
from nexus.cadastro import ligacoes as L
from nexus.cadastro.cifra import gerar_chave
from nexus.cadastro.servico import Carga

from conftest import SENHA_TESTE

FR = "Fracttal · Classificação 1"
FONTES = {FR: [{"chave": "Thopen - Brodowski 1 - SP", "codigo": "BWK100", "nome": "Thopen - Brodowski 1 - SP"},
               {"chave": "Athon - Matões 1 - MA", "codigo": "MTS100", "nome": "Athon - Matões 1 - MA", "tarefas": 843}]}


@pytest.fixture
def app_lig(tmp_path):
    app = create_app({"NEXUS_SECRET_KEY": "chave-de-teste", "NEXUS_SENHA_ADMIN": SENHA_TESTE,
                      "NEXUS_CHAVE_CADASTRO": gerar_chave(), "NEXUS_ARMAZEM_LOCAL": str(tmp_path / "cadastro.json"),
                      "NEXUS_DADOS": str(tmp_path / "dados")})
    app.config.update({"TESTING": True, "SESSION_COOKIE_SECURE": False, "NEXUS_LIGACOES_FONTES_TESTE": FONTES})
    from nexus.cadastro.telas import servico
    with app.app_context():
        servico().aplicar_carga(Carga(
            entidades={
                "clientes": [{"id": "1", "ordem": 1, "valores": {"nome": "Thopen"}},
                             {"id": "2", "ordem": 2, "valores": {"nome": "Faro Energy"}},
                             {"id": "3", "ordem": 3, "valores": {"nome": "Athon"}}],
                "usinas": [
                    {"id": "1", "ordem": 1, "valores": {"nome": "Brodowski", "codigo": "THPN-BWK100", "cliente": "1",
                                                         "status": "OPERAÇÃO", "cidade": "Brodowski", "uf": "SP"}},
                    {"id": "2", "ordem": 2, "valores": {"nome": "Matões 100", "codigo": "CÓDIGO", "cliente": "3",
                                                         "status": "OPERAÇÃO", "cidade": "Matões", "uf": "MA"}},
                    {"id": "3", "ordem": 3, "valores": {"nome": "Pedra do Sal 1", "cliente": "2", "status": "OPERAÇÃO"}},
                ]},
            listas={"status_usina": ["OPERAÇÃO"], "uf": ["SP", "MA"]}))
        L.calcular(app.config, servico())
    return app


@pytest.fixture
def cli(app_lig):
    c = app_lig.test_client()
    assert c.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    return c


def _linhas(app):
    return [tuple(l) for l in L.ler(app.config)["linhas"] if l[1] == FR]


def _decidir(cli, **form):
    r = cli.post("/t/base/ligacoes/decidir", data={"alvo_sistema": FR, **form})
    assert r.status_code == 303 and "/t/base/governanca?" in r.headers["Location"] and r.headers["Location"].endswith("#ligacoes")
    return parse_qs(urlparse(r.headers["Location"]).query)


def test_tela_exige_login(app_lig):
    assert app_lig.test_client().get("/t/base/governanca").status_code == 302


def test_a_tela_antiga_virou_secao_da_governanca(cli):
    """Levi, 11/10/2026: "essa visão de Base > Ligações entre bases vire uma seção no final de Governança de dados"."""
    r = cli.get("/t/base/ligacoes?aba=fora&sistema=x")
    assert r.status_code == 302 and r.headers["Location"].endswith("/t/base/governanca?aba=fora&sistema=x#ligacoes")
    html = cli.get("/t/base/governanca").get_data(as_text=True)
    secao = html.split('<section id="ligacoes"')[1]
    assert "Ligações entre bases" in secao and "Ler as bases de novo" in secao and "Publicar no banco" in secao
    depois = secao.split("</section>", 1)[1]
    assert "dd-h2" not in depois and "dd-h2" in html.split('<section id="ligacoes"')[0], "a seção fica no FIM da Governança"
    menu = html.split("</nav>")[0] if "</nav>" in html else html
    assert 'href="/t/base/ligacoes"' not in menu, "o item saiu do menu"


def test_quem_nao_e_admin_ve_so_o_aviso_da_secao(app_lig):
    c = app_lig.test_client()
    with c.session_transaction() as s:
        s["logado"] = True; s["admin"] = False
        s["usuario"] = {"email": "pessoa@exemplo.com", "nome": "Pessoa", "perfil": ""}
    secao = c.get("/t/base/governanca").get_data(as_text=True).split('<section id="ligacoes"')[1]
    assert "só administradores" in secao and "Publicar no banco" not in secao


def test_buraco_aparece_com_a_sugestao_certa(cli):
    html = cli.get("/t/base/governanca").get_data(as_text=True).split('<section id="ligacoes"')[1]
    assert "Athon - Matões 1 - MA" in html and "843 tarefas" in html
    assert "Athon - Matões 100" in html                       # a sugestão (código "CÓDIGO" no cadastro: só o nome)
    assert "Thopen - Brodowski 1 - SP" not in html.split("lig-tabela")[1].split("</table>")[0]   # ligado: não é buraco


def test_ligar_na_tela_vale_na_hora_e_fica_gravado_com_quem(app_lig, cli):
    q = _decidir(cli, acao="ligar", chave="Athon - Matões 1 - MA", usina="2 · Athon - Matões 100")
    assert "ok" in q
    linha = next(l for l in _linhas(app_lig) if l[2] == "Athon - Matões 1 - MA")
    assert linha[0] == 2 and linha[3].startswith("manual (") and "admin" not in linha[3]   # quem: só na decisão local
    regras = json.loads(L.caminho_regras(app_lig.config).read_text(encoding="utf-8"))
    assert regras["ligar"][0]["quem"] == "admin" and regras["ligar"][0]["usina_id"] == 2


def test_desligar_e_desfazer(app_lig, cli):
    _decidir(cli, acao="desligar", chave="Thopen - Brodowski 1 - SP", usina="1")
    assert (None, FR, "Thopen - Brodowski 1 - SP", "desligado à mão") in _linhas(app_lig)
    _decidir(cli, acao="desfazer", motivo="desligar", chave="Thopen - Brodowski 1 - SP")
    assert (1, FR, "Thopen - Brodowski 1 - SP", "código") in _linhas(app_lig)


def test_ignorar_pede_motivo(app_lig, cli):
    assert "erro" in _decidir(cli, acao="ignorar", chave="Athon - Matões 1 - MA", motivo=" ")
    _decidir(cli, acao="ignorar", chave="Athon - Matões 1 - MA", motivo="usina vendida")
    assert (None, FR, "Athon - Matões 1 - MA", "ignorado: usina vendida") in _linhas(app_lig)


def test_ausencia_esperada_por_cliente_some_da_aba_fora(app_lig, cli):
    """Faro Energy inteira fora do Fracttal (04/10: 36 usinas): marcada uma vez para o cliente, sai da lista."""
    antes = cli.get("/t/base/governanca?aba=fora").get_data(as_text=True).split('<section id="ligacoes"')[1]
    assert 'href="/t/base/usina/3"' in antes                  # Pedra do Sal 1 (Faro) na tabela de fora
    _decidir(cli, acao="ausencia", cliente_id="2", motivo="operada fora do Fracttal")
    depois = cli.get("/t/base/governanca?aba=fora").get_data(as_text=True).split('<section id="ligacoes"')[1]
    assert 'href="/t/base/usina/3"' not in depois and 'href="/t/base/usina/2"' in depois   # Matões continua


def test_teste_sem_pasta_propria_nao_grava_na_pasta_real():
    with pytest.raises(RuntimeError):
        L.caminho_regras({"TESTING": True})


def test_publicar_sem_token_avisa_e_nao_envia(cli):
    r = cli.post("/t/base/ligacoes/publicar", data={})
    assert "GRIDCO_SQL_TOKEN" in parse_qs(urlparse(r.headers["Location"]).query)["erro"][0]


def test_sugestao_pelo_codigo_parecido():
    usinas = [{"id": 2, "nome": "Matões 100", "cliente": "Athon", "codigo": "", "cidade": "Matões", "titulo": "Athon - Matões 100"},
              {"id": 9, "nome": "Marabá 100", "cliente": "Athon", "codigo": "ATHN-MAB100", "cidade": "Marabá", "titulo": "Athon - Marabá 100"}]
    s = L.sugestoes({"chave": "Athon - Matões 1 - MA", "codigo": "MTS100", "nome": "Athon - Matões 1 - MA"}, usinas)
    assert [x["id"] for x in s][0] == 2


def test_sugestao_nunca_cruza_cliente():
    """Achado na tela real (04/10): para "Andradina" da Thopen o Nexus sugeria "E1 - Andradina 1"."""
    usinas = [{"id": 5, "nome": "Andradina 1", "cliente": "E1", "codigo": "", "cidade": "Andradina", "titulo": "E1 - Andradina 1"}]
    assert L.sugestoes({"chave": "Andradina", "nome": "Andradina", "cliente": "Thopen"}, usinas) == []
    assert L.sugestoes({"chave": "Andradina", "nome": "Andradina", "cliente": "E1"}, usinas)[0]["id"] == 5


def test_sugestao_nao_e_coincidencia_de_letra():
    """Na tela real: "Andradina" sugeria "Canarana" e "Anápolis" sugeria "Fernandópolis", a 53%."""
    usinas = [{"id": 46, "nome": "Canarana 1", "cliente": "Thopen", "codigo": "CNN100", "cidade": "Canarana", "titulo": "Thopen - Canarana 1"},
              {"id": 82, "nome": "Fernandópolis", "cliente": "Thopen", "codigo": "THPN-FRN100", "cidade": "Fernandópolis", "titulo": "Thopen - Fernandópolis"},
              {"id": 55, "nome": "Caxambu 1", "cliente": "Thopen", "codigo": "THPN-CXB100", "cidade": "Jundiaí", "titulo": "Thopen - Caxambu 1"}]
    assert L.sugestoes({"chave": "Andradina", "nome": "Andradina", "cliente": "Thopen"}, usinas) == []
    assert L.sugestoes({"chave": "Anápolis", "nome": "Anápolis", "cliente": "Thopen"}, usinas) == []
    assert [x["id"] for x in L.sugestoes({"chave": "Caxambu", "nome": "Caxambu", "cliente": "Thopen"}, usinas)] == [55]


def test_numero_diferente_e_outra_usina():
    """Na tela real: "Thopen - Marajoara 2 - SP" (MRJ200) sugeria "Marajoara 1" a 100%."""
    usinas = [{"id": 98, "nome": "Marajoara 1", "cliente": "Thopen", "codigo": "THPN-MRJ100", "cidade": "Caçapava", "titulo": "Thopen - Marajoara 1"},
              {"id": 92, "nome": "Ipixuna 1 e 2", "cliente": "Thopen", "codigo": "THPN-IPX100", "cidade": "Ipixuna", "titulo": "Thopen - Ipixuna 1 e 2"}]
    assert L.sugestoes({"chave": "Thopen - Marajoara 2 - SP", "codigo": "MRJ200", "nome": "Thopen - Marajoara 2 - SP"}, usinas) == []
    assert [x["id"] for x in L.sugestoes({"chave": "Ipixuna 2", "nome": "Ipixuna 2", "cliente": "Thopen"}, usinas)] == [92]
    assert L.sugestoes({"chave": "Marajoara 2 1", "nome": "Marajoara 2 1", "cliente": "Thopen"}, usinas) == []


def test_sugestao_respeita_cidade_e_potencia():
    usinas = [{"id": 105, "nome": "Ouro Branco", "cliente": "Thopen", "codigo": "THPN-ORB100", "cidade": "Ouro Branco", "mwp": 2.0, "titulo": "Thopen - Ouro Branco"},
              {"id": 11, "nome": "Aparecida do Taboado 1 e 2", "cliente": "Thopen", "codigo": "THPN-ADT100", "cidade": "Aparecida do Taboado", "mwp": 2.58, "titulo": "x"}]
    assert L.sugestoes({"chave": "Ouro Branco I", "nome": "Ouro Branco I", "cliente": "Thopen", "cidade": "Bandeirantes"}, usinas) == []
    assert L.sugestoes({"chave": "AP. do Taboado", "nome": "AP. do Taboado", "cliente": "Thopen",
                        "cidade": "Aparecida do Taboado", "mwp": 0.413}, usinas) == []


# ── a árvore de ativos do Fracttal (27/10/2026) ────────────────────────────────────────────────────────────────────

def _arvore(pasta, nomes):
    p = pasta / L.ARVORE
    p.write_text(json.dumps({str(i): [n, "Equipe X"] for i, n in enumerate(nomes)}, ensure_ascii=False), "utf-8")
    return p


def test_usina_da_arvore_sem_tarefa_entra_na_ligacao(tmp_path):
    """Caso de 27/10/2026: as usinas da Faro estão na árvore de ativos e quase não têm tarefa; sem esta leitura não
    apareciam nas Ligações e iam ao App de Campo sem o nome do Fracttal. Só "Cliente - Usina - UF" entra (a
    Classificação 1 também tem "1.Essencial" e o cliente sozinho), e a grafia que só muda no espaço ou na caixa de uma
    chave que já existe não entra de novo."""
    p = _arvore(tmp_path, ["Faro - Pedra do Sal 1 - PI", "Faro - Pedra do Sal 1 - PI", "Thopen - Brodowski  1 - SP",
                           "thopen - brodowski 1 - SP", "Faro", "1.Essencial", "", "Apolo - Iramaia 2 - BA"])
    novos = L.usinas_da_arvore(p, {"Thopen - Brodowski 1 - SP"})
    assert novos == [{"chave": "Apolo - Iramaia 2 - BA", "nome": "Apolo - Iramaia 2 - BA",
                      "origem": "árvore de ativos do Fracttal"},
                     {"chave": "Faro - Pedra do Sal 1 - PI", "nome": "Faro - Pedra do Sal 1 - PI",
                      "origem": "árvore de ativos do Fracttal"}]
    assert L.usinas_da_arvore(tmp_path / "nao-existe.json", set()) == []
    (tmp_path / "torta.json").write_text("{nao é json", "utf-8")
    assert L.usinas_da_arvore(tmp_path / "torta.json", set()) == []


def test_fracttal_le_a_arvore_ao_lado_da_foto(tmp_path):
    """A foto das tarefas e a árvore guardada AO LADO dela (a do motor do PCM, na pasta da rodada): as usinas das tarefas
    com o código, as da árvore sem tarefa com a origem; a árvore de outra rodada não entra."""
    import pickle
    import pandas as pd
    rodada = tmp_path / "trabalho" / "geracoes" / "20261023-W44"
    rodada.mkdir(parents=True)
    df = pd.DataFrame([{"Ativo Classificação 1": "Thopen - Brodowski 1 - SP", "Código": "THPN-BWK100-INVR1.1",
                        "Localização ou parte de": ""}])
    with open(rodada / ".cache_semanal_api.pkl", "wb") as f:
        pickle.dump({"v": 1, "df": df}, f)
    _arvore(rodada, ["Thopen - Brodowski 1 - SP", "Faro - Pedra do Sal 1 - PI"])
    outra = tmp_path / "trabalho" / "geracoes" / "20261001-W41"
    outra.mkdir(parents=True)
    _arvore(outra, ["Faro - Corisco - PE"])
    cfg = {"NEXUS_PCM_TRABALHO": str(tmp_path / "trabalho"), "NEXUS_PCM_ORIGEM": str(tmp_path / "sem-pcm")}
    itens = {i["chave"]: i for i in L.fracttal(cfg)}
    assert set(itens) == {"Thopen - Brodowski 1 - SP", "Faro - Pedra do Sal 1 - PI"}
    assert itens["Thopen - Brodowski 1 - SP"]["codigo"] == "THPN-BWK100"
    assert itens["Faro - Pedra do Sal 1 - PI"]["origem"] == "árvore de ativos do Fracttal"


def test_fracttal_nao_abre_foto_da_pasta_compartilhada_do_pcm(tmp_path):
    """Auditoria de 08/11/2026: `pickle.load` executa código do arquivo, e a pasta de origem do PCM (OneDrive) é da equipe,
    não só do motor. A foto lida é só a do Nexus (`geracoes/`); a da pasta de origem não é aberta."""
    import pickle
    marcador = tmp_path / "executou.txt"

    class _Planta:
        def __reduce__(self):
            return (marcador.write_text, ("x", "utf-8"))
    origem = tmp_path / "origem"
    origem.mkdir()
    with open(origem / ".cache_semanal_api.pkl", "wb") as f:
        pickle.dump({"df": _Planta()}, f)
    cfg = {"NEXUS_PCM_TRABALHO": str(tmp_path / "trabalho"), "NEXUS_PCM_ORIGEM": str(origem)}
    L.fracttal(cfg)
    assert not marcador.exists()


def test_usina_da_arvore_liga_a_mao_na_tela(app_lig, cli):
    """A chave da árvore vira buraco nas Ligações (a Faro do Fracttal não é a "Faro Energy" do cadastro, e o nome não
    casa sozinho) e liga pela decisão da tela, como qualquer chave."""
    from nexus.cadastro.telas import servico
    fontes = {FR: FONTES[FR] + [{"chave": "Faro - Pedra do Sal 1 - PI", "nome": "Faro - Pedra do Sal 1 - PI",
                                 "origem": "árvore de ativos do Fracttal"}]}
    with app_lig.app_context():
        L.calcular(app_lig.config, servico(), fontes)
        assert ["", FR, "Faro - Pedra do Sal 1 - PI"] in [[l[0] or "", l[1], l[2]] for l in L.ler(app_lig.config)["linhas"]]
    cli.post("/t/base/ligacoes/decidir", data={"acao": "ligar", "alvo_sistema": FR,
                                               "chave": "Faro - Pedra do Sal 1 - PI", "usina": "3"})
    with app_lig.app_context():
        linhas = L.ler(app_lig.config)["linhas"]
    assert [3, FR, "Faro - Pedra do Sal 1 - PI"] in [l[:3] for l in linhas]


# ── a publicação que perde ligação do de-para não sai (10/11/2026) ───────────────────────────────────────────────
def _banco_de_mentira(cli, monkeypatch, no_banco) -> list:
    """O banco de mentira: `no_banco` = as linhas do de-para que o banco tem agora. Devolve a lista do que foi enviado."""
    from nexus.cadastro import banco as B
    enviados = []
    cli.application.config["GRIDCO_SQL_TOKEN"] = "token-de-teste"
    monkeypatch.setattr(B, "ler_anteriores", lambda base, sessao=None: {})
    monkeypatch.setattr(B, "ler_de_para", lambda base, sessao=None: no_banco)
    monkeypatch.setattr(B, "sincronizar", lambda conteudo, base, token, sessao=None: enviados.append(conteudo)
                        or {"inserted": 0, "updated": 1})
    return enviados


def _publicar_com(cli, monkeypatch, no_banco, **form):
    """O "Publicar no banco" com o banco de mentira (`form`: o que o botão manda a mais, como o `aceitar_trocas`)."""
    enviados = _banco_de_mentira(cli, monkeypatch, no_banco)
    r = cli.post("/t/base/ligacoes/publicar", data=form)
    return parse_qs(urlparse(r.headers["Location"]).query), enviados


def _de_para_enviado(conteudo: bytes) -> list[list]:
    """As linhas da aba de_para do xlsx que a publicação mandou ao banco (sem o cabeçalho)."""
    import io as _io
    from openpyxl import load_workbook
    ws = load_workbook(_io.BytesIO(conteudo), read_only=True)["de_para"]
    return [list(l) for l in ws.iter_rows(min_row=2, values_only=True)]


def test_a_ligacao_de_chave_que_esta_maquina_nao_leu_fica_como_esta_no_banco(cli, monkeypatch):
    """09/11/2026: o "Publicar no banco" do SERVIDOR recalculou o de-para com as bases que ele tinha lido em 07/10, sem as
    abas do BD_Thopen e do BD_Performance, e trocou o do banco: 187 ligações sumiram. A trava de 10/11 passou a recusar a
    publicação inteira, e em 12/11/2026 ela não saía de jeito nenhum: o banco tinha ligações de chaves que o servidor não
    lê (a usina que só a árvore de ativos do PC traz), e não há o que ligar na tela para uma chave que a máquina não tem.
    A regra agora: a ligação de chave que ESTA máquina não leu volta ao banco como estava; nada some e a publicação sai."""
    do_banco = {"usina_id": "1.0", "sistema": "BD_Thopen · aba", "chave_externa": "Brodowski", "casou_por": "nome da aba"}
    sem_usina = {"usina_id": None, "sistema": "BD_Thopen · aba", "chave_externa": "Sem Par", "casou_por": "sem par no cadastro"}
    q, enviados = _publicar_com(cli, monkeypatch, [do_banco, sem_usina])
    assert len(enviados) == 1
    linhas = _de_para_enviado(enviados[0])
    assert [1, "BD_Thopen · aba", "Brodowski", "nome da aba"] in linhas          # voltou como estava, com o id inteiro
    assert not [l for l in linhas if l[2] == "Sem Par"]                         # o que não era ligação não volta
    assert "Publicado no banco" in q["ok"][0] and "1 ligação de chave que esta máquina não leu ficou como estava" in q["ok"][0]


def test_a_publicacao_que_deixa_sem_usina_uma_chave_que_ela_leu_nao_sai(cli, monkeypatch, app_lig):
    """A perda de verdade continua travando: a chave que esta máquina LEU e deixaria sem usina (ignorada, desligada ou sem
    par aqui, e ligada no banco). A tela diz qual chave é, de que base e a que usina o banco a liga (12/11/2026: a mensagem
    só dizia quantas, e não havia como saber o que ligar)."""
    from nexus.cadastro import banco as B
    from nexus.cadastro.telas import servico
    with app_lig.app_context():
        novas = B.de_para(servico(), L.ler(app_lig.config)["fontes"], L.carregar_regras(app_lig.config))
    sem = next(l for l in novas if l[0] in (None, ""))                          # um buraco desta máquina
    no_banco = [dict(zip(B.CAB_DE_PARA, l)) for l in novas if l is not sem]
    no_banco.append({"usina_id": 1, "sistema": sem[1], "chave_externa": sem[2], "casou_por": "manual (27/10)"})
    q, enviados = _publicar_com(cli, monkeypatch, no_banco)
    assert enviados == []
    erro = q["erro"][0]
    assert "perderia 1 ligação" in erro and str(sem[1]) in erro and str(sem[2]) in erro and "usina 1" in erro


def test_a_ligacao_do_banco_a_usina_que_nao_existe_mais_nao_volta():
    """A chave que esta máquina não leu só volta se a usina dela ainda existe no cadastro que vai ser publicado."""
    from nexus.cadastro import banco as B
    novas = [[5, FR, "Cliente Alfa - Serra Exemplo 3 - SC", "código"], [None, FR, "Cliente Alfa - Buraco - SC", B.SEM_PAR]]
    no_banco = [{"usina_id": 5, "sistema": FR, "chave_externa": "Cliente Alfa - Serra Exemplo 3 - SC", "casou_por": "código"},
                {"usina_id": "7.0", "sistema": FR, "chave_externa": "Cliente Alfa - Vale Exemplo - MT",
                 "casou_por": "nome (árvore de ativos do Fracttal)"},
                {"usina_id": 9, "sistema": FR, "chave_externa": "Cliente Alfa - Usina Que Saiu - MT", "casou_por": "código"},
                {"usina_id": 5, "sistema": FR, "chave_externa": "Cliente Alfa - Buraco - SC", "casou_por": "manual (27/10)"}]
    mantidas = B.ligacoes_que_nao_li(novas, no_banco, {5, 7})
    assert mantidas == [[7, FR, "Cliente Alfa - Vale Exemplo - MT", "nome (árvore de ativos do Fracttal)"]]
    # com as mantidas, sobram as perdas de verdade: a usina que saiu do cadastro e a chave lida aqui que ficaria sem usina
    perdidas = B.chaves_que_perderia(novas + mantidas, no_banco)
    assert sorted(d["chave_externa"] for d in perdidas) == ["Cliente Alfa - Buraco - SC", "Cliente Alfa - Usina Que Saiu - MT"]
    assert B.perdas_de_para(novas + mantidas, no_banco) == {FR: 2}


def test_a_publicacao_sem_perda_sai(cli, monkeypatch, app_lig):
    """Sem ligação perdida (o banco igual, ou só com chaves que a publicação também liga), publica como sempre."""
    from nexus.cadastro import banco as B
    from nexus.cadastro.telas import servico
    with app_lig.app_context():
        novas = B.de_para(servico(), L.ler(app_lig.config)["fontes"], L.carregar_regras(app_lig.config))
    no_banco = [dict(zip(B.CAB_DE_PARA, l)) for l in novas]
    q, enviados = _publicar_com(cli, monkeypatch, no_banco)
    assert len(enviados) == 1 and "Publicado no banco" in q["ok"][0]
    # a leitura do banco que falha também não publica: sem comparar, não sai
    def quebra(base, sessao=None):
        raise ConnectionError("banco fora")
    monkeypatch.setattr(B, "ler_de_para", quebra)
    r = cli.post("/t/base/ligacoes/publicar", data={})
    assert "não consegui ler o de-para do banco" in parse_qs(urlparse(r.headers["Location"]).query)["erro"][0]


# ── a chave que trocaria de usina sem ninguém decidir não publica (12/11/2026) ───────────────────────────────────
BROD = "Thopen - Brodowski 1 - SP"          # esta máquina a liga à usina 1, pelo código


def _banco_com_a_chave_noutra_usina(app_lig, usina=3, como="nome (árvore de ativos do Fracttal)"):
    """O de-para do banco igual ao desta máquina, menos a chave BROD, que o banco liga a `usina`."""
    from nexus.cadastro import banco as B
    from nexus.cadastro.telas import servico
    with app_lig.app_context():
        novas = B.de_para(servico(), L.ler(app_lig.config)["fontes"], L.carregar_regras(app_lig.config))
    return [dict(zip(B.CAB_DE_PARA, [usina, l[1], l[2], como] if l[2] == BROD else l)) for l in novas]


def _secao(cli, consulta=""):
    return cli.get("/t/base/governanca" + consulta).get_data(as_text=True).split('<section id="ligacoes"')[1]


def test_a_chave_que_trocaria_de_usina_por_regra_automatica_e_listada():
    """12/11/2026: a trava só barrava a chave que ficava SEM usina; a que TROCAVA de usina passava calada. Na primeira
    publicação do servidor depois do conserto das mantidas, a chave do Fracttal de um cliente saiu da usina dele para a
    usina de OUTRO cliente na mesma cidade: a usina certa não tinha código no cadastro, e o código do local no Fracttal
    casou pelo sufixo com o da outra. Só a conferência com a cópia de antes mostrou. Troca é: a chave tinha usina no banco
    e a publicação a liga a um conjunto DIFERENTE de usinas (outra, uma a menos ou uma a mais), por regra automática; a
    decidida à mão nesta máquina é escolha de alguém."""
    from nexus.cadastro import banco as B
    AB = "BD_Exemplo · aba"
    novas = [[113, FR, "Cliente Beta - Vila Exemplo - MT", "código"],           # o banco liga à 220: troca
             [5, FR, "Cliente Alfa - Serra Exemplo 3 - SC", "código"],          # igual ao banco
             [7, FR, "Cliente Alfa - Vale Exemplo - MT", "manual (12/11)"],     # trocou por decisão da tela: passa
             [8, AB, "Dupla", "igual a X"], [9, AB, "Dupla", "igual a X"],      # duas usinas, as mesmas do banco
             [8, AB, "Dupla que perdeu uma", "igual a X"],                      # o banco tinha a 8 e a 9: troca
             [8, AB, "Ganhou outra", "nome"], [9, AB, "Ganhou outra", "nome"],  # o banco só tinha a 8: a 9 a mais é troca
             [10, AB, 10, "código"],                                            # a chave numérica: "10.0" é a mesma
             [13, AB, "12.0", "código"],                                        # e a 12 do banco é a "12.0" daqui
             [None, FR, "Cliente Alfa - Buraco - SC", B.SEM_PAR],               # ficou sem usina: é perda, não troca
             [4, FR, "Cliente Alfa - Nova - SC", "código"]]                     # o banco não tinha: ligação nova
    no_banco = [{"usina_id": "220.0", "sistema": FR, "chave_externa": "Cliente Beta - Vila Exemplo - MT",
                 "casou_por": "nome (árvore de ativos do Fracttal)"},
                {"usina_id": 5, "sistema": FR, "chave_externa": "Cliente Alfa - Serra Exemplo 3 - SC", "casou_por": "código"},
                {"usina_id": 6, "sistema": FR, "chave_externa": "Cliente Alfa - Vale Exemplo - MT", "casou_por": "nome"},
                {"usina_id": 8, "sistema": AB, "chave_externa": "Dupla", "casou_por": "igual a X"},
                {"usina_id": 9, "sistema": AB, "chave_externa": "Dupla", "casou_por": "igual a X"},
                {"usina_id": 9, "sistema": AB, "chave_externa": "Dupla que perdeu uma", "casou_por": "igual a X"},
                {"usina_id": 8, "sistema": AB, "chave_externa": "Dupla que perdeu uma", "casou_por": "igual a X"},
                {"usina_id": 8, "sistema": AB, "chave_externa": "Ganhou outra", "casou_por": "nome"},
                {"usina_id": 11, "sistema": AB, "chave_externa": "10.0", "casou_por": "código"},
                {"usina_id": 14, "sistema": AB, "chave_externa": 12, "casou_por": "código"},
                {"usina_id": 5, "sistema": FR, "chave_externa": "Cliente Alfa - Buraco - SC", "casou_por": "manual (27/10)"},
                {"usina_id": None, "sistema": FR, "chave_externa": "Cliente Alfa - Nova - SC", "casou_por": B.SEM_PAR}]
    assert B.chaves_que_trocariam(novas, no_banco) == [
        {"sistema": AB, "chave_externa": 10, "de": [11], "para": [10], "casou_por": "código"},
        {"sistema": AB, "chave_externa": "12.0", "de": [14], "para": [13], "casou_por": "código"},
        {"sistema": AB, "chave_externa": "Dupla que perdeu uma", "de": [8, 9], "para": [8], "casou_por": "igual a X"},
        {"sistema": AB, "chave_externa": "Ganhou outra", "de": [8], "para": [8, 9], "casou_por": "nome"},
        {"sistema": FR, "chave_externa": "Cliente Beta - Vila Exemplo - MT", "de": [220], "para": [113], "casou_por": "código"}]


def test_a_chave_de_duas_usinas_que_esta_maquina_nao_leu_volta_com_as_duas():
    """A revisão de 12/11/2026 achou: a mantida voltava com UMA usina só (a 1ª linha da chave), e a 2ª ligação de uma
    chave que o banco liga a duas usinas (as "I e II" de uma aba) sumia calada. "Como estava" é com todas as usinas."""
    from nexus.cadastro import banco as B
    AB = "BD_Exemplo · aba"
    no_banco = [{"usina_id": 8, "sistema": AB, "chave_externa": "Dupla", "casou_por": "igual a X"},
                {"usina_id": "9.0", "sistema": AB, "chave_externa": "Dupla", "casou_por": "igual a X"},
                {"usina_id": 8, "sistema": AB, "chave_externa": "Dupla", "casou_por": "igual a X"},     # linha repetida
                {"usina_id": 77, "sistema": AB, "chave_externa": "Dupla", "casou_por": "igual a X"}]    # usina que saiu
    assert B.ligacoes_que_nao_li([], no_banco, {8, 9}) == [[8, AB, "Dupla", "igual a X"], [9, AB, "Dupla", "igual a X"]]


def test_a_tela_e_a_rota_contam_as_mesmas_trocas_com_chave_mantida(cli, monkeypatch, app_lig):
    """A revisão de 12/11/2026: a rota contava as trocas DEPOIS de juntar as mantidas e a tela, antes; com uma chave de
    duas usinas que esta máquina não leu, a rota recusava uma troca que a tela não mostrava, sem botão para sair. A troca
    é só de chave que esta máquina LEU, nos dois lugares: a marca da tela vale na rota, e a mantida volta inteira."""
    import re
    AB = "BD_Exemplo · aba"
    dupla = [{"usina_id": 2, "sistema": AB, "chave_externa": "Dupla", "casou_por": "igual a X"},
             {"usina_id": 3, "sistema": AB, "chave_externa": "Dupla", "casou_por": "igual a X"}]
    # só a mantida de duas usinas: não há troca, a publicação sai e as duas ligações voltam
    from nexus.cadastro import banco as B
    from nexus.cadastro.telas import servico
    with app_lig.app_context():
        iguais = [dict(zip(B.CAB_DE_PARA, l)) for l in
                  B.de_para(servico(), L.ler(app_lig.config)["fontes"], L.carregar_regras(app_lig.config))]
    q, enviados = _publicar_com(cli, monkeypatch, iguais + dupla)
    assert len(enviados) == 1 and "2 ligações de chaves que esta máquina não leu ficaram" in q["ok"][0]
    linhas = _de_para_enviado(enviados[0])
    assert [2, AB, "Dupla", "igual a X"] in linhas and [3, AB, "Dupla", "igual a X"] in linhas
    # a mantida com uma usina que saiu do cadastro volta só com a que existe, e isso não é troca desta máquina (contada
    # depois de juntar as mantidas, a rota recusaria uma troca que a tela não lista)
    saiu = [{"usina_id": 2, "sistema": AB, "chave_externa": "Meia", "casou_por": "igual a X"},
            {"usina_id": 99, "sistema": AB, "chave_externa": "Meia", "casou_por": "igual a X"}]
    q, enviados = _publicar_com(cli, monkeypatch, iguais + saiu)
    assert len(enviados) == 1 and "ok" in q
    meia = [l for l in _de_para_enviado(enviados[0]) if l[2] == "Meia"]
    assert meia == [[2, AB, "Meia", "igual a X"]]
    # com uma troca de verdade junto: a tela lista só ela, e o aceite da tela vale na rota
    no_banco = _banco_com_a_chave_noutra_usina(app_lig) + dupla
    q, enviados = _publicar_com(cli, monkeypatch, no_banco)
    assert enviados == [] and "1 chave trocaria de usina" in q["erro"][0] and "Dupla" not in q["erro"][0]
    secao = _secao(cli, "?trocas=1")
    bloco = secao.split('class="lig-trocas"')[1].split("</table>")[0]
    assert BROD in bloco and "Dupla" not in bloco
    assinatura = re.search(r'name="aceitar_trocas" value="([0-9a-f]{16})"', secao).group(1)
    q, enviados = _publicar_com(cli, monkeypatch, no_banco, aceitar_trocas=assinatura)
    assert len(enviados) == 1 and "1 chave trocou de usina" in q["ok"][0]


def test_a_troca_pelo_id_do_bd_nao_tem_o_manter(cli, monkeypatch, app_lig):
    """A chave do BD_Operações é o ID do BD da ficha da usina: sai do Registro mestre, não do de-para decidido na tela,
    e a decisão de ligar não a alcança (revisão de 12/11/2026: o "Manter" gravava uma decisão sem efeito e dizia
    "aplicada"). A troca aparece, sem o botão, e diz onde se corrige."""
    from nexus.cadastro import banco as B
    de_para = B.de_para
    monkeypatch.setattr(B, "de_para", lambda srv, fontes, regras=None:
                        de_para(srv, fontes, regras) + [[1, "BD_Operações", "UFV-001", B.COMO_ID_BD]])
    no_banco = _banco_com_a_chave_noutra_usina(app_lig, usina=1, como="código")
    no_banco.append({"usina_id": 2, "sistema": "BD_Operações", "chave_externa": "UFV-001", "casou_por": B.COMO_ID_BD})
    _banco_de_mentira(cli, monkeypatch, no_banco)
    secao = _secao(cli, "?trocas=1")
    bloco = secao.split('class="lig-trocas"')[1].split("</table>")[0]
    assert "UFV-001" in bloco and "Manter a do banco" not in bloco and "Registro mestre" in bloco
    assert 'name="aceitar_trocas"' in secao


def _ferramenta(app_lig, monkeypatch, no_banco, *args):
    """Roda a `ferramentas/publicar_cadastro.py --bases-guardadas` com o cadastro e as bases da fixture e o banco de
    mentira. Devolve (o que foi enviado, o código de saída: None = terminou sem `sys.exit`)."""
    import sys
    import ferramentas.publicar_cadastro as P
    from nexus.cadastro import banco as B
    env = {k: app_lig.config[k] for k in ("NEXUS_CHAVE_CADASTRO", "NEXUS_ARMAZEM_LOCAL", "NEXUS_DADOS")}
    env["GRIDCO_SQL_TOKEN"] = "token-de-teste"
    enviados = []
    monkeypatch.setattr(P, "ler_ambiente", lambda: env)
    monkeypatch.setattr(B, "ler_anteriores", lambda base, sessao=None: {})
    monkeypatch.setattr(B, "ler_de_para", lambda base, sessao=None: no_banco)
    monkeypatch.setattr(B, "sincronizar", lambda conteudo, base, token, sessao=None: enviados.append(conteudo)
                        or {"inserted": 0, "updated": 1})
    monkeypatch.setattr(sys, "argv", ["publicar_cadastro.py", "--bases-guardadas", *args])
    try:
        P.main()
    except SystemExit as e:
        return enviados, e.code
    return enviados, None


def test_a_ferramenta_do_pc_passa_pelas_mesmas_tres_regras(app_lig, monkeypatch, capsys):
    """A `ferramentas/publicar_cadastro.py` enviava direto, sem regra nenhuma (achado de 12/11/2026): depois da
    publicação do servidor daquela noite o banco tinha ligações que só o servidor conhece (os projetos da FAMA, o
    plant_id), e a ferramenta rodada no PC apagaria todas. Agora ela passa pela mesma conferência do botão da tela
    (`banco.conferir_com_o_banco`): mantém o que não leu, não sai com perda, e a troca pede a marca."""
    import re
    from nexus.cadastro import banco as B
    from nexus.cadastro.telas import servico
    with app_lig.app_context():
        proprias = B.de_para(servico(), L.ler(app_lig.config)["fontes"], L.carregar_regras(app_lig.config))
    iguais = [dict(zip(B.CAB_DE_PARA, l)) for l in proprias]
    so_do_banco = {"usina_id": 3, "sistema": "FAMA · Projetos", "chave_externa": "21", "casou_por": "manual (12/11)"}
    # 1. a chave que esta máquina não leu volta como estava
    enviados, saida = _ferramenta(app_lig, monkeypatch, iguais + [so_do_banco])
    assert saida is None and len(enviados) == 1
    assert [3, "FAMA · Projetos", "21", "manual (12/11)"] in _de_para_enviado(enviados[0])
    # 2. a perda não sai, e a ferramenta diz a chave
    buraco = next(l for l in proprias if l[0] in (None, ""))
    com_perda = [d for d in iguais if d["chave_externa"] != buraco[2]] + [
        {"usina_id": 1, "sistema": buraco[1], "chave_externa": buraco[2], "casou_por": "manual (27/10)"}]
    capsys.readouterr()
    enviados, saida = _ferramenta(app_lig, monkeypatch, com_perda)
    assert enviados == [] and saida not in (None, 0)
    assert str(buraco[2]) in capsys.readouterr().out
    # 3. a troca não sai sem a marca; com a marca que a ferramenta mostrou, sai
    com_troca = _banco_com_a_chave_noutra_usina(app_lig)
    enviados, saida = _ferramenta(app_lig, monkeypatch, com_troca)
    dito = capsys.readouterr().out
    assert enviados == [] and saida not in (None, 0) and BROD in dito
    marca = re.search(r"--aceitar-trocas ([0-9a-f]{16})", dito).group(1)
    enviados, saida = _ferramenta(app_lig, monkeypatch, com_troca, "--aceitar-trocas", "0" * 16)
    assert enviados == [] and saida not in (None, 0)
    enviados, saida = _ferramenta(app_lig, monkeypatch, com_troca, "--aceitar-trocas", marca)
    assert saida is None and len(enviados) == 1
    # o ensaio confere e não envia: nem com a troca à vista, nem com tudo certo
    enviados, saida = _ferramenta(app_lig, monkeypatch, com_troca, "--ensaio")
    assert enviados == [] and saida is None and BROD in capsys.readouterr().out
    enviados, saida = _ferramenta(app_lig, monkeypatch, iguais, "--ensaio")
    assert enviados == [] and saida is None


def test_o_publicar_de_outro_site_nao_sai(cli, monkeypatch, app_lig):
    """O aceite das trocas é passo de risco, e a marca não é segredo (calcula-se com o de-para do banco, de leitura
    aberta): o pedido que não vem de uma página do próprio Nexus não publica (a mesma guarda do "Ligar as sugestões")."""
    no_banco = _banco_com_a_chave_noutra_usina(app_lig, usina=1, como="código")        # igual a esta máquina
    enviados = _banco_de_mentira(cli, monkeypatch, no_banco)
    r = cli.post("/t/base/ligacoes/publicar", data={}, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403 and enviados == []
    r = cli.post("/t/base/ligacoes/publicar", data={}, headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 303 and len(enviados) == 1


def test_a_assinatura_das_trocas_e_do_conjunto_mostrado():
    """O "Publicar com as trocas" só vale para o conjunto que a tela mostrou: a ordem não muda a assinatura, e qualquer
    chave, usina de antes ou usina de depois diferente muda."""
    from nexus.cadastro import banco as B
    a = {"sistema": FR, "chave_externa": "Cliente Beta - Vila Exemplo - MT", "de": [220], "para": [113], "casou_por": "código"}
    b = {"sistema": FR, "chave_externa": "Cliente Alfa - Vale Exemplo - MT", "de": [6], "para": [7], "casou_por": "nome"}
    assert B.assinatura_das_trocas([a, b]) == B.assinatura_das_trocas([b, a])
    assert B.assinatura_das_trocas([a]) != B.assinatura_das_trocas([a, b])
    assert B.assinatura_das_trocas([a]) != B.assinatura_das_trocas([{**a, "para": [114]}])
    assert B.assinatura_das_trocas([a]) != B.assinatura_das_trocas([{**a, "de": [221]}])
    assert B.assinatura_das_trocas([a]) != B.assinatura_das_trocas([{**a, "chave_externa": "Cliente Beta - Outra - MT"}])


def test_a_publicacao_que_trocaria_a_usina_de_uma_chave_nao_sai_sem_o_aceite(cli, monkeypatch, app_lig):
    """A troca por regra automática não publica: a tela diz a chave, a usina do banco e a usina nova, lista cada uma com
    o "Manter a do banco" e oferece o "Publicar com as trocas", que só vale para a lista mostrada."""
    import re
    no_banco = _banco_com_a_chave_noutra_usina(app_lig)
    q, enviados = _publicar_com(cli, monkeypatch, no_banco)
    assert enviados == [] and q["trocas"] == ["1"]
    erro = q["erro"][0]
    assert "1 chave trocaria de usina" in erro and BROD in erro and "usina 3" in erro and "usina 1" in erro
    bloco = _secao(cli, "?trocas=1").split('class="lig-trocas"')[1].split("</table>")[0]
    assert BROD in bloco and "Faro Energy - Pedra do Sal 1" in bloco and "Thopen - Brodowski" in bloco
    assert "Manter a do banco" in bloco and 'name="usina" value="3"' in bloco
    assinatura = re.search(r'name="aceitar_trocas" value="([0-9a-f]{16})"', _secao(cli, "?trocas=1")).group(1)
    # o aceite de outro conjunto não vale
    q, enviados = _publicar_com(cli, monkeypatch, no_banco, aceitar_trocas="0" * 16)
    assert enviados == [] and "trocaria de usina" in q["erro"][0]
    # o aceite da lista mostrada publica, e a mensagem diz que trocou
    q, enviados = _publicar_com(cli, monkeypatch, no_banco, aceitar_trocas=assinatura)
    assert len(enviados) == 1 and [1, FR, BROD, "código"] in _de_para_enviado(enviados[0])
    assert "Publicado no banco" in q["ok"][0] and "1 chave trocou de usina" in q["ok"][0]


def test_manter_a_usina_do_banco_vira_decisao_e_a_publicacao_sai(cli, monkeypatch, app_lig):
    """O "Manter a do banco" grava a decisão de ligar a chave à usina que o banco tem: deixa de ser troca, a lista
    continua aberta para a próxima chave e a publicação sai sem o aceite."""
    no_banco = _banco_com_a_chave_noutra_usina(app_lig)
    _banco_de_mentira(cli, monkeypatch, no_banco)
    assert 'class="lig-trocas"' in _secao(cli, "?trocas=1")
    q = _decidir(cli, acao="ligar", chave=BROD, usina="3", trocas="1")
    assert "ok" in q and q["trocas"] == ["1"]
    assert 'class="lig-trocas"' not in _secao(cli, "?trocas=1")        # não sobrou troca: o bloco some
    q, enviados = _publicar_com(cli, monkeypatch, no_banco)
    assert len(enviados) == 1 and "trocou de usina" not in q["ok"][0]
    linha = next(l for l in _de_para_enviado(enviados[0]) if l[2] == BROD)
    assert linha[0] == 3 and linha[3].startswith("manual (")


def test_o_manter_so_aparece_quando_o_banco_liga_a_uma_usina_do_cadastro(cli, monkeypatch, app_lig):
    """A decisão de ligar aponta UMA usina: a chave que o banco liga a duas, ou a uma usina que saiu do cadastro, não tem
    o "Manter a do banco" (a linha diz por quê), e segue podendo sair pelo "Publicar com as trocas"."""
    duas = _banco_com_a_chave_noutra_usina(app_lig, usina=2)
    duas.append({**next(d for d in duas if d["chave_externa"] == BROD), "usina_id": 3})
    _banco_de_mentira(cli, monkeypatch, duas)
    bloco = _secao(cli, "?trocas=1").split('class="lig-trocas"')[1].split("</table>")[0]
    assert "Manter a do banco" not in bloco and "o banco liga a mais de uma usina" in bloco
    _banco_de_mentira(cli, monkeypatch, _banco_com_a_chave_noutra_usina(app_lig, usina=99))
    secao = _secao(cli, "?trocas=1")
    bloco = secao.split('class="lig-trocas"')[1].split("</table>")[0]
    assert "Manter a do banco" not in bloco and "a usina do banco saiu do cadastro" in bloco
    assert 'name="aceitar_trocas"' in secao and "Publicar com a troca" in secao


def test_a_troca_decidida_a_mao_nesta_maquina_publica(cli, monkeypatch, app_lig):
    """Quem ligou a chave a outra usina na tela desta máquina já decidiu: a publicação não pergunta de novo."""
    _decidir(cli, acao="ligar", chave=BROD, usina="3")
    no_banco = _banco_com_a_chave_noutra_usina(app_lig, usina=1, como="código")
    q, enviados = _publicar_com(cli, monkeypatch, no_banco)
    assert len(enviados) == 1 and "ok" in q
    assert next(l for l in _de_para_enviado(enviados[0]) if l[2] == BROD)[0] == 3


def test_a_lista_das_trocas_so_le_o_banco_quando_pedida(cli, monkeypatch, app_lig):
    """A Governança não lê o de-para do banco a cada visita: só com o `trocas=1` que a recusa põe no endereço. E a
    leitura que falha não derruba a tela: ela diz que não conseguiu listar."""
    from nexus.cadastro import banco as B
    leituras = []
    def quebra(base, sessao=None):
        leituras.append(base)
        raise ConnectionError("banco fora")
    monkeypatch.setattr(B, "ler_de_para", quebra)
    sem = _secao(cli)
    assert leituras == [] and 'class="lig-trocas"' not in sem and "não consegui ler o de-para do banco" not in sem
    com = _secao(cli, "?trocas=1")
    assert len(leituras) == 1 and 'class="lig-trocas"' not in com and "não consegui ler o de-para do banco" in com


def test_o_ligar_usa_a_lista_do_nexus_e_nao_o_datalist(cli):
    """Levi, 12/11/2026: o <datalist> abria solto e fora do estilo ("tem que estar alinhado com o campo")."""
    html = cli.get("/t/base/governanca?sistema=" + FR).get_data(as_text=True)
    assert '<datalist id="lig-usinas">' not in html and 'list="lig-usinas"' not in html
    assert 'data-lista="lig-usinas-opcoes"' in html
    opcoes = json.loads(html.split('id="lig-usinas-opcoes">')[1].split("</script>")[0])
    assert "2 · Athon - Matões 100" in opcoes and "1 · Thopen - Brodowski" in opcoes
    assert "lista-sugestoes.js" in html


def test_decidir_recebe_o_mesmo_valor_id_e_titulo(cli, app_lig):
    q = _decidir(cli, acao="ligar", chave="Athon - Matões 1 - MA", usina="2 · Athon - Matões 100")
    assert "ok" in q
