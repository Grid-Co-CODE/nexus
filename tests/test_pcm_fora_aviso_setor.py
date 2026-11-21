"""O aviso do Fora da programação ao setor citado (16/11/2026, nexus/pcm/fora_avisos.py).

Levi, 16/11/2026: "fora da programação deve notificar quem é daquele setor caso o setor seja citado! a notificação fica
ao lado da notificação do OS Creator". O setor citado é o do MOTIVO (a coluna "Avisa o setor" do Cadastro de motivos,
`dim_motivo.setor_id`, pelo ID do setor de Base → Acessos, nunca pelo nome: Levi, 04/11/2026, "não podemos ficar
dependente de texto"). Engenharia e Performance, motivos do pedido de 16/10 que são setores, já vêm ligados pelo ID do
motivo; Chamados (garantia) não, porque em 16/11/2026 não havia setor Chamados ativo. O que estes
testes seguram: o setor de cada motivo (o padrão, o livro sem a coluna, a troca e o "Nenhum" no cadastro), o aviso só
para o setor citado e só da tarefa que segue fora, o lido que sai e volta quando o motivo volta, o botão do topo ao lado
do OS Creator (e nada para o setor que nenhum motivo cita) e o "Marcar todas como lidas" só destes avisos."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from nexus import casca
from nexus.auth import setor_telas
from nexus.cadastro import setor_ids as SID
from nexus.cadastro.cifra import gerar_chave
from nexus.comando import avisos as AV
from nexus.pcm import fora_avisos as FA
from nexus.pcm import motivos as M

PESSOA = {"email": "pessoa.teste@exemplo.com", "nome": "Pessoa Teste"}
T1 = {"os": "15596", "codigo": "ELF1-INV02", "tarefa": "[Grid Co.] - MPA - Inversor", "usina": "Cliente A - Usina 1 - SP",
      "cliente": "Cliente A", "tipo": "MPA"}
T2 = dict(T1, os="15597", tarefa="[Grid Co.] - MPA - Trafo")
T3 = dict(T1, os="15598", tarefa="[Grid Co.] - MPA - String box")


@pytest.fixture
def cfg(tmp_path):
    M.limpar()
    FA.limpar()
    AV.limpar()
    return {"TESTING": True, "NEXUS_PCM_MOTIVOS_ARQUIVO": str(tmp_path / "motivos.json"),
            "NEXUS_CHAVE_CADASTRO": gerar_chave(), "NEXUS_PESSOA_HMAC": "chave-hmac-de-teste"}


def _mid(cfg, nome) -> int:
    return next(m["id"] for m in M.ativos(M.ler(cfg, forcar=True)) if m["nome"] == nome)


def _setores(cfg) -> dict:
    return {m["nome"]: m["setor_id"] for m in M.ativos(M.ler(cfg, forcar=True))}


class Relogio:
    def __init__(self, monkeypatch):
        self.t = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
        monkeypatch.setattr(M, "_agora", self)

    def __call__(self):
        self.t += timedelta(minutes=1)
        return self.t


# ── o setor de cada motivo ──────────────────────────────────────────────────────────────────────────────────────────
def test_engenharia_e_performance_ja_vem_ligados_pelo_id(cfg):
    s = _setores(cfg)
    assert s["Engenharia"] == SID.ENGENHARIA and s["Performance"] == SID.PERFORMANCE
    assert {n for n, v in s.items() if v} == {"Engenharia", "Performance"}
    # a 1ª gravação leva o setor junto, e ele volta igual do livro
    M.marcar(cfg, T1, _mid(cfg, "Engenharia"), "", PESSOA)
    assert _setores(cfg) == s
    linha = json.loads(open(cfg["NEXUS_PCM_MOTIVOS_ARQUIVO"], encoding="utf-8").read())[M.ABA_MOTIVO][0]
    assert str(linha["setor_id"]) == str(SID.ENGENHARIA)


def test_o_livro_de_antes_sem_a_coluna_vale_o_padrao_pelo_id(cfg):
    """O livro do servidor foi gravado antes de 16/11/2026, sem `setor_id`: os motivos 1 e 3 valem pelo ID."""
    linhas = [{"motivo_id": i, "nome": n, "descricao": "", "tira_da_programacao": "não", "excluido": ""}
              for i, n in ((1, "Engenharia"), (2, "Chamados (garantia)"), (3, "Performance"), (9, "Prioridade"))]
    open(cfg["NEXUS_PCM_MOTIVOS_ARQUIVO"], "w", encoding="utf-8").write(json.dumps({M.ABA_MOTIVO: linhas}))
    assert _setores(cfg) == {"Engenharia": SID.ENGENHARIA, "Chamados (garantia)": None,
                             "Performance": SID.PERFORMANCE, "Prioridade": None}


def test_o_cadastro_troca_o_setor_e_o_nenhum_fica(cfg):
    eng = _mid(cfg, "Engenharia")
    M.cadastro(cfg, "editar", PESSOA, motivo_id=eng, nome="Engenharia", descricao="", tira=False, setor=SID.SEGURANCA)
    assert _setores(cfg)["Engenharia"] == SID.SEGURANCA
    # "Nenhum" grava e não volta ao padrão do ID
    r = M.cadastro(cfg, "editar", PESSOA, motivo_id=eng, nome="Engenharia", descricao="", tira=False, setor="")
    assert r["mudou"] and _setores(cfg)["Engenharia"] is None
    # quem edita sem o campo não mexe no setor
    M.cadastro(cfg, "editar", PESSOA, motivo_id=_mid(cfg, "Performance"), nome="Performance", descricao="x", tira=False)
    assert _setores(cfg)["Performance"] == SID.PERFORMANCE
    # o mesmo setor de antes não é mudança
    r = M.cadastro(cfg, "editar", PESSOA, motivo_id=_mid(cfg, "Performance"), nome="Performance", descricao="x",
                   tira=False, setor=str(SID.PERFORMANCE))
    assert not r["mudou"]
    # o motivo novo nasce com o setor escolhido (ou sem nenhum)
    M.cadastro(cfg, "criar", PESSOA, nome="Segurança do trabalho", descricao="", tira=False, setor=str(SID.SEGURANCA))
    M.cadastro(cfg, "criar", PESSOA, nome="Outro motivo", descricao="", tira=False)
    s = _setores(cfg)
    assert s["Segurança do trabalho"] == SID.SEGURANCA and s["Outro motivo"] is None


def test_setor_que_nao_e_id_e_recusado(cfg):
    with pytest.raises(M.Recusada):
        M.cadastro(cfg, "editar", PESSOA, motivo_id=_mid(cfg, "Engenharia"), nome="Engenharia", descricao="",
                   tira=False, setor="Engenharia")


# ── o aviso ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_aviso_vai_so_ao_setor_citado_e_so_da_tarefa_que_segue_fora(cfg, monkeypatch):
    Relogio(monkeypatch)
    M.marcar(cfg, T1, _mid(cfg, "Engenharia"), "Aguardando o parecer", PESSOA)
    M.marcar(cfg, T2, _mid(cfg, "Aguardando material"), "", PESSOA)
    M.marcar(cfg, T3, _mid(cfg, "Performance"), "", PESSOA)
    est = M.ler(cfg)
    eng = FA.do_setor(cfg, est, SID.ENGENHARIA)
    assert [a["os"] for a in eng] == ["15596"]
    a = eng[0]
    assert a["motivo"] == "Engenharia" and a["tarefa"] == T1["tarefa"] and a["obs"] == "Aguardando o parecer"
    iid = M.item_id("15596", "ELF1-INV02", T1["tarefa"])
    desde = M.vigentes(cfg, est)[iid]["desde"]          # o começo da sequência com o motivo, em UTC
    assert a["id"] == "F:" + iid + ":" + desde[:16].replace("-", "").replace("T", "").replace(":", "")
    assert [x["os"] for x in FA.do_setor(cfg, est, SID.PERFORMANCE)] == ["15598"]
    assert FA.do_setor(cfg, est, SID.COS) == []
    # a tarefa que voltou à programação (o motivo tirado) sai do aviso
    M.marcar(cfg, T1, None, "", PESSOA)
    assert FA.do_setor(cfg, M.ler(cfg), SID.ENGENHARIA) == []


def test_o_mais_novo_primeiro(cfg, monkeypatch):
    Relogio(monkeypatch)
    M.marcar(cfg, T1, _mid(cfg, "Engenharia"), "", PESSOA)
    M.marcar(cfg, T2, _mid(cfg, "Engenharia"), "", PESSOA)
    assert [a["os"] for a in FA.do_setor(cfg, M.ler(cfg), SID.ENGENHARIA)] == ["15597", "15596"]


def test_o_aviso_e_um_aviso_do_sino_e_o_lido_sai_ate_o_motivo_voltar(cfg, monkeypatch):
    Relogio(monkeypatch)
    M.marcar(cfg, T1, _mid(cfg, "Engenharia"), "", PESSOA)
    aid = FA.do_setor(cfg, M.ler(cfg), SID.ENGENHARIA)[0]["id"]
    assert AV.AVISO_RE.fullmatch(aid) and AV.TIPO_DO_PREFIXO[aid[:1]] == "fora"
    M.ler(cfg)
    assert FA.para_o_sino(cfg, SID.ENGENHARIA, {aid}) == []
    # trocar só a observação não é aviso novo
    M.marcar(cfg, T1, _mid(cfg, "Engenharia"), "outra observação", PESSOA)
    M.ler(cfg)
    assert FA.para_o_sino(cfg, SID.ENGENHARIA, {aid}) == []
    # o motivo que sai e volta é aviso novo
    M.marcar(cfg, T1, _mid(cfg, "Prioridade"), "", PESSOA)
    M.marcar(cfg, T1, _mid(cfg, "Engenharia"), "", PESSOA)
    M.ler(cfg)
    novos = FA.para_o_sino(cfg, SID.ENGENHARIA, {aid})
    assert len(novos) == 1 and novos[0]["id"] != aid


def test_sem_a_copia_do_livro_o_sino_nao_espera_o_banco(cfg):
    """O sino está em toda página: sem a cópia (logo depois de subir), não sai nada e a leitura começa por trás."""
    assert FA.para_o_sino(cfg, SID.ENGENHARIA, set()) is None


# ── o botão do topo ─────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def no_app(app, cfg):
    app.config.update(cfg)
    return app


SINO_VAZIO = {"n": 0, "criticos": 0, "mencoes": [], "n_mencoes": 0, "pedidos": [], "n_pedidos": 0, "avisos": [],
              "n_avisos": 0, "icone_os": "clipboard-text", "perf": [], "n_perf": 0}


def _entrar(c, setor, monkeypatch, tudo=False):
    with c.session_transaction() as s:
        s.update(logado=True, admin=False, usuario=dict(PESSOA), casca_codigo="x")
    monkeypatch.setattr(setor_telas, "acesso", lambda: {"tudo": tudo, "telas": set(), "setor": setor, "erro": ""})
    # o botão do OS Creator sem nada (no teste não há as cópias do motor nem das conversas): só para ver a ordem
    monkeypatch.setattr(casca, "_sino", lambda: dict(SINO_VAZIO))


def test_o_botao_do_topo_fica_ao_lado_do_os_creator_so_para_o_setor_citado(no_app, cfg, monkeypatch):
    Relogio(monkeypatch)
    M.marcar(cfg, T1, _mid(cfg, "Engenharia"), "Aguardando o parecer", PESSOA)
    M.ler(cfg)
    c = no_app.test_client()
    _entrar(c, {"id": SID.ENGENHARIA, "nome": "Engenharia"}, monkeypatch)
    html = c.get("/").get_data(as_text=True)
    # no sino das notificações do setor, junto das demandas e das contestações (21/11/2026, Levi: "Una o 1 e o 3")
    assert 'class="sino-topo sino-dem"' in html and 'class="ph ph-bell"' in html
    assert 'aria-label="Notificações: 1"' in html
    assert "1 tarefa fora da programação cita o setor Engenharia" in html
    assert "OS 15596" in html and "Aguardando o parecer" in html
    assert "/os/_nexus/card/folio/15596" in html
    # o sino vem antes do botão do OS Creator, e os dois antes do Menu
    assert html.index('class="sino-topo sino-dem"') < html.index('class="sino-topo"') < html.index("abre-menu")
    # quem não tem a tela do Fora da programação não ganha o link que o barraria
    assert "/t/pcm/fora-da-programacao" not in html.split('class="sino-topo sino-dem"')[1].split("</details>")[0]
    # o setor que nenhum motivo cita não ganha a parte do Fora
    _entrar(c, {"id": SID.COS, "nome": "COS"}, monkeypatch)
    assert "fora da programação cita" not in c.get("/").get_data(as_text=True)


def test_o_botao_vazio_do_setor_citado_e_o_link_para_quem_tem_a_tela(no_app, cfg, monkeypatch):
    M.ler(cfg)
    c = no_app.test_client()
    _entrar(c, {"id": SID.PERFORMANCE, "nome": "Performance"}, monkeypatch, tudo=True)
    html = c.get("/").get_data(as_text=True)
    caixa = html.split('class="sino-topo sino-dem"')[1].split("</details>")[0]
    assert "Nenhuma tarefa fora da programação cita o setor Performance." in caixa
    assert "/t/pcm/fora-da-programacao" in caixa


def test_marcar_todas_como_lidas_leva_so_os_do_fora(no_app, cfg, monkeypatch):
    Relogio(monkeypatch)
    M.marcar(cfg, T1, _mid(cfg, "Engenharia"), "", PESSOA)
    M.marcar(cfg, T2, _mid(cfg, "Engenharia"), "", PESSOA)
    M.ler(cfg)
    ids = {a["id"] for a in FA.do_setor(cfg, M.ler(cfg), SID.ENGENHARIA)}
    pegos = []
    monkeypatch.setattr(AV, "marcar_lidos", lambda u, aids: pegos.append(list(aids)) or len(aids))
    monkeypatch.setattr(AV, "para_o_sino", lambda u: [{"id": "A:1"}])
    c = no_app.test_client()
    _entrar(c, {"id": SID.ENGENHARIA, "nome": "Engenharia"}, monkeypatch, tudo=True)
    r = c.post("/t/comando/aviso/lida", data={"todos": "fora"}, headers={"Accept": "application/json"})
    assert r.get_json() == {"ok": True, "lidos": 2}
    assert set(pegos[0]) == ids


# ── a coluna "Avisa o setor" do Cadastro de motivos ─────────────────────────────────────────────────────────────────
def test_o_cadastro_mostra_e_grava_o_setor_pela_tela(no_app, cfg, monkeypatch):
    from nexus.pcm import telas as PT
    monkeypatch.setattr(PT, "_setores_do_cadastro", lambda: [{"id": SID.ENGENHARIA, "nome": "Engenharia"},
                                                             {"id": SID.SEGURANCA, "nome": "Segurança"}])
    c = no_app.test_client()
    _entrar(c, {"id": SID.PCM, "nome": "PCM"}, monkeypatch, tudo=True)
    html = c.get("/t/pcm/fora-da-programacao?ver=cadastro").get_data(as_text=True)
    assert "<th>Avisa o setor</th>" in html
    linha = html.split('data-motivo="1"')[1].split("</tr>")[0]
    assert f'<option value="{SID.ENGENHARIA}" selected>Engenharia</option>' in linha
    # Performance (o padrão do motivo 3) não está na lista de agora e continua aparecendo, escolhida
    linha3 = html.split('data-motivo="3"')[1].split("</tr>")[0]
    assert f'<option value="{SID.PERFORMANCE}" selected>' in linha3
    r = c.post("/t/pcm/fora-da-programacao/cadastro", data={"acao": "editar", "motivo_id": "1", "nome": "Engenharia",
                                                            "descricao": M.CADASTRO_INICIAL[0][1],
                                                            "setor_id": str(SID.SEGURANCA)})
    assert r.status_code == 303
    assert _setores(cfg)["Engenharia"] == SID.SEGURANCA
