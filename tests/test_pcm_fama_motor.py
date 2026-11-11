"""O adaptador do programador para as OS da FAMA (fase 2: pronto e DESLIGADO; só com NEXUS_FAMA_PROGRAMA=1; 11/11/2026).

O que estes testes seguram: com a variável desligada, a rodada é a de hoje (nem o adaptador nem a leitura antes do motor
rodam, e a foto fica intacta); com ela ligada, as OS abertas e em andamento da FAMA entram no `.cache_semanal_api.pkl` da
rodada com as colunas do motor (`COLS_BD_SEMANAL`), a preventiva do Fracttal ainda por fazer das usinas da FAMA sai, e a
planilha volta a dizer FAMA-<id>; o título da OS nunca vai para o motor (o log dele imprime o texto das tarefas); a rodada
ligada e sem OS da FAMA não sai. A FAMA, o banco e o Fracttal são de mentira: o motor e a leitura do Fracttal são falsos."""
import ast
import json
import os
import pickle
import textwrap
import time
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

from nexus import config as CONFIG
from nexus.pcm import fama_motor as FM
from nexus.pcm import geracao as G
from test_pcm_geracao import CAB, LINHAS, config, origem  # noqa: F401 (fixtures)

RAIZ = Path(__file__).resolve().parents[1]
MOTOR_BD = RAIZ / "nexus" / "pcm" / "motor" / "gerar_bd_via_api.py"
MOTOR_V7 = RAIZ / "nexus" / "pcm" / "motor" / "programacao_v7.py"
TITULO_SIGILOSO = "Vazamento no telhado da cabine"


def _cols_bd_semanal() -> list[str]:
    """As colunas que o motor lê, tiradas do próprio arquivo do motor (sem importar: ele lê o .env ao subir)."""
    arvore = ast.parse(MOTOR_BD.read_text(encoding="utf-8"))
    no = next(n for n in arvore.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "COLS_BD_SEMANAL")
    return ast.literal_eval(no.value)


COLS = _cols_bd_semanal()


def _fr(os_id, usina, tipo, status="Em processo", estado="Não Iniciada", equipe="SP Leste 02", tarefa="Tarefa"):
    """Uma linha do Fracttal como o leitor do motor a grava no cache (`transformar_wo_para_bd`)."""
    d = {c: "" for c in COLS}
    d.update({"OSs ID": str(os_id), "Status": status, "Código": f"C{os_id}", "Ativo": "Ativo", "Tarefa": tarefa,
              "Ativo Classificação 1": usina, "Ativo Classificação 2": equipe, "Estado da Tarefa": estado,
              "Tipo de tarefa": tipo, "Data Programada": pd.Timestamp("2026-10-06 08:00"),
              "Tarefa -> Duração estimada": pd.Timedelta(hours=1), "Total de Horas": pd.Timedelta(hours=1)})
    return d


U1, U2, U4 = "Cliente A - Usina 1 - SP", "Cliente B - Usina 2 - RN", "Cliente D - Usina 4 - MG"
FRACTTAL = [_fr(15001, U1, "Preventiva", tarefa="[Grid Co.] - MPM - Cabine"),       # a preventiva por fazer: sai
            _fr(15002, U1, "Preventiva", status="Finalizados", estado="Finalizados"),   # feita: é histórico, fica
            _fr(15003, U1, "Corretiva"),                                                # corretiva: fica
            _fr(15004, U2, "Preventiva", equipe="RN Sul 01"),                           # usina sem FAMA: fica
            _fr(15005, U1, "Preventiva", status="Verificação")]                         # ainda por fazer: sai


def _df(linhas=FRACTTAL):
    return pd.DataFrame(linhas, columns=COLS)


CADASTRO = {10: {"nomes": [U1], "nome": "Usina 1", "cliente": "Cliente A", "equipe": "SP Leste 02"},
            30: {"nomes": [], "nome": "Usina 3", "cliente": "Cliente C", "equipe": "SP Leste 02"},
            40: {"nomes": [U4], "nome": "Usina 4", "cliente": "Cliente D", "equipe": "MG Sul 01"},
            50: {"nomes": ["Cliente E - Usina 5 - BA"], "nome": "Usina 5", "cliente": "Cliente E", "equipe": "Usina 5 local"}}


def _f(i, usina, status="created", tipo="Corrective", prevista=20261006):
    return {"fama_os_id": i, "usina_id": usina, "status": status, "tipo": tipo, "severidade": "Critical",
            "data_id_prevista": prevista, "data_id_criacao": 20260901, "titulo": TITULO_SIGILOSO}


FAMA = [_f(101, 10),
        _f(102, 10, "paused", "Preventive/Predictive", 20260928),
        _f(103, 10, "under execution", "Modules cleaning", 20261008),
        _f(104, None),                                    # sem usina ligada
        _f(105, 10, "closed"),                            # fechada: não é trabalho a programar
        _f(106, 10, prevista=None),                       # sem data prevista
        _f(107, 30),                                      # a usina sem nome no Fracttal
        _f(108, 10, tipo="Something else"),               # tipo fora do catálogo
        _f(109, 40),                                      # usina sem tarefa no cache: a equipe do cadastro
        _f(110, 50)]                                      # equipe do cadastro fora do padrão do PCM


# ── a linha do motor ─────────────────────────────────────────────────────────────────────────────────────────────
def test_a_variavel_esta_declarada_e_desligada_por_padrao():
    assert "NEXUS_FAMA_PROGRAMA" in CONFIG.OPCIONAIS
    assert "NEXUS_FAMA_PROGRAMA=" in (RAIZ / ".env.example").read_text(encoding="utf-8")
    assert FM.ligado({"NEXUS_FAMA_PROGRAMA": "1"}) and FM.ligado({"NEXUS_FAMA_PROGRAMA": " 1 "})
    assert not any(FM.ligado(c) for c in ({}, {"NEXUS_FAMA_PROGRAMA": "0"}, {"NEXUS_FAMA_PROGRAMA": ""}))


def test_as_colunas_do_motor_sao_as_do_arquivo_dele():
    assert FM.colunas_do_motor() == COLS and "OSs ID" in COLS and "Ativo Classificação 2" in COLS


def test_o_motor_nao_aceita_texto_no_numero_da_os():
    """Por que o número da FAMA vai ao motor como um substituto: o `task_key` e a tarefa atômica do motor fazem int() no
    "OSs ID", e "FAMA-101" derrubaria a rodada inteira. A planilha que sai volta a dizer FAMA-101 (`depois_do_motor`)."""
    arvore = ast.parse(MOTOR_V7.read_text(encoding="utf-8"))
    ns: dict = {}
    exec(compile(ast.Module([n for n in arvore.body if isinstance(n, ast.FunctionDef) and n.name == "task_key"], []),
                 "programacao_v7", "exec"), ns)
    with pytest.raises(ValueError):
        ns["task_key"]("FAMA-101", "")
    s = FM.substituto(101)
    assert ns["task_key"](s, "") == f"{int(s)}|" and int(float(str(s).strip())) == int(s)   # as duas contas do motor
    assert FM.fama_do_substituto(s) == 101 and FM.fama_do_substituto(float(s)) == 101
    assert FM.fama_do_substituto("15001") is None and FM.fama_do_substituto("x") is None
    assert int(s) > 10 ** 9                                # longe de qualquer número de OS do Fracttal


def test_aplicar_poe_as_os_da_fama_e_tira_a_preventiva_do_fracttal_das_usinas_da_fama():
    df, rel = FM.aplicar(_df(), FAMA, CADASTRO)
    assert list(df.columns) == COLS
    fr = df[df["OSs ID"].map(lambda v: FM.fama_do_substituto(v) is None)]
    assert sorted(fr["OSs ID"]) == ["15002", "15003", "15004"]                  # a 15001 e a 15005 saíram
    fama = {FM.fama_do_substituto(r["OSs ID"]): r for _, r in df.iterrows() if FM.fama_do_substituto(r["OSs ID"])}
    assert sorted(fama) == [101, 102, 103, 109]
    a = fama[101]
    assert (a["Status"], a["Estado da Tarefa"], a["Tipo de tarefa"]) == ("Em processo", "Não Iniciada", "Corretiva")
    assert (a["Ativo Classificação 1"], a["Ativo Classificação 2"], a["Ativo"]) == (U1, "SP Leste 02", U1)
    assert a["Data Programada"] == pd.Timestamp("2026-10-06") and a["Data de Criação da OS"] == pd.Timestamp("2026-09-01")
    # a duração é a que o motor dá à tarefa sem informação (1,5 h): vazia, a preventiva sem sigla e sem par na Lista de
    # Prioridades sai com NaN e derruba o motor de verdade (prova de 11/11/2026, `test_o_motor_de_verdade_...`)
    assert a["Tarefa -> Duração estimada"] == pd.Timedelta(hours=1.5) and pd.isna(a["Total de Horas"])
    assert a["Tarefa"] == "OS da FAMA 101" and a["Código"] == ""
    assert (fama[102]["Estado da Tarefa"], fama[102]["Tipo de tarefa"]) == ("pausado", "Preventiva")
    assert (fama[103]["Estado da Tarefa"], fama[103]["Tipo de tarefa"]) == ("Em progresso", "Preventiva")
    # a usina sem tarefa no cache: o nome do de-para e a equipe do cadastro
    assert (fama[109]["Ativo Classificação 1"], fama[109]["Ativo Classificação 2"]) == (U4, "MG Sul 01")
    # o título da OS nunca vai para o motor
    assert not df.astype(str).apply(lambda col: col.str.contains(TITULO_SIGILOSO)).any().any()
    assert rel == {"os_fama": 4, "preventivas_tiradas": 2, "usinas": 4, "sem_usina": 1, "sem_previsao": 1,
                   "sem_nome_no_fracttal": 1, "sem_equipe": 1, "tipo_desconhecido": 1, "numero_invalido": 0}
    # a forma das colunas que o motor lê não muda (a data segue data; a duração, duração)
    assert df["Data Programada"].dtype == _df()["Data Programada"].dtype
    assert df["Tarefa -> Duração estimada"].dtype == _df()["Tarefa -> Duração estimada"].dtype
    # aplicar de novo não duplica
    df2, rel2 = FM.aplicar(df, FAMA, CADASTRO)
    assert len(df2) == len(df) and rel2["os_fama"] == 4 and rel2["preventivas_tiradas"] == 0


def test_aplicar_recusa_o_cache_sem_as_colunas_do_motor():
    with pytest.raises(FM.FamaErro):
        FM.aplicar(pd.DataFrame({"OSs ID": ["1"]}), FAMA, CADASTRO)


def test_depois_do_motor_a_planilha_volta_a_dizer_fama(tmp_path):
    p = tmp_path / "sombra.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SP Leste 02"
    ws.append(CAB)
    ws.append(LINHAS[0])
    linha = list(LINHAS[0])
    linha[2] = int(FM.substituto(101))
    ws.append(linha)
    wp = wb.create_sheet("_Pendentes")
    wp.append(["Equipe", "OSs ID", "Código Equipamento", "Tarefa", "Motivo"])
    wp.append(["SP Leste 02", int(FM.substituto(102)), "", "OS da FAMA 102", "Sem capacidade"])
    wb.save(p)
    assert FM.depois_do_motor(p) == {"linhas": 2}
    wb = openpyxl.load_workbook(p)
    oss = {aba.title: [c.value for c in aba[next(c.column_letter for c in aba[1] if c.value == "OSs ID")][1:]]
           for aba in wb.worksheets}
    wb.close()
    assert oss == {"SP Leste 02": [15020, "FAMA-101"], "_Pendentes": ["FAMA-102"]}
    antes = p.read_bytes()
    assert FM.depois_do_motor(p) == {"linhas": 0} and p.read_bytes() == antes         # nada a trocar: não regrava


# ── a rodada ─────────────────────────────────────────────────────────────────────────────────────────────────────
def _motor_e_leitor(tmp_path, cache_deve_existir: bool):
    """Uma pasta de motor falsa: o `programacao_v7.py` e o `fonte_bd_api.py` (a leitura do Fracttal que o motor faz no
    começo). O leitor falso grava o cache com as linhas do Fracttal de mentira; o motor falso confere o cache que recebeu
    e escreve a planilha com uma linha da 15003 e uma da OS da FAMA que estiver no cache."""
    d = tmp_path / ("motor_ligado" if cache_deve_existir else "motor_desligado")
    d.mkdir()
    linhas = [{k: (str(v) if isinstance(v, (pd.Timestamp, pd.Timedelta)) else v) for k, v in l.items()} for l in FRACTTAL]
    (d / "fonte_bd_api.py").write_text(textwrap.dedent(f"""
        import json, os, pickle
        import pandas as pd
        def df_semanal():
            linhas = json.loads({json.dumps(json.dumps(linhas))})
            df = pd.DataFrame(linhas, columns=json.loads({json.dumps(json.dumps(COLS))}))
            for c in ("Data Programada",):
                df[c] = pd.to_datetime(df[c])
            for c in ("Tarefa -> Duração estimada", "Total de Horas"):
                df[c] = pd.to_timedelta(df[c])
            with open(os.path.join(os.environ["PCM_PROG_DIR"], ".cache_semanal_api.pkl"), "wb") as f:
                pickle.dump({{"v": 1, "df": df}}, f)
            print("leitura falsa do Fracttal")
            return df
    """), encoding="utf-8")
    (d / "programacao_v7.py").write_text(textwrap.dedent(f"""
        import json, os, pickle
        import openpyxl
        base = os.environ["PCM_PROG_DIR"]
        cache = os.path.join(base, ".cache_semanal_api.pkl")
        assert not any(k.startswith("NEXUS_") for k in os.environ)
        oss = []
        if {cache_deve_existir}:
            assert int(os.environ["PROG_API_TTL_MIN"]) >= 60, "o cache com as OS da FAMA venceria antes do motor"
            df = pickle.load(open(cache, "rb"))["df"]
            oss = list(df["OSs ID"])
            assert "15001" not in oss and "15005" not in oss and "15004" in oss
            assert {TITULO_SIGILOSO!r} not in df.to_string()
        else:
            assert not os.path.exists(cache), "com a FAMA desligada o Nexus não mexe no Fracttal do motor"
            assert "PROG_API_TTL_MIN" not in os.environ
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "SP Leste 02"
        ws.append(json.loads({json.dumps(json.dumps(CAB))}))
        for l in json.loads({json.dumps(json.dumps(LINHAS))}):
            ws.append(l)
        for o in oss:
            if int(o) > 10 ** 9:
                ws.append(["SP Leste 02", "Segunda-feira (05/10)", int(o), "Usina", "", "Corretiva", "OS da FAMA",
                           "Não", 1, "07:30", "09:00", 1.5, 12])
        wp = wb.create_sheet("_Pendentes")
        wp.append(["Equipe", "OSs ID", "Código Equipamento", "Tarefa", "Motivo"])
        wb.save(os.environ["PCM_OUTPUT"])
        print("OK")
    """), encoding="utf-8")
    return d / "programacao_v7.py"


def _com_fama(config, **extra):
    return dict(config, NEXUS_FAMA_LINHAS_TESTE=FAMA, NEXUS_FAMA_CADASTRO_TESTE=CADASTRO, **extra)


def test_com_a_variavel_desligada_a_rodada_e_a_de_hoje(config, tmp_path, monkeypatch):
    def nao(*a, **k):
        raise AssertionError("o adaptador da FAMA rodou com a variável desligada")
    for nome in ("entrada", "antes_do_motor", "aplicar_no_cache", "depois_do_motor"):
        monkeypatch.setattr(FM, nome, nao)
    cfg = _com_fama(config, NEXUS_PCM_MOTOR=str(_motor_e_leitor(tmp_path, cache_deve_existir=False)))
    st = G.aguardar(cfg, G.iniciar(cfg, "2026-W41")["id"], 60)
    assert st["estado"] == "ok", st
    assert "fama" not in st and st["resumo"]["linhas"] == 2
    log = G.log(cfg, st["id"])
    assert "FAMA" not in log and "leitura falsa do Fracttal" not in log       # a leitura antes do motor não rodou


def test_com_a_variavel_ligada_as_os_da_fama_entram_e_a_preventiva_do_fracttal_sai(config, tmp_path):
    cfg = _com_fama(config, NEXUS_FAMA_PROGRAMA="1",
                    NEXUS_PCM_MOTOR=str(_motor_e_leitor(tmp_path, cache_deve_existir=True)))
    st = G.aguardar(cfg, G.iniciar(cfg, "2026-W41")["id"], 60)
    assert st["estado"] == "ok", st
    assert st["fama"]["os_fama"] == 4 and st["fama"]["preventivas_tiradas"] == 2 and st["fama"]["planilha"]["linhas"] == 4
    log = G.log(cfg, st["id"])
    assert "leitura falsa do Fracttal" in log and "[FAMA] 4 OS da FAMA" in log and TITULO_SIGILOSO not in log
    planilha = G.planilha(cfg, st["id"])
    wb = openpyxl.load_workbook(planilha, read_only=True)
    oss = [r[2] for r in wb["SP Leste 02"].iter_rows(min_row=2, values_only=True)]
    wb.close()
    assert oss == [15020, 15021, "FAMA-101", "FAMA-102", "FAMA-103", "FAMA-109"]
    assert st["resumo"]["linhas"] == 6


def test_ligada_sem_os_da_fama_a_rodada_nao_sai(config):
    cfg = dict(config, NEXUS_FAMA_PROGRAMA="1")
    with pytest.raises(G.NaoPronto) as erro:
        G.iniciar(cfg, "2026-W41")
    assert "FAMA" in str(erro.value)
    assert not list((G.pasta_trabalho(cfg) / "geracoes").iterdir())        # a pasta da rodada não fica para trás


def _foto_de_verdade(origem):
    """A foto com o cache de verdade (a forma que o motor grava) e a idade de uma foto de verdade."""
    with open(origem / ".cache_semanal_api.pkl", "wb") as f:
        pickle.dump({"v": 1, "df": _df()}, f)
    velho = time.time() - 3 * 3600
    os.utime(origem / ".cache_semanal_api.pkl", (velho, velho))
    return origem


def _motor_da_foto_com_fama(tmp_path):
    m = tmp_path / "motor_foto_fama.py"
    m.write_text(textwrap.dedent(f"""
        import json, os, pickle, time
        import openpyxl
        base = os.environ["PCM_PROG_DIR"]
        assert os.environ["FRACTTAL_CLIENT_ID"] == ""
        foto = os.path.join(base, ".cache_semanal_api.pkl")
        assert time.time() - os.path.getmtime(foto) > 3600, "a foto perdeu a idade"
        oss = list(pickle.load(open(foto, "rb"))["df"]["OSs ID"])
        assert "15001" not in oss and sum(1 for o in oss if int(o) > 10 ** 9) == 4
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "SP Leste 02"
        ws.append(json.loads({json.dumps(json.dumps(CAB))}))
        for l in json.loads({json.dumps(json.dumps(LINHAS))}):
            ws.append(l)
        wb.save(os.environ["PCM_OUTPUT"])
    """), encoding="utf-8")
    return m


def test_foto_com_a_variavel_ligada(config, origem, tmp_path):
    _foto_de_verdade(origem)
    antes = (origem / ".cache_semanal_api.pkl").read_bytes()
    cfg = _com_fama(config, NEXUS_FAMA_PROGRAMA="1", NEXUS_PCM_MOTOR=str(_motor_da_foto_com_fama(tmp_path)))
    st = G.gerar_com_foto(cfg, "2026-W41")
    assert st["estado"] == "ok", st
    assert st["fama"]["os_fama"] == 4 and st["foto"]["intacta"]            # intacta = a foto com as OS da FAMA
    assert (origem / ".cache_semanal_api.pkl").read_bytes() == antes        # a pasta do PCM só foi lida


def test_o_motor_de_verdade_programa_as_os_da_fama(config, origem):
    """A prova que achou a duração vazia (11/11/2026): o motor DE VERDADE (a cópia do PCM), com a foto de mentira e sem
    Fracttal (credencial vazia, endereço numa porta fechada), programa as OS da FAMA, tira a preventiva por fazer do
    Fracttal da usina da FAMA e a planilha diz FAMA-<id>. Com a duração vazia, a preventiva da FAMA quebrava o motor
    (NaN no `alloc_diurno`). O motor gera sempre a semana da próxima segunda (o `--semana` da linha de comando não pega
    nele): as datas saem dela, e o teste não envelhece."""
    from datetime import timedelta
    from nexus.pcm import historico_banco as HB
    semana = G.semana_padrao()
    seg = HB.segunda(semana)
    fr = [dict(l, **{"Data Programada": pd.Timestamp(seg) + pd.Timedelta(hours=8)}) for l in FRACTTAL]
    with open(origem / FM.CACHE, "wb") as f:
        pickle.dump({"v": 1, "df": _df(fr)}, f)
    dia = lambda n: int((seg + timedelta(days=n)).strftime("%Y%m%d"))      # noqa: E731
    fama = [_f(201, 10, prevista=dia(1)), _f(202, 10, "paused", "Preventive/Predictive", dia(2)), _f(203, 40, prevista=dia(3))]
    cfg = dict(config, NEXUS_PCM_MOTOR=str(G.MOTOR), NEXUS_FAMA_PROGRAMA="1", NEXUS_FAMA_LINHAS_TESTE=fama,
               NEXUS_FAMA_CADASTRO_TESTE=CADASTRO)
    st = G.gerar_com_foto(cfg, semana)
    assert st["estado"] == "ok", G.log(cfg, st["id"], 30)
    assert st["foto"]["intacta"] and st["fama"]["os_fama"] == 3 and st["fama"]["preventivas_tiradas"] == 2
    wb = openpyxl.load_workbook(G.pasta_trabalho(cfg) / "geracoes" / st["id"] / "saida" / "sombra.xlsx", read_only=True)
    oss = {}
    for aba in wb.worksheets:
        it = aba.iter_rows(values_only=True)
        cab = list(next(it, None) or [])
        if "OSs ID" in cab:
            for r in it:
                oss[str(r[cab.index("OSs ID")])] = aba.title
    wb.close()
    assert {"FAMA-201", "FAMA-202", "FAMA-203", "15003", "15004"} <= set(oss)
    assert not {"15001", "15005"} & set(oss) and not any(o.startswith("9000") for o in oss)
    assert (oss["FAMA-201"], oss["FAMA-203"]) == ("SP Leste 02", "MG Sul 01")      # a equipe da usina; a do cadastro
    assert TITULO_SIGILOSO not in G.log(cfg, st["id"])


def test_foto_com_a_variavel_desligada_fica_como_era(config, origem, tmp_path):
    from test_pcm_geracao import motor_da_foto
    _foto_de_verdade(origem)
    cfg = _com_fama(config, NEXUS_PCM_MOTOR=str(motor_da_foto(tmp_path)))
    st = G.gerar_com_foto(cfg, "2026-W41")
    assert st["estado"] == "ok" and st["foto"]["intacta"] and "fama" not in st
    rodada = G.pasta_trabalho(cfg) / "geracoes" / st["id"]
    assert (rodada / ".cache_semanal_api.pkl").read_bytes() == (origem / ".cache_semanal_api.pkl").read_bytes()
