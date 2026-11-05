"""Os administradores do App de Campo (05/11/2026, nexus/pcm/admins_app.py: a aba `fato_admin_app` do livro dos
técnicos por usina, que o App já lê).

Levi, 05/11/2026: "os administradores do App de Campo e os técnicos por usina têm de ser escolhidos no Nexus". O que
estes testes seguram: a assinatura igual à do contrato com o App (o vetor fixo); vale a última decisão de cada código ×
papel (empate: a de depois no livro), com as datas e o dia de Brasília; pôr, tirar e a mesma decisão que não grava de
novo; sem código, sem a NEXUS_PESSOA_HMAC, a leitura que falha e a observação sem a chave do cadastro não gravam; nada em
claro no livro; as duas abas do livro vão juntas a cada gravação (no arquivo e no banco de mentira), e a outra que não se
relê não grava; e o catálogo e o radar da Governança conhecem a aba. Nada vai ao banco de verdade."""
import hashlib
import hmac
import io
import json
from datetime import datetime, timezone

import pytest
from pg_falso import ApiPGFalsa

from nexus.cadastro.cifra import gerar_chave
from nexus.dados import catalogo, explica, livros, radar
from nexus.pcm import admins_app as AA
from nexus.pcm import atribuicoes as A
from test_dados_camada import PROIBIDAS
from test_pcm_atribuicoes import Relogio

PESSOA = {"email": "pessoa.teste@exemplo.com", "nome": "Pessoa Teste"}
CHAVE = "chave-hmac-de-teste"
# o vetor do contrato (`_propostas/admins-app-nexus/LEIA.md` do app-campo-docs): o mesmo nos dois lados
VETOR_LINHA = {"pessoa_hmac": "0123456789abcdef01234567", "papel": "admin", "ativo": "sim", "de_data_id": "",
               "ate_data_id": 20261231, "decidida_em": "2026-11-05T14:30:00Z"}
VETOR = "c657c3aaf1d64a5aae81f585a40115bb9bf11dffbd98bcff9338c00eeea9241c"


@pytest.fixture
def cfg(tmp_path):
    A.limpar()
    AA.limpar()
    return {"TESTING": True, "NEXUS_PCM_ATRIBUICOES_ARQUIVO": str(tmp_path / "atribuicoes.json"),
            "NEXUS_CHAVE_CADASTRO": gerar_chave(), "NEXUS_PESSOA_HMAC": CHAVE}


@pytest.fixture
def relogio(monkeypatch):
    """O relógio do livro em 05/11/2026 12:00Z, um minuto a cada decisão."""
    return Relogio(monkeypatch, inicio=datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc))


def cod(pid, versao=0):
    return f"{pid + 1000 * versao:024x}"


def _por(cfg, pid=10, codigo=None, **kw):
    return AA.decidir(cfg, pessoa_id=pid, pessoa_hmac=codigo or cod(pid), ativo=True, usuario=PESSOA, **kw)


def _tirar(cfg, pid=10, codigo=None):
    return AA.decidir(cfg, pessoa_id=pid, pessoa_hmac=codigo or cod(pid), ativo=False, usuario=PESSOA)


def _atuais(cfg, hoje=20261105):
    return AA.atuais(AA.ler(cfg, forcar=True), hoje)


def _arquivo(cfg):
    return json.loads(open(cfg["NEXUS_PCM_ATRIBUICOES_ARQUIVO"], encoding="utf-8").read())


# ── o contrato com o App ─────────────────────────────────────────────────────────────────────────────────────────
def test_assinatura_igual_a_do_contrato_com_o_app():
    assert AA.assinatura(VETOR_LINHA, CHAVE) == VETOR
    # a mesma conta, à mão, como o contrato a escreve (chave derivada pelo rótulo; o texto com o dia como inteiro)
    chave = hmac.new(CHAVE.encode(), b"nexus:pcm:admins-app", hashlib.sha256).digest()
    txt = "admin_app|0123456789abcdef01234567|admin|sim||20261231|2026-11-05T14:30:00Z"
    assert hmac.new(chave, txt.encode(), hashlib.sha256).hexdigest() == VETOR
    assert AA.assinatura(VETOR_LINHA, "") == "" and AA.assinatura(VETOR_LINHA, "outra") != VETOR
    # a assinatura dos técnicos é outra (outro rótulo, outro texto): uma linha não vale pela outra
    assert A.ROTULO_CHAVE != AA.ROTULO_CHAVE


def test_as_colunas_e_cada_linha_como_o_contrato(cfg, relogio):
    assert A.CAB_ADMIN == ("decidida_em", "data_id", "pessoa_id", "pessoa_hmac", "papel", "ativo", "de_data_id",
                           "ate_data_id", "origem", "decidida_por_hmac", "dados_cifrados", "assinatura")
    assert _por(cfg)["gravou"] is True
    linha = _arquivo(cfg)[A.ABA_ADMIN][0]
    assert list(linha) == list(A.CAB_ADMIN)
    assert (linha["papel"], linha["ativo"], linha["origem"], linha["pessoa_id"], linha["pessoa_hmac"]) == (
        "admin", "sim", "tela", 10, cod(10))
    assert linha["decidida_em"] == "2026-11-05T12:01:00Z" and linha["data_id"] == 20261105
    assert linha["de_data_id"] is None and linha["ate_data_id"] is None            # vazio no livro
    assert linha["assinatura"] == AA.assinatura(linha, CHAVE)
    from nexus.campo.ligacao_cadastro import codigo_da_pessoa
    assert linha["decidida_por_hmac"] == codigo_da_pessoa(CHAVE, PESSOA["email"])


# ── o vigente ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_vale_a_ultima_decisao_de_cada_codigo_e_papel(cfg, relogio):
    _por(cfg, 10)
    _por(cfg, 11)
    _tirar(cfg, 10)
    assert set(_atuais(cfg)) == {(cod(11), "admin")}
    assert _atuais(cfg)[(cod(11), "admin")]["status"] == "vale"
    # o App acha a pessoa pelo código: a mesma ficha com o e-mail corrigido é outra linha (o tirar leva o código que pôs)
    _por(cfg, 11, codigo=cod(11, 1))
    assert set(_atuais(cfg)) == {(cod(11), "admin"), (cod(11, 1), "admin")}


def test_no_empate_da_hora_vale_a_de_depois_no_livro():
    def linha(ativo):
        return {"decidida_em": "2026-11-05T12:00:00Z", "pessoa_id": 10, "pessoa_hmac": cod(10), "papel": "admin",
                "ativo": ativo, "de_data_id": None, "ate_data_id": None}
    assert AA.atuais({"decisoes": [linha("sim"), linha("nao")]}, 20261105) == {}
    assert set(AA.atuais({"decisoes": [linha("nao"), linha("sim")]}, 20261105)) == {(cod(10), "admin")}


def test_as_datas_pelo_dia_de_brasilia(cfg, monkeypatch):
    rel = Relogio(monkeypatch, inicio=datetime(2026, 11, 6, 2, 29, tzinfo=timezone.utc))    # 23h30 de 05/11 em Brasília
    _por(cfg, 10, ate="2026-11-05")
    assert _arquivo(cfg)[A.ABA_ADMIN][0]["data_id"] == 20261105
    _por(cfg, 11, de="2026-11-10")
    assert _atuais(cfg, 20261105)[(cod(10), "admin")]["status"] == "vale"          # o último dia ainda vale
    assert (cod(10), "admin") not in _atuais(cfg, 20261106)
    assert _atuais(cfg, 20261105)[(cod(11), "admin")]["status"] == "agendado"
    assert _atuais(cfg, 20261110)[(cod(11), "admin")]["status"] == "vale"
    with pytest.raises(AA.Recusada):
        _por(cfg, 12, ate="2026-11-04")                                           # o prazo que já acabou
    with pytest.raises(AA.Recusada):
        _por(cfg, 12, de="2026-11-20", ate="2026-11-12")
    with pytest.raises(AA.Recusada):
        _por(cfg, 12, ate="05/11/2026")
    assert rel.t.date().isoformat() == "2026-11-06"


# ── pôr e tirar ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_mesma_decisao_nao_grava_de_novo_e_tirar_quem_nao_e_recusa(cfg, relogio):
    assert _por(cfg)["gravou"] is True
    assert _por(cfg)["gravou"] is False
    assert len(_arquivo(cfg)[A.ABA_ADMIN]) == 1
    assert _tirar(cfg)["gravou"] is True
    with pytest.raises(AA.Recusada, match="já não é administrador"):
        _tirar(cfg)
    with pytest.raises(AA.Recusada, match="já não é administrador"):
        _tirar(cfg, 11)
    assert [x["ativo"] for x in _arquivo(cfg)[A.ABA_ADMIN]] == ["sim", "nao"]
    with pytest.raises(AA.Recusada):
        AA.decidir(cfg, pessoa_id=10, pessoa_hmac=cod(10), ativo=True, usuario=PESSOA, papel="dono")


def test_sem_codigo_nao_poe(cfg, relogio):
    with pytest.raises(AA.Recusada, match="sem e-mail na ficha nem usuário do Fracttal ligado: o App não a reconheceria"):
        AA.decidir(cfg, pessoa_id=10, pessoa_hmac="", ativo=True, usuario=PESSOA)
    assert AA.ler(cfg, forcar=True)["decisoes"] == []


def test_sem_a_chave_hmac_nada_grava(cfg, relogio):
    """Sem a NEXUS_PESSOA_HMAC a linha iria sem assinatura e o App a descartaria: o Nexus diria uma coisa e o App faria
    outra."""
    cfg.pop("NEXUS_PESSOA_HMAC")
    with pytest.raises(AA.Recusada, match="NEXUS_PESSOA_HMAC"):
        _por(cfg)
    assert AA.ler(cfg, forcar=True)["decisoes"] == []


def test_leitura_que_falha_nao_grava(cfg, relogio, monkeypatch, tmp_path):
    _por(cfg, 10)
    antes = (tmp_path / "atribuicoes.json").read_text(encoding="utf-8")
    original = A._ler_cru

    def cai(c, aba=A.ABA):
        if aba == A.ABA_ADMIN:
            raise ConnectionError("banco fora")
        return original(c, aba)
    monkeypatch.setattr(A, "_ler_cru", cai)
    with pytest.raises(AA.Recusada, match="nada foi gravado"):
        _por(cfg, 11)
    assert (tmp_path / "atribuicoes.json").read_text(encoding="utf-8") == antes
    assert AA.ler(cfg, forcar=True)["erro"].startswith("ConnectionError")


def test_nada_em_claro_e_a_observacao_cifrada(cfg, relogio, tmp_path):
    _por(cfg, 10, obs="cobre as férias do supervisor")
    _tirar(cfg, 10)
    txt = (tmp_path / "atribuicoes.json").read_text(encoding="utf-8")
    assert "férias" not in txt and "ferias" not in txt and "Pessoa Teste" not in txt and "@" not in txt
    h = AA.historico(cfg, AA.ler(cfg, forcar=True))
    assert [x["acao"] for x in h] == ["tirou", "pôs"]
    assert h[1]["obs"] == "cobre as férias do supervisor" and h[0]["obs"] == ""
    assert h[1]["pessoa_id"] == 10 and h[1]["pessoa_hmac"] == cod(10) and h[1]["quem_hmac"]
    cfg.pop("NEXUS_CHAVE_CADASTRO")
    with pytest.raises(AA.Recusada, match="NEXUS_CHAVE_CADASTRO"):
        _por(cfg, 11, obs="sem a chave a observação não vai")
    assert AA.historico(cfg, AA.ler(cfg, forcar=True))[1]["obs"] == ""         # sem a chave, sem a observação


# ── o livro: as duas abas juntas ────────────────────────────────────────────────────────────────────────────────
def _tecnico(cfg, pid):
    return A.decidir(cfg, usina_id=1, usina_fracttal="Cliente A - Usina 1 - SP", pessoa_id=pid,
                     pessoa_hmac=cod(pid), na_usina=True, usuario=PESSOA)


def test_as_duas_abas_vao_juntas_no_arquivo(cfg, relogio):
    """Gravar troca o livro inteiro: a decisão dos técnicos leva a aba dos administradores, e a dos administradores leva
    a dos técnicos (sem isso, uma apagaria a outra)."""
    _tecnico(cfg, 10)
    _por(cfg, 20)
    _tecnico(cfg, 11)
    _por(cfg, 21)
    d = _arquivo(cfg)
    assert [x["pessoa_id"] for x in d[A.ABA]] == [10, 11] and [x["pessoa_id"] for x in d[A.ABA_ADMIN]] == [20, 21]
    assert set(A.atuais(A.ler(cfg, forcar=True), 20261105)) == {(1, 10, "executa"), (1, 11, "executa")}


class _Gravacoes(ApiPGFalsa):
    """O banco de mentira que guarda as abas de cada gravação e pode falhar a leitura de uma aba."""

    def __init__(self):
        super().__init__()
        self.enviadas, self.falhar = [], None

    def get(self, url, params=None, headers=None, timeout=None):
        if self.falhar and url.endswith(f"/api/sheets/{self.abas[(A.LIVRO, self.falhar)]['id']}/rows"):
            raise ConnectionError("a leitura da aba caiu")
        return super().get(url, params=params, headers=headers, timeout=timeout)

    def post(self, url, headers=None, json=None, params=None, files=None, timeout=None):
        if files:
            from openpyxl import load_workbook
            self.enviadas.append(load_workbook(io.BytesIO(files["file"][1])).sheetnames)
        return super().post(url, headers=headers, json=json, params=params, files=files, timeout=timeout)


@pytest.fixture
def no_banco(app):
    """O livro no banco de mentira (sem o arquivo da cópia de prova e fora do modo de teste, que não lê o banco)."""
    A.limpar()
    AA.limpar()
    api = _Gravacoes()
    app.extensions["nexus_dados_sessao"] = api
    cfg = {"GRIDCO_DB_API": "http://pg.falso", "GRIDCO_SQL_TOKEN": "tk", "NEXUS_PESSOA_HMAC": CHAVE,
           "NEXUS_CHAVE_CADASTRO": gerar_chave()}
    with app.app_context():
        yield api, cfg
    app.extensions.pop("nexus_dados_sessao", None)


def test_as_duas_abas_vao_juntas_no_banco(no_banco, relogio):
    api, cfg = no_banco
    _tecnico(cfg, 10)
    _por(cfg, 20)
    _tecnico(cfg, 11)
    _por(cfg, 21)
    assert api.enviadas == [[A.ABA, A.ABA_ADMIN]] * 4
    assert [x["pessoa_id"] for x in api.linhas(A.LIVRO, A.ABA)] == [10, 11]
    assert [x["pessoa_id"] for x in api.linhas(A.LIVRO, A.ABA_ADMIN)] == [20, 21]
    # a outra aba que não se relê na hora de gravar: nada vai ao banco
    api.falhar = A.ABA
    with pytest.raises(AA.Recusada, match="nada foi gravado"):
        _por(cfg, 22)
    api.falhar = A.ABA_ADMIN
    with pytest.raises(A.Recusada, match="nada foi gravado"):
        _tecnico(cfg, 12)
    assert api.syncs == 4 and len(api.linhas(A.LIVRO, A.ABA_ADMIN)) == 2 and len(api.linhas(A.LIVRO, A.ABA)) == 2


def test_a_trava_do_catalogo_nao_deixa_gravar_o_livro_sem_a_aba_dos_administradores(no_banco, relogio):
    """O livro só cresce e declara as duas abas: quem gravar só os técnicos (um código que esqueça a aba nova) é
    recusado, e os administradores ficam."""
    api, cfg = no_banco
    _por(cfg, 20)
    with pytest.raises(livros.GravacaoRecusada, match=A.ABA_ADMIN):
        livros.publicar(A.LIVRO, A.NOME_LIVRO, {A.ABA: (list(A.CAB), [])}, base="http://pg.falso", token="tk",
                        sessao=api)
    assert len(api.linhas(A.LIVRO, A.ABA_ADMIN)) == 1


# ── a governança ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_aba_esta_no_catalogo_e_o_radar_nao_a_acusa():
    f = catalogo.POR_ID["decisao_admin_app"]
    assert f.livro == f"{A.LIVRO} · {A.ABA_ADMIN}" == "nexus_pcm_atribuicoes · fato_admin_app" and f.fontes == (f.livro,)
    assert f.grao.startswith("1 linha = 1 decisão de pôr ou tirar 1 pessoa como administrador do App de Campo")
    assert f.tipo == "sem_medida" and f.medidas == () and f.chave[0] == A.CAB_ADMIN[0]
    assert set(f.chave) <= set(A.CAB_ADMIN)
    assert {d for d, (e, _c) in f.dims.items() if e != "nao"} == {"data", "pessoa"}
    assert f.dims["data"][0] == f.dims["pessoa"][0] == "id"
    lv = catalogo.LIVRO_POR_NOME[A.LIVRO]
    assert lv.abas == (A.ABA, A.ABA_ADMIN) and lv.so_cresce == lv.abas and "admins_app.py" in lv.quem_grava
    caixas = radar.classificar({(A.LIVRO, A.ABA_ADMIN): {"id": 1, "row_count": 2},
                                (A.LIVRO, A.ABA): {"id": 2, "row_count": 9}})
    assert caixas["nova"] == [] and {t["aba"] for t in caixas["fato"]} == {A.ABA, A.ABA_ADMIN}
    assert explica.RESUMO["decisao_admin_app"] and explica.PARA_QUE["decisao_admin_app"]
    # nada pessoal em claro nas colunas (regra 8): pessoa só como pessoa_id e código; a observação só cifrada
    assert not [c for c in A.CAB_ADMIN if any(c == p or c.startswith(p + "_") for p in PROIBIDAS)]
