"""Os motivos das tarefas do PCM e a lista do backoffice (16/10/2026, nexus/pcm/motivos.py).

Levi, 16/10/2026, com os 11 motivos e "Quando a OS estiver atrelada como responsável para alguém do time de backoffice,
desconsiderar para a programação da semana". O que estes testes seguram: o cadastro inicial (os 11, os 6 que tiram), um
motivo por tarefa (marcar outro troca), o "desde" que só reinicia quando o motivo muda, a marca da OS (sem código) e a
do ativo (a do ativo vence), o motivo tirado do cadastro que deixa de valer e o ID que não volta, a lista do backoffice
(vale a última decisão de cada nome, sem acento), nada em claro no livro (a API do banco tem leitura aberta), o arquivo
do motor e do robô (sem observação nem quem marcou; o hash não muda com a hora), a rodada que escreve o arquivo (e usa a
cópia quando o banco cai), o GitHub (só grava o que mudou) e as telas: quem marca (PCM, Responsáveis UFV,
administrador), quem mexe no cadastro (administrador e PCM), a janela do Quadro (a tarefa vem da semana), o painel (só
os que tiram, sem a finalizada, o filtro Motivo, marcar pela OS) e a lista no Gerar a semana. Nada vai ao banco nem ao
GitHub: o livro é um arquivo (`NEXUS_PCM_MOTIVOS_ARQUIVO`) e o GitHub é o falso dos testes da publicação."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from nexus.cadastro.cifra import gerar_chave
from nexus.campo.ligacao_cadastro import codigo_da_pessoa
from nexus.pcm import geracao as G
from nexus.pcm import motivos as M
from nexus.pcm import quadro as Q
from test_pcm_geracao import config, origem  # noqa: F401 (fixtures)
from test_pcm_publicar import GitHubFalso, _no_setor, _pessoa
from test_pcm_quadro import _semana_teste

PESSOA = {"email": "pessoa.teste@exemplo.com", "nome": "Pessoa Teste"}
T1 = {"os": "15596", "codigo": "ELF1-INV02", "tarefa": "[Grid Co.] - MPA - Inversor", "usina": "Cliente A - Usina 1 - SP",
      "cliente": "Cliente A", "tipo": "MPA"}
TIRAM = {"Aguardando cliente", "Aguardando concessionária", "Aguardando material", "Aguardando fabricante/terceiro",
         "Condições climáticas adversas", "Pendente recurso", "Vegetação alta impossibilitando ação"}


@pytest.fixture
def cfg(tmp_path):
    M.limpar()
    M.esquecer_estado_no_repositorio()
    return {"TESTING": True, "NEXUS_PCM_MOTIVOS_ARQUIVO": str(tmp_path / "motivos.json"),
            "NEXUS_CHAVE_CADASTRO": gerar_chave(), "NEXUS_PESSOA_HMAC": "chave-hmac-de-teste"}


def _mid(cfg, nome) -> int:
    return next(m["id"] for m in M.ativos(M.ler(cfg, forcar=True)) if m["nome"] == nome)


def _vig(cfg) -> dict:
    return {k: v for k, v in M.vigentes(cfg, M.ler(cfg, forcar=True)).items() if not k.startswith("_")}


class Relogio:
    """O `_agora` do módulo andando um minuto por chamada: cada decisão com a sua hora."""

    def __init__(self, monkeypatch):
        self.t = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
        monkeypatch.setattr(M, "_agora", self)

    def __call__(self):
        self.t += timedelta(minutes=1)
        return self.t


# ── o cadastro e a marca ──────────────────────────────────────────────────────────────────────────────────────
def test_cadastro_inicial_sao_os_12_do_pedido(cfg):
    est = M.ler(cfg)
    assert est["inicial"] and not est["erro"]
    assert [m["nome"] for m in est["motivos"]] == [n for n, _d, _t in M.CADASTRO_INICIAL]
    assert [m["id"] for m in est["motivos"]] == list(range(1, 13))
    assert {m["nome"] for m in est["motivos"] if m["tira"]} == TIRAM
    # a 1ª gravação leva o cadastro inicial junto: depois dela, o cadastro vem do livro
    M.marcar(cfg, T1, _mid(cfg, "Engenharia"), "", PESSOA)
    est = M.ler(cfg, forcar=True)
    assert not est["inicial"] and [m["nome"] for m in est["motivos"]] == [n for n, _d, _t in M.CADASTRO_INICIAL]


def test_um_motivo_por_tarefa_e_o_desde(cfg, monkeypatch):
    """Levi: "Um só por tarefa". Marcar o mesmo motivo com a mesma observação não grava; trocar só a observação não
    reinicia o "desde"; trocar o motivo, sim; tirar e tirar de novo não grava."""
    rel = Relogio(monkeypatch)
    am, si = _mid(cfg, "Aguardando material"), _mid(cfg, "Sinistro")
    r = M.marcar(cfg, T1, am, "falta o IGBT", PESSOA)
    assert r["gravou"] and r["marca"]["motivo"] == "Aguardando material" and r["marca"]["tira"]
    t0 = r["marca"]["desde"]
    assert not M.marcar(cfg, T1, am, "falta o IGBT", PESSOA)["gravou"]
    r = M.marcar(cfg, T1, am, "falta o IGBT; chega dia 20", PESSOA)
    assert r["gravou"] and r["marca"]["desde"] == t0 and r["marca"]["obs"] == "falta o IGBT; chega dia 20"
    r = M.marcar(cfg, T1, si, "", PESSOA)
    assert r["gravou"] and r["marca"]["motivo"] == "Sinistro" and r["marca"]["desde"] > t0
    assert len(_vig(cfg)) == 1                                   # trocou: a tarefa tem um motivo só
    assert M.marcar(cfg, T1, None, "", PESSOA)["gravou"] and _vig(cfg) == {}
    assert not M.marcar(cfg, T1, None, "", PESSOA)["gravou"]
    assert rel.t > datetime(2026, 10, 16, 12, 3, tzinfo=timezone.utc)
    livro = json.loads(open(cfg["NEXUS_PCM_MOTIVOS_ARQUIVO"], encoding="utf-8").read())
    assert len(livro[M.ABA_MARCA]) == 4 and livro[M.ABA_MARCA][-1]["motivo_id"] is None
    assert {x["decidida_por_hmac"] for x in livro[M.ABA_MARCA]} == {codigo_da_pessoa("chave-hmac-de-teste", PESSOA["email"])}


def test_cada_justificativa_conta_uma_vez_por_dia(cfg, monkeypatch):
    """Levi, 16/10/2026: "Priorizei outras atividades" não tira a tarefa da programação e ela segue cobrada nos outros
    dias; o histórico conta "cada justificativa, 1 por dia", "por tarefa". A mesma justificativa no mesmo dia não grava;
    no dia seguinte, grava e conta; só editar o texto no mesmo dia não conta; outro motivo no mesmo dia conta; tirar não."""
    rel = Relogio(monkeypatch)
    pr, am = _mid(cfg, "Prioridade"), _mid(cfg, "Aguardando material")
    assert not next(m for m in M.ativos(M.ler(cfg)) if m["id"] == pr)["tira"]
    TEC_A = {"email": "tecnico.a@exemplo.com", "nome": "Técnico A"}
    t0 = M.marcar(cfg, T1, pr, "fui para a parada da usina 2", TEC_A, origem="app")["marca"]["desde"]
    assert not M.marcar(cfg, T1, pr, "fui para a parada da usina 2", TEC_A, origem="app")["gravou"]
    assert M.marcar(cfg, T1, pr, "fui para a parada da usina 2; volto amanhã", PESSOA, origem="painel")["gravou"]
    rel.t += timedelta(days=1)
    r = M.marcar(cfg, T1, pr, "fui para a parada da usina 2; volto amanhã", TEC_A, origem="app")
    assert r["gravou"] and r["marca"]["desde"] == t0                 # o motivo segue o mesmo: o "desde" não reinicia
    assert M.marcar(cfg, T1, am, "falta o IGBT", PESSOA)["gravou"]    # outro motivo no mesmo dia: conta
    assert M.marcar(cfg, T1, None, "", PESSOA)["gravou"]              # tirar: não conta
    h = M.historico(cfg, M.ler(cfg, forcar=True), {M.item_id(T1["os"], T1["codigo"], T1["tarefa"])})
    assert [(x["dia"], x["motivo"]) for x in h] == [("2026-10-16", "Prioridade"), ("2026-10-17", "Prioridade"),
                                                    ("2026-10-17", "Aguardando material")]
    assert h[0]["quem"] == "Técnico A" and h[0]["origem"] == "app"   # quem justificou, não o PCM que editou o texto
    assert h[0]["obs"] == "fui para a parada da usina 2; volto amanhã"  # o texto mais novo do dia


def test_o_painel_mostra_quantas_vezes_e_o_historico(app, logado, tela, monkeypatch):
    """A coluna Vezes no painel (16/10/2026): o técnico justifica a mesma tarefa em dois dias e conta 2; o número abre
    a lista com a data, o motivo, quem e o texto."""
    cfg = app.config
    rel = Relogio(monkeypatch)
    pr = next(m["id"] for m in M.ativos(M.ler(cfg)) if m["nome"] == "Prioridade")
    cab = {"os": "5", "codigo": "UFV1-CAB01", "tarefa": "[Grid Co.] - MPM - Cabine", "motivo": pr,
           "obs": "priorizei a corretiva do inversor 3", "tecnico_hmac": TEC, "tecnico_nome": "Técnico Teste"}
    assert _pelo_app(app, cab).get_json()["gravou"]
    rel.t += timedelta(days=1)
    assert _pelo_app(app, cab).get_json()["gravou"]                   # no dia seguinte, a mesma justificativa grava
    assert not _pelo_app(app, cab).get_json()["gravou"]               # no mesmo dia, não
    html = " ".join(logado.get("/t/pcm/fora-da-programacao").get_data(as_text=True).split())
    assert 'aria-controls="fp-h-1"' in html and ">2</button>" in html
    lista = html.split('id="fp-h-1"', 1)[1].split("</ol>", 1)[0]
    assert lista.count("<li>") == 2 and "16/10/2026" in lista and "17/10/2026" in lista
    assert lista.count("priorizei a corretiva do inversor 3") == 2 and lista.count("Técnico Teste") == 2


def test_marca_da_os_e_marca_do_ativo(cfg):
    """A marca pelo número da OS (o painel, pela Gestão PCM, sem código) vale para a tarefa em todos os ativos; a do
    ativo (o Quadro) vence a da OS naquele ativo; tirar a do ativo volta a valer a da OS."""
    ac, am = _mid(cfg, "Aguardando cliente"), _mid(cfg, "Aguardando material")
    M.marcar(cfg, dict(T1, codigo=""), ac, "", PESSOA, origem="painel")
    idx = M.indice(_vig(cfg))
    assert M.motivo_de(idx, "15596", "ELF1-INV02", T1["tarefa"])["motivo"] == "Aguardando cliente"
    assert M.motivo_de(idx, "15596", "ELF1-INV03", T1["tarefa"])["motivo"] == "Aguardando cliente"
    assert M.motivo_de(idx, "15596", "ELF1-INV02", "[Grid Co.] - MPA - Trafo") is None
    M.marcar(cfg, T1, am, "", PESSOA)
    idx = M.indice(_vig(cfg))
    assert M.motivo_de(idx, "15596", "ELF1-INV02", T1["tarefa"])["motivo"] == "Aguardando material"
    assert M.motivo_de(idx, "15596", "ELF1-INV03", T1["tarefa"])["motivo"] == "Aguardando cliente"
    # a OS, o código e o nome casam sem caixa, acento nem espaço a mais (como o robô compara)
    assert M.motivo_de(idx, 15596.0, " elf1-inv02", "[grid co.]  -  mpa - inversor ")["motivo"] == "Aguardando material"
    M.marcar(cfg, T1, None, "", PESSOA)
    assert M.motivo_de(M.indice(_vig(cfg)), "15596", "ELF1-INV02", T1["tarefa"])["motivo"] == "Aguardando cliente"
    with pytest.raises(M.Recusada):
        M.marcar(cfg, dict(T1, os="abc"), ac, "", PESSOA)
    with pytest.raises(M.Recusada):
        M.marcar(cfg, T1, ac, "x" * (M.OBS_MAX + 1), PESSOA)
    with pytest.raises(M.Recusada):
        M.marcar(cfg, T1, 99, "", PESSOA)


def test_cadastro_tirar_nao_reusa_o_id_e_a_marca_deixa_de_valer(cfg):
    pr = _mid(cfg, "Pendente recurso")
    M.marcar(cfg, T1, pr, "", PESSOA)
    assert len(_vig(cfg)) == 1
    M.cadastro(cfg, "excluir", PESSOA, motivo_id=pr)
    assert _vig(cfg) == {} and "Pendente recurso" not in {m["nome"] for m in M.ativos(M.ler(cfg, forcar=True))}
    novo = M.cadastro(cfg, "criar", PESSOA, nome="aguardando LAUDO da COS", descricao="Laudo da engenharia", tira=True)
    assert novo["nome"] == "Aguardando laudo da COS"           # a regra do Levi: 1ª maiúscula, sigla fica (16/10/2026)
    assert novo["motivo_id"] == 13                                # o 11 não volta
    for nome in ("AGUARDANDO LAUDO DA COS", "a", "x@y.com", "x" * (M.NOME_MAX + 1)):
        with pytest.raises(M.Recusada):
            M.cadastro(cfg, "criar", PESSOA, nome=nome)
    pri = _mid(cfg, "Prioridade")
    r = M.cadastro(cfg, "editar", PESSOA, motivo_id=pri, nome="Prioridade", descricao="Prioridades a pedido do cliente.",
                   tira=False)
    assert r["mudou"] is False                                    # nada mudou: não grava
    M.cadastro(cfg, "editar", PESSOA, motivo_id=pri, nome="Prioridade do cliente", descricao="", tira=True)
    m = next(m for m in M.ativos(M.ler(cfg, forcar=True)) if m["id"] == pri)
    assert m["nome"] == "Prioridade do cliente" and m["tira"]
    with pytest.raises(M.Recusada):
        M.cadastro(cfg, "editar", PESSOA, motivo_id=pr, nome="Volta", tira=False)   # excluído não se edita


def test_backoffice_vale_a_ultima_decisao_de_cada_nome(cfg):
    assert M.backoffice_definir(cfg, "Rógerio Fictício", True, PESSOA)["gravou"]
    assert not M.backoffice_definir(cfg, "rogerio  ficticio", True, PESSOA)["gravou"]     # o mesmo nome, sem acento
    M.backoffice_definir(cfg, "Ciclano Exemplo", True, PESSOA)
    assert [b["nome"] for b in M.backoffice(cfg, M.ler(cfg, forcar=True))] == ["Ciclano Exemplo", "Rógerio Fictício"]
    assert M.backoffice_definir(cfg, "CICLANO EXEMPLO", False, PESSOA)["gravou"]
    assert not M.backoffice_definir(cfg, "Ciclano Exemplo", False, PESSOA)["gravou"]
    assert [b["nome"] for b in M.backoffice(cfg, M.ler(cfg, forcar=True))] == ["Rógerio Fictício"]
    for nome in ("ab", "fulano@exemplo.com"):
        with pytest.raises(M.Recusada):
            M.backoffice_definir(cfg, nome, True, PESSOA)
    with pytest.raises(M.Recusada):
        M.backoffice_definir(dict(cfg, NEXUS_PESSOA_HMAC=""), "Joana Teste", True, PESSOA)


def test_nada_em_claro_no_livro(cfg):
    """A API do banco tem leitura aberta (regra 8): a tarefa, a usina, a observação, o nome do backoffice e quem marcou
    vão só cifrados. Em claro: a OS, o código do ativo, o equipamento_id e o tarefa_chave."""
    M.marcar(cfg, T1, _mid(cfg, "Aguardando material"), "falta o IGBT, avisar Fulano de Tal", PESSOA)
    M.backoffice_definir(cfg, "Beltrana Ramos", True, PESSOA)
    cru = open(cfg["NEXUS_PCM_MOTIVOS_ARQUIVO"], encoding="utf-8").read()
    for texto in ("Fulano", "IGBT", "MPA - Inversor", "Usina 1", "Cliente A", "Beltrana", "pessoa.teste", "Pessoa Teste"):
        assert texto not in cru, texto
    marca = json.loads(cru)[M.ABA_MARCA][0]
    assert marca["os"] == 15596 and marca["codigo_ativo"] == "ELF1-INV02" and marca["equipamento_id"]
    from nexus.dados import fatos as D
    assert marca["tarefa_chave"] == D.tarefa_chave(T1["tarefa"]) and marca["dados_cifrados"].startswith("cf1:")
    # com outra chave nada abre: a marca conta como ilegível e não vale
    outro = dict(cfg, NEXUS_CHAVE_CADASTRO=gerar_chave())
    assert M.vigentes(outro, M.ler(cfg, forcar=True)) == {"_ilegiveis": 1}
    with pytest.raises(M.Recusada):
        M.marcar(dict(cfg, NEXUS_CHAVE_CADASTRO=""), T1, 1, "", PESSOA)


# ── o arquivo do motor, do robô e do App ──────────────────────────────────────────────────────────────────────
def test_arquivo_do_robo_sem_observacao_nem_quem(cfg):
    M.marcar(cfg, T1, _mid(cfg, "Aguardando material"), "obs que não sai", PESSOA)
    M.marcar(cfg, {"os": 15020, "codigo": "", "tarefa": "Limpeza de módulos"}, _mid(cfg, "Engenharia"), "", PESSOA,
             origem="painel")
    M.backoffice_definir(cfg, "Beltrana Ramos", True, PESSOA)
    M.backoffice_definir(cfg, "Joana Teste", True, PESSOA)
    a = M.arquivo(cfg)
    assert a["versao"] == 1 and len(a["motivos"]) == 12 and a["backoffice"] == ["Beltrana Ramos", "Joana Teste"]
    assert [(t["os"], t["codigo"], t["tira_da_programacao"]) for t in a["tarefas"]] == [
        ("15020", "", False), ("15596", "ELF1-INV02", True)]
    assert set(a["tarefas"][1]) == {"os", "codigo", "tarefa", "usina", "cluster", "data_prog", "motivo", "origem",
                                    "tira_da_programacao", "desde"}
    assert {t["origem"] for t in a["tarefas"]} == {"nexus"}
    assert all(m["ativo"] for m in a["motivos"])
    # o texto vai como está na linha da programação (o App de Campo casa sem normalizar); a tarefa é a mesma
    M.marcar(cfg, {"os": "15700", "codigo": "ELF1-INV09 ", "tarefa": " [Grid Co.]  -  MPA - Inversor"},
             _mid(cfg, "Aguardando material"), "", PESSOA)
    t = next(t for t in M.arquivo(cfg)["tarefas"] if t["os"] == "15700")
    assert (t["codigo"], t["tarefa"]) == ("ELF1-INV09", "[Grid Co.]  -  MPA - Inversor")
    assert M.motivo_de(M.indice(_vig(cfg)), "15700", "elf1-inv09", "[Grid Co.] - MPA - Inversor")
    M.marcar(cfg, {"os": "15700", "codigo": "ELF1-INV09", "tarefa": "[Grid Co.] - MPA - Inversor"}, None, "", PESSOA)
    corpo = M.bytes_do_arquivo(a).decode("utf-8")
    assert "obs que não sai" not in corpo and "Pessoa Teste" not in corpo and "pessoa.teste" not in corpo
    # o hash é do conteúdo: a hora não muda, a marca nova muda
    assert M.arquivo(cfg)["hash"] == a["hash"]
    M.marcar(cfg, T1, None, "", PESSOA)
    assert M.arquivo(cfg)["hash"] != a["hash"]


def test_a_rodada_escreve_o_arquivo_e_usa_a_copia_quando_o_banco_cai(cfg, tmp_path, monkeypatch):
    M.marcar(cfg, T1, _mid(cfg, "Aguardando material"), "", PESSOA)
    M.backoffice_definir(cfg, "Beltrana Ramos", True, PESSOA)
    trab = tmp_path / "trab"
    (tmp_path / "r1").mkdir()
    c = M.materializar(cfg, tmp_path / "r1", trab)
    feito = json.loads((tmp_path / "r1" / M.ARQUIVO).read_text(encoding="utf-8"))
    assert feito["tarefas"][0]["os"] == "15596" and feito["backoffice"] == ["Beltrana Ramos"]
    assert not c["aviso"] and "1 tarefa fora por motivo, 1 nome do backoffice" in c["detalhe"]
    # o banco cai: vale a última cópia boa desta máquina, com aviso
    def cai(_cfg):
        raise RuntimeError("banco fora")
    monkeypatch.setattr(M, "_ler_cru", cai)
    M.limpar()
    (tmp_path / "r2").mkdir()
    c2 = M.materializar(cfg, tmp_path / "r2", trab)
    assert c2["aviso"] and "o banco não respondeu" in c2["detalhe"]
    assert json.loads((tmp_path / "r2" / M.ARQUIVO).read_text(encoding="utf-8"))["tarefas"] == feito["tarefas"]
    # sem cópia, a rodada não sai: gerar sem as exclusões programaria o que o PCM tirou
    (trab / ("ultimo_" + M.ARQUIVO)).unlink()
    M.limpar()
    with pytest.raises(M.Recusada):
        M.materializar(cfg, tmp_path / "r2", trab)


def test_a_geracao_leva_o_arquivo_para_o_motor(config, tmp_path):
    """O Fora_da_programacao.json entra na pasta da rodada, com o carimbo no status (o motor o lê dali)."""
    M.limpar()
    cfg = dict(config, NEXUS_PCM_MOTIVOS_ARQUIVO=str(tmp_path / "motivos.json"), NEXUS_CHAVE_CADASTRO=gerar_chave(),
               NEXUS_PESSOA_HMAC="chave-hmac-de-teste")
    M.marcar(cfg, T1, _mid(cfg, "Aguardando cliente"), "", PESSOA)
    r = G.iniciar(cfg, "2026-W41")
    st = G.aguardar(cfg, r["id"], 60)
    assert st["estado"] == "ok", st
    pasta = G.pasta_trabalho(cfg) / "geracoes" / r["id"]
    assert json.loads((pasta / M.ARQUIVO).read_text(encoding="utf-8"))["tarefas"][0]["tarefa"] == T1["tarefa"]
    assert any(i["nome"].startswith("Motivos e backoffice") for i in st["insumos"])


def test_github_so_grava_o_que_mudou(cfg):
    gh = GitHubFalso()
    cfg.update(NEXUS_PCM_GITHUB_TOKEN="tok-teste", NEXUS_PCM_GITHUB_SESSAO=gh)
    M.marcar(cfg, T1, _mid(cfg, "Aguardando material"), "", PESSOA)
    r = M.publicar_arquivo(cfg)
    assert r["commit"] and not r["igual"] and len(gh.commits) == 1
    no_repo = json.loads(gh.arquivos[M.ARQUIVO].decode("utf-8"))
    assert no_repo["tarefas"][0]["os"] == "15596" and "Pessoa Teste" not in gh.commits[0]["mensagem"]
    assert M.publicar_arquivo(cfg)["igual"] and len(gh.commits) == 1
    M.esquecer_estado_no_repositorio()
    assert M.estado_no_repositorio(cfg)["em_dia"]
    M.marcar(cfg, T1, None, "", PESSOA)
    M.esquecer_estado_no_repositorio()
    assert not M.estado_no_repositorio(cfg)["em_dia"]
    with pytest.raises(M.Recusada):
        M.publicar_arquivo(dict(cfg, NEXUS_PCM_GITHUB_TOKEN=""))


# ── as telas ──────────────────────────────────────────────────────────────────────────────────────────────────
GESTAO = [
    {"os": "5", "tarefa": "[Grid Co.] - MPM - Cabine", "estado": "Não iniciada", "tipo": "MPM",
     "usina": "Cliente A - Usina 1 - SP", "cliente": "Cliente A"},
    {"os": "6", "tarefa": "Troca de fusível", "estado": "Finalizada", "tipo": "Corretiva",
     "usina": "Cliente B - Usina 2 - RN", "cliente": "Cliente B"},
    {"os": "7", "tarefa": "Limpeza do inversor", "estado": "Em progresso", "tipo": "Corretiva",
     "usina": "Cliente B - Usina 2 - RN", "cliente": "Cliente B"},
    {"os": "7", "tarefa": "Limpeza do inversor", "estado": "Não iniciada", "tipo": "Corretiva",
     "usina": "Cliente B - Usina 2 - RN", "cliente": "Cliente B"},
    {"os": "9", "tarefa": "Troca de cabo", "estado": "Finalizada", "tipo": "Corretiva",       # só na Gestão, finalizada
     "usina": "Cliente B - Usina 2 - RN", "cliente": "Cliente B"},
]


@pytest.fixture
def tela(app, tmp_path, monkeypatch):
    """A semana 41 do teste do Quadro em curso (com o código do ativo nas linhas da OS 5), a Gestão PCM, o livro dos
    motivos num arquivo e o GitHub falso."""
    M.limpar()
    M.esquecer_estado_no_repositorio()
    monkeypatch.setattr(Q, "hoje", lambda: date(2026, 10, 7))
    sem = _semana_teste()
    for r in sem["rows"]:
        if r["os_id"] == "5":
            r["codigo"] = "UFV1-CAB01" if "Cabine" in r["tarefa"] else "UFV1-TR01"
    sem.update(num=41, geradaEm="2026-10-02T21:54:41Z")
    banco = tmp_path / "banco_dados.json"
    banco.write_text(json.dumps({"geradoEm": "2026-10-07T12:00:00Z", "semana_ativa": "2026-W41", "semanas": [sem]}),
                     encoding="utf-8")
    gestao = tmp_path / "gestao_pcm.json"
    gestao.write_text(json.dumps({"geradoEm": "2026-10-07T12:00:00Z", "dataHash": "abc", "tarefas": GESTAO}),
                      encoding="utf-8")
    gh = GitHubFalso()
    app.config.update(NEXUS_PCM_FONTE=str(banco), NEXUS_PCM_GESTAO_FONTE=str(gestao),
                      NEXUS_PCM_TRABALHO=str(tmp_path / "trab"), NEXUS_PCM_MOTIVOS_ARQUIVO=str(tmp_path / "motivos.json"),
                      NEXUS_CHAVE_CADASTRO=gerar_chave(), NEXUS_PESSOA_HMAC="chave-hmac-de-teste",
                      NEXUS_PCM_GITHUB_TOKEN="tok-teste", NEXUS_PCM_GITHUB_SESSAO=gh)
    return gh


def _dados(html: str) -> dict:
    return json.loads(html.split('id="q-dados">', 1)[1].split("</script>", 1)[0])


def test_quem_marca_e_quem_mexe_no_cadastro(app, tela, monkeypatch):
    """Marca e tira: PCM, Responsáveis UFV (os supervisores) e administrador. Cadastro: administrador e PCM."""
    c = _pessoa(app)
    marca = {"semana": "2026-W41", "os": "6", "tarefa": "Troca de fusível", "codigo": "", "motivo_id": 6}
    _no_setor(monkeypatch, "Performance")
    assert c.post("/t/pcm/quadro/motivo", json=marca).status_code == 403
    assert c.post("/t/pcm/fora-da-programacao/marcar", data={"item": "x", "tirar": "1"}).status_code == 403
    assert c.post("/t/pcm/fora-da-programacao/cadastro", data={"acao": "criar", "nome": "Novo"}).status_code == 403
    assert not _dados(c.get("/t/pcm/quadro").get_data(as_text=True))["pode_marcar"]
    _no_setor(monkeypatch, "Responsáveis UFV")
    r = c.post("/t/pcm/quadro/motivo", json=marca)
    assert r.status_code == 200 and r.get_json()["ok"] and r.get_json()["marca"]["n"] == "Aguardando material"
    assert c.post("/t/pcm/fora-da-programacao/cadastro", data={"acao": "criar", "nome": "Novo"}).status_code == 403
    _no_setor(monkeypatch, "pcm")
    r = c.post("/t/pcm/fora-da-programacao/cadastro", data={"acao": "criar", "nome": "Aguardando laudo", "tira": "1"})
    assert r.status_code == 303 and "ver=cadastro" in r.headers["Location"]
    html = c.get("/t/pcm/fora-da-programacao?ver=cadastro").get_data(as_text=True)
    assert "Motivo Aguardando laudo incluído." in html and "Aguardando laudo" in html
    # pedido de outro site não grava, nem para quem pode
    assert c.post("/t/pcm/quadro/motivo", json=marca, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_janela_do_quadro_marca_a_tarefa_da_semana(app, logado, tela):
    html = logado.get("/t/pcm/quadro").get_data(as_text=True)
    d = _dados(html)
    assert d["pode_marcar"] and len(d["motivos"]) == 12 and d["url_motivo"] == "/t/pcm/quadro/motivo"
    assert '<span class="q-mp' not in html                       # nada marcado ainda: nenhum selo
    am = next(m[0] for m in d["motivos"] if m[1] == "Aguardando material")
    cab = {"semana": "2026-W41", "os": "5", "tarefa": "[Grid Co.] - MPM - Cabine", "codigo": "UFV1-CAB01"}
    # a tarefa vem da semana: OS, nome ou código que a semana não tem não gravam
    for errado in (dict(cab, os="999"), dict(cab, tarefa="Outra"), dict(cab, codigo="UFV1-XX")):
        r = logado.post("/t/pcm/quadro/motivo", json=dict(errado, motivo_id=am))
        assert r.status_code == 400 and not r.get_json()["ok"]
    assert logado.post("/t/pcm/quadro/motivo", json=cab).status_code == 400            # sem motivo
    r = logado.post("/t/pcm/quadro/motivo", json=dict(cab, motivo_id=am, obs="falta o disjuntor")).get_json()
    assert r["ok"] and r["gravou"] and not r["geral"] and r["efetiva"]["n"] == "Aguardando material"
    assert "robô do PCM tira a tarefa da semana em curso" in r["efeito"] and r["arquivo"]["ok"]
    assert len(tela.commits) == 1 and tela.commits[0]["caminho"] == M.ARQUIVO
    # o que o App de Campo recebe: a tarefa como na linha, com usina, cluster e o dia em que estava na agenda
    no_repo = json.loads(tela.arquivos[M.ARQUIVO].decode("utf-8"))
    assert no_repo["tarefas"] == [{"os": "5", "codigo": "UFV1-CAB01", "tarefa": "[Grid Co.] - MPM - Cabine",
                                   "usina": "Cliente A - Usina 1 - SP", "cluster": "SP Leste 02",
                                   "data_prog": "2026-10-07", "motivo": am, "origem": "nexus", "tira_da_programacao": True,
                                   "desde": no_repo["tarefas"][0]["desde"]}]
    # o cartão da Cabine ganha o selo; o do Trafo (outro ativo, outra tarefa) não
    html = logado.get("/t/pcm/quadro").get_data(as_text=True)
    d = _dados(html)
    cabine = next(i for i in d["itens"] if i["t"].endswith("Cabine"))
    assert cabine["mp"]["n"] == "Aguardando material" and cabine["mp"]["obs"] == "falta o disjuntor"
    assert "mp" not in next(i for i in d["itens"] if i["t"].endswith("Trafo"))
    assert html.count('q-mp q-mp--tira"') == 1
    # tirar
    r = logado.post("/t/pcm/quadro/motivo", json=dict(cab, tirar=True)).get_json()
    assert r["ok"] and r["gravou"] and r["efetiva"] is None and len(tela.commits) == 2
    assert "mp" not in next(i for i in _dados(logado.get("/t/pcm/quadro").get_data(as_text=True))["itens"]
                            if i["t"].endswith("Cabine"))


def test_janela_do_quadro_mexe_na_marca_da_os(app, logado, tela):
    """A pendente sem código (a do App) marca pela OS; na janela, trocar a marca da OS mexe nela."""
    ac = next(m["id"] for m in M.ativos(M.ler(app.config)) if m["nome"] == "Aguardando cliente")
    fus = {"semana": "2026-W41", "os": "6", "tarefa": "Troca de fusível", "codigo": ""}
    r = logado.post("/t/pcm/quadro/motivo", json=dict(fus, motivo_id=ac)).get_json()
    assert r["ok"] and r["geral"] and r["marca"]["geral"]
    vig = {k: v for k, v in M.vigentes(app.config, M.ler(app.config, forcar=True)).items() if not k.startswith("_")}
    assert [(m["os"], m["codigo"]) for m in vig.values()] == [("6", "")]
    # a linha da agenda TEM código, mas a marca que vale nela foi feita pela OS (no painel): trocar e tirar na janela
    # mexem nessa marca (em todos os ativos), e não criam uma marca do ativo por cima
    am = next(m["id"] for m in M.ativos(M.ler(app.config)) if m["nome"] == "Aguardando material")
    M.marcar(app.config, {"os": "5", "codigo": "", "tarefa": "[Grid Co.] - MPM - Cabine"}, ac, "", PESSOA, origem="painel")
    cab = {"semana": "2026-W41", "os": "5", "tarefa": "[Grid Co.] - MPM - Cabine", "codigo": "UFV1-CAB01"}
    r = logado.post("/t/pcm/quadro/motivo", json=dict(cab, motivo_id=am)).get_json()
    assert r["ok"] and r["gravou"] and r["geral"] and r["efetiva"]["n"] == "Aguardando material"
    vig = {k: v for k, v in M.vigentes(app.config, M.ler(app.config, forcar=True)).items() if not k.startswith("_")}
    assert sorted((m["os"], m["codigo"], m["motivo"]) for m in vig.values()) == [
        ("5", "", "Aguardando material"), ("6", "", "Aguardando cliente")]
    r = logado.post("/t/pcm/quadro/motivo", json=dict(cab, tirar=True)).get_json()
    assert r["ok"] and r["gravou"] and r["efetiva"] is None
    vig = {k: v for k, v in M.vigentes(app.config, M.ler(app.config, forcar=True)).items() if not k.startswith("_")}
    assert [(m["os"], m["codigo"]) for m in vig.values()] == [("6", "")]


def test_painel_fora_da_programacao(app, logado, tela):
    cfg = app.config
    am, ac, en, conc = (next(m["id"] for m in M.ativos(M.ler(cfg)) if m["nome"] == n) for n in (
        "Aguardando material", "Aguardando cliente", "Engenharia", "Aguardando concessionária"))
    M.marcar(cfg, {"os": "5", "codigo": "UFV1-CAB01", "tarefa": "[Grid Co.] - MPM - Cabine",
                   "usina": "Cliente A - Usina 1 - SP"}, am, "falta o disjuntor", PESSOA)
    M.marcar(cfg, {"os": "6", "codigo": "", "tarefa": "Troca de fusível"}, ac, "", PESSOA)       # finalizada
    M.marcar(cfg, {"os": "8", "codigo": "", "tarefa": "Inspeção termográfica do trafo 9"}, en, "", PESSOA)             # não tira
    M.marcar(cfg, {"os": "7", "codigo": "", "tarefa": "Limpeza do inversor"}, conc, "", PESSOA, origem="painel")
    html = " ".join(logado.get("/t/pcm/fora-da-programacao").get_data(as_text=True).split())
    assert "falta o disjuntor" in html and "UFV1-CAB01" in html and "Troca de fusível" not in html
    assert "termográfica do trafo 9" not in html and "1 finalizada no Fracttal saiu daqui" in html
    assert "todos os ativos da OS" in html and "Limpeza do inversor" in html        # a marca da OS (de antes) aparece
    filtro = html.split('id="f-motivo"', 1)[1].split("</select>", 1)[0]
    assert "Aguardando material (1)" in filtro and "Aguardando cliente" not in filtro    # o filtro lista o que existe
    html = " ".join(logado.get(f"/t/pcm/fora-da-programacao?motivo={ac}").get_data(as_text=True).split())
    assert "Nenhuma tarefa com esse motivo." in html
    # tirar pelo painel
    item = next(k for k, m in M.vigentes(cfg, M.ler(cfg, forcar=True)).items() if m["os"] == "7")
    logado.post("/t/pcm/fora-da-programacao/marcar", data={"item": item, "tirar": "1"})
    assert "Limpeza do inversor" not in logado.get("/t/pcm/fora-da-programacao").get_data(as_text=True)


def test_painel_sem_marcar_pela_os_e_a_tabela_da_2a_rodada(app, logado, tela):
    """Levi, 16/10/2026 (2ª rodada): "tire esse 'Marcar pela OS' atrapalha mais que ajuda"; "Tire a observação 'Os
    motivos se marcam no Nexus...'"; centrar tudo menos a Tarefa; sem a coluna Editar que abria a linha. O pedido pela
    OS, sem a tarefa já marcada, não grava mais nada."""
    am = next(m["id"] for m in M.ativos(M.ler(app.config)) if m["nome"] == "Aguardando material")
    M.marcar(app.config, {"os": "5", "codigo": "UFV1-CAB01", "tarefa": "[Grid Co.] - MPM - Cabine"}, am, "", PESSOA)
    html = " ".join(logado.get("/t/pcm/fora-da-programacao?os=7").get_data(as_text=True).split())
    assert "Marcar pela OS" not in html and "Ver as tarefas" not in html and 'name="os"' not in html
    assert "Os motivos se marcam no Nexus" not in html and "<details>" not in html
    assert 'class="pcm-tabela fp-tab"' in html and '<th class="fp-esq">Tarefa</th>' in html
    assert 'class="fp-mais-b"' in html and "Retornar à programação" in html and 'class="fp-tirar"' not in html
    antes = len(M.vigentes(app.config, M.ler(app.config, forcar=True)))
    r = logado.post("/t/pcm/fora-da-programacao/marcar", data={"os": "7", "tarefa": "Limpeza do inversor",
                                                                 "motivo_id": am})
    assert r.status_code == 303
    assert "A tarefa não foi achada: atualize a página." in logado.get("/t/pcm/fora-da-programacao").get_data(as_text=True)
    assert len(M.vigentes(app.config, M.ler(app.config, forcar=True))) == antes and not tela.commits


def test_painel_3a_rodada_usina_hora_os_e_tres_pontos(app, logado, tela, monkeypatch):
    """Levi, 16/10/2026 (3ª rodada): "Em usina só o nome da usina, sem o nome do cliente no início"; "números de 5 a 6
    dígitos ficará em verde grid, quando a pessoa clicar vai sobrepor na tela a mesma tela que aparece quando você clica
    na OS no histórico de OS do OS Creator Web"; os três pontos com "retornar a programação"; "em desde quero data e
    hora"; abaixo da tarefa "só MPA · no Fracttal: Não Iniciada"."""
    from datetime import datetime as _dt, timezone as _tz
    cfg = app.config
    monkeypatch.setattr(M, "_agora", lambda: _dt(2026, 10, 7, 17, 32, tzinfo=_tz.utc))        # 14:32 de Brasília
    am = next(m["id"] for m in M.ativos(M.ler(cfg)) if m["nome"] == "Aguardando material")
    M.marcar(cfg, {"os": "5", "codigo": "UFV1-CAB01", "tarefa": "[Grid Co.] - MPM - Cabine", "tipo": "MPM",
                   "usina": "Cliente A - Usina 1 - SP"}, am, "Realizado atividade da OS16290, ver OS 16291", PESSOA)
    html = " ".join(logado.get("/t/pcm/fora-da-programacao").get_data(as_text=True).split())
    linha = html.split('<tbody>', 1)[1].split('</tr>', 1)[0]
    assert '<td class="fp-usina" title="Cliente A - Usina 1 - SP">Usina 1</td>' in linha
    assert '<td class="gc-dado">07/10/2026 14:32</td>' in linha
    assert 'title="UFV1-CAB01">[Grid Co.] - MPM - Cabine<small>MPM · no Fracttal: Não iniciada</small>' in linha
    # a OS e os números de 5 a 6 dígitos da observação: botões que abrem o card (pelo número, sem a OS na Gestão)
    assert '<button type="button" class="fp-os-n" data-os="5" title="Abrir a OS 5">5</button>' in linha
    assert ('Realizado atividade da OS<button type="button" class="fp-os-n" data-os="16290" title="Abrir a OS 16290">'
            '16290</button>, ver OS <button type="button" class="fp-os-n" data-os="16291"') in linha
    assert 'NexusOsCard.abrirFolio' in html and "card_os_abrir" not in html.split("<body", 1)[0]
    # os três pontos: o menu com o Retornar à programação (tira o motivo)
    assert 'class="fp-mais-b"' in linha and 'name="tirar" value="1"' in linha and "Retornar à programação" in linha
    from nexus.pcm import telas as T
    assert [T._nome_da_usina(x) for x in ("Thopen - Parelhas 1 - RN", "Thopen - Araçoiaba da Serra 1- SP",
                                          "2C - Ipixuna do Pará 1 - PA", "Usina sem cliente", "")] == [
        "Parelhas 1", "Araçoiaba da Serra 1", "Ipixuna do Pará 1", "Usina sem cliente", ""]
    # o texto da observação é escapado antes: só o número vira botão
    assert str(T._com_os("<b>OS 123456</b> e 1234567", None)) == (
        '&lt;b&gt;OS <button type="button" class="fp-os-n" data-os="123456" title="Abrir a OS 123456">123456</button>'
        '&lt;/b&gt; e 1234567')


def test_motivo_do_tecnico_nao_se_troca_e_a_observacao_sim(app, logado, tela):
    """Levi, 16/10/2026: "nem deveria poder trocar o motivo, se o técnico disse tá dito, observação Ok editar" e
    "Motivo também deve ter como trocar pela coluna!" (o do PCM). A observação editada pelo PCM não tira a justificativa
    do painel nem troca quem marcou (antes, a "Prioridade" do técnico sumia daqui e virava do PCM)."""
    cfg = app.config
    pr, am, conc, en = (next(m["id"] for m in M.ativos(M.ler(cfg)) if m["nome"] == n) for n in (
        "Prioridade", "Aguardando material", "Aguardando concessionária", "Engenharia"))
    assert _pelo_app(app, {"os": "5", "codigo": "UFV1-CAB01", "tarefa": "[Grid Co.] - MPM - Cabine", "motivo": pr,
                           "obs": "atendi a parada antes", "tecnico_hmac": TEC,
                           "tecnico_nome": "Técnico Teste"}).get_json()["gravou"]
    M.marcar(cfg, {"os": "5", "codigo": "UFV1-TR01", "tarefa": "[Grid Co.] - MPM - Trafo"}, am, "", PESSOA)
    vig = M.vigentes(cfg, M.ler(cfg, forcar=True))
    app_item = next(k for k, m in vig.items() if m["codigo"] == "UFV1-CAB01")
    pcm_item = next(k for k, m in vig.items() if m["codigo"] == "UFV1-TR01")
    html = logado.get("/t/pcm/fora-da-programacao").get_data(as_text=True)
    linha_app = html.split(app_item, 1)[0].rsplit("<tr>", 1)[1] + html.split(app_item, 1)[1].split("</tr>", 1)[0]
    linha_pcm = html.split(pcm_item, 1)[0].rsplit("<tr>", 1)[1] + html.split(pcm_item, 1)[1].split("</tr>", 1)[0]
    assert 'class="fp-mot"' not in linha_app and "q-mp" in linha_app       # o do técnico: o selo, sem a lista
    assert 'class="fp-mot"' in linha_pcm and "fp-obs-form" in linha_app     # o do PCM troca na célula; a obs, nos dois
    # o servidor também não troca o motivo do técnico
    logado.post("/t/pcm/fora-da-programacao/marcar", data={"item": app_item, "motivo_id": conc})
    aviso = logado.get("/t/pcm/fora-da-programacao").get_data(as_text=True)
    assert "O motivo que o técnico mandou pelo App não se troca" in aviso
    assert M.vigentes(cfg, M.ler(cfg, forcar=True))[app_item]["motivo_id"] == pr
    # a observação do técnico se edita: a linha continua, com o técnico em "Quem marcou" e a origem App no arquivo
    logado.post("/t/pcm/fora-da-programacao/marcar", data={"item": app_item, "obs": "atendi a parada antes (PCM ciente)"})
    m = M.vigentes(cfg, M.ler(cfg, forcar=True))[app_item]
    assert m["obs"] == "atendi a parada antes (PCM ciente)" and m["origem"] == "painel"
    assert (m["origem_motivo"], m["quem_motivo"], m["motivo_id"]) == ("app", "Técnico Teste", pr)
    html = " ".join(logado.get("/t/pcm/fora-da-programacao").get_data(as_text=True).split())
    assert "OS 5: observação salva." in html and "atendi a parada antes (PCM ciente)" in html
    assert "Técnico Teste <span class=\"gc-ajuda\">(App)</span>" in html
    no_arquivo = {(t["codigo"], t["origem"]) for t in M.arquivo(cfg)["tarefas"]}
    assert ("UFV1-CAB01", "app") in no_arquivo and ("UFV1-TR01", "nexus") in no_arquivo
    # o motivo do PCM troca pela coluna (e o que não tira tira a tarefa do painel)
    logado.post("/t/pcm/fora-da-programacao/marcar", data={"item": pcm_item, "motivo_id": conc})
    m = M.vigentes(cfg, M.ler(cfg, forcar=True))[pcm_item]
    assert m["motivo_id"] == conc and m["origem_motivo"] == "painel"
    assert "OS 5: Aguardando concessionária." in logado.get("/t/pcm/fora-da-programacao").get_data(as_text=True)
    logado.post("/t/pcm/fora-da-programacao/marcar", data={"item": pcm_item, "motivo_id": en})
    assert "[Grid Co.] - MPM - Trafo" not in logado.get("/t/pcm/fora-da-programacao").get_data(as_text=True)


def test_lista_do_backoffice_no_gerar(app, logado, config, tmp_path):
    M.limpar()
    app.config.update({k: v for k, v in config.items() if k != "TESTING"})
    app.config.update(NEXUS_PCM_MOTIVOS_ARQUIVO=str(tmp_path / "motivos.json"), NEXUS_CHAVE_CADASTRO=gerar_chave(),
                      NEXUS_PESSOA_HMAC="chave-hmac-de-teste", NEXUS_PCM_GITHUB_TOKEN="tok-teste",
                      NEXUS_PCM_GITHUB_SESSAO=GitHubFalso())
    html = logado.get("/t/pcm/gerar?semana=2026-W42").get_data(as_text=True)
    assert "Backoffice: OS fora da programação" in html and "Ninguém na lista" in html
    r = logado.post("/t/pcm/gerar/backoffice", data={"nome": "Beltrana  Ramos", "acao": "por", "semana": "2026-W42"})
    assert r.status_code == 303 and r.headers["Location"].endswith("semana=2026-W42#backoffice")
    html = logado.get("/t/pcm/gerar?semana=2026-W42").get_data(as_text=True)
    assert "Beltrana Ramos entrou na lista do backoffice." in html and "Ninguém na lista" not in html
    logado.post("/t/pcm/gerar/backoffice", data={"nome": "Beltrana Ramos", "acao": "tirar", "semana": "2026-W42"})
    assert "Ninguém na lista" in logado.get("/t/pcm/gerar?semana=2026-W42").get_data(as_text=True)


# ── o contrato com o motor e o robô do PCM (nexus/pcm/motor/fora_da_programacao.py, cópia do repositório do PCM) ──
def _leitor_do_pcm():
    import importlib.util
    from pathlib import Path
    caminho = Path(__file__).resolve().parent.parent / "nexus" / "pcm" / "motor" / "fora_da_programacao.py"
    spec = importlib.util.spec_from_file_location("fora_da_programacao_pcm", caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_o_motor_e_o_robo_leem_o_arquivo_do_nexus(cfg, tmp_path):
    """O arquivo que o Nexus escreve (motivos.arquivo) é lido pelo módulo do PCM com a MESMA regra: a marca do ativo
    vence a da OS (também a que não tira), a OS como inteiro, o código sem espaço e sem caixa, o nome sem acento; o
    backoffice pelo nome sem acento. Mudou a regra num lado, este teste quebra."""
    F = _leitor_do_pcm()
    am, en = _mid(cfg, "Aguardando material"), _mid(cfg, "Engenharia")
    M.marcar(cfg, T1, am, "", PESSOA)                                                   # do ativo, tira
    M.marcar(cfg, {"os": 15020, "codigo": "", "tarefa": "Limpeza de módulos"}, am, "", PESSOA, origem="painel")
    M.marcar(cfg, {"os": 15020, "codigo": "UFV2-INV01", "tarefa": "Limpeza de módulos"}, en, "", PESSOA)
    M.marcar(cfg, {"os": 15030, "codigo": "X1", "tarefa": "Inspeção"}, en, "", PESSOA)  # não tira
    M.backoffice_definir(cfg, "Rógerio Fictício", True, PESSOA)
    (tmp_path / F.ARQUIVO).write_bytes(M.bytes_do_arquivo(M.arquivo(cfg)))
    fora = F.carregar(str(tmp_path))
    assert not fora["erro"] and fora["n_tarefas"] == 2 and len(fora["marcas"]) == 4
    assert F.motivo_que_tira(fora, 15596, "ELF1-INV02", T1["tarefa"]) == "Aguardando material"
    assert F.motivo_que_tira(fora, "15596.0", " elf1-inv02", "[grid co.]  -  MPA - inversor ") == "Aguardando material"
    assert F.motivo_que_tira(fora, 15596, "ELF1-INV03", T1["tarefa"]) is None          # outro ativo, sem marca
    assert F.motivo_que_tira(fora, 15020, "UFV2-INV02", "Limpeza de modulos") == "Aguardando material"   # a da OS
    assert F.motivo_que_tira(fora, 15020, "UFV2-INV01", "Limpeza de módulos") is None   # o ativo com marca própria
    assert F.motivo_que_tira(fora, 15030, "X1", "Inspeção") is None                     # marca que não tira
    assert F.do_backoffice(fora, "  rogerio  FICTICIO ") and not F.do_backoffice(fora, "Rógerio")
    # o Nexus e o PCM normalizam igual
    for s in ("Ação  Elétrica", " ÇÃO ç ", "[Grid Co.] - MPM - Caixa d'água", "", None, "15596.0"):
        assert F.norm(s) == M.norm(s) and F.canon(s) == M.canon(s) and F.os_de(s) == M.os_de(s), s
    # sem o arquivo, nada fica de fora; arquivo quebrado também não (e diz por quê)
    assert F.carregar(str(tmp_path / "nao_existe")) == F.vazio()
    (tmp_path / F.ARQUIVO).write_text("{quebrado", encoding="utf-8")
    quebrado = F.carregar(str(tmp_path))
    assert not quebrado["marcas"] and "ilegível" in quebrado["erro"]


# ── a marca do técnico pelo App de Campo (nexus/pcm/motivos_app.py; Levi, 16/10/2026: "Sim, e já vale") ──────────
TEC = "ab" * 12                         # o código do técnico (24 hexadecimais, como o "Técnico (HMAC)" das rondas)


def _pelo_app(app, corpo: dict, ts=None, chave=None, assinar=True):
    import time as _tempo
    from nexus.pcm import motivos_app as MA
    bruto = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
    ts = int(_tempo.time()) if ts is None else int(ts)
    k = chave or MA.chave(app.config)
    cab = {"X-Nexus-Ts": str(ts), "X-Nexus-Assinatura": MA.assinatura(k, ts, bruto) if assinar else "0" * 64,
           "Content-Type": "application/json"}
    return app.test_client().post("/t/pcm/motivos/app", data=bruto, headers=cab)       # sem sessão nenhuma


def test_o_tecnico_marca_pelo_app(app, logado, tela):
    """O App manda a marca assinada (chave derivada da NEXUS_PESSOA_HMAC, como as fotos dos extintores); vale na hora:
    grava como a do PCM (origem app, quem marcou pelo código do técnico) e o arquivo do robô vai ao repositório."""
    cfg = app.config
    am, en = (next(m["id"] for m in M.ativos(M.ler(cfg)) if m["nome"] == n) for n in ("Aguardando material", "Engenharia"))
    cab = {"os": "5", "codigo": "UFV1-CAB01", "tarefa": "[Grid Co.] - MPM - Cabine", "motivo": am,
           "obs": "falta o disjuntor", "tecnico_hmac": TEC, "tecnico_nome": "Técnico Teste"}
    r = _pelo_app(app, cab)
    j = r.get_json()
    assert r.status_code == 200 and j["gravou"] and j["marca"]["n"] == "Aguardando material" and j["marca"]["app"]
    ultima = json.loads(open(cfg["NEXUS_PCM_MOTIVOS_ARQUIVO"], encoding="utf-8").read())[M.ABA_MARCA][-1]
    assert ultima["origem"] == "app" and ultima["decidida_por_hmac"] == TEC and "Técnico Teste" not in json.dumps(ultima)
    no_repo = json.loads(tela.arquivos[M.ARQUIVO])["tarefas"][0]
    assert len(tela.commits) == 1 and no_repo["tarefa"] == cab["tarefa"] and no_repo["origem"] == "app"
    assert not _pelo_app(app, cab).get_json()["gravou"] and len(tela.commits) == 1          # o mesmo envio de novo
    html = " ".join(logado.get("/t/pcm/fora-da-programacao").get_data(as_text=True).split())
    assert "Técnico Teste <span class=\"gc-ajuda\">(App)</span>" in html and "falta o disjuntor" in html
    # a OS avulsa do App (aberta na Gestão PCM, fora da programação): marca com o código que o App mandou
    r = _pelo_app(app, {"os": "7", "codigo": "UFV2-INV03", "tarefa": "limpeza do  INVERSOR", "motivo": en,
                        "tecnico_hmac": TEC, "tecnico_nome": "Técnico Teste"})
    assert r.status_code == 200 and r.get_json()["gravou"]
    vig = {k: v for k, v in M.vigentes(cfg, M.ler(cfg, forcar=True)).items() if not k.startswith("_")}
    assert ("7", "UFV2-INV03", "Limpeza do inversor") in {(m["os"], m["codigo"], m["tarefa"]) for m in vig.values()}
    # tirar pelo App
    j = _pelo_app(app, dict(cab, motivo=None)).get_json()
    assert j["ok"] and j["gravou"] and j["marca"] is None
    # a marca que vale na tarefa foi feita pela OS (painel): tirar pelo App mexe nela, como na janela do Quadro
    M.marcar(cfg, {"os": "5", "codigo": "", "tarefa": "[Grid Co.] - MPM - Trafo"}, am, "", PESSOA, origem="painel")
    j = _pelo_app(app, {"os": "5", "codigo": "UFV1-TR01", "tarefa": "[Grid Co.] - MPM - Trafo", "motivo": None,
                        "tecnico_hmac": TEC, "tecnico_nome": "Técnico Teste"}).get_json()
    assert j["ok"] and j["gravou"]
    vig = {k: v for k, v in M.vigentes(cfg, M.ler(cfg, forcar=True)).items() if not k.startswith("_")}
    assert not [m for m in vig.values() if m["tarefa"].endswith("Trafo")]


def test_o_painel_mostra_toda_justificativa_do_app(app, logado, tela):
    """16/10/2026: o técnico justificava com "Prioridade", que não tira da programação, e o painel mostrava 0 tarefas. A
    justificativa do App aparece com qualquer motivo (texto, quem e desde quando) e o filtro ganha o motivo dela; a marca
    do PCM que não tira continua fora."""
    cfg = app.config
    pr, en = (next(m["id"] for m in M.ativos(M.ler(cfg)) if m["nome"] == n) for n in ("Prioridade", "Engenharia"))
    r = _pelo_app(app, {"os": "5", "codigo": "UFV1-CAB01", "tarefa": "[Grid Co.] - MPM - Cabine", "motivo": pr,
                        "obs": "o supervisor mandou atender a parada antes", "tecnico_hmac": TEC,
                        "tecnico_nome": "Técnico Teste"})
    assert r.status_code == 200 and r.get_json()["gravou"]
    M.marcar(cfg, {"os": "8", "codigo": "", "tarefa": "Inspeção termográfica do trafo 9"}, en, "", PESSOA)
    html = " ".join(logado.get("/t/pcm/fora-da-programacao").get_data(as_text=True).split())
    assert "o supervisor mandou atender a parada antes" in html and "UFV1-CAB01" in html
    assert "Técnico Teste <span class=\"gc-ajuda\">(App)</span>" in html and "termográfica do trafo 9" not in html
    assert "1</b> tarefa: 0 fora da programação, 1 só com justificativa do App" in html
    assert "justificativas que os técnicos mandam pelo App" in html
    filtro = html.split('id="f-motivo"', 1)[1].split("</select>", 1)[0]
    assert "Prioridade (1)" in filtro and "Engenharia" not in filtro
    html = " ".join(logado.get(f"/t/pcm/fora-da-programacao?motivo={pr}").get_data(as_text=True).split())
    assert "o supervisor mandou atender a parada antes" in html


def test_o_app_sem_assinatura_ou_com_tarefa_que_nao_existe_nao_grava(app, tela, monkeypatch):
    cfg = app.config
    am = next(m["id"] for m in M.ativos(M.ler(cfg)) if m["nome"] == "Aguardando material")
    cab = {"os": "5", "codigo": "UFV1-CAB01", "tarefa": "[Grid Co.] - MPM - Cabine", "motivo": am,
           "tecnico_hmac": TEC, "tecnico_nome": "Técnico Teste"}
    from nexus.pcm import motivos_app as MA
    casos = [(_pelo_app(app, cab, assinar=False), 401), (_pelo_app(app, cab, ts=1_000_000_000), 401),
             (_pelo_app(app, cab, chave=MA.hmac.new(b"outra", MA.ROTULO_CHAVE, MA.hashlib.sha256).digest()), 401),
             (_pelo_app(app, dict(cab, os="999")), 404),                              # a tarefa não existe
             (_pelo_app(app, dict(cab, os="9", codigo="", tarefa="Troca de cabo")), 404),   # finalizada, fora da semana
             (_pelo_app(app, dict(cab, tecnico_hmac="fulano")), 400), (_pelo_app(app, dict(cab, motivo="x")), 400),
             (_pelo_app(app, dict(cab, motivo=999)), 400), (_pelo_app(app, dict(cab, tarefa="")), 400)]
    for r, esperado in casos:
        assert r.status_code == esperado and not r.get_json()["ok"], (r.status_code, r.get_json())
    assert not tela.commits and not M.vigentes(cfg, M.ler(cfg, forcar=True))
    app.config["NEXUS_PESSOA_HMAC"] = ""
    assert _pelo_app(app, cab, chave=b"x" * 32).status_code == 503
    # só POST, e o portão deixa passar só esta rota do PCM sem login
    from nexus.auth import ROTAS_PUBLICAS
    assert "torre_pcm.motivo_do_app" in ROTAS_PUBLICAS
    assert app.test_client().get("/t/pcm/motivos/app").status_code in (302, 405)


def test_nome_do_motivo_na_regra_do_levi():
    """Levi, 16/10/2026: "Padronizar texto: sempre a primeira letra maiúscula o resto minúscula conforme regra gramatical"
    — a mesma regra do App de Campo (a sigla de 2 a 4 letras em maiúsculas fica)."""
    assert [M.padronizar(s) for s in ("Aguardando Concessionária", "  aguardando Peça do FORNECEDOR  PCM ",
                                      "Chamados (garantia)", "Aguardando Fabricante/Terceiro", "UFV parada")] == [
        "Aguardando concessionária", "Aguardando peça do fornecedor PCM", "Chamados (garantia)",
        "Aguardando fabricante/terceiro", "UFV parada"]
    assert all(m["nome"] == M.padronizar(m["nome"]) for m in M.cadastro_inicial())


def test_sem_o_arquivo_no_repositorio_o_painel_manda(app, logado, tela):
    """O Justificar do App lê o cadastro do arquivo: sem marca nenhuma, o arquivo que não existe ainda é "desatualizado"
    e o painel mostra o botão de mandar (16/10/2026: o painel escondia e o App ficava sem a lista)."""
    html = " ".join(logado.get("/t/pcm/fora-da-programacao").get_data(as_text=True).split())
    assert "O arquivo ainda não existe no repositório" in html and "Mandar o arquivo de novo" in html
    r = logado.post("/t/pcm/fora-da-programacao/publicar")
    assert r.status_code == 303 and len(tela.commits) == 1
    assert len(json.loads(tela.arquivos[M.ARQUIVO])["motivos"]) == 12
    html = " ".join(logado.get("/t/pcm/fora-da-programacao").get_data(as_text=True).split())
    assert "O arquivo ainda não existe" not in html and "desatualizado" not in html
    assert "Mandar o arquivo de novo" not in html


def test_o_arquivo_vai_fora_do_pedido_e_junta_as_marcas(monkeypatch):
    """Fora dos testes, o arquivo do robô vai ATRASO_PUBLICAR_S depois da marca e as marcas seguidas viram UMA
    publicação (16/10/2026: com o GitHub dentro do pedido, o Justificar do App passava de 20 s)."""
    import time as _tempo
    chamadas = []
    monkeypatch.setattr(M, "publicar_arquivo", lambda cfg: chamadas.append(_tempo.time()) or {"igual": True, "commit": ""})
    monkeypatch.setattr(M, "ATRASO_PUBLICAR_S", 0.2)
    cfg = {"TESTING": False}
    for _ in range(3):
        M.publicar_depois(cfg)
        assert not chamadas                       # a resposta sai antes: nada foi ao GitHub ainda
    _tempo.sleep(0.6)
    assert len(chamadas) == 1
