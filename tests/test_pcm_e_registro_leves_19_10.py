"""O PCM e o Registro mestre mais leves (Levi, 19/10/2026: "faça 2 e 3"). Medido no PC com o cadastro e o banco reais:
cada visita ao Gerar a semana gastava 0,34 a 0,39 s de processador (decifrava de novo as ~570 fichas do cadastro e
comparava os nomes das usinas todos contra todos, ~28 mil normalizações), o Quadro 0,14 s (o índice do tipo das tarefas
da Gestão PCM refeito a cada visita) e o Registro mestre 0,31 a 0,42 s e 1,3 MB (as ~300 usinas x 53 colunas montadas a
cada visita). Depois: 0,12 a 0,16 s, 0,05 s e 0,02 a 0,03 s (936 KB), com as páginas do PCM iguais byte a byte e o
Registro mestre com a mesma tabela (só sem o espaço entre as células e sem o class vazio)."""
import json

import pytest

from nexus import create_app
from nexus.cadastro.armazem import ArmazemLocal
from nexus.cadastro.cifra import Cofre, gerar_chave
from nexus.cadastro.servico import Carga, Servico
from nexus.pcm import auxiliar as A
from nexus.pcm import observacoes as O
from nexus.pcm import quadro as Q

from conftest import SENHA_TESTE
from test_pcm_observacoes import FRACTTAL

USINAS = [{"id": "1", "ordem": 1, "valores": {"nome": "Altair", "codigo": "THPN-ALT100", "cliente": "1",
                                              "status": "OPERAÇÃO"}},
          {"id": "2", "ordem": 2, "valores": {"nome": "Brodowski 1", "codigo": "THPN-BWK100", "cliente": "1",
                                              "status": "OPERAÇÃO"}}]


def _carga(usinas=USINAS):
    return Carga(entidades={"clientes": [{"id": "1", "ordem": 1, "valores": {"nome": "Thopen"}}], "usinas": usinas},
                 listas={"status_usina": ["OPERAÇÃO"]})


# ── o Registro mestre ─────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def cli(tmp_path, monkeypatch):
    app = create_app({"NEXUS_SECRET_KEY": "chave-de-teste", "NEXUS_SENHA_ADMIN": SENHA_TESTE,
                      "NEXUS_CHAVE_CADASTRO": gerar_chave(), "NEXUS_ARMAZEM_LOCAL": str(tmp_path / "cadastro.json")})
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    from nexus.cadastro import telas
    with app.app_context():
        telas.servico().aplicar_carga(_carga())
    montadas = []
    original = telas.render_template

    def contar(nome, **kw):
        if nome == "cadastro/_lista_linhas.html":
            montadas.append(len(kw.get("linhas") or []))
        return original(nome, **kw)
    monkeypatch.setattr(telas, "render_template", contar)
    c = app.test_client()
    assert c.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    c.app_, c.montadas = app, montadas
    return c


def test_as_linhas_do_registro_mestre_sao_montadas_uma_vez_por_versao(cli):
    from nexus.cadastro import telas
    h1 = cli.get("/t/base/registro-mestre").get_data(as_text=True)
    h2 = cli.get("/t/base/registro-mestre").get_data(as_text=True)
    assert cli.montadas == [2] and h1 == h2 and "Altair" in h1 and "Brodowski 1" in h1
    assert 'class=""' not in h1 and '<span class="gc-num">2</span> de' in h1
    # outra busca, outras colunas: outra chave; a mesma de antes volta da memória
    assert "Brodowski 1" not in cli.get("/t/base/registro-mestre?q=altair").get_data(as_text=True)
    cli.get("/t/base/registro-mestre?cols=nome,codigo")
    cli.get("/t/base/registro-mestre")
    assert len(cli.montadas) == 3
    # gravou no cadastro (o arquivo mudou): as linhas são montadas de novo, com o que foi gravado
    with cli.app_.app_context():
        telas.servico().aplicar_carga(_carga(USINAS + [{"id": "3", "ordem": 3, "valores": {
            "nome": "Coração 1", "codigo": "THPN-COR100", "cliente": "1", "status": "OPERAÇÃO"}}]))
    h3 = cli.get("/t/base/registro-mestre").get_data(as_text=True)
    assert "Coração 1" in h3 and cli.montadas[-1] == 3


# ── o serviço do cadastro do PCM ──────────────────────────────────────────────────────────────────────────────
def test_o_pcm_decifra_o_cadastro_uma_vez_por_versao(tmp_path, monkeypatch):
    chave = gerar_chave()
    caminho = tmp_path / "cadastro.json"
    Servico(ArmazemLocal(caminho), Cofre(chave)).aplicar_carga(_carga())
    monkeypatch.setattr(A, "_SERVICOS", {})
    decifradas = []
    original = Servico._decifrar
    monkeypatch.setattr(Servico, "_decifrar", lambda self, ent, linha: decifradas.append(1) or original(self, ent, linha))
    cfg = {"NEXUS_CHAVE_CADASTRO": chave, "NEXUS_ARMAZEM_LOCAL": str(caminho)}
    assert A.servico(cfg) is A.servico(cfg)
    primeira = [l["UFV"] for l in A.linhas(A.servico(cfg))]
    n = len(decifradas)
    assert [l["UFV"] for l in A.linhas(A.servico(cfg))] == primeira == ["Thopen - Altair", "Thopen - Brodowski 1"]
    assert len(decifradas) == n                                   # a 2ª visita não decifra nada


# ── as usinas por dia do Gerar a semana ───────────────────────────────────────────────────────────────────────
def _usinas_por_dia_de_antes(regras, usinas_fracttal):
    """A conta como era até 19/10/2026 (o `casa` em todos os pares), para provar que o resultado é o mesmo."""
    valendo = {}
    for i, r in enumerate(regras):
        if r["tipo"] == "usina" and r.get("usina") and r.get("dias"):
            valendo[O.norm_usina(r["usina"])] = i
    from nexus.pcm import clientes
    m, saida = clientes.mapa(), []
    for f in usinas_fracttal:
        info = O.separar_nome(f)
        if not info:
            continue
        info["cliente"] = clientes.nome(info["cliente"], m)
        regra = next((i for chave, i in valendo.items() if O.casa(f, chave)), None)
        info["regra"] = regra
        info["dias"] = list(regras[regra]["dias"]) if regra is not None else list(O.DIAS)
        saida.append(info)
    saida.sort(key=lambda u: (O._sem_acento(u["cliente"]).lower(), O._sem_acento(u["nome"]).lower()))
    for u in saida:
        curto = O.norm_usina(u["nome"])
        outras = [x for x in saida if x is not u and O.casa(x["fracttal"], curto)]
        u["nome_regra"] = u["nome"] if not outras else u["fracttal"]
        u["divide"] = [x["nome"] for x in saida if x is not u and u["regra"] is not None and x["regra"] == u["regra"]]
    return saida


@pytest.mark.parametrize("texto", [
    "@usina Marabá 1 = seg, qua\n@usina Araçoiaba da Serra 1 = ter\n@usina Linhares 1 = sex\n",
    "@usina Marabá = seg\n@usina Marabá 1 = sex\n@usina Timon 1 = qua\n",
    "@usina Usina Que Não Existe = seg\n@usina (Sunpower) = ter\n",
    "",
])
def test_as_usinas_por_dia_dao_o_mesmo_que_antes(texto):
    regras = O.ler(texto)
    usinas = FRACTTAL + ["Thopen - Marabá 1 e 2 - PA", "Athon - Timon 10 - MA", "Axis - Cascavel 1 (Sunpower) - CE"]
    assert O.usinas_por_dia(regras, usinas) == _usinas_por_dia_de_antes(regras, usinas)


# ── o tipo do Fracttal no Quadro ──────────────────────────────────────────────────────────────────────────────
def test_o_indice_do_tipo_e_feito_uma_vez_por_leitura_da_gestao(monkeypatch):
    monkeypatch.setattr(Q, "_INDICE_TIPO", {"tarefas": None, "tipo": None})
    tarefas = [{"os": 15290, "tarefa": "Troca de módulos danificados", "tipo": "Corretiva"},
               {"os": 15291, "tarefa": "Roçada", "tipo": "Zeladoria"}]
    sem = {"rows": [{"os_id": "15290", "tarefa": "Troca de módulos danificados", "tipo": "Zeladoria"},
                    {"os_id": "15291", "tarefa": "Roçada", "tipo": "Zeladoria"}], "pendentes": []}
    normas = []
    original = Q._norm
    monkeypatch.setattr(Q, "_norm", lambda s: normas.append(1) or original(s))
    novo, n = Q.tipo_do_fracttal(sem, tarefas)
    assert n == 1 and [r["tipo"] for r in novo["rows"]] == ["Corretiva", "Zeladoria"]
    por_visita = len(normas)
    Q.tipo_do_fracttal(sem, tarefas)
    assert len(normas) - por_visita < por_visita                  # a 2ª visita não normaliza as tarefas de novo
    outra = [dict(t) for t in tarefas]                             # a Gestão PCM relida: índice novo
    assert Q.tipo_do_fracttal(sem, outra)[1] == 1 and Q._INDICE_TIPO["tarefas"] is outra
