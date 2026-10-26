"""O livro do inventário do almoxarifado no Nexus (26/10/2026, Levi): `nexus_almoxarifado_inventario`, onde o PCM deixa o
rastro de cada mudança (auditoria), a régua de mínimo e máximo e a curadoria do que veio fora do catálogo. Desenho:
docs/superpowers/specs/2026-10-26-inventario-almoxarifado-design.md (seção 5). Governança primeiro (PRIORIDADE 0): o
livro só cresce, cada fato carrega IDs, e nome, e-mail e o motivo do PCM (texto livre) nunca vão em coluna em claro (a
API do banco tem leitura aberta). Banco falso (tests/pg_falso.py); o resto, o arquivo local da cópia de prova. Dado de
mentira: usina, códigos e IDs inventados, sem nome de gente."""
import json
from pathlib import Path

import pytest
import requests
from pg_falso import ApiPGFalsa, Resposta

from nexus.cadastro.cifra import gerar_chave
from nexus.dados import catalogo, dominios, explica, fatos, livros
from nexus.dados import fato_inventario as F
from nexus.pcm.inventario import contas

BASE = "http://pg.falso"
HMAC = "a1b2c3d4e5f60718293a4b5c"
ALMOX = "900"
LIGADA = "de-para do Fracttal"          # por onde a usina do almoxarifado ligou (o mesmo texto do fato_almoxarifado)
RAIZ = Path(__file__).resolve().parent.parent


class ApiQueFalha(ApiPGFalsa):
    """O banco que cai: qualquer leitura levanta (ou volta 500) enquanto `falhar` estiver ligado. `cortar` = N: a leitura
    das linhas de cada aba perde as N últimas, e a listagem (`row_count`) segue dizendo o número de verdade (a página que
    volta curta)."""
    falhar = ""
    cortar = 0

    def get(self, url, params=None, headers=None, timeout=None):
        if self.falhar == "rede":
            raise requests.ConnectionError("banco fora do ar")
        if self.falhar == "500":
            return Resposta(500, {})
        r = super().get(url, params=params, headers=headers, timeout=timeout)
        if self.cortar and url.endswith("/rows"):
            return Resposta(200, r.json()[:-self.cortar])
        return r


@pytest.fixture
def banco(app):
    """O banco falso entregue como o Nexus entrega o de verdade (a sessão dos dados), com o token e a chave do cadastro.
    Sem `TESTING` na configuração do módulo: o banco falso é o "banco" e nada vai à rede."""
    api = ApiQueFalha(como_texto=True)
    app.extensions["nexus_dados_sessao"] = api
    cfg = {"GRIDCO_DB_API": BASE, "GRIDCO_SQL_TOKEN": "tk", "NEXUS_CHAVE_CADASTRO": gerar_chave()}
    F.limpar()
    with app.app_context():
        yield api, cfg
    app.extensions.pop("nexus_dados_sessao", None)
    F.limpar()


@pytest.fixture
def cfg(tmp_path):
    """A cópia de prova: o livro é um arquivo (`NEXUS_ALMOX_INVENTARIO_ARQUIVO`), nada vai ao banco."""
    F.limpar()
    return {"TESTING": True, "NEXUS_ALMOX_INVENTARIO_ARQUIVO": str(tmp_path / "inventario.json"),
            "NEXUS_CHAVE_CADASTRO": gerar_chave()}


def _ev(tipo="contagem_recebida", **mais):
    return {"tipo": tipo, "contagem_id": "C-1", "id_almoxarifado": ALMOX, "usina_id": 7, "usina_ligada_por": LIGADA,
            "id_item": "5001", "codigo": "SP-TST-001", **mais}


def _regua(**mais):
    return {"id_almoxarifado": ALMOX, "usina_id": 7, "usina_ligada_por": LIGADA, "id_item": "5001",
            "codigo": "SP-TST-001", "acordado_min_qtd": 2, "acordado_max_qtd": 20, "pessoa_id": 3, "pessoa_hmac": HMAC,
            **mais}


def _cur(**mais):
    return {"contagem_id": "C-1", "chave_linha": "L-3", "decisao": "cadastrar", "id_item": "5099",
            "codigo_criado": "SP-TST-002", "pessoa_id": 3, "pessoa_hmac": HMAC, "id_almoxarifado": ALMOX, "usina_id": 7,
            "usina_ligada_por": LIGADA, **mais}


# ── o contrato do livro ──────────────────────────────────────────────────────────────────────────────────────────────

def test_contrato_do_livro():
    """As colunas e a lista de eventos, na ordem: as Tasks 5 a 9 (a lista, a revisão, a gravação, a régua, a curadoria)
    leem e gravam por elas, e coluna nova só no FIM. Na revisão da Task 4 (26/10/2026, antes da 1ª gravação): o
    `usina_ligada_por` (regra 5) no fim do evento e da régua, e a curadoria ganhou `data_id`, `id_almoxarifado`, `usina_id`
    e `usina_ligada_por` (regras 3 e 7), no fim."""
    assert F.LIVRO == "nexus_almoxarifado_inventario"
    assert (F.ABA_EVENTO, F.ABA_REGUA, F.ABA_CURADORIA) == (
        "fato_evento_inventario", "fato_regua_minimo", "fato_curadoria_inventario")
    assert F.CAB_EVENTO == ["evento_id", "quando", "data_id", "contagem_id", "tipo", "id_almoxarifado", "usina_id",
                            "id_item", "codigo", "de_qtd", "para_qtd", "contado_qtd", "movimento_fracttal", "situacao",
                            "lote", "pessoa_id", "pessoa_hmac", "dados_cifrados", "usina_ligada_por"]
    assert F.TIPOS_EVENTO == ("contagem_recebida", "aprovada", "peca_gravada", "conflito", "erro", "peca_tirada",
                              "recontagem_pedida", "numero_corrigido", "substituida", "curadoria", "regua_gravada")
    assert F.CAB_REGUA == ["decidida_em", "data_id", "id_almoxarifado", "usina_id", "id_item", "codigo",
                           "sugestao_min_qtd", "sugestao_max_qtd", "recomendado_min_qtd", "recomendado_max_qtd",
                           "acordado_min_qtd", "acordado_max_qtd", "gravado_fracttal", "pessoa_id", "pessoa_hmac",
                           "usina_ligada_por"]
    assert F.CAB_CURADORIA == ["decidida_em", "contagem_id", "chave_linha", "decisao", "id_item", "codigo_criado",
                               "pessoa_id", "pessoa_hmac", "dados_cifrados", "data_id", "id_almoxarifado", "usina_id",
                               "usina_ligada_por"]
    assert F.DECISOES_CURADORIA == ("cadastrar", "e_a_peca", "confirmar", "descartar")
    assert issubclass(F.Recusada, ValueError)


# ── acrescentar: relê, junta, grava tudo ─────────────────────────────────────────────────────────────────────────────

def test_acrescentar_guarda_o_que_havia(banco):
    """A gravação troca o livro inteiro: sem reler antes, a segunda apagaria a primeira. Com `como_texto=True` a API
    devolve tudo como texto, e a releitura tem de entender igual."""
    api, cfg = banco
    F.acrescentar(cfg, F.ABA_EVENTO, [_ev(), _ev("aprovada", pessoa_id=3, pessoa_hmac=HMAC)])
    F.acrescentar(cfg, F.ABA_REGUA, [_regua()])
    F.acrescentar(cfg, F.ABA_CURADORIA, [_cur(dados={"motivo": "foto não mostra a peça"})])
    F.acrescentar(cfg, F.ABA_EVENTO, [_ev("peca_gravada", de_qtd=2, para_qtd=3, movimento_fracttal="77", lote=1)])
    ev = api.linhas(F.LIVRO, F.ABA_EVENTO)
    assert [e["tipo"] for e in ev] == ["contagem_recebida", "aprovada", "peca_gravada"]
    assert len(api.linhas(F.LIVRO, F.ABA_REGUA)) == 1 and len(api.linhas(F.LIVRO, F.ABA_CURADORIA)) == 1
    assert api.syncs == 4 and api.criacoes == 1
    # o que o módulo põe sozinho: o ID do evento (único), a hora (UTC, com Z) e o dia de Brasília
    assert len({e["evento_id"] for e in ev}) == 3
    assert all(e["quando"].endswith("Z") and len(e["data_id"]) == 8 for e in ev)
    assert ev[0]["usina_id"] == "7" and ev[2]["movimento_fracttal"] == "77"        # texto, como a API devolve
    # as cinco abas do livro, sempre: faltar uma a apagaria (a trava do `so_cresce` recusa)
    assert [q["fato"] for q in api.linhas(F.LIVRO, "qualidade")] == [
        "evento_inventario", "regua_minimo", "curadoria_inventario"]
    assert len(api.linhas(F.LIVRO, "atualizacao")) == 1
    lido = F.ler(cfg, forcar=True)
    assert set(lido) == {F.ABA_EVENTO, F.ABA_REGUA, F.ABA_CURADORIA}
    assert [e["tipo"] for e in lido[F.ABA_EVENTO]] == ["contagem_recebida", "aprovada", "peca_gravada"]
    assert lido[F.ABA_REGUA][0]["acordado_max_qtd"] == "20" and lido[F.ABA_CURADORIA][0]["decisao"] == "cadastrar"


def test_a_ordem_do_livro_e_a_da_gravacao(banco):
    """O estado de cada contagem sai dos eventos na ordem da gravação: uma linha nova vai no FIM, nunca no meio."""
    api, cfg = banco
    for t in ("contagem_recebida", "aprovada", "conflito"):
        F.acrescentar(cfg, F.ABA_EVENTO, [_ev(t)])
    assert [e["tipo"] for e in api.linhas(F.LIVRO, F.ABA_EVENTO)] == ["contagem_recebida", "aprovada", "conflito"]


def test_leitura_que_falha_nao_grava(banco):
    """Se o banco não deixa reler o livro, gravar só a linha nova apagaria o histórico: nada é gravado e quem chamou
    recebe a `Recusada` com o motivo para mostrar na tela."""
    api, cfg = banco
    F.acrescentar(cfg, F.ABA_EVENTO, [_ev()])
    for jeito in ("rede", "500"):
        api.falhar = jeito
        with pytest.raises(F.Recusada, match="nada foi gravado"):
            F.acrescentar(cfg, F.ABA_EVENTO, [_ev("aprovada")])
        with pytest.raises(F.Recusada):
            F.ler(cfg, forcar=True)
    api.falhar = ""
    assert api.syncs == 1 and [e["tipo"] for e in api.linhas(F.LIVRO, F.ABA_EVENTO)] == ["contagem_recebida"]


def test_listagem_incompleta_do_banco_nao_apaga_o_historico(banco):
    """O banco disse que o livro tem 5 abas e a listagem não trouxe nenhuma: quem relê recebe vazio, e a troca apagaria
    tudo. A trava do `so_cresce` (livros.publicar) recusa, e o módulo devolve `Recusada` (não um erro 500)."""
    api, cfg = banco
    F.acrescentar(cfg, F.ABA_EVENTO, [_ev(), _ev("aprovada")])
    api.omitir.add(F.LIVRO)
    F.limpar()
    with pytest.raises(F.Recusada, match="nada foi gravado"):
        F.acrescentar(cfg, F.ABA_EVENTO, [_ev("conflito")])
    api.omitir.clear()
    assert api.syncs == 1 and len(api.linhas(F.LIVRO, F.ABA_EVENTO)) == 2


def test_sem_a_chave_de_gravacao_do_banco_nada_e_gravado(banco):
    api, cfg = banco
    sem = {k: v for k, v in cfg.items() if k != "GRIDCO_SQL_TOKEN"}
    with pytest.raises(F.Recusada, match="GRIDCO_SQL_TOKEN"):
        F.acrescentar(sem, F.ABA_EVENTO, [_ev()])
    assert api.syncs == 0


def test_arquivo_local(cfg, tmp_path):
    """A cópia de prova troca o banco por um arquivo, como o `atribuicoes`; teste sem o arquivo nunca vai à rede."""
    arq = Path(cfg["NEXUS_ALMOX_INVENTARIO_ARQUIVO"])
    assert F.ler(cfg) == {F.ABA_EVENTO: [], F.ABA_REGUA: [], F.ABA_CURADORIA: []}      # ainda não existe: vazio
    F.acrescentar(cfg, F.ABA_EVENTO, [_ev()])
    F.acrescentar(cfg, F.ABA_REGUA, [_regua()])
    F.limpar()                                              # outra "máquina": só o arquivo guarda
    F.acrescentar(cfg, F.ABA_EVENTO, [_ev("aprovada")])
    guardado = json.loads(arq.read_text(encoding="utf-8"))
    assert set(guardado) == {F.ABA_EVENTO, F.ABA_REGUA, F.ABA_CURADORIA}
    assert [e["tipo"] for e in guardado[F.ABA_EVENTO]] == ["contagem_recebida", "aprovada"]
    assert guardado[F.ABA_REGUA][0]["acordado_min_qtd"] == 2 and guardado[F.ABA_CURADORIA] == []
    assert not list(tmp_path.glob("*.tmp"))
    assert [e["tipo"] for e in F.ler(cfg, forcar=True)[F.ABA_EVENTO]] == ["contagem_recebida", "aprovada"]
    # teste sem arquivo: lê vazio e não grava (o banco de verdade nunca é tocado por um teste)
    F.limpar()
    sem = {"TESTING": True, "GRIDCO_SQL_TOKEN": "tk", "NEXUS_CHAVE_CADASTRO": cfg["NEXUS_CHAVE_CADASTRO"]}
    assert F.ler(sem, forcar=True) == {F.ABA_EVENTO: [], F.ABA_REGUA: [], F.ABA_CURADORIA: []}
    with pytest.raises(F.Recusada, match="nada foi gravado"):
        F.acrescentar(sem, F.ABA_EVENTO, [_ev()])


def test_a_leitura_fica_2_minutos_e_a_gravacao_a_renova(cfg, monkeypatch):
    t = [1000.0]
    monkeypatch.setattr(F, "_relogio", lambda: t[0])
    F.acrescentar(cfg, F.ABA_EVENTO, [_ev()])
    arq = Path(cfg["NEXUS_ALMOX_INVENTARIO_ARQUIVO"])
    de_fora = json.loads(arq.read_text(encoding="utf-8"))
    de_fora[F.ABA_EVENTO].append(dict(de_fora[F.ABA_EVENTO][0], evento_id="escrito-por-fora", tipo="aprovada"))
    arq.write_text(json.dumps(de_fora), encoding="utf-8")
    assert len(F.ler(cfg)[F.ABA_EVENTO]) == 1                 # a cópia ainda vale
    t[0] += 119
    assert len(F.ler(cfg)[F.ABA_EVENTO]) == 1
    t[0] += 2
    assert len(F.ler(cfg)[F.ABA_EVENTO]) == 2                 # passou de 2 minutos: relê
    F.acrescentar(cfg, F.ABA_EVENTO, [_ev("conflito")])
    assert [e["tipo"] for e in F.ler(cfg)[F.ABA_EVENTO]] == ["contagem_recebida", "aprovada", "conflito"]
    F.ler(cfg)[F.ABA_EVENTO].append("lixo")                   # quem recebe a lista não estraga a cópia
    assert len(F.ler(cfg)[F.ABA_EVENTO]) == 3


# ── o que o módulo põe e o que ele recusa ────────────────────────────────────────────────────────────────────────────

def test_o_dia_e_o_de_brasilia_e_o_que_veio_pronto_vale(cfg):
    """O App e o servidor falam UTC: 02:30Z ainda é o dia anterior em Brasília (regra 7). A hora e o ID que o chamador
    já trouxe (a retomada de uma gravação, por exemplo) o módulo não troca."""
    F.acrescentar(cfg, F.ABA_EVENTO, [_ev(quando="2026-10-27T02:30:00Z", evento_id="E-1")])
    F.acrescentar(cfg, F.ABA_REGUA, [_regua(decidida_em="2026-10-27T03:00:00Z")])
    ev, rg = F.ler(cfg, forcar=True)[F.ABA_EVENTO][0], F.ler(cfg)[F.ABA_REGUA][0]
    assert (ev["evento_id"], ev["quando"], ev["data_id"]) == ("E-1", "2026-10-27T02:30:00Z", 20261026)
    assert (rg["decidida_em"], rg["data_id"]) == ("2026-10-27T03:00:00Z", 20261027)
    with pytest.raises(ValueError, match="quando"):
        F.acrescentar(cfg, F.ABA_EVENTO, [_ev(quando="ontem")])


def test_lote_que_nao_vale_nao_grava_nada(cfg):
    F.acrescentar(cfg, F.ABA_EVENTO, [_ev()])
    with pytest.raises(ValueError, match="tipo"):                    # fora da lista fechada (regra 4)
        F.acrescentar(cfg, F.ABA_EVENTO, [_ev("aprovada"), _ev("inventei")])
    with pytest.raises(ValueError, match="aba"):
        F.acrescentar(cfg, "fato_qualquer", [_ev()])
    with pytest.raises(ValueError, match="decisao"):
        F.acrescentar(cfg, F.ABA_CURADORIA, [_cur(decisao="sei la")])
    with pytest.raises(ValueError, match="chave_linha"):             # sem a linha, a decisão não diz de que peça é
        F.acrescentar(cfg, F.ABA_CURADORIA, [_cur(chave_linha="")])
    with pytest.raises(ValueError, match="id_item"):
        F.acrescentar(cfg, F.ABA_REGUA, [_regua(id_item="")])
    assert [e["tipo"] for e in F.ler(cfg, forcar=True)[F.ABA_EVENTO]] == ["contagem_recebida"]


def test_numeros_e_ids_entram_limpos(cfg):
    """A quantidade é número (o texto "2,5" da tela vira 2.5; o 0 digitado fica 0 e o em branco fica vazio, nunca 0:
    "não contei" não zera o estoque), e o ID do Fracttal fica texto (sem virar 5001.0 na ida e volta pela API)."""
    F.acrescentar(cfg, F.ABA_EVENTO, [_ev("peca_gravada", de_qtd="2,5", para_qtd=0, contado_qtd=None, id_item=5001,
                                          lote="3", usina_id="7.0")])
    e = F.ler(cfg, forcar=True)[F.ABA_EVENTO][0]
    assert (e["de_qtd"], e["para_qtd"], e["contado_qtd"]) == (2.5, 0, None)
    assert (e["id_item"], e["lote"], e["usina_id"]) == ("5001", 3, 7)
    F.acrescentar(cfg, F.ABA_REGUA, [_regua(gravado_fracttal=True, acordado_min_qtd=2.0)])
    r = F.ler(cfg, forcar=True)[F.ABA_REGUA][0]
    assert (r["gravado_fracttal"], r["acordado_min_qtd"]) == (1, 2)
    for ruim in ({"contado_qtd": "abc"}, {"contado_qtd": "nan"}, {"de_qtd": float("inf")}, {"para_qtd": True}):
        with pytest.raises(ValueError, match="_qtd"):
            F.acrescentar(cfg, F.ABA_EVENTO, [_ev(**ruim)])
    with pytest.raises(ValueError, match="usina_id"):
        F.acrescentar(cfg, F.ABA_EVENTO, [_ev(usina_id="Irecê")])        # o nome da usina não é ID: não chuta
    with pytest.raises(ValueError, match="gravado_fracttal"):
        F.acrescentar(cfg, F.ABA_REGUA, [_regua(gravado_fracttal="talvez")])
    assert len(F.ler(cfg, forcar=True)[F.ABA_EVENTO]) == 1


def test_evento_repetido_nao_grava(cfg):
    """O ID do evento é a chave do fato: o mesmo duas vezes (na leitura ou no mesmo lote) é grão repetido."""
    F.acrescentar(cfg, F.ABA_EVENTO, [_ev(evento_id="E-1")])
    with pytest.raises(F.Recusada, match="E-1"):
        F.acrescentar(cfg, F.ABA_EVENTO, [_ev(evento_id="E-1")])
    with pytest.raises(F.Recusada, match="E-2"):
        F.acrescentar(cfg, F.ABA_EVENTO, [_ev(evento_id="E-2"), _ev(evento_id="E-2")])
    assert len(F.ler(cfg, forcar=True)[F.ABA_EVENTO]) == 1


def test_a_lista_vazia_nao_grava(banco):
    api, cfg = banco
    F.acrescentar(cfg, F.ABA_EVENTO, [])
    assert api.syncs == 0


# ── governança: nada de nome, e-mail nem texto livre em claro ────────────────────────────────────────────────────────

def test_nada_de_nome_no_livro(cfg):
    """A API do banco tem leitura aberta: nome, e-mail e o motivo do PCM (texto livre) não têm coluna em claro. O
    motivo vai só dentro do `dados_cifrados` (o Cofre do cadastro), amarrado à linha."""
    proibidas = ("nome", "email", "e_mail", "motivo", "obs", "descri", "texto", "comentario", "tecnico")
    for cab in (F.CAB_EVENTO, F.CAB_REGUA, F.CAB_CURADORIA):
        assert not [c for c in cab if any(p in c for p in proibidas)], cab
    assert "dados_cifrados" in F.CAB_EVENTO and "dados_cifrados" in F.CAB_CURADORIA
    assert "dados_cifrados" not in F.CAB_REGUA                  # a régua é número: não tem texto livre
    F.acrescentar(cfg, F.ABA_EVENTO, [_ev("peca_tirada", dados={"motivo": "peça com defeito do lote azul"})])
    F.acrescentar(cfg, F.ABA_CURADORIA, [_cur(decisao="descartar", dados={"motivo": "duplicada da prateleira cinza"})])
    bruto = Path(cfg["NEXUS_ALMOX_INVENTARIO_ARQUIVO"]).read_text(encoding="utf-8")
    assert "defeito" not in bruto and "lote azul" not in bruto and "prateleira" not in bruto
    ev, cur = F.ler(cfg, forcar=True)[F.ABA_EVENTO][0], F.ler(cfg)[F.ABA_CURADORIA][0]
    assert ev["dados_cifrados"].startswith("cf1:") and cur["dados_cifrados"].startswith("cf1:")
    assert F.decifrar(cfg, F.ABA_EVENTO, ev) == {"motivo": "peça com defeito do lote azul"}
    assert F.decifrar(cfg, F.ABA_CURADORIA, cur) == {"motivo": "duplicada da prateleira cinza"}
    # amarrada à linha: a cifra copiada para outra linha não abre; e a chave de outra instalação também não
    assert F.decifrar(cfg, F.ABA_EVENTO, dict(ev, evento_id="outro")) == {}
    assert F.decifrar(cfg, F.ABA_CURADORIA, dict(cur, chave_linha="L-9")) == {}
    assert F.decifrar(dict(cfg, NEXUS_CHAVE_CADASTRO=gerar_chave()), F.ABA_EVENTO, ev) == {}
    assert F.decifrar({}, F.ABA_EVENTO, ev) == {} and F.decifrar(cfg, F.ABA_EVENTO, dict(ev, dados_cifrados="")) == {}


def test_texto_livre_em_claro_e_erro_de_quem_chama(cfg):
    """O motivo não é coluna: passar `motivo=` (ou nome, ou e-mail) é erro de quem chama, e não vira texto em claro nem
    some em silêncio. E-mail em qualquer coluna em claro (a pessoa é o `pessoa_hmac`) também."""
    for ruim in ({"motivo": "x"}, {"nome": "Fulano"}, {"email": "a@b.c"}, {"obs": "x"}):
        with pytest.raises(ValueError, match="coluna"):
            F.acrescentar(cfg, F.ABA_EVENTO, [_ev(**ruim)])
    with pytest.raises(ValueError, match="e-mail"):
        F.acrescentar(cfg, F.ABA_EVENTO, [_ev(codigo="alguem@exemplo.com")])
    with pytest.raises(ValueError, match="pessoa_hmac"):
        F.acrescentar(cfg, F.ABA_EVENTO, [_ev(pessoa_hmac="alguem@exemplo.com")])
    with pytest.raises(ValueError, match="dados"):               # a régua não tem onde cifrar texto
        F.acrescentar(cfg, F.ABA_REGUA, [_regua(dados={"motivo": "x"})])
    assert F.ler(cfg, forcar=True)[F.ABA_EVENTO] == []


def test_sem_a_chave_do_cadastro_o_texto_livre_nao_vai(cfg):
    sem = {k: v for k, v in cfg.items() if k != "NEXUS_CHAVE_CADASTRO"}
    with pytest.raises(F.Recusada, match="NEXUS_CHAVE_CADASTRO"):
        F.acrescentar(sem, F.ABA_EVENTO, [_ev("peca_tirada", dados={"motivo": "x"})])
    F.acrescentar(sem, F.ABA_EVENTO, [_ev()])                    # o evento sem texto não precisa da chave
    assert len(F.ler(sem, forcar=True)[F.ABA_EVENTO]) == 1


# ── a revisão da Task 4 (26/10/2026): nenhuma coluna em claro aceita texto livre ─────────────────────────────────────

def test_dados_cifrados_nao_entra_pronto(cfg):
    """O revisor guardou `dados_cifrados="o motivo em claro..."` e o módulo aceitou: a cifra só vale se for o módulo a
    fazê-la. O texto livre entra por `dados`; a coluna não se passa."""
    with pytest.raises(ValueError, match="dados_cifrados"):
        F.acrescentar(cfg, F.ABA_EVENTO, [_ev("peca_tirada", dados_cifrados="o motivo em claro: peça do fulano")])
    with pytest.raises(ValueError, match="dados_cifrados"):
        F.acrescentar(cfg, F.ABA_CURADORIA, [_cur(dados_cifrados="cf1:parece-cifra-mas-nao-e")])
    assert F.ler(cfg, forcar=True)[F.ABA_EVENTO] == [] and F.ler(cfg)[F.ABA_CURADORIA] == []


def test_pessoa_hmac_e_o_codigo_de_24_hexadecimais(cfg):
    """O código de verdade é o `ligacao_cadastro.codigo_da_pessoa` (24 hexadecimais minúsculos). Nome, e-mail ou qualquer
    outro texto na coluna é recusado, nos três fatos."""
    from nexus.campo.ligacao_cadastro import codigo_da_pessoa
    real = codigo_da_pessoa("chave-hmac-de-teste", "pessoa.teste@exemplo.com")
    assert F._RE_HMAC.fullmatch(real)
    F.acrescentar(cfg, F.ABA_EVENTO, [_ev(pessoa_hmac=real)])
    for ruim in ("Fulano de Tal", "alguem@exemplo.com", "A1B2C3D4E5F60718293A4B5C", HMAC[:-1], HMAC + "0", "g" * 24):
        for aba, linha in ((F.ABA_EVENTO, _ev), (F.ABA_REGUA, _regua), (F.ABA_CURADORIA, _cur)):
            with pytest.raises(ValueError, match="pessoa_hmac"):
                F.acrescentar(cfg, aba, [linha(pessoa_hmac=ruim)])
    assert len(F.ler(cfg, forcar=True)[F.ABA_EVENTO]) == 1


def test_situacao_e_lista_fechada(cfg):
    """A `situacao` é uma das seis situações da peça no lote (`contas.SITUACOES`) ou vazia: o texto do erro do Fracttal
    ("erro do Fracttal para fulano") não tem coluna em claro. A lista mora em `dominios.py`, que não importa o PCM, e o teste
    garante que é a mesma do PCM."""
    assert dominios.SITUACAO_INVENTARIO == contas.SITUACOES
    for boa in contas.SITUACOES:
        F.acrescentar(cfg, F.ABA_EVENTO, [_ev("conflito", situacao=boa)])
    F.acrescentar(cfg, F.ABA_EVENTO, [_ev("conflito", situacao="")])
    for ruim in ("erro do Fracttal para fulano", "Para cima", "gravada"):
        with pytest.raises(ValueError, match="situacao"):
            F.acrescentar(cfg, F.ABA_EVENTO, [_ev("erro", situacao=ruim)])
    assert len(F.ler(cfg, forcar=True)[F.ABA_EVENTO]) == len(contas.SITUACOES) + 1


def test_ids_do_fracttal_sao_digitos(cfg):
    """`id_item`, `id_almoxarifado` e `movimento_fracttal` (o folio que o Fracttal devolve) são números; vazio só onde a
    coluna deixa (a peça fora do catálogo não tem item, e o evento sem gravação não tem movimento). O "5001.0" que a API às
    vezes devolve é o 5001. Os IDs opacos (evento, contagem, linha) não levam espaço: frase não é ID."""
    F.acrescentar(cfg, F.ABA_EVENTO, [_ev("contagem_recebida", id_item="", movimento_fracttal="", codigo=""),
                                      _ev("peca_gravada", id_item="5001.0", movimento_fracttal=7)])
    e = F.ler(cfg, forcar=True)[F.ABA_EVENTO]
    assert (e[0]["id_item"], e[1]["id_item"], e[1]["movimento_fracttal"]) == (None, "5001", "7")
    for coluna, ruim in (("id_item", "SP-TST-001"), ("id_item", "5 001"), ("id_almoxarifado", "almox norte"),
                         ("movimento_fracttal", "M-77"), ("evento_id", "meu evento"), ("contagem_id", "contagem de ontem"),
                         ("codigo", "x" * 61)):
        with pytest.raises(ValueError, match=coluna):
            F.acrescentar(cfg, F.ABA_EVENTO, [_ev("peca_gravada", **{coluna: ruim})])
    with pytest.raises(ValueError, match="chave_linha"):
        F.acrescentar(cfg, F.ABA_CURADORIA, [_cur(chave_linha="a linha do fulano")])
    with pytest.raises(ValueError, match="id_item"):
        F.acrescentar(cfg, F.ABA_REGUA, [_regua(id_item="SP-TST-001")])
    assert len(F.ler(cfg, forcar=True)[F.ABA_EVENTO]) == 2


def test_curadoria_leva_data_usina_e_almoxarifado(cfg):
    """Revisão de 26/10/2026: a curadoria ganhou `data_id` (o dia de Brasília do `decidida_em`, regra 7), `id_almoxarifado`,
    `usina_id` e `usina_ligada_por`. A decisão das 23:30 de Brasília é do dia de Brasília, não do dia UTC."""
    F.acrescentar(cfg, F.ABA_CURADORIA, [_cur(decidida_em="2026-10-27T02:30:00Z")])
    c = F.ler(cfg, forcar=True)[F.ABA_CURADORIA][0]
    assert (c["data_id"], c["id_almoxarifado"], c["usina_id"], c["usina_ligada_por"]) == (20261026, ALMOX, 7, LIGADA)
    with pytest.raises(ValueError, match="data_id"):
        F.acrescentar(cfg, F.ABA_CURADORIA, [_cur(decidida_em="2026-10-27T02:30:00Z", data_id=20261027)])


def test_usina_so_com_a_linhagem_dela(cfg):
    """Regra 5: o fato diz por onde ligou a usina. `usina_id` sem `usina_ligada_por` não se grava (nem o inverso), e o
    caminho tem de ser um que o almoxarifado conhece (a de-para do Fracttal, nunca o código da usina)."""
    for aba, linha in ((F.ABA_EVENTO, _ev), (F.ABA_REGUA, _regua), (F.ABA_CURADORIA, _cur)):
        with pytest.raises(ValueError, match="usina_ligada_por"):
            F.acrescentar(cfg, aba, [linha(usina_ligada_por=None)])
        with pytest.raises(ValueError, match="usina_ligada_por"):
            F.acrescentar(cfg, aba, [linha(usina_id=None)])
        with pytest.raises(ValueError, match="usina_ligada_por"):
            F.acrescentar(cfg, aba, [linha(usina_ligada_por="código da usina")])
        F.acrescentar(cfg, aba, [linha(usina_id=None, usina_ligada_por=None)])      # sem usina: vazio, nunca chutado
    assert F.USINA_LIGADA_POR == (LIGADA,)


def test_hora_em_utc_com_z_e_data_id_do_dia_de_brasilia(cfg):
    """`quando` e `decidida_em` são normalizados para UTC com "Z" (a hora com o deslocamento de Brasília vira a UTC); sem
    fuso a hora é ambígua e não entra; o `data_id` que o chamador traz tem de ser o dia de Brasília dessa hora."""
    F.acrescentar(cfg, F.ABA_EVENTO, [_ev(quando="2026-10-26T23:30:00-03:00"), _ev(quando="2026-10-26T12:00:00+00:00"),
                                      _ev(quando="2026-10-26T12:00:00.987Z", data_id=20261026)])
    quandos = [e["quando"] for e in F.ler(cfg, forcar=True)[F.ABA_EVENTO]]
    assert quandos == ["2026-10-27T02:30:00Z", "2026-10-26T12:00:00Z", "2026-10-26T12:00:00Z"]
    assert F.ler(cfg)[F.ABA_EVENTO][0]["data_id"] == 20261026               # 23:30 em Brasília: ainda o dia 26
    with pytest.raises(ValueError, match="fuso"):
        F.acrescentar(cfg, F.ABA_EVENTO, [_ev(quando="2026-10-27T02:30:00")])
    with pytest.raises(ValueError, match="data_id"):
        F.acrescentar(cfg, F.ABA_EVENTO, [_ev(quando="2026-10-27T02:30:00Z", data_id=20261027)])
    assert len(F.ler(cfg, forcar=True)[F.ABA_EVENTO]) == 3


# ── a revisão da Task 4: a leitura que vem curta e a cópia ───────────────────────────────────────────────────────────

def test_leitura_menor_que_o_banco_diz_nao_grava(banco):
    """A listagem diz 3 linhas e a leitura devolve 2 (página curta): gravar +1 daria 3, e a trava `so_cresce` (que compara
    com o `row_count`) deixaria passar, perdendo a peça gravada no Fracttal que as Tasks 6 a 8 derivam destes eventos. Antes
    de gravar, o módulo compara o que leu com o `row_count` e recusa."""
    api, cfg = banco
    F.acrescentar(cfg, F.ABA_EVENTO, [_ev(), _ev("aprovada"), _ev("peca_gravada")])
    api.cortar = 1
    with pytest.raises(F.Recusada, match="nada foi gravado"):
        F.acrescentar(cfg, F.ABA_EVENTO, [_ev("conflito")])
    with pytest.raises(F.Recusada):
        F.ler(cfg, forcar=True)
    api.cortar = 0
    assert api.syncs == 1 and len(api.linhas(F.LIVRO, F.ABA_EVENTO)) == 3
    F.acrescentar(cfg, F.ABA_EVENTO, [_ev("conflito")])                     # a leitura inteira volta a gravar
    assert len(api.linhas(F.LIVRO, F.ABA_EVENTO)) == 4


def test_ler_devolve_copia_das_linhas(cfg):
    F.acrescentar(cfg, F.ABA_EVENTO, [_ev(evento_id="E-1")])
    F.ler(cfg)[F.ABA_EVENTO][0]["tipo"] = "adulterado"                      # a linha de quem recebe é só dele
    assert F.ler(cfg)[F.ABA_EVENTO][0]["tipo"] == "contagem_recebida"
    F.limpar()
    F.ler(cfg)[F.ABA_EVENTO][0]["tipo"] = "adulterado"
    assert F.ler(cfg)[F.ABA_EVENTO][0]["tipo"] == "contagem_recebida"


def test_leitura_lenta_nao_sobrescreve_a_cache_mais_nova(cfg, monkeypatch):
    """Uma leitura que demora enquanto outra thread grava não pode pôr a cópia velha por cima da que a gravação acabou de
    renovar (a tela voltaria a mostrar a contagem como `nova` depois de gravada)."""
    F.acrescentar(cfg, F.ABA_EVENTO, [_ev()])
    original, feito = F._ler_cru, []

    def lenta(c):
        velho = original(c)
        if not feito:
            feito.append(1)
            F.acrescentar(c, F.ABA_EVENTO, [_ev("aprovada")])                # outra thread gravou enquanto esta lia
        return velho

    monkeypatch.setattr(F, "_ler_cru", lenta)
    F.ler(cfg, forcar=True)
    monkeypatch.setattr(F, "_ler_cru", original)
    assert [e["tipo"] for e in F.ler(cfg)[F.ABA_EVENTO]] == ["contagem_recebida", "aprovada"]


# ── a qualidade e a atualização ──────────────────────────────────────────────────────────────────────────────────────

def test_a_qualidade_mede_a_ligacao_de_cada_fato(banco):
    api, cfg = banco
    F.acrescentar(cfg, F.ABA_EVENTO, [_ev(pessoa_id=3, pessoa_hmac=HMAC), _ev("conflito"),
                                      _ev("erro", usina_id=None, usina_ligada_por=None)])
    F.acrescentar(cfg, F.ABA_REGUA, [_regua()])
    q = {l["fato"]: l for l in api.linhas(F.LIVRO, "qualidade")}
    assert list(api.linhas(F.LIVRO, "qualidade")[0]) == fatos.CAB_QUALIDADE
    e = q["evento_inventario"]
    assert (e["linhas"], e["com_data"], e["com_usina"], e["com_pessoa"]) == ("3", "3", "2", "1")
    assert (float(e["pct_data"]), float(e["pct_usina"])) == (100.0, 66.7)
    assert (e["usina_por_de_para"], e["usina_por_codigo"]) == ("2", "0")        # só liga pela de-para do Fracttal
    assert json.loads(e["extra"]) == {"tipo_contagem_recebida": 1, "tipo_conflito": 1, "tipo_erro": 1}
    assert q["regua_minimo"]["linhas"] == "1" and float(q["regua_minimo"]["pct_pessoa"]) == 100.0
    assert q["curadoria_inventario"]["linhas"] == "0" and q["curadoria_inventario"]["pct_data"] in (None, "")
    assert e["livro_origem"] and e["gerado_em"].endswith("Z")
    at = api.linhas(F.LIVRO, "atualizacao")[0]
    assert list(at) == F.CAB_ATUALIZACAO and at["linhas"] == "4" and at["maquina"] in ("pc", "servidor")


def test_governanca_le_a_qualidade_do_inventario(app, banco, monkeypatch):
    """A tela Base → Governança de dados lê a qualidade do livro (como a do almoxarifado), pela `_ultima_qualidade`."""
    from nexus.dados import telas as T
    api, cfg = banco
    F.acrescentar(cfg, F.ABA_EVENTO, [_ev()])
    app.config.update(GRIDCO_DB_API=BASE)
    monkeypatch.setitem(T._CACHE, "v", None)
    v = T._ultima_qualidade()
    assert v["qualidade"]["evento_inventario"]["linhas"] == "1", v.get("erro")


# ── o catálogo (PRIORIDADE 0: a fonte nova entra primeiro, com grão, tipo e dimensões) ───────────────────────────────

def test_inventario_no_catalogo():
    lv = catalogo.LIVRO_POR_NOME[F.LIVRO]
    assert lv.abas == (F.ABA_EVENTO, F.ABA_REGUA, F.ABA_CURADORIA, "qualidade", "atualizacao")
    assert lv.so_cresce == (F.ABA_EVENTO, F.ABA_REGUA, F.ABA_CURADORIA) and not lv.no_banco
    assert all(catalogo.aba_segue_a_regra(a) for a in lv.abas)
    assert livros._so_cresce(F.LIVRO) == lv.so_cresce
    por_id = {"evento_inventario": (F.ABA_EVENTO, F.CAB_EVENTO, "transacao"),
              "regua_minimo": (F.ABA_REGUA, F.CAB_REGUA, "transacao"),
              "curadoria_inventario": (F.ABA_CURADORIA, F.CAB_CURADORIA, "sem_medida")}
    for fid, (aba, cab, tipo) in por_id.items():
        f = catalogo.POR_ID[fid]
        assert f.estado == "conformado" and f.area == "pcm" and f.tipo == tipo, fid        # o Nexus é a fonte
        assert f.livro == f.conformado_em == f"{F.LIVRO} · {aba}" and f.fontes == (f.livro,), fid
        assert f.grao.startswith("1 linha") and f.chave[0] == cab[0] and all(c in cab for c in f.chave), fid
        assert all(m.coluna in cab and catalogo.medida_valida(m) for m in f.medidas), fid
        assert (f.tipo == "sem_medida") == (f.medidas == ()), fid
        assert set(f.dims) == set(catalogo.DIM_IDS) and f.dims["pessoa"][0] == "id", fid
        assert explica.RESUMO.get(fid) and explica.PARA_QUE.get(fid), fid
    assert catalogo.POR_ID["evento_inventario"].chave == ("evento_id",)
    # data e usina ligam por ID nos três (a curadoria ganhou data_id e usina_id na revisão de 26/10/2026), com a linhagem
    assert all(catalogo.POR_ID[f].dims[d][0] == "id" for f in por_id for d in ("data", "usina", "pessoa"))
    assert all("usina_ligada_por" in cab for _aba, cab, _t in por_id.values())
    assert catalogo.POR_ID["evento_inventario"].dims["equipamento"][0] == "prop"     # o item, como no almoxarifado
    assert {m.coluna for m in catalogo.POR_ID["evento_inventario"].medidas} == {"de_qtd", "para_qtd", "contado_qtd"}
    assert "gravado_fracttal" in {m.coluna for m in catalogo.POR_ID["regua_minimo"].medidas}
    # o contado e o saldo somam entre almoxarifados do MESMO item, nunca entre itens (a unidade é a do item)
    assert all(m.soma == "semi" for fid in ("evento_inventario", "regua_minimo")
               for m in catalogo.POR_ID[fid].medidas if m.unidade != "1/0")


def test_config_e_env_example_do_arquivo_local():
    from nexus import config
    assert "NEXUS_ALMOX_INVENTARIO_ARQUIVO" in config.OPCIONAIS
    assert "NEXUS_ALMOX_INVENTARIO_ARQUIVO=" in RAIZ.joinpath(".env.example").read_text("utf-8")
