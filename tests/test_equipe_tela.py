"""A tela Mapa de equipe da Usinas 360° (08/11/2026; `nexus/torres/campo/equipe_tela.py`), o Abrir rota pelo servidor, o
registro de quem abriu (LGPD) e o piloto, que só o administrador muda.

Quem vê é a regra escrita ao técnico: os setores PCM, COS, Performance, Supervisão Campo e Responsáveis UFV, e os
administradores, conferido DENTRO da rota (o portão por setor fica desligado nos testes, e a marca de outro setor em
Base → Acessos não abre a tela). A coordenada (do técnico ou da usina) nunca vai à página: o mapa e o percurso levam
só o x/y do SVG. Desde 10/11/2026 (Levi, pela sessão Nexus Field) a última posição de cada técnico vai ao mapa em toda
situação, também o parado fora de usina e o ponto de outro dia, e o "Ver percurso" desenha o período pedido.

Banco de mentira (`ApiPGFalsa`), relógio parado, coordenadas e pessoas inventadas; nada vai à rede."""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pg_falso import ApiPGFalsa
from test_campo_visao import _aba

from nexus.auth import setor_telas
from nexus.cadastro import setor_ids as SID
from nexus.cadastro.cifra import Cofre, gerar_chave
from nexus.campo import mapa_responsaveis as MR
from nexus.campo import visao
from nexus.campo.equipe import ABA_PILOTO, CAB_ACESSOS, LIVRO_PILOTO
from nexus.campo.equipe import municipios as MU
from nexus.campo.equipe import servico as S
from nexus.campo.equipe import situacao as SI
from nexus.campo.ligacao_cadastro import codigo_da_pessoa

CHAVE_CADASTRO = gerar_chave()
CHAVE_HMAC = "hmac-de-teste-do-mapa"
AGORA = datetime(2026, 11, 8, 15, 0, tzinfo=timezone.utc)          # 12:00 em Brasília
URL = "/t/campo/equipe"
URL_ROTA = "/t/campo/equipe/rota"
URL_PILOTO = "/t/campo/equipe/piloto"
# a lista de técnicos (o botão Técnico e Rotas): desde 10/11/2026 o painel ao lado do mapa abre nos Eventos do dia
TECNICOS = {"painel": "tecnicos"}

# as usinas, com casas incomuns: se alguma virar texto na página, o teste acha
USINA_A, USINA_B = 7, 8
COORDS = {"7": (-16.612345, -49.187654, "GO"), "8": (-17.334571, -48.712389, "GO")}
NOME_USINA = {USINA_A: "Usina Alfa Teste", USINA_B: "Usina Bravo Teste"}

# os técnicos do piloto, um por situação, e um técnico fora do piloto
NA_USINA, ANDANDO, FORA, SEM_SINAL, SEM_PERMISSAO, SEM_POSICAO, FORA_DO_PILOTO = 1, 2, 3, 4, 5, 6, 9
PONTO = {NA_USINA: ((-16.605173, -49.187654), 3, False),           # 0,8 km da Alfa, há 3 min
         ANDANDO: ((-16.981237, -48.954321), 1, True),             # na estrada, há 1 min
         FORA: ((-16.567381, -49.187643), 5, False),               # 5 km da Alfa, parado: a casa, o hotel
         SEM_SINAL: ((-17.331873, -48.712311), 40, False),         # na Bravo, há 40 min
         FORA_DO_PILOTO: ((-17.295127, -48.701263), 2, False)}
# o painel mostra o "Nome padrão" (o 1º e o último nome, `visao.nome_curto`): por isso nomes de duas palavras
NOME = {NA_USINA: "Naira Teste", ANDANDO: "Andre Teste", FORA: "Fabio Teste", SEM_SINAL: "Sinara Teste",
        SEM_PERMISSAO: "Pietra Teste", SEM_POSICAO: "Paulo Teste", FORA_DO_PILOTO: "Otavio Teste"}
PILOTO = (NA_USINA, ANDANDO, FORA, SEM_SINAL, SEM_PERMISSAO, SEM_POSICAO)
# a estrutura de O&M de 10/2026, como o cadastro a modela (`visao._Base`): a equipe é de uma região de campo, e o
# supervisor do técnico é o Supervisor de Campo da região da equipe dele. A Oeste só tem o técnico fora do piloto
CENTRO, LESTE, OESTE = 10, 11, 12
EQUIPE = {CENTRO: "Equipe Centro Teste", LESTE: "Equipe Leste Teste", OESTE: "Equipe Oeste Teste"}
SUP_CENTRO, SUP_LESTE, SUP_OESTE = 30, 31, 32
NOME_SUP = {SUP_CENTRO: "Sergio Teste", SUP_LESTE: "Silvia Teste", SUP_OESTE: "Sandro Teste"}
REGIAO = {CENTRO: (1, SUP_CENTRO), LESTE: (2, SUP_LESTE), OESTE: (3, SUP_OESTE)}       # equipe: (região, supervisor)
EQUIPE_DE = {NA_USINA: CENTRO, ANDANDO: CENTRO, FORA: CENTRO, SEM_SINAL: CENTRO, SEM_PERMISSAO: LESTE,
             SEM_POSICAO: LESTE, FORA_DO_PILOTO: OESTE}
# quem olha o mapa
PCM, ADMIN = 20, 21
EMAIL = {PCM: "pcm.teste@gridco.com.br", ADMIN: "admin.teste@gridco.com.br"}
OUTRO = "engenharia.teste@gridco.com.br"
DIGITOS = ("612345", "187654", "334571", "712389", "605173", "981237", "954321", "567381", "187643", "331873",
           "712311", "295127", "701263")


def _ficha(pid, nome, email=None, vinculo="Colaborador de campo", equipe_id=CENTRO):
    sensivel = {"nome": nome, "nome_padrao": nome, **({"email": email} if email else {})}
    return {"pessoa_id": pid, "vinculo": vinculo, "cargo": "Técnico O&M", "equipe_id": equipe_id, "status": "Ativo",
            "excluido": "não",
            "sensivel_cifrado": Cofre(CHAVE_CADASTRO).cifrar(json.dumps(sensivel), f"banco/pessoas/{pid}")}


def _decisao(pid, sim=True):
    return {"decisao_id": f"L{pid:011x}", "instante": "2026-11-07T12:00:00Z", "data_id": 20261107, "pessoa_id": pid,
            "no_piloto": 1 if sim else 0, "decidida_por_hmac": "hmac-de-teste"}


class Relogio:
    def __init__(self):
        self.agora = AGORA


@pytest.fixture
def relogio(monkeypatch):
    r = Relogio()
    monkeypatch.setattr(S, "_agora", lambda: r.agora)
    return r


@pytest.fixture
def banco(app, tmp_path, monkeypatch, relogio):
    api = ApiPGFalsa()
    fichas = [_ficha(pid, nome, equipe_id=EQUIPE_DE[pid]) for pid, nome in NOME.items()]
    fichas += [_ficha(PCM, "Analista Pcm Teste", EMAIL[PCM], vinculo="Colaborador"),
               _ficha(ADMIN, "Administradora Teste", EMAIL[ADMIN], vinculo="Colaborador")]
    fichas += [_ficha(sid, nome, vinculo="Colaborador", equipe_id=None) for sid, nome in NOME_SUP.items()]
    _aba(api, "cadastro_nexus", "pessoas", fichas)
    _aba(api, "cadastro_nexus", "equipes", [{"equipe_id": e, "nome": n, "regiao_campo_id": REGIAO[e][0]}
                                            for e, n in EQUIPE.items()])
    _aba(api, "cadastro_nexus", "regioes_campo", [{"regiao_campo_id": r, "nome": f"Região {r} Teste",
                                                   "supervisor_campo_id": s, "ordem": r} for r, s in REGIAO.values()])
    _aba(api, "cadastro_nexus", "usinas", [{"usina_id": u, "nome": n, "status": "OPERAÇÃO", "equipe_id": 10}
                                           for u, n in NOME_USINA.items()])
    _aba(api, LIVRO_PILOTO, ABA_PILOTO, [_decisao(p) for p in PILOTO])
    app.config.update(GRIDCO_DB_API="http://pg.falso", NEXUS_CHAVE_CADASTRO=CHAVE_CADASTRO,
                      NEXUS_DADOS=str(tmp_path / "dados"), NEXUS_PESSOA_HMAC=CHAVE_HMAC, GRIDCO_SQL_TOKEN="token-teste",
                      NEXUS_ADMINS=EMAIL[ADMIN])
    app.extensions["nexus_dados_sessao"] = api
    monkeypatch.setattr(MR, "coordenadas", lambda: (dict(COORDS), ""))
    visao.limpar()
    MU.limpar()
    yield api
    visao.limpar()
    MU.limpar()


@pytest.fixture
def setor(monkeypatch):
    """O setor de cada e-mail, como Base → Acessos → Pessoas e setores o daria; `None` = sem setor."""
    caixa = {EMAIL[PCM]: {"id": SID.PCM, "nome": "PCM"}, OUTRO: {"id": SID.ENGENHARIA, "nome": "Engenharia"}}
    monkeypatch.setattr(setor_telas, "setor_da_pessoa", lambda cfg, email, base, sessao: caixa.get(email))
    return caixa


@pytest.fixture
def pontos(app, banco):
    """O serviço com o último ponto de cada técnico, recebidos como as rotas do contrato recebem."""
    srv = S.do_app(app)
    for pid, ((lat, lon), minutos, mov) in PONTO.items():
        t = int((AGORA - timedelta(minutes=minutos)).timestamp() * 1000)
        lote = {"fuso": -180, "pontos": [{"t": t, "lat": lat, "lon": lon, "prec": 8.0, "vel": 1.5 if mov else 0.0,
                                          "mov": mov}]}
        assert srv.receber(pid, lote, AGORA) == 1
    srv.receber(SEM_PERMISSAO, {"fuso": -180, "permissao": "sem", "pontos": []}, AGORA - timedelta(hours=1))
    srv.registro.novos()                          # a fila de acessos começa vazia
    return srv


def _entrar(cliente, email, admin=False):
    with cliente.session_transaction() as s:
        s["logado"], s["admin"] = True, admin
        s["usuario"] = {"email": email, "nome": "Pessoa de Teste", "perfil": ""}
    return cliente


def _html(cliente, url=URL, **kw):
    r = cliente.get(url, **kw)
    return r.status_code, r.get_data(as_text=True)


def _svg(html):
    return html.split('<svg class="eq-svg', 1)[1].split("</svg>", 1)[0]          # o do mapa ou o do percurso


def _no_svg(svg, pid) -> bool:
    """O ponto do técnico está no desenho? O link dele abre o percurso do dia (10/11/2026): `tecnico=N&de=...&ate=...`."""
    return bool(re.search(rf'tecnico={pid}(?:&amp;|")', svg))


def _acessos(srv):
    return [dict(zip(CAB_ACESSOS, linha)) for linha in srv.registro.novos()]


# ── quem vê ────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_tela_esta_logo_depois_da_visao_do_cliente_e_e_dos_cinco_setores():
    from nexus.torres.campo import TORRE
    ids = [t.id for t in TORRE.telas]
    assert ids.index("equipe") == ids.index("cliente") + 1
    t = TORRE.tela("equipe")
    assert t.nome == "Mapa de equipe" and set(t.do_setor) == {SID.PCM, SID.COS, SID.PERFORMANCE,
                                                               SID.SUPERVISAO_CAMPO, SID.RESPONSAVEL_UFV}


def test_so_os_cinco_setores_e_o_admin_veem(app, cliente, pontos, setor, monkeypatch):
    assert not setor_telas.ligado(app.config)                         # o portão por setor desligado, como no teste
    for sid in (SID.PCM, SID.COS, SID.PERFORMANCE, SID.SUPERVISAO_CAMPO, SID.RESPONSAVEL_UFV):
        setor[EMAIL[PCM]] = {"id": sid, "nome": f"Setor {sid}"}
        st, html = _html(_entrar(cliente, EMAIL[PCM]))
        assert st == 200 and NOME[NA_USINA] in html, sid
    for sid in (SID.ENGENHARIA, SID.ZELADORIA, SID.SEGURANCA, SID.CHAMADOS):
        setor[EMAIL[PCM]] = {"id": sid, "nome": f"Setor {sid}"}
        st, html = _html(_entrar(cliente, EMAIL[PCM]))
        assert st == 403 and NOME[NA_USINA] not in html, sid
        assert "PCM, COS, Performance, Supervisão Campo e Responsáveis UFV" in html
    pontos.registro.novos()
    # de outro setor, nem a rota nem o piloto
    _entrar(cliente, OUTRO)
    assert _html(cliente)[0] == 403
    assert cliente.get(URL_ROTA, query_string={"tecnico": NA_USINA, "usina": USINA_B}).status_code == 403
    assert cliente.post(URL_PILOTO, data={"pessoa_id": FORA_DO_PILOTO, "no_piloto": "sim"}).status_code == 403
    assert _acessos(pontos) == []                                     # a recusa não conta como acesso
    # sem setor, e com o setor que não se lê
    setor.pop(EMAIL[PCM])
    assert _html(_entrar(cliente, EMAIL[PCM]))[0] == 403

    def ilegivel(cfg, email, base, sessao):
        raise RuntimeError("setores ilegíveis")
    monkeypatch.setattr(setor_telas, "setor_da_pessoa", ilegivel)
    st, html = _html(_entrar(cliente, EMAIL[PCM]))
    assert st == 403 and "Não consegui ler o seu setor" in html
    # o administrador vê, com ou sem setor (nem pergunta o setor)
    st, html = _html(_entrar(cliente, EMAIL[ADMIN], admin=True))
    assert st == 200 and NOME[NA_USINA] in html


def test_sem_a_chave_hmac_so_o_administrador_ve(app, cliente, pontos, setor):
    app.config["NEXUS_PESSOA_HMAC"] = ""
    st, html = _html(_entrar(cliente, EMAIL[PCM]))
    assert st == 403 and "só o administrador" in html
    assert _html(_entrar(cliente, EMAIL[ADMIN], admin=True))[0] == 200


def test_sem_a_chave_do_cadastro_a_tela_avisa(logado):
    st, html = _html(logado)
    assert st == 200 and "Mapa de equipe" in html and "NEXUS_CHAVE_CADASTRO" in html
    assert "Em construção" not in html


# ── a coordenada nunca na página ─────────────────────────────────────────────────────────────────────────────────────
def test_a_pagina_e_o_json_nao_tem_coordenada(cliente, pontos, setor):
    _entrar(cliente, EMAIL[PCM])
    for pid in (None, *PILOTO):
        st, html = _html(cliente, query_string={"tecnico": pid} if pid else None)
        assert st == 200
        achados = [d for d in DIGITOS if d in html]
        assert achados == [], (pid, achados)
        for c in [*COORDS.values(), *(p[0] for p in PONTO.values())]:
            for v in c[:2]:
                assert f"{abs(v):.4f}" not in html and f"{abs(v):.4f}".replace(".", ",") not in html, (pid, v)
    # as recusas da rota também não dizem coordenada nenhuma
    for pid in (SEM_POSICAO, SEM_PERMISSAO):
        r = cliente.get(URL_ROTA, query_string={"tecnico": pid, "usina": USINA_A})
        assert r.status_code == 404 and not [d for d in DIGITOS if d in r.get_data(as_text=True)]
    # o "!" diz a regra que vale, sem prometer o que não se cumpre (revisão final de 08/11/2026): desde 11/11/2026, com o
    # mapa de verdade, a coordenada de quem aparece vai à página depois do registro (Levi: "Pode trocar"), e o texto diz isso
    assert "precisão do GPS" in html and "depois de gravado o registro" in html and "nunca traz a latitude" not in html


@pytest.mark.parametrize("valor", ["²", "1" * 5000], ids=["sobrescrito", "5000_algarismos"])
def test_numero_torto_na_url_nunca_e_500(cliente, pontos, setor, valor):
    """`"²".isdigit()` é True e o `int("²")` quebra; o número de 5000 algarismos passa do teto de algarismos do `int`
    (Python 3.11+) e quebra também: os dois eram 500. Só algarismos ASCII, até 12 (revisão final de 08/11/2026)."""
    _entrar(cliente, EMAIL[ADMIN], admin=True)
    assert cliente.get(URL, query_string={"tecnico": valor}).status_code == 200          # sem técnico escolhido
    assert cliente.get(URL_ROTA, query_string={"tecnico": valor, "usina": USINA_A}).status_code == 404
    assert cliente.get(URL_ROTA, query_string={"tecnico": NA_USINA, "usina": valor}).status_code == 404
    assert cliente.post(URL_PILOTO, data={"pessoa_id": valor, "no_piloto": "sim"}).status_code == 400


def test_a_pre_carga_nunca_abre_o_mapa(app):
    """A pré-carga abre as telas por dentro, com uma sessão de administrador, e a volta do boot abre todas: no Mapa de
    equipe isso subiria o serviço e gravaria na trilha da LGPD um "abriu_mapa" que ninguém abriu (revisão final de
    08/11/2026)."""
    from nexus.auth import pre_carga as PC
    assert "campo/equipe" in PC.SEM_PRE_CARGA and "campo/equipe" not in PC.aqueciveis(app)


def test_o_mapa_desenha_a_ultima_posicao_de_quem_tem_ponto_tambem_o_parado_fora_de_usina(cliente, pontos, setor):
    """10/11/2026 (Levi: "se tem dados de localização tem que estar mostrando no nexus"): toda última posição dos 7 dias
    vai ao mapa, no lugar exato e na cor da situação; o parado fora de usina no cinza. Quem não tem ponto (o sem
    permissão que nunca mandou, o sem posição) fica só na lista."""
    _, html = _html(_entrar(cliente, EMAIL[PCM]), query_string=TECNICOS)
    svg = _svg(html)
    for pid, tom in ((NA_USINA, "ok"), (ANDANDO, "info"), (SEM_SINAL, "alerta"), (FORA, "neutro")):
        assert re.search(rf'tecnico={pid}&amp;[^"]*"[^>]*><circle class="eq-p eq-p--{tom}"', svg), pid
    for pid in (SEM_PERMISSAO, SEM_POSICAO, FORA_DO_PILOTO):
        assert not _no_svg(svg, pid), pid
    assert svg.count('class="eq-u"') == 2                              # as duas usinas, como marca discreta
    # os nomes vêm decifrados do cadastro, a equipe e a hora de Brasília
    assert NOME[NA_USINA] in html and "Equipe Centro Teste" in html
    # quem não está no piloto não aparece, nem como "sem posição hoje"
    assert NOME[FORA_DO_PILOTO] not in html
    lado = html.split('class="eq-lado"', 1)[1]
    sem_pos = lado.split("Sem posição hoje", 1)[1]
    assert NOME[SEM_POSICAO] in sem_pos


def test_o_painel_do_tecnico_tem_a_equipe_a_hora_e_a_usina_mais_perto(cliente, pontos, setor):
    _, html = _html(_entrar(cliente, EMAIL[PCM]), query_string={"tecnico": NA_USINA})
    lado = html.split('class="eq-lado"', 1)[1]
    assert NOME[NA_USINA] in lado and "Equipe Centro Teste" in lado and "Na usina" in lado
    assert "11:57" in lado                                            # 14:57 UTC = 11:57 de Brasília
    assert "a 0,8 km da Usina Alfa Teste" in lado
    assert 'action="/t/campo/equipe/rota"' in lado and f'name="tecnico" value="{NA_USINA}"' in lado
    for uid, nome in NOME_USINA.items():
        assert f'<option value="{uid}">{nome}</option>' in lado
    assert "eq-p--sel" in _svg(html)
    # sem sinal: a rota sai do último ponto, e o painel diz há quanto tempo
    _, html = _html(cliente, query_string={"tecnico": SEM_SINAL})
    lado = html.split('class="eq-lado"', 1)[1]
    assert "Sem sinal há 40 min" in lado and 'action="/t/campo/equipe/rota"' in lado


def test_parado_fora_de_usina_no_mapa_com_a_rota(cliente, pontos, setor):
    """Até 09/11/2026 o parado fora de usina ficava fora do mapa e sem rota ("o mapa não mostra onde o técnico mora");
    o Levi trocou a decisão em 10/11/2026: ele vai ao mapa no cinza, com a distância de uma casa e o Abrir rota."""
    _, html = _html(_entrar(cliente, EMAIL[PCM]), query_string=TECNICOS)
    assert _no_svg(_svg(html), FORA)
    lado = html.split('class="eq-lado"', 1)[1]
    fora = lado.split("Parados fora de usina", 1)[1].split("</section>", 1)[0]
    assert NOME[FORA] in fora and "GO" in fora and "a 5,0 km da Usina Alfa Teste" in fora
    # o painel dele: o estado, a distância e o Abrir rota
    _, html = _html(cliente, query_string={"tecnico": FORA})
    lado = html.split('class="eq-lado"', 1)[1]
    assert NOME[FORA] in lado and "Parado fora de usina" in lado and "GO" in lado
    assert 'action="/t/campo/equipe/rota"' in lado and "eq-p--sel" in _svg(html)


def test_o_parado_fora_de_usina_mostra_a_cidade_e_o_estado(app, cliente, pontos, setor):
    """A cidade sai da malha de municípios do IBGE no disco (Task 7b): "Cidade/UF". Sem a malha (nos testes o IBGE
    nunca é chamado de verdade), só o estado, como no teste de cima."""
    from test_equipe_municipios import IBGE
    # a malha de Goiás baixada antes (a mentira do IBGE, numa "thread" que termina na hora), e o processo reiniciado:
    # a tela lê só o disco
    pasta = Path(app.config["NEXUS_DADOS"])
    assert MU.cidade(-16.8123, -49.8321, "GO", pasta=pasta, baixar=IBGE(), iniciar=lambda alvo: alvo()) is None
    assert (pasta / "equipe" / "ibge" / "GO.json").exists()
    MU.limpar()
    _, html = _html(_entrar(cliente, EMAIL[PCM]), query_string=TECNICOS)
    fora = html.split('class="eq-lado"', 1)[1].split("Parados fora de usina", 1)[1].split("</section>", 1)[0]
    assert NOME[FORA] in fora and "Cidade Um Teste/GO" in fora
    _, html = _html(cliente, query_string={"tecnico": FORA})
    lado = html.split('class="eq-lado"', 1)[1]
    assert "<dt>Cidade</dt><dd>Cidade Um Teste/GO</dd>" in lado
    # quem está na usina não ganha cidade nenhuma no painel dele (a cidade do outro está no quadro de eventos)
    _, html = _html(cliente, query_string={"tecnico": NA_USINA})
    assert "Cidade Um Teste" not in html.split('class="eq-lado"', 1)[1].split("</aside>", 1)[0]


def test_a_pagina_nunca_baixa_do_ibge_e_a_cidade_vem_na_proxima(cliente, pontos, setor, monkeypatch):
    """Revisão de 08/11/2026: a abertura do mapa nunca espera o IBGE. Sem a malha da UF no disco, a página sai já com
    só o estado e manda UMA ida ao IBGE para o fundo; a próxima abertura tem a cidade."""
    from test_equipe_municipios import IBGE, Fundo
    ibge, fundo = IBGE(), Fundo()
    monkeypatch.setattr(MU, "_baixador", lambda: ibge)
    monkeypatch.setattr(MU, "_em_fundo", fundo)
    _, html = _html(_entrar(cliente, EMAIL[PCM]), query_string=TECNICOS)
    fora = html.split('class="eq-lado"', 1)[1].split("Parados fora de usina", 1)[1].split("</section>", 1)[0]
    assert NOME[FORA] in fora and "· GO ·" in fora and "/GO" not in fora
    assert ibge.pedidos == [] and len(fundo.alvos) == 1               # a página não baixou; uma ida em fundo
    _html(cliente, query_string={"tecnico": FORA})                     # a ida corre: não dispara outra
    assert len(fundo.alvos) == 1
    fundo.terminar()
    _, html = _html(cliente, query_string=TECNICOS)
    assert "Cidade Um Teste/GO" in html.split('class="eq-lado"', 1)[1] and len(ibge.pedidos) == 2


# ── o anel do técnico escolhido (08/11/2026) ─────────────────────────────────────────────────────────────────────────
def test_o_anel_do_escolhido_e_branco_com_halo_escuro_e_se_ve_nos_dois_temas():
    """Levi, 08/11/2026: "Ao clicar no técnico o círculo que fica em volta do técnico ser branco, esse verde não está
    dando contraste!". O anel é branco nos dois temas, por token (a cor fixa no CSS é proibida, `test_tema`), e um halo
    escuro fino por fora o deixa visível no claro, onde o branco sobre o cartão cinza some. A conta é a do contraste de
    componente da WCAG (3:1): no escuro, o branco contra o cartão; no claro, o halo contra o cartão; e o anel contra o
    halo nos dois."""
    from test_tema import SELETOR_CLARO, SELETOR_ESCURO, _razao, _rgba, _tokens
    css = re.sub(r"/\*.*?\*/", "", (Path(__file__).resolve().parent.parent / "nexus" / "static" / "campo.css")
                 .read_text(encoding="utf-8"), flags=re.S)

    def regra(seletor):
        return re.search(r"(?:^|[}\s])" + re.escape(seletor) + r"\{([^}]*)\}", css).group(1)

    def valor(corpo, prop):
        return re.search(r"(?:^|;)\s*" + re.escape(prop) + r"\s*:\s*([^;]+)", corpo).group(1).strip()
    sel, halo, local = regra(".eq-p--sel"), regra(".eq-halo"), regra(".eq-svg")
    assert valor(sel, "stroke") == "var(--eq-anel)" and "--verde" not in sel
    assert valor(halo, "stroke") == "var(--eq-halo)" and valor(halo, "pointer-events") == "none"
    # o halo é mais largo que o anel: a sobra (metade da diferença) é o contorno escuro que fica de fora
    assert float(valor(halo, "stroke-width").rstrip("px")) - float(valor(sel, "stroke-width").rstrip("px")) >= 3
    anel_tok = re.fullmatch(r"var\((--[\w-]+)\)", valor(local, "--eq-anel")).group(1)
    halo_tok = re.fullmatch(r"var\((--[\w-]+)\)", valor(local, "--eq-halo")).group(1)
    for tema in (SELETOR_ESCURO, SELETOR_CLARO):
        t = _tokens(tema)
        branco, escuro, cartao = _rgba(t[anel_tok]), _rgba(t[halo_tok]), _rgba(t["--superficie"])
        assert branco[:3] == [255, 255, 255], tema                     # branco de verdade, nos dois temas
        assert _razao(branco, escuro) >= 3, tema
        assert max(_razao(branco, cartao), _razao(escuro, cartao)) >= 3, tema
    assert _razao(_rgba(_tokens(SELETOR_CLARO)[halo_tok]), _rgba(_tokens(SELETOR_CLARO)["--superficie"])) >= 3
    # o ponto e o halo têm a MESMA escala, a da tela (11/11/2026: o --eq-un do campo-percurso.js no lugar do 1,8 vez do
    # celular): o halo cresce junto com o ponto em qualquer tela e em qualquer zoom, senão ficaria dentro dele
    assert all("transform:scale(calc(var(--eq-un) * .75))" in regra(r) for r in (".eq-p", ".eq-halo"))


def test_o_escolhido_tem_o_halo_e_vai_por_cima_dos_outros(cliente, pontos, setor):
    """O halo é um círculo atrás do ponto escolhido (o SVG não tem dois contornos num círculo só), e o escolhido é
    desenhado por último: dois técnicos na mesma usina caem no mesmo lugar, e o anel ficaria embaixo do outro."""
    _entrar(cliente, EMAIL[PCM])
    svg = _svg(_html(cliente)[1])
    assert "eq-halo" not in svg and "eq-p--sel" not in svg                # ninguém escolhido
    svg = _svg(_html(cliente, query_string={"tecnico": NA_USINA})[1])
    pontos_svg = svg.split('<g class="eq-pontos">', 1)[1]
    links = re.findall(r"<a href=[^>]*>.*?</a>", pontos_svg, flags=re.S)
    assert len(links) == 4 and _no_svg(links[-1], NA_USINA)                # o escolhido por último
    assert re.search(r'<circle class="eq-halo" cx="[^"]+" cy="[^"]+" r="11"/><circle class="eq-p eq-p--ok eq-p--sel"',
                     links[-1])
    assert svg.count("eq-halo") == 1 and svg.count("eq-p--sel") == 1


# ── o filtro por supervisor e por equipe (08/11/2026) ────────────────────────────────────────────────────────────────
def _opcoes(html, nome):
    corpo = html.split(f'name="{nome}"', 1)[1].split("</select>", 1)[0]
    return re.findall(r'<option value="([^"]*)"(?: selected)?>([^<]*)</option>', corpo)


def _no_painel(html):
    lado = html.split('class="eq-lado"', 1)[1]
    return {pid for pid, nome in NOME.items() if nome in lado}


def test_os_filtros_listam_so_o_supervisor_e_a_equipe_de_quem_esta_no_piloto(cliente, pontos, setor):
    """Levi, 08/11/2026: "Opção de filtrar por supervisor ou equipe". As opções são as de quem o mapa mostra (técnico de
    campo ativo E no piloto), com o nome do cadastro: o supervisor (o Supervisor de Campo da região da equipe) e a equipe
    que só têm o técnico de fora do piloto não entram."""
    _, html = _html(_entrar(cliente, EMAIL[PCM]))
    assert _opcoes(html, "supervisor") == [("", "Todos os supervisores"), (str(SUP_CENTRO), NOME_SUP[SUP_CENTRO]),
                                           (str(SUP_LESTE), NOME_SUP[SUP_LESTE])]
    assert _opcoes(html, "equipe") == [("", "Todas as equipes"), (str(CENTRO), EQUIPE[CENTRO]),
                                       (str(LESTE), EQUIPE[LESTE])]
    assert NOME_SUP[SUP_OESTE] not in html and EQUIPE[OESTE] not in html
    # sem JavaScript, o botão Filtrar; com ele, a troca do select já envia (o mesmo da Visão do cliente)
    form = re.search(r'<form class="cn-filtros eq-filtros"[^>]*>(.*?)</form>', html, flags=re.S)
    assert 'method="get"' in form.group(0) and form.group(1).count('onchange="this.form.submit()"') == 2
    assert "<noscript><button" in form.group(1)


def test_o_filtro_estreita_o_mapa_a_lista_e_o_resumo(cliente, pontos, setor):
    _entrar(cliente, EMAIL[PCM])
    assert _no_painel(_html(cliente, query_string=TECNICOS)[1]) == set(PILOTO)   # sem filtro: todos
    # a Equipe Leste: os dois de lá, nenhum no mapa (sem permissão e sem posição ficam só na lista)
    _, html = _html(cliente, query_string={"equipe": LESTE, **TECNICOS})
    assert _no_painel(html) == {SEM_PERMISSAO, SEM_POSICAO} and "tecnico=" not in _svg(html)
    resumo = html.split('class="eq-resumo"', 1)[1].split("</p>", 1)[0]
    assert "1 sem permissão" in resumo and "1 sem posição hoje" in resumo and "na usina" not in resumo
    assert f'<option value="{LESTE}" selected>' in html
    # o link do técnico leva o filtro junto, e o "Ver todos" do painel dele volta ao filtro, não a todos
    assert f'href="/t/campo/equipe?tecnico={SEM_POSICAO}&amp;equipe={LESTE}"' in html
    _, html = _html(cliente, query_string={"equipe": LESTE, "tecnico": SEM_POSICAO})
    assert f'href="/t/campo/equipe?painel=tecnicos&amp;equipe={LESTE}">Ver todos os técnicos' in html
    # o técnico de fora do filtro não abre o painel dele
    _, html = _html(cliente, query_string={"equipe": LESTE, "tecnico": NA_USINA})
    assert "eq-det" not in html and NOME[NA_USINA] not in html
    # o supervisor da Centro: os quatro dela, todos no mapa (desde 10/11/2026 o parado fora de usina também)
    _, html = _html(cliente, query_string={"supervisor": SUP_CENTRO, **TECNICOS})
    assert _no_painel(html) == {NA_USINA, ANDANDO, FORA, SEM_SINAL}
    svg = _svg(html)
    assert all(re.search(rf'tecnico={p}&amp;[^"]*supervisor={SUP_CENTRO}"', svg)
               for p in (NA_USINA, ANDANDO, SEM_SINAL, FORA))
    assert f'<option value="{SUP_CENTRO}" selected>' in html
    # os dois juntos valem juntos: o supervisor da Centro e a equipe Leste não têm ninguém, e a tela diz
    _, html = _html(cliente, query_string={"supervisor": SUP_CENTRO, "equipe": LESTE, **TECNICOS})
    assert _no_painel(html) == set() and "Nenhum técnico do piloto neste filtro." in html


@pytest.mark.parametrize("pedido", [{"supervisor": 999}, {"equipe": 999}, {"supervisor": SUP_OESTE}, {"equipe": OESTE},
                                    {"supervisor": "x"}, {"equipe": "²"}, {"supervisor": "1" * 5000},
                                    {"equipe": "", "supervisor": ""}],
                         ids=["sup_999", "eq_999", "sup_fora_do_piloto", "eq_fora_do_piloto", "letra", "sobrescrito",
                              "5000_algarismos", "vazios"])
def test_id_desconhecido_no_filtro_mostra_todos_sem_erro(cliente, pontos, setor, pedido):
    """O id que não está nas opções (não existe, é de quem está fora do piloto, ou vem torto) não filtra: a tela mostra
    todos, sem 500 e sem nada marcado no select."""
    st, html = _html(_entrar(cliente, EMAIL[PCM]), query_string={**pedido, **TECNICOS})
    assert st == 200 and _no_painel(html) == set(PILOTO)
    assert " selected>" not in html.split('class="cn-filtros eq-filtros"', 1)[1].split("</form>", 1)[0]


# ── o Abrir rota ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_abrir_rota_redireciona_para_o_google_e_registra_o_acesso(cliente, pontos, setor):
    _entrar(cliente, EMAIL[PCM])
    r = cliente.get(URL_ROTA, query_string={"tecnico": NA_USINA, "usina": USINA_B})
    (lat, lon), _, _ = PONTO[NA_USINA]
    assert r.status_code == 302
    assert r.headers["Location"] == SI.url_da_rota((lat, lon), COORDS["8"][:2])
    assert r.headers["Location"].startswith("https://www.google.com/maps/dir/?api=1&origin=")
    assert r.headers["Cache-Control"] == "no-store" and r.headers["Referrer-Policy"] == "no-referrer"
    acesso = _acessos(pontos)
    assert [(a["acao"], a["alvo_pessoa_id"], a["usina_id"]) for a in acesso] == [("abriu_rota", NA_USINA, USINA_B)]
    assert acesso[0]["pessoa_id"] == PCM and acesso[0]["pessoa_hmac"] == codigo_da_pessoa(CHAVE_HMAC, EMAIL[PCM])
    assert EMAIL[PCM] not in repr(acesso) and "Teste" not in repr(acesso)
    # andando, sem sinal (do último ponto, que era na usina) e, desde 10/11/2026, parado fora de usina: a rota abre
    for pid in (ANDANDO, SEM_SINAL, FORA):
        r = cliente.get(URL_ROTA, query_string={"tecnico": pid, "usina": USINA_A})
        assert r.status_code == 302 and r.headers["Location"].startswith("https://www.google.com/maps/dir/"), pid
    pontos.registro.novos()
    # sem permissão, sem posição, fora do piloto, usina ou técnico que não existe: 404, sem registro
    for pid, uid in ((SEM_PERMISSAO, USINA_A), (SEM_POSICAO, USINA_A), (FORA_DO_PILOTO, USINA_A),
                     (NA_USINA, 99), (NA_USINA, "x"), ("x", USINA_A)):
        assert cliente.get(URL_ROTA, query_string={"tecnico": pid, "usina": uid}).status_code == 404, (pid, uid)
    assert _acessos(pontos) == []
    # o pedido que vem de outro site não abre a rota (nem vira registro de quem não clicou)
    r = cliente.get(URL_ROTA, query_string={"tecnico": NA_USINA, "usina": USINA_B},
                    headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403 and _acessos(pontos) == []


def test_abrir_o_mapa_registra_o_acesso(cliente, pontos, setor):
    _entrar(cliente, EMAIL[PCM])
    _html(cliente)
    _html(cliente, query_string={"tecnico": ANDANDO})
    _html(cliente, query_string={"tecnico": FORA_DO_PILOTO})          # quem não está no mapa não vira alvo
    acesso = _acessos(pontos)
    assert [(a["acao"], a["alvo_pessoa_id"]) for a in acesso] == [("abriu_mapa", None), ("abriu_mapa", ANDANDO),
                                                                  ("abriu_mapa", None)]
    hmac_pcm = codigo_da_pessoa(CHAVE_HMAC, EMAIL[PCM])
    assert all(a["pessoa_id"] == PCM and a["pessoa_hmac"] == hmac_pcm and a["usina_id"] is None for a in acesso)
    assert all(a["instante"] == "2026-11-08T15:00:00Z" and a["data_id"] == 20261108 for a in acesso)
    assert EMAIL[PCM] not in repr(acesso)


def test_quem_abriu_e_achado_pelo_email_exato_e_nao_pelo_nome(cliente, pontos, setor):
    """A trilha da LGPD não pode gravar o homônimo (revisão final de 08/11/2026): o `pessoa_do_login`, sem o e-mail no
    cadastro, acha pelo nome tirado do próprio e-mail (andre.teste@ -> "andre teste"), e o técnico Andre Teste ficaria
    registrado como quem abriu o mapa. Sem a ficha do e-mail exato, só o código do e-mail identifica."""
    email = "andre.teste@gridco.com.br"                       # nenhuma ficha tem este e-mail
    setor[email] = {"id": SID.COS, "nome": "COS"}              # quem abre é do COS
    assert _html(_entrar(cliente, email))[0] == 200
    (a,) = _acessos(pontos)
    assert a["pessoa_id"] is None and a["pessoa_hmac"] == codigo_da_pessoa(CHAVE_HMAC, email)


def test_sem_gravar_o_registro_o_mapa_e_a_rota_nao_abrem(cliente, pontos, setor, monkeypatch):
    """O registro da LGPD vai a um jornal em disco antes de o mapa ou a rota abrir: sem conseguir gravá-lo (o disco
    cheio), nada abre, e a posição não sai do servidor sem a trilha."""
    def disco_cheio(*a, **k):
        raise OSError("disco cheio (teste)")
    monkeypatch.setattr(pontos.registro, "acrescentar", disco_cheio)
    _entrar(cliente, EMAIL[PCM])
    st, html = _html(cliente)
    assert st == 503 and NOME[NA_USINA] not in html and "registro" in html
    r = cliente.get(URL_ROTA, query_string={"tecnico": NA_USINA, "usina": USINA_B})
    assert r.status_code == 503 and "Location" not in r.headers


# ── o ponto de outro dia e o Ver percurso (10/11/2026) ───────────────────────────────────────────────────────────
# o percurso da manhã do técnico andando (além do ponto de há 1 min), com casas incomuns: se alguma virar texto, o teste
# acha
MANHA = (((-16.913579, -48.924681), 3 * 60, True), ((-16.957913, -48.946813), 2 * 60, False),
         ((-16.968024, -48.951357), 60, True))
DIGITOS_MANHA = ("913579", "924681", "957913", "946813", "968024", "951357")


def _receber(srv, pid, pares, agora=AGORA):
    lote = {"fuso": -180, "pontos": [{"t": int((agora - timedelta(minutes=m)).timestamp() * 1000), "lat": lat,
                                      "lon": lon, "prec": 8.0, "mov": mov} for (lat, lon), m, mov in pares]}
    assert srv.receber(pid, lote, agora) == len(pares)


@pytest.fixture
def manha(pontos):
    _receber(pontos, ANDANDO, MANHA)
    pontos.registro.novos()
    return pontos


def test_o_ponto_de_outro_dia_vai_ao_mapa_marcado_e_sem_rota(cliente, pontos, setor):
    """O trajeto de teste de 09/11 chegou ao banco e a tela de 10/11 não mostrou nada: o ponto de ontem era só
    "sem posição hoje" na lista. Desde 10/11/2026 a última posição de outro dia (até 7 dias) vai ao mapa marcada (o
    contorno), com a hora; a rota não sai dela (não é de onde o técnico sai hoje)."""
    _receber(pontos, SEM_POSICAO, [((-16.712468, -49.013579), 16 * 60, False)])     # ontem às 20:00 de Brasília
    pontos.registro.novos()
    _, html = _html(_entrar(cliente, EMAIL[PCM]))
    assert re.search(rf'tecnico={SEM_POSICAO}&amp;[^"]*"[^>]*><circle class="eq-p eq-p--neutro eq-p--velho"',
                     _svg(html))
    _, html = _html(cliente, query_string={"tecnico": SEM_POSICAO})
    lado = html.split('class="eq-lado"', 1)[1]
    assert "Sem posição hoje" in lado and "07/11 às 20:00" in lado
    assert 'action="/t/campo/equipe/rota"' not in lado and 'name="de"' in lado          # sem rota, com o percurso
    assert cliente.get(URL_ROTA, query_string={"tecnico": SEM_POSICAO, "usina": USINA_A}).status_code == 404
    assert "712468" not in html and "013579" not in html


def test_ver_percurso_desenha_o_periodo_na_ordem_com_a_hora_e_registra(cliente, manha, setor):
    """Levi, 10/11/2026: "consegue ver o percurso que aquela pessoa fez em determinado período de dias e horas!". O
    período vai em dias e horas de Brasília (`de` e `ate`); o mapa desenha só o percurso (a linha na ordem, os pontos e a
    hora), o painel lista cada ponto com a hora, e a abertura entra no registro da LGPD com o período, antes de a página
    sair. Nenhuma coordenada na página."""
    _entrar(cliente, EMAIL[PCM])
    # o painel do técnico já traz o formulário, com o dia dele de 6h até agora e o limite dos 7 dias
    _, html = _html(cliente, query_string={"tecnico": ANDANDO})
    form = re.search(r'<form class="eq-perc-form".*?</form>', html, flags=re.S).group(0)
    assert 'name="de" value="2026-11-08T06:00"' in form and 'name="ate" value="2026-11-08T12:00"' in form
    assert 'min="2026-11-01T12:00"' in form and 'max="2026-11-08T12:00"' in form
    assert f'name="tecnico" value="{ANDANDO}"' in form and "Ver percurso" in form
    manha.registro.novos()
    st, html = _html(cliente, query_string={"tecnico": ANDANDO, "de": "2026-11-08T06:00", "ate": "2026-11-08T12:00"})
    assert st == 200
    svg = _svg(html)
    assert svg.count('<polyline class="eq-perc-linha"') == 1
    assert svg.count('class="eq-perc-p') == 4                           # os 3 da manhã e o de há 1 min
    assert "tecnico=" not in svg                                        # os outros técnicos saem do desenho
    # a hora de cada ponto no título de cada um, na ordem
    assert [h for h in re.findall(r"<title>(\d\d:\d\d)", svg)] == ["09:00", "10:00", "11:00", "11:59"]
    # o mapa inteiro primeiro, com o zoom do navegador (Levi, 10/11/2026): o svg diz o foco, a escala e os níveis, e a
    # tela traz os botões e o script do zoom
    cab = html.split('<svg class="eq-svg', 1)[1].split(">", 1)[0]
    assert all(a in cab for a in ("data-eq-perc", "data-foco=", "data-km=", "data-niveis=", "data-min="))
    assert all(f'data-eq-zoom="{z}"' in html for z in ("mais", "menos", "percurso", "inteiro"))
    assert "campo-percurso.js" in html
    lado = html.split('class="eq-lado"', 1)[1]
    # a lista conta o percurso por usina (Levi, 11/11/2026: "deve ser mais generalista por exemplo 'Chegou na UFV X',
    # 'Saiu da Usina X'"; `eventos.do_percurso`): andando às 9h, parado fora de usina às 10h, andando até as 11:59
    itens = re.findall(r'<li class="eq-perc-item eq-perc-item--(\w+)">(.*?)</li>', lado, flags=re.S)
    assert [(t, re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", i)).strip()) for t, i in itens] == [
        ("inicio", "09:00 Primeira posição, em deslocamento"), ("parado", "10:00 Parado fora de usina"),
        ("ultimo", "11:59 Última posição, em deslocamento")]
    assert "4 pontos" in lado and "Fechar o percurso" in lado
    assert not [d for d in (*DIGITOS, *DIGITOS_MANHA) if d in html]
    (a,) = _acessos(manha)
    assert (a["acao"], a["alvo_pessoa_id"], a["pessoa_id"], a["periodo_de"], a["periodo_ate"]) == \
        ("abriu_percurso", ANDANDO, PCM, "2026-11-08T09:00:00Z", "2026-11-08T15:00:00Z")
    # o período sem ponto: a tela diz, o mapa de sempre volta, e a abertura também fica registrada
    _, html = _html(cliente, query_string={"tecnico": ANDANDO, "de": "2026-11-07T06:00", "ate": "2026-11-07T22:00"})
    assert "Nenhum ponto de Andre Teste neste período" in html and "eq-perc-linha" not in html
    assert [x["acao"] for x in _acessos(manha)] == ["abriu_percurso"]


@pytest.mark.parametrize("de, ate, aviso, abre", [
    ("2026-10-01T06:00", "2026-11-08T12:00", "o início foi para 01/11 às 12:00", True),       # antes dos 7 dias
    ("2026-11-08T06:00", "2026-11-09T22:00", "", True),                                         # o fim depois de agora
    ("2026-11-08T11:00", "2026-11-08T09:00", "O fim do período tem de ser depois do início", False),
    ("ontem", "2026-11-08T12:00", "Período fora do formato", False),
    ("2026-11-08T06:00", "", "Período fora do formato", False),
    ("2026-02-30T06:00", "2026-11-08T12:00", "Período fora do formato", False),
], ids=["antes_dos_7_dias", "fim_no_futuro", "fim_antes_do_inicio", "texto", "sem_fim", "dia_que_nao_existe"])
def test_o_periodo_do_percurso_cabe_nos_7_dias_e_o_torto_e_dito(cliente, manha, setor, de, ate, aviso, abre):
    """O período fica dentro da guarda (o início que passa dos 7 dias vai para o limite, e a tela diz; o fim depois de
    agora vira agora). O período torto não é 500: a tela diz e mostra o painel do técnico, e o registro é o de sempre
    (abriu_mapa), porque nenhum percurso foi visto."""
    st, html = _html(_entrar(cliente, EMAIL[PCM]), query_string={"tecnico": ANDANDO, "de": de, "ate": ate})
    assert st == 200 and (aviso in html)
    assert ("eq-perc-linha" in html) is abre
    (a,) = _acessos(manha)
    if abre:
        assert a["acao"] == "abriu_percurso"
        assert a["periodo_de"] == ("2026-11-01T15:00:00Z" if de.startswith("2026-10") else "2026-11-08T09:00:00Z")
        assert a["periodo_ate"] == "2026-11-08T15:00:00Z"                 # o fim nunca passa de agora
    else:
        assert (a["acao"], a["alvo_pessoa_id"], a["periodo_de"]) == ("abriu_mapa", ANDANDO, None)


def test_o_percurso_so_de_quem_a_tela_mostra(cliente, manha, setor):
    """O percurso abre só para o técnico que o painel abre (no piloto e no filtro): o de fora não vira percurso nem
    alvo no registro."""
    _entrar(cliente, EMAIL[PCM])
    periodo = {"de": "2026-11-08T06:00", "ate": "2026-11-08T12:00"}
    _, html = _html(cliente, query_string={"tecnico": FORA_DO_PILOTO, **periodo})
    assert "eq-perc-linha" not in html and NOME[FORA_DO_PILOTO] not in html
    _, html = _html(cliente, query_string={"tecnico": ANDANDO, "equipe": LESTE, **periodo})
    assert "eq-perc-linha" not in html
    assert [(a["acao"], a["alvo_pessoa_id"]) for a in _acessos(manha)] == [("abriu_mapa", None)] * 2


def test_sem_gravar_o_registro_o_percurso_nao_abre(cliente, manha, setor, monkeypatch):
    def disco_cheio(*a, **k):
        raise OSError("disco cheio (teste)")
    monkeypatch.setattr(manha.registro, "acrescentar", disco_cheio)
    st, html = _html(_entrar(cliente, EMAIL[PCM]),
                     query_string={"tecnico": ANDANDO, "de": "2026-11-08T06:00", "ate": "2026-11-08T12:00"})
    assert st == 503 and "eq-perc-linha" not in html and "registro" in html


# ── os eventos do dia (10/11/2026) ─────────────────────────────────────────────────────────────────────────────
def _eventos_da_tela(html):
    ev = html.split('<section class="eq-ev"', 1)[1].split("</section>", 1)[0]
    itens = re.findall(r'<time>(\d\d:\d\d)</time>.*?href="([^"]+)".*?<b>([^<]+)</b> · ([^<]+)</span>', ev, flags=re.S)
    return ev, itens


def test_os_eventos_do_dia_no_estilo_do_quadro_de_ocorrencias(cliente, pontos, setor):
    """Levi, 10/11/2026, com a imagem do quadro de eventos do COS: "Quero que apareça tipo ocorrências: Algo nesse
    estilo". Abaixo do mapa, os eventos de hoje do mais novo ao mais velho: a hora, o técnico, o que aconteceu e a
    etiqueta; a faixa "Agora" e o resumo no alto. O clique leva ao percurso do dia do técnico (o sem permissão, ao painel
    dele). Nenhuma coordenada."""
    from html import unescape
    from urllib.parse import parse_qs, urlsplit
    _, html = _html(_entrar(cliente, EMAIL[PCM]))
    ev, itens = _eventos_da_tela(html)
    assert "Eventos do dia" in ev and "Agora · 12:00" in ev
    assert "4 inícios do dia · 1 sem sinal · 1 sem permissão" in ev
    assert [(h, n, t) for h, _href, n, t in itens] == [
        ("11:59", NOME[ANDANDO], "primeira posição do dia, fora de usina"),
        ("11:57", NOME[NA_USINA], "primeira posição do dia, na Usina Alfa Teste"),
        ("11:55", NOME[FORA], "primeira posição do dia, fora de usina"),
        ("11:50", NOME[SEM_SINAL], "sem sinal desde 11:20"),
        ("11:20", NOME[SEM_SINAL], "primeira posição do dia, na Usina Bravo Teste"),
        ("11:00", NOME[SEM_PERMISSAO], "sem permissão no celular")]
    assert ev.count("<small>Nexus Field</small>") == 6 and "cn-pill cn-alerta" in ev and "cn-pill cn-critico" in ev
    links = {n: parse_qs(urlsplit(unescape(href)).query) for _h, href, n, _t in itens}
    assert links[NOME[ANDANDO]] == {"tecnico": [str(ANDANDO)], "de": ["2026-11-08T06:00"], "ate": ["2026-11-08T12:00"]}
    assert links[NOME[SEM_PERMISSAO]] == {"tecnico": [str(SEM_PERMISSAO)]}
    assert not [d for d in DIGITOS if d in ev]
    # o filtro vale para os eventos, e vai junto no link
    _, html = _html(cliente, query_string={"equipe": LESTE})
    ev, itens = _eventos_da_tela(html)
    assert [n for _h, _href, n, _t in itens] == [NOME[SEM_PERMISSAO]] and f"equipe={LESTE}" in itens[0][1]
    # com o percurso aberto o quadro sai (a gaveta lista os pontos dele)
    _, html = _html(cliente, query_string={"tecnico": ANDANDO, "de": "2026-11-08T06:00", "ate": "2026-11-08T12:00"})
    assert '<section class="eq-ev"' not in html


def test_sem_evento_hoje_o_quadro_diz(cliente, banco, setor):
    S.do_app(cliente.application).registro.novos()
    _, html = _html(_entrar(cliente, EMAIL[PCM]))
    ev, itens = _eventos_da_tela(html)
    assert itens == [] and "Nenhum evento hoje." in ev


# ── o painel ao lado do mapa: os eventos e o botão Técnico e Rotas (10/11/2026) ─────────────────────────────────
def _lado(html):
    return html.split('class="eq-lado', 1)[1].split("</aside>", 1)[0]


def _q(href):
    from html import unescape
    from urllib.parse import parse_qs, urlsplit
    return parse_qs(urlsplit(unescape(href)).query)


def test_o_painel_ao_lado_do_mapa_abre_nos_eventos_e_o_botao_leva_a_tecnico_e_rotas(cliente, pontos, setor):
    """Levi, 10/11/2026: "A parte de eventos deve ficar ao lado do mapa do lado direito essa visão de técnico e rotas
    pode ficar em uma botão do eventos como 'Técnico e Rotas' se clicar vai para essa visão, mas a ideia é fica abrindo
    os eventos, vai até o limite do mapa e vai tendo a barra de rolagem"."""
    _, html = _html(_entrar(cliente, EMAIL[PCM]))
    assert 'class="eq-corpo eq-corpo--ev"' in html
    lado = _lado(html)
    assert '<section class="eq-ev"' in lado and 'class="eq-grupo"' not in lado
    assert html.count('<section class="eq-ev"') == 1                    # o quadro de baixo saiu
    (href,) = re.findall(r'<a class="[^"]*eq-ev-botao[^"]*" href="([^"]+)">[^<]*(?:<[^>]+>[^<]*)*Técnico e Rotas</a>',
                         lado)
    assert _q(href) == {"painel": ["tecnicos"]}
    # Técnico e Rotas: a lista de sempre, com o botão de volta aos eventos
    _, html = _html(cliente, query_string={"painel": "tecnicos"})
    lado = _lado(html)
    assert 'class="eq-grupo"' in lado and '<section class="eq-ev"' not in lado and "eq-corpo--ev" not in html
    (volta,) = re.findall(r'<a class="[^"]*eq-ev-botao[^"]*" href="([^"]+)">[^<]*(?:<[^>]+>[^<]*)*Eventos do dia</a>',
                          lado)
    assert _q(volta) == {}
    # o filtro vai junto no botão; o "Ver todos os técnicos" do técnico volta à lista de técnicos
    _, html = _html(cliente, query_string={"equipe": LESTE})
    (href,) = re.findall(r'eq-ev-botao[^"]*" href="([^"]+)"', _lado(html))
    assert _q(href) == {"painel": ["tecnicos"], "equipe": [str(LESTE)]}
    _, html = _html(cliente, query_string={"tecnico": NA_USINA})
    (ver,) = re.findall(r'href="([^"]+)">Ver todos os técnicos', html)
    assert _q(ver) == {"painel": ["tecnicos"]}


def test_o_painel_ao_lado_tem_a_altura_do_cartao_do_mapa():
    """Levi, 11/11/2026: "a barra lateral tem que ser do mesmo tamanho da barra do mapa, pode aumentar a altura do card
    do mapa". O cartão do mapa tem uma altura só (`--eq-alt`, a da janela), o painel ao lado e o do clima têm a mesma, e
    o que não cabe rola dentro deles (os eventos, a lista de técnicos, a gaveta do técnico)."""
    css = (Path(__file__).resolve().parent.parent / "nexus" / "static" / "campo.css").read_text(encoding="utf-8")
    assert re.search(r"\.eq-corpo\{[^}]*--eq-alt:", css)
    assert re.search(r"\.eq-quadro,\.eq-lado,\.eq-clima\{[^}]*height:var\(--eq-alt\)", css)
    assert re.search(r"\.eq-lado,\.eq-clima\{[^}]*overflow:auto", css)
    assert re.search(r"\.eq-ev-lista\{[^}]*overflow:auto", css)
    # o desenho ocupa o palco inteiro: não é mais cortado pela altura dele (era height:auto com max-height:72vh)
    assert re.search(r"\.eq-svg\{display:block;width:100%;height:100%", css)


def test_o_texto_e_os_pontos_do_mapa_seguem_a_tela_e_nao_o_desenho():
    """Levi, 11/11/2026, com a imagem do percurso: "mesmo eu dando um zoom os municípios ficam bem pequenos, tem que ser
    responsivo!". O desenho é mais alto que largo e o cartão é largo: a escala de verdade saía da altura, e os 14 px do
    texto viravam 7 na tela. O script mede a tela (a largura da vista sobre a do elemento) e o CSS escreve o texto e os
    pontos em pixels dela (`--eq-un` = unidades do desenho por pixel)."""
    raiz = Path(__file__).resolve().parent.parent / "nexus" / "static"
    css = (raiz / "campo.css").read_text(encoding="utf-8")
    js = (raiz / "campo-percurso.js").read_text(encoding="utf-8")
    assert re.search(r"\.eq-svg text\{[^}]*font-size:calc\(var\(--eq-fs\) \* var\(--eq-un\)\)", css)
    assert re.search(r"\.eq-svg \.eq-u,[^{]*\{[^}]*transform:scale\(var\(--eq-un\)\)", css)
    assert '"--eq-un"' in js and "clientWidth" in js and "ResizeObserver" in js
    assert "--eq-zt" not in css and "--eq-k" not in css and "--eq-zt" not in js


def test_as_linhas_do_mapa_pulsam_em_verde_grid(cliente, pontos, setor):
    """Levi, 11/11/2026: "quero mais cores da grid nesse mapa! Talvez a linha dos mapas poderia ficar pulsando levemente
    em verde grid". O contorno dos estados é redesenhado numa camada por cima (`eq-brilho`, um <use> do mesmo desenho),
    em verde, e só a opacidade dela anima. Com os efeitos de animação do Windows desligados (o caso do Levi) o Nexus
    para toda animação: esta foi pedida, e a regra a mantém."""
    _, html = _html(_entrar(cliente, EMAIL[PCM]))
    assert '<g class="eq-ufs" id="eq-ufs">' in _svg(html)
    brilho = html.split('<svg class="eq-brilho"', 1)[1].split("</svg>", 1)[0]
    assert '<use href="#eq-ufs"/>' in brilho and 'aria-hidden="true"' in brilho
    css = (Path(__file__).resolve().parent.parent / "nexus" / "static" / "campo.css").read_text(encoding="utf-8")
    assert "@keyframes eq-pulso" in css and re.search(r"\.eq-brilho\{[^}]*animation:eq-pulso", css)
    assert re.search(r"prefers-reduced-motion:reduce\)\{\.eq-brilho\{animation:eq-pulso[^}]*!important", css)
    # o mapa dos técnicos também aproxima (o mesmo script do percurso), sem o botão do percurso
    cab = html.split('<svg class="eq-svg', 1)[1].split(">", 1)[0]
    assert "data-eq-mapa" in cab and "data-min=" in cab and "campo-percurso.js" in html
    assert all(f'data-eq-zoom="{z}"' in html for z in ("mais", "menos", "inteiro")) and 'data-eq-zoom="percurso"' not in html


def test_o_destino_vem_da_programacao_do_dia_da_equipe(app, cliente, banco, pontos, setor, relogio, tmp_path):
    """Levi, 10/11/2026: "Pode subir o destino do técnico". O destino é o próximo bloco de hoje da programação do PCM
    da equipe dele (o banco_dados.json do App), com a usina pelo de-para do Fracttal; a chegada prevista é a régua do
    motor do PCM. A gaveta do técnico diz o destino."""
    seg = AGORA + timedelta(days=1)          # segunda-feira, 09/11, 12:00 de Brasília (a programação é de seg. a sex.)
    relogio.agora = seg
    _aba(banco, "cadastro_nexus", "de_para", [{"usina_id": USINA_B, "sistema": "Fracttal · Classificação 1",
                                                "chave_externa": "UFV Bravo do Fracttal"}])
    visao.limpar()
    prog = {"semana_ativa": "2026-W46", "semanas": [{"week": "2026-W46", "rows": [
        {"cluster": EQUIPE[CENTRO], "dia": "Segunda-feira", "h_ini": "13:00", "h_fim": "15:00",
         "usina": "UFV Bravo do Fracttal", "status": "Não Iniciada"},
        {"cluster": EQUIPE[CENTRO], "dia": "Terça-feira", "h_ini": "07:00", "h_fim": "09:00",
         "usina": "Outra do Fracttal", "status": "Não Iniciada"}]}]}
    arq = tmp_path / "banco_dados.json"
    arq.write_text(json.dumps(prog), encoding="utf-8")
    app.config["NEXUS_PCM_FONTE"] = str(arq)
    # parado fora de usina às 09:00 e andando às 09:10 (Brasília, segunda)
    _receber(pontos, ANDANDO, [((-16.712468, -49.013579), 3 * 60, False), ((-16.756789, -48.998765), 170, True)],
             agora=seg)
    pontos.registro.novos()
    _, html = _html(_entrar(cliente, EMAIL[PCM]))
    _ev, itens = _eventos_da_tela(html)
    (saida,) = [t for _h, _href, n, t in itens if n == NOME[ANDANDO] and t.startswith("saiu")]
    assert saida.startswith("saiu de um ponto fora de usina para Usina Bravo Teste; chegada prevista ")
    # a gaveta dele diz o destino e a chegada prevista
    _, html = _html(cliente, query_string={"tecnico": ANDANDO})
    lado = _lado(html)
    assert "<dt>Destino</dt>" in lado and "Usina Bravo Teste" in lado and "chegada prevista" in lado
    # sem a programação (o arquivo do PCM que não abre), a saída sem destino e nenhum erro na tela
    app.config["NEXUS_PCM_FONTE"] = str(tmp_path / "nao_existe.json")
    st, html = _html(cliente)
    _ev, itens = _eventos_da_tela(html)
    assert st == 200 and [t for _h, _href, n, t in itens if n == NOME[ANDANDO] and t.startswith("saiu")] == [
        "saiu de um ponto fora de usina"]


# ── o clique na pessoa abre o percurso, e o mouse diz quem é (10/11/2026) ──────────────────────────────────────
def test_o_clique_na_pessoa_no_mapa_ja_abre_o_percurso_do_dia(cliente, pontos, setor):
    """Levi, 10/11/2026: "Quero que ao clicar na pessoa no mapa já apareça o percurso e ao passar o mouse o nome da
    pessoa e a equipe!". O link do ponto leva o período do dia da última posição dela (das 6h até agora, ou até as 22h
    do dia dela): abre o percurso direto, e a abertura fica no registro da LGPD como todo percurso. A dica (o
    campo-equipe.js) lê o nome, a equipe e a situação do próprio link; nada de coordenada."""
    from html import unescape
    from urllib.parse import parse_qs, urlsplit
    _receber(pontos, SEM_POSICAO, [((-16.712468, -49.013579), 16 * 60, False)])     # ontem às 20:00 de Brasília
    pontos.registro.novos()
    _, html = _html(_entrar(cliente, EMAIL[PCM]))
    svg = _svg(html)
    a = re.search(rf'<a href="([^"]*tecnico={ANDANDO}[^"]*)"([^>]*)>', svg)
    assert parse_qs(urlsplit(unescape(a.group(1))).query) == {
        "tecnico": [str(ANDANDO)], "de": ["2026-11-08T06:00"], "ate": ["2026-11-08T12:00"]}
    # o ponto de ontem abre o dia DELE, das 6h às 22h
    ontem = re.search(rf'<a href="([^"]*tecnico={SEM_POSICAO}[^"]*)"', svg)
    assert parse_qs(urlsplit(unescape(ontem.group(1))).query) == {
        "tecnico": [str(SEM_POSICAO)], "de": ["2026-11-07T06:00"], "ate": ["2026-11-07T22:00"]}
    # a dica: o nome, a equipe e a situação no próprio link; o título do navegador saiu (a dica o substitui)
    attrs = unescape(a.group(2))
    assert f'data-eq-nome="{NOME[ANDANDO]}"' in attrs and 'data-eq-equipe="Equipe Centro Teste"' in attrs
    assert 'data-eq-sit="Em deslocamento"' in attrs and f'aria-label="{NOME[ANDANDO]}, Equipe Centro Teste' in attrs
    assert "<title>" not in svg.split('<g class="eq-pontos">', 1)[1]
    assert 'class="eq-dica"' in html and "campo-equipe.js" in html
    # o clique abre o percurso (e registra)
    st, html = _html(cliente, query_string=parse_qs(urlsplit(unescape(a.group(1))).query))
    assert st == 200 and 'class="eq-perc-linha"' in html
    assert [x["acao"] for x in _acessos(pontos)][-1] == "abriu_percurso"


def test_a_busca_da_barra_entra_no_padrao_do_filtro_suspenso():
    """Levi, 10/11/2026: "o campo buscar e as cores também tem que estar no mesmo padrão viu!". O script do filtro
    suspenso põe a busca da barra no campo do modelo (o das Rondas: a lupa, a mesma borda e o mesmo fundo do botão
    Filtros) e a deixa antes do botão, como no Histórico de OS."""
    js = (Path(__file__).resolve().parent.parent / "nexus" / "static" / "campo-filtros.js").read_text(encoding="utf-8")
    assert 'input[type="search"]' in js and "rd-campo rd-busca" in js and "ph-magnifying-glass" in js
    assert 'classList.remove("gc-campo")' in js


def test_a_barra_do_mapa_aproveita_a_linha_e_a_hora_da_leitura_vai_ao_explica(cliente, pontos, setor):
    """Levi, 10/11/2026: "Filtros pode ficar do lado dos botões de técnico e usina, pense que precisamos aproveitar ao
    máximo o espaço na tela, essa informação de Lida em x horas pode ficar na exclamação do mapa de equipe!". O Técnicos
    | Usinas, o formulário dos filtros e o resumo ficam numa linha só (`eq-barra`), e o "Lido às" sai do cabeçalho e
    entra no "!" do título."""
    _, html = _html(_entrar(cliente, EMAIL[PCM]))
    barra = html.split('<div class="eq-barra">', 1)[1].split('<div class="eq-corpo', 1)[0]
    assert barra.index('class="cn-seg eq-ver"') < barra.index("data-fs") < barra.index('class="eq-resumo"')
    assert "cn-frescor" not in html
    explica = html.split('class="gc-explica-caixa"', 1)[1].split("</section>", 1)[0]
    assert "Lido às <b>12:00</b> de Brasília" in explica


# ── o piloto ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_piloto_so_o_admin_muda(app, cliente, banco, pontos, setor):
    antes = banco.linhas(LIVRO_PILOTO, ABA_PILOTO)
    # quem não é administrador vê o mapa, mas não o controle do piloto, e o POST dele é recusado
    _, html = _html(_entrar(cliente, EMAIL[PCM]))
    assert 'action="/t/campo/equipe/piloto"' not in html
    r = cliente.post(URL_PILOTO, data={"pessoa_id": FORA_DO_PILOTO, "no_piloto": "sim"})
    assert r.status_code == 403 and banco.linhas(LIVRO_PILOTO, ABA_PILOTO) == antes
    # o administrador vê o controle com os técnicos de campo, e o pedido de outro site é recusado
    _entrar(cliente, EMAIL[ADMIN], admin=True)
    _, html = _html(cliente)
    assert 'action="/t/campo/equipe/piloto"' in html and NOME[FORA_DO_PILOTO] in html.split("eq-piloto", 1)[1]
    r = cliente.post(URL_PILOTO, data={"pessoa_id": FORA_DO_PILOTO, "no_piloto": "sim"},
                     headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403 and banco.linhas(LIVRO_PILOTO, ABA_PILOTO) == antes
    # quem não é técnico de campo ativo não entra no piloto; o pedido torto também não
    for dado in ({"pessoa_id": PCM, "no_piloto": "sim"}, {"pessoa_id": FORA_DO_PILOTO, "no_piloto": "talvez"},
                 {"pessoa_id": "x", "no_piloto": "sim"}):
        assert cliente.post(URL_PILOTO, data=dado).status_code == 400, dado
    # o administrador põe um técnico no piloto: a decisão vai ao livro, com quem decidiu só pelo HMAC
    r = cliente.post(URL_PILOTO, data={"pessoa_id": FORA_DO_PILOTO, "no_piloto": "sim"})
    assert r.status_code == 303 and r.headers["Location"].endswith("/t/campo/equipe?piloto=ok")
    depois = banco.linhas(LIVRO_PILOTO, ABA_PILOTO)
    # as decisões de antes ficam como estavam; ganham só a coluna `teste` (09/11/2026), com 0
    assert len(depois) == len(antes) + 1
    assert [{k: v for k, v in r.items() if k != "teste"} for r in depois[:-1]] == antes
    assert all(r["teste"] == 0 for r in depois)
    nova = depois[-1]
    assert nova["pessoa_id"] == FORA_DO_PILOTO and nova["no_piloto"] == 1 and nova["data_id"] == 20261108
    assert nova["decidida_por_hmac"] == codigo_da_pessoa(CHAVE_HMAC, EMAIL[ADMIN])
    assert nova["instante"] == "2026-11-08T15:00:00Z" and str(nova["decisao_id"])[0].isalpha()
    assert EMAIL[ADMIN] not in repr(depois)
    # vale já: o mapa mostra o técnico novo sem esperar o minuto da cópia, e a coleta dele vale
    _, html = _html(cliente, query_string={"piloto": "ok", **TECNICOS})
    assert NOME[FORA_DO_PILOTO] in html.split('class="eq-lado"', 1)[1] and "Decisão do piloto gravada" in html
    assert pontos.coleta_vale(FORA_DO_PILOTO, AGORA) is True
    # e tira
    r = cliente.post(URL_PILOTO, data={"pessoa_id": FORA_DO_PILOTO, "no_piloto": "nao"})
    assert r.status_code == 303 and banco.linhas(LIVRO_PILOTO, ABA_PILOTO)[-1]["no_piloto"] == 0
    assert pontos.coleta_vale(FORA_DO_PILOTO, AGORA) is False


def test_o_admin_poe_no_piloto_uma_pessoa_de_teste_que_nao_e_de_campo(app, cliente, banco, pontos, setor):
    """09/11/2026, pedido do Levi pela sessão Nexus Field ("use meu usuário para testes"): ele não é Colaborador de campo.
    O administrador põe no piloto, MARCADA COMO TESTE, qualquer pessoa do cadastro (pelo pessoa_id, sem mexer no vínculo
    dela): a coleta dela vale, o painel a mostra com a marca de teste e o resumo dos técnicos não a conta."""
    def sem_posicao(html):
        m = re.search(r'(\d+) sem posição hoje</span>', html)
        return int(m.group(1)) if m else 0
    _entrar(cliente, EMAIL[ADMIN], admin=True)
    _, html = _html(cliente)
    bloco = html.split("eq-piloto", 1)[1]
    # a escolha da pessoa de teste: as pessoas do cadastro que não são técnicas de campo (as de campo já estão acima)
    assert 'name="teste" value="1"' in bloco and f'<option value="{PCM}">Analista Teste</option>' in bloco
    assert f'<option value="{FORA_DO_PILOTO}">' not in bloco.split('name="teste"', 1)[1].split("</form>", 1)[0]
    antes = sem_posicao(html)
    assert pontos.coleta_vale(PCM, AGORA) is False
    r = cliente.post(URL_PILOTO, data={"pessoa_id": PCM, "no_piloto": "sim", "teste": "1"})
    assert r.status_code == 303 and r.headers["Location"].endswith("/t/campo/equipe?piloto=ok")
    nova = banco.linhas(LIVRO_PILOTO, ABA_PILOTO)[-1]
    assert (nova["pessoa_id"], nova["no_piloto"], nova["teste"]) == (PCM, 1, 1)
    assert pontos.coleta_vale(PCM, AGORA) is True                  # sem ser técnica de campo, pela marca de teste
    _, html = _html(cliente, query_string=TECNICOS)
    lado = html.split('class="eq-lado"', 1)[1]
    assert "Analista Teste" in lado and 'class="eq-teste"' in lado      # no painel, com a marca
    assert sem_posicao(html) == antes                               # e fora da conta dos técnicos
    # a pessoa que não existe no cadastro não entra nem como teste; o técnico de campo segue pelo caminho de sempre
    assert cliente.post(URL_PILOTO, data={"pessoa_id": "999999", "no_piloto": "sim", "teste": "1"}).status_code == 400
    # e sai
    r = cliente.post(URL_PILOTO, data={"pessoa_id": PCM, "no_piloto": "nao", "teste": "1"})
    assert r.status_code == 303 and banco.linhas(LIVRO_PILOTO, ABA_PILOTO)[-1]["no_piloto"] == 0
    assert pontos.coleta_vale(PCM, AGORA) is False


def test_a_leitura_do_piloto_que_cruzou_a_decisao_nao_fica_como_fresca():
    """A decisão gravada no meio de uma leitura do piloto (que pode ter visto o banco de antes dela): a cópia boa fica,
    mas a próxima pergunta vai ao banco de novo, em vez de servir a velha por 1 minuto."""
    lidas = []

    def ler():
        lidas.append(1)
        if len(lidas) == 1:
            copia.esquecer()                # a decisão chega com a 1ª leitura em curso
        return frozenset({len(lidas)})
    copia = S._Copia("o piloto de teste", 60, ler)
    assert copia.valor(1000.0) == frozenset({1})
    assert copia.valor(1001.0) == frozenset({2}) and len(lidas) == 2       # foi ao banco de novo
    assert copia.valor(1002.0) == frozenset({2}) and len(lidas) == 2       # agora, sim, fresca


# ── o botão Técnicos | Usinas e o Incluir clima (08/11/2026; refeito em 11/11/2026) ─────────────────────────────────
@pytest.fixture
def risco(monkeypatch):
    """O clima no mundo inventado do Mapa de risco (`clima_mapa_mundo`): o cadastro das usinas do clima
    (`usinas.do_app`, seis usinas) e as leituras prontas no lugar das fontes. Nada vai à rede."""
    from clima_mapa_mundo import REF as REF_RISCO
    from clima_mapa_mundo import cadastro, instalar_leituras, mundo_completo, mundo_de_usinas
    from nexus.performance.clima import usinas as U
    from nexus.performance.clima import visao as V
    monkeypatch.setattr(U, "do_app", lambda: cadastro(*mundo_de_usinas()))
    monkeypatch.setattr(V, "agora", lambda: REF_RISCO)
    mundo_completo(instalar_leituras(monkeypatch))


@pytest.fixture
def clima_das_usinas(monkeypatch):
    """O clima das duas usinas DESTE arquivo (as de `COORDS`, as que o mapa dos técnicos desenha): um Vendaval em Grande
    Perigo em cima da Alfa e nada na Bravo. As leituras prontas no lugar das fontes; nada vai à rede."""
    from clima_mapa_mundo import REF as REF_RISCO
    from clima_mapa_mundo import aviso, cadastro, dias, instalar_leituras, lei_avisos, lei_risco, tudo_instalado, usina
    from nexus.performance.clima import usinas as U
    from nexus.performance.clima import visao as V
    duas = [usina(str(u), NOME_USINA[u], COORDS[str(u)][:2], uf="GO") for u in (USINA_A, USINA_B)]
    monkeypatch.setattr(U, "do_app", lambda: cadastro(*duas))
    monkeypatch.setattr(V, "agora", lambda: REF_RISCO)
    tudo_instalado(instalar_leituras(monkeypatch), avisos=lei_avisos(aviso(3, "Vendaval", COORDS[str(USINA_A)][:2])),
                   risco=lei_risco({str(u): dias(0.1, 0.1, 0.1, 0.1) for u in (USINA_A, USINA_B)}))


def _botao_clima(html):
    """(classes, endereço, o resto dos atributos) do botão Incluir clima."""
    return re.search(r'<a class="([^"]*eq-clima-bt[^"]*)" href="([^"]*)"([^>]*)>', html).groups()


def _painel_do_clima(html):
    return html.split('<aside class="eq-clima"', 1)[1].split("</aside>", 1)[0]


def _conteudo(html):
    """O que a tela põe dentro do <main> (o topo do base.html tem o recolher do menu pela preferência guardada)."""
    return html.split("<main", 1)[1].split("</main>", 1)[0]


def _seg(html):
    seg = re.search(r'<nav class="cn-seg eq-ver"[^>]*>(.*?)</nav>', html, flags=re.S).group(1)
    return re.findall(r'<a href="([^"]*)"( aria-current="page")?>([^<]*)</a>', seg)


def test_o_botao_usinas_mostra_so_as_usinas_no_mapa(cliente, pontos, setor, risco, monkeypatch):
    """Levi, 11/11/2026: "esse botão usinas poderia mostrar só as usinas no mapa". O botão Usinas deixou de trazer a
    tela do Mapa de risco da Performance (08/11/2026) para dentro desta: é o MESMO mapa do Técnicos, só com as usinas em
    destaque e a lista delas ao lado. Nada de técnico (nem nome, nem ponto, nem o filtro de supervisor), e sem o clima
    pedido a página nem vai às fontes do clima."""
    from nexus.performance.clima import mapa as M

    def proibido(*a, **k):
        raise AssertionError("o modo Usinas sem o clima foi às fontes do clima")
    monkeypatch.setattr(M, "montar", proibido)
    _entrar(cliente, EMAIL[PCM])
    r = cliente.get(URL, query_string={"ver": "usinas"})
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and r.headers["Cache-Control"] == "no-store"
    assert "data-mapa" not in html and "mp-svg" not in html and "clima-mapa.js" not in html and "<iframe" not in html
    svg = _svg(html)
    assert svg.count('class="eq-u eq-u--dest"') == 6 and "eq-pontos" not in svg and "tecnico=" not in svg
    assert 'data-eq-nome="Usina Alfa"' in svg and 'data-eq-equipe="Cliente X · PI"' in svg
    assert not [n for n in NOME.values() if n in html] and 'name="supervisor"' not in html
    lado = _lado(html)
    assert all(f"Usina {n}" in lado for n in ("Alfa", "Beta", "Gama", "Delta", "Epsilon", "Teta"))
    assert "Cliente X · PI" in lado and "6 usinas" in lado
    assert '<aside class="eq-clima"' not in html and 'class="eq-avisos"' not in html
    assert _seg(html) == [("/t/campo/equipe", "", "Técnicos"), ("/t/campo/equipe?ver=usinas", ' aria-current="page"',
                                                                 "Usinas")]
    # o "Técnicos" é a tela de sempre, com o botão marcado do outro lado; o ver que não é "usinas" também
    for ver in (None, "tecnicos", "lixo"):
        _, html = _html(cliente, query_string={"ver": ver} if ver else None)
        assert NOME[NA_USINA] in html and "eq-u--dest" not in html and 'name="supervisor"' in html, ver
        assert re.search(r'<a href="/t/campo/equipe" aria-current="page">Técnicos</a>', html), ver


def test_o_incluir_clima_recolhe_o_menu_e_mostra_os_alertas_por_usina(cliente, pontos, setor, risco, monkeypatch):
    """Levi, 11/11/2026: 'poderia ter um botão "incluir clima" se apertar vai recolher a barra lateral esquerda e vai
    mostrar os climas os alertas, tanto por usina ou por técnico, por mais que mostre os técnicos os avisos tem que ser
    por usina'. O botão liga o `?clima=1`: a página recolhe o menu (só nela, sem gravar a preferência), o mapa ganha a
    área dos avisos e os focos e pinta cada usina pelo nível, e um painel à esquerda lista os alertas POR USINA. É o
    modelo do Mapa de risco (`clima.mapa.montar`), pedido na vista deste mapa: regra nenhuma copiada."""
    from nexus.performance.clima import mapa as M
    chamadas, montar = [], M.montar

    def espiao(config, **kw):
        chamadas.append(kw)
        return montar(config, **kw)
    monkeypatch.setattr(M, "montar", espiao)
    _entrar(cliente, EMAIL[PCM])
    # sem o clima: o botão o liga, e nada do clima na página
    _, html = _html(cliente, query_string={"ver": "usinas"})
    classes, href, resto = _botao_clima(html)
    assert _q(href) == {"ver": ["usinas"], "clima": ["1"]} and "aria-current" not in resto
    assert 'classList.add("menu-recolhido")' not in _conteudo(html) and chamadas == []
    # com o clima
    st, html = _html(cliente, query_string={"ver": "usinas", "clima": "1"})
    assert st == 200
    (kw,) = chamadas
    assert kw["vista_propria"] is not None and kw["fundo"] == "avisos" and kw["cadastro"] is not None
    conteudo = _conteudo(html)
    # só nesta página: a preferência guardada do menu (o localStorage do base.html) não é tocada
    assert 'classList.add("menu-recolhido")' in conteudo and "localStorage" not in conteudo
    classes, href, resto = _botao_clima(html)
    assert _q(href) == {"ver": ["usinas"]} and 'aria-current="true"' in resto and "eq-clima-bt--on" in classes
    assert 'class="eq-corpo eq-corpo--clima"' in html
    svg = _svg(html)
    assert '<g class="eq-avisos"' in svg and 'class="eq-u eq-u--dest eq-u--agir"' in svg
    assert 'class="eq-u eq-u--dest eq-u--sem"' in svg
    clima = _painel_do_clima(html)
    assert "Agir agora" in clima and "Vendaval" in clima
    # quem pede ação primeiro; quem não tem alerta não vira linha, só a conta
    linhas = re.findall(r'<li class="eq-clima-item eq-clima-item--(\w+)">.*?<b>([^<]*)</b>', clima, flags=re.S)
    assert linhas[0] == ("agir", "Usina Alfa") and all(n != "sem" for n, _ in linhas)
    assert "Usina Teta" not in "".join(nome for _, nome in linhas) and "Sem alerta" in clima
    assert not [n for n in NOME.values() if n in html]                     # nada de técnico
    assert _seg(html) == [("/t/campo/equipe?clima=1", "", "Técnicos"),
                          ("/t/campo/equipe?ver=usinas&amp;clima=1", ' aria-current="page"', "Usinas")]
    assert _acessos(pontos) == []                                          # sem dado pessoal, sem linha na trilha


def test_o_clima_no_modo_tecnicos_mostra_os_tecnicos_e_os_avisos_por_usina(cliente, pontos, setor, clima_das_usinas):
    """'tanto por usina ou por técnico, por mais que mostre os técnicos os avisos tem que ser por usina' (Levi,
    11/11/2026): no Técnicos com o clima, os técnicos seguem no mapa e no painel da direita, e o painel do clima fala
    das USINAS (nome de técnico nenhum nele). O `clima=1` segue em todo link da tela, e a abertura grava a trilha da
    LGPD como sempre."""
    _, html = _html(_entrar(cliente, EMAIL[PCM]), query_string={"clima": "1"})
    svg = _svg(html)
    assert all(_no_svg(svg, pid) for pid in (NA_USINA, ANDANDO, SEM_SINAL, FORA))
    assert '<g class="eq-avisos"' in svg
    assert svg.count('class="eq-u eq-u--agir"') == 1 and svg.count('class="eq-u eq-u--sem"') == 1
    clima = _painel_do_clima(html)
    assert NOME_USINA[USINA_A] in clima and "Agir agora" in clima and "Vendaval" in clima
    assert not [n for n in NOME.values() if n in clima]
    assert 'class="eq-corpo eq-corpo--ev eq-corpo--clima"' in html
    assert 'classList.add("menu-recolhido")' in _conteudo(html)
    # o clima segue nos links: o ponto do técnico, o botão do painel, o Técnicos | Usinas e o formulário do filtro
    ponto = re.search(rf'<a href="([^"]*tecnico={ANDANDO}[^"]*)"', svg).group(1)
    assert _q(ponto)["clima"] == ["1"]
    (href,) = re.findall(r'eq-ev-botao[^"]*" href="([^"]+)"', _lado(html))
    assert _q(href) == {"painel": ["tecnicos"], "clima": ["1"]}
    assert _seg(html) == [("/t/campo/equipe?clima=1", ' aria-current="page"', "Técnicos"),
                          ("/t/campo/equipe?ver=usinas&amp;clima=1", "", "Usinas")]
    filtros = re.search(r'<form class="cn-filtros eq-filtros".*?</form>', html, flags=re.S).group(0)
    assert '<input type="hidden" name="clima" value="1">' in filtros
    assert "neste filtro" not in html                                      # o clima não é filtro de técnico
    assert [a["acao"] for a in _acessos(pontos)] == ["abriu_mapa"]
    # com o percurso aberto, o clima vai no desenho do percurso, e o Fechar o percurso o leva
    _, html = _html(cliente, query_string={"tecnico": ANDANDO, "de": "2026-11-08T06:00", "ate": "2026-11-08T12:00",
                                           "clima": "1"})
    svg = _svg(html)
    assert 'class="eq-perc-linha"' in svg and '<g class="eq-avisos"' in svg and 'class="eq-u eq-u--agir"' in svg
    (fechar,) = re.findall(r'href="([^"]+)">Fechar o percurso', html)
    assert _q(fechar) == {"tecnico": [str(ANDANDO)], "clima": ["1"]}
    assert not [d for d in DIGITOS if d in html]                           # a coordenada segue fora da página


def test_o_clima_sem_leitura_nao_pinta_a_usina_de_verde(cliente, pontos, setor, clima_das_usinas, monkeypatch):
    """A honestidade do Mapa de risco vale aqui: com uma fonte fora, a usina que ficaria "Sem alerta" fica cinza ("Sem
    leitura completa") e o painel diz qual fonte falta. Sem dado não se inventa."""
    from clima_mapa_mundo import instalar_leituras
    instalar_leituras(monkeypatch)()                                       # os avisos, os focos e o risco fora
    _, html = _html(_entrar(cliente, EMAIL[PCM]), query_string={"clima": "1"})
    svg = _svg(html)
    assert svg.count('class="eq-u eq-u--nx"') == 2 and "eq-u--sem" not in svg and "eq-avisos" not in svg
    clima = _painel_do_clima(html)
    assert "O clima não inclui" in clima and "Sem leitura completa" in clima


def test_o_clima_sem_o_cadastro_diz_por_que_e_o_mapa_dos_tecnicos_continua(cliente, pontos, setor, clima_das_usinas,
                                                                          monkeypatch):
    from nexus.performance.clima import usinas as U

    def sem():
        raise U.SemCadastro("o cadastro não está nesta máquina")
    monkeypatch.setattr(U, "do_app", sem)
    st, html = _html(_entrar(cliente, EMAIL[PCM]), query_string={"clima": "1"})
    assert st == 200 and all(_no_svg(_svg(html), pid) for pid in (NA_USINA, ANDANDO))
    assert "Cadastro indisponível: o cadastro não está nesta máquina" in _painel_do_clima(html)
    assert svg_sem_nivel(_svg(html))


def svg_sem_nivel(svg) -> bool:
    return svg.count('class="eq-u"') == 2 and "eq-u--" not in svg


def test_o_modo_usinas_nao_grava_na_trilha_nem_sobe_o_servico_da_equipe(cliente, pontos, setor, risco, monkeypatch):
    """Sem dado pessoal na tela das usinas, nenhuma linha "abriu_mapa" na trilha da LGPD (nem na releitura sozinha do
    mapa, que pede a mesma página); e o serviço das posições nem sobe."""
    _entrar(cliente, EMAIL[PCM])
    assert _html(cliente, query_string={"ver": "usinas"})[0] == 200
    assert _acessos(pontos) == []
    _html(cliente)
    assert [a["acao"] for a in _acessos(pontos)] == ["abriu_mapa"]               # o Técnicos grava, como antes

    def sem_servico(app):
        raise AssertionError("o modo Usinas subiu o serviço das posições")
    monkeypatch.setattr(S, "do_app", sem_servico)
    assert _html(cliente, query_string={"ver": "usinas"})[0] == 200


def test_quem_nao_ve_o_mapa_de_equipe_nao_ve_as_usinas_dele(app, cliente, banco, setor, risco):
    _entrar(cliente, OUTRO)                                                        # Engenharia
    st, html = _html(cliente, query_string={"ver": "usinas"})
    assert st == 403 and "data-mapa" not in html and "Usina Alfa" not in html
    # a sessão de cliente nem chega à rota (o portão a manda embora antes), e o mapa não sai
    with cliente.session_transaction() as s:
        s["via"] = "cliente"
    st, html = _html(cliente, query_string={"ver": "usinas"})
    assert st in (302, 403) and "data-mapa" not in html
    st, html = _html(_entrar(cliente, EMAIL[ADMIN], admin=True), query_string={"ver": "usinas"})
    assert st == 200 and "Usina Alfa" in html
