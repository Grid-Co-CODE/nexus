"""A tela Mapa de equipe da Usinas 360° (08/11/2026; `nexus/torres/campo/equipe_tela.py`), o Abrir rota pelo servidor, o
registro de quem abriu (LGPD) e o piloto, que só o administrador muda.

Quem vê é a regra escrita ao técnico: os setores PCM, COS, Performance, Supervisão Campo e Responsáveis UFV, e os
administradores, conferido DENTRO da rota (o portão por setor fica desligado nos testes, e a marca de outro setor em
Base → Acessos não abre a tela). A coordenada (do técnico ou da usina) nunca vai à página: o mapa leva só o x/y do
SVG, e o "parado fora de usina" nem isso.

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
    return html.split('<svg class="eq-svg"', 1)[1].split("</svg>", 1)[0]


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
    for pid in (FORA, SEM_POSICAO, SEM_PERMISSAO):
        r = cliente.get(URL_ROTA, query_string={"tecnico": pid, "usina": USINA_A})
        assert r.status_code == 404 and not [d for d in DIGITOS if d in r.get_data(as_text=True)]
    # o x/y do desenho dá o lugar aproximado: o "!" diz isso, e não promete o que o SVG não cumpre (revisão final de
    # 08/11/2026)
    assert "aproximado" in html and "nunca traz a latitude" not in html


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


def test_o_mapa_desenha_quem_esta_na_usina_andando_e_sem_sinal(cliente, pontos, setor):
    _, html = _html(_entrar(cliente, EMAIL[PCM]))
    svg = _svg(html)
    for pid, tom in ((NA_USINA, "ok"), (ANDANDO, "info"), (SEM_SINAL, "alerta")):
        assert f"tecnico={pid}\"" in svg and f"eq-p--{tom}" in svg, pid
    for pid in (FORA, SEM_PERMISSAO, SEM_POSICAO, FORA_DO_PILOTO):
        assert f"tecnico={pid}\"" not in svg, pid
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


def test_parado_fora_de_usina_sem_ponto_e_sem_rota(cliente, pontos, setor):
    _, html = _html(_entrar(cliente, EMAIL[PCM]))
    assert f"tecnico={FORA}\"" not in _svg(html)                        # não está no mapa
    lado = html.split('class="eq-lado"', 1)[1]
    fora = lado.split("Parados fora de usina", 1)[1].split("</section>", 1)[0]
    # a distância do parado fora de usina vai em km inteiro (revisão final de 08/11/2026): com a casa decimal, a
    # distância a duas usinas já cercava a casa no mapa
    assert NOME[FORA] in fora and "GO" in fora and "a 5 km da Usina Alfa Teste" in fora and "5,0 km" not in html
    # o painel dele: o estado e a distância, sem o Abrir rota
    _, html = _html(cliente, query_string={"tecnico": FORA})
    lado = html.split('class="eq-lado"', 1)[1]
    assert NOME[FORA] in lado and "Parado fora de usina" in lado and "GO" in lado
    assert "/t/campo/equipe/rota" not in html and "Abrir rota" not in lado
    assert f"tecnico={FORA}\"" not in _svg(html)


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
    _, html = _html(_entrar(cliente, EMAIL[PCM]))
    fora = html.split('class="eq-lado"', 1)[1].split("Parados fora de usina", 1)[1].split("</section>", 1)[0]
    assert NOME[FORA] in fora and "Cidade Um Teste/GO" in fora
    _, html = _html(cliente, query_string={"tecnico": FORA})
    lado = html.split('class="eq-lado"', 1)[1]
    assert "<dt>Cidade</dt><dd>Cidade Um Teste/GO</dd>" in lado
    # quem está na usina não ganha cidade nenhuma (está no mapa)
    _, html = _html(cliente, query_string={"tecnico": NA_USINA})
    assert "Cidade Um Teste" not in html


def test_a_pagina_nunca_baixa_do_ibge_e_a_cidade_vem_na_proxima(cliente, pontos, setor, monkeypatch):
    """Revisão de 08/11/2026: a abertura do mapa nunca espera o IBGE. Sem a malha da UF no disco, a página sai já com
    só o estado e manda UMA ida ao IBGE para o fundo; a próxima abertura tem a cidade."""
    from test_equipe_municipios import IBGE, Fundo
    ibge, fundo = IBGE(), Fundo()
    monkeypatch.setattr(MU, "_baixador", lambda: ibge)
    monkeypatch.setattr(MU, "_em_fundo", fundo)
    _, html = _html(_entrar(cliente, EMAIL[PCM]))
    fora = html.split('class="eq-lado"', 1)[1].split("Parados fora de usina", 1)[1].split("</section>", 1)[0]
    assert NOME[FORA] in fora and "· GO ·" in fora and "/GO" not in fora
    assert ibge.pedidos == [] and len(fundo.alvos) == 1               # a página não baixou; uma ida em fundo
    _html(cliente, query_string={"tecnico": FORA})                     # a ida corre: não dispara outra
    assert len(fundo.alvos) == 1
    fundo.terminar()
    _, html = _html(cliente)
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
    # no celular o ponto cresce 1,8 vez: o halo cresce junto, senão ficaria dentro do ponto
    assert re.search(r"@media \(max-width:700px\)\{[^}]*\.eq-halo[^}]*transform:scale\(1\.8\)", css)


def test_o_escolhido_tem_o_halo_e_vai_por_cima_dos_outros(cliente, pontos, setor):
    """O halo é um círculo atrás do ponto escolhido (o SVG não tem dois contornos num círculo só), e o escolhido é
    desenhado por último: dois técnicos na mesma usina caem no mesmo lugar, e o anel ficaria embaixo do outro."""
    _entrar(cliente, EMAIL[PCM])
    svg = _svg(_html(cliente)[1])
    assert "eq-halo" not in svg and "eq-p--sel" not in svg                # ninguém escolhido
    svg = _svg(_html(cliente, query_string={"tecnico": NA_USINA})[1])
    pontos_svg = svg.split('<g class="eq-pontos">', 1)[1]
    links = re.findall(r"<a href=[^>]*>.*?</a>", pontos_svg, flags=re.S)
    assert len(links) == 3 and f"tecnico={NA_USINA}\"" in links[-1]        # o escolhido por último
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
    assert _no_painel(_html(cliente)[1]) == set(PILOTO)                  # sem filtro: todos
    # a Equipe Leste: os dois de lá, nenhum no mapa (sem permissão e sem posição ficam só na lista)
    _, html = _html(cliente, query_string={"equipe": LESTE})
    assert _no_painel(html) == {SEM_PERMISSAO, SEM_POSICAO} and "tecnico=" not in _svg(html)
    resumo = html.split('class="eq-resumo"', 1)[1].split("</p>", 1)[0]
    assert "1 sem permissão" in resumo and "1 sem posição hoje" in resumo and "na usina" not in resumo
    assert f'<option value="{LESTE}" selected>' in html
    # o link do técnico leva o filtro junto, e o "Ver todos" do painel dele volta ao filtro, não a todos
    assert f'href="/t/campo/equipe?tecnico={SEM_POSICAO}&amp;equipe={LESTE}"' in html
    _, html = _html(cliente, query_string={"equipe": LESTE, "tecnico": SEM_POSICAO})
    assert f'href="/t/campo/equipe?equipe={LESTE}">Ver todos os técnicos' in html
    # o técnico de fora do filtro não abre o painel dele
    _, html = _html(cliente, query_string={"equipe": LESTE, "tecnico": NA_USINA})
    assert "eq-det" not in html and NOME[NA_USINA] not in html
    # o supervisor da Centro: os quatro dela, e os três que estão no mapa
    _, html = _html(cliente, query_string={"supervisor": SUP_CENTRO})
    assert _no_painel(html) == {NA_USINA, ANDANDO, FORA, SEM_SINAL}
    svg = _svg(html)
    assert all(f"tecnico={p}&amp;supervisor={SUP_CENTRO}\"" in svg for p in (NA_USINA, ANDANDO, SEM_SINAL))
    assert f'<option value="{SUP_CENTRO}" selected>' in html
    # os dois juntos valem juntos: o supervisor da Centro e a equipe Leste não têm ninguém, e a tela diz
    _, html = _html(cliente, query_string={"supervisor": SUP_CENTRO, "equipe": LESTE})
    assert _no_painel(html) == set() and "Nenhum técnico do piloto neste filtro." in html


@pytest.mark.parametrize("pedido", [{"supervisor": 999}, {"equipe": 999}, {"supervisor": SUP_OESTE}, {"equipe": OESTE},
                                    {"supervisor": "x"}, {"equipe": "²"}, {"supervisor": "1" * 5000},
                                    {"equipe": "", "supervisor": ""}],
                         ids=["sup_999", "eq_999", "sup_fora_do_piloto", "eq_fora_do_piloto", "letra", "sobrescrito",
                              "5000_algarismos", "vazios"])
def test_id_desconhecido_no_filtro_mostra_todos_sem_erro(cliente, pontos, setor, pedido):
    """O id que não está nas opções (não existe, é de quem está fora do piloto, ou vem torto) não filtra: a tela mostra
    todos, sem 500 e sem nada marcado no select."""
    st, html = _html(_entrar(cliente, EMAIL[PCM]), query_string=pedido)
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
    # andando e sem sinal (do último ponto, que era na usina): a rota abre
    for pid in (ANDANDO, SEM_SINAL):
        r = cliente.get(URL_ROTA, query_string={"tecnico": pid, "usina": USINA_A})
        assert r.status_code == 302 and r.headers["Location"].startswith("https://www.google.com/maps/dir/"), pid
    pontos.registro.novos()
    # parado fora de usina, sem permissão, sem posição, fora do piloto, usina ou técnico que não existe: 404, sem
    # registro
    for pid, uid in ((FORA, USINA_A), (SEM_PERMISSAO, USINA_A), (SEM_POSICAO, USINA_A), (FORA_DO_PILOTO, USINA_A),
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
    assert len(depois) == len(antes) + 1 and depois[:-1] == antes
    nova = depois[-1]
    assert nova["pessoa_id"] == FORA_DO_PILOTO and nova["no_piloto"] == 1 and nova["data_id"] == 20261108
    assert nova["decidida_por_hmac"] == codigo_da_pessoa(CHAVE_HMAC, EMAIL[ADMIN])
    assert nova["instante"] == "2026-11-08T15:00:00Z" and str(nova["decisao_id"])[0].isalpha()
    assert EMAIL[ADMIN] not in repr(depois)
    # vale já: o mapa mostra o técnico novo sem esperar o minuto da cópia, e a coleta dele vale
    _, html = _html(cliente, query_string={"piloto": "ok"})
    assert NOME[FORA_DO_PILOTO] in html.split('class="eq-lado"', 1)[1] and "Decisão do piloto gravada" in html
    assert pontos.coleta_vale(FORA_DO_PILOTO, AGORA) is True
    # e tira
    r = cliente.post(URL_PILOTO, data={"pessoa_id": FORA_DO_PILOTO, "no_piloto": "nao"})
    assert r.status_code == 303 and banco.linhas(LIVRO_PILOTO, ABA_PILOTO)[-1]["no_piloto"] == 0
    assert pontos.coleta_vale(FORA_DO_PILOTO, AGORA) is False


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
