"""O pacote `chamado_garantia` 1.3.0: a OS de ACOMPANHAMENTO do chamado (a administrativa do time de chamados) sai do pacote,
para o App de Campo e o OS Creator seguirem um padrão só (desenho de 08/11/2026, "segue!" do Levi).

O que se trava aqui:
- `mapa_chaves` é o `_mapa_chaves` do servidor do App (v332), e a nota com as respostas sai IGUAL à do
  `_acompanhamento_se_chamado` de hoje (a referência abaixo é a cópia daquele laço);
- nascida junto com a Inspeção (`respostas=None`), a nota diz "aguardando a inspeção" e o `nota_aguardando` a reconhece;
- a 1ª linha e a subtarefa do ticket são as que o quadro do Acompanhamento de chamados lê (`acomp_web`).
Ativos, códigos e respostas de mentira: o repositório é público."""
import sys
from pathlib import Path

from nexus.torres.oscreator import ponte

_RAIZ = str(Path(ponte.RAIZ_CLONE).parent)
if _RAIZ not in sys.path:
    sys.path.append(_RAIZ)                  # append: a raiz do clone tem um app.py que não pode sombrear o do Nexus
if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import chamado_garantia as cg  # noqa: E402
from chamado_garantia import spec  # noqa: E402

TIPO = "Inversor"
EVENTO = "2026-11-03T12:00:00+00:00"


def _marca_com_chaves():
    """Uma marca do inversor cujo bloco tem campo com chave (é o caso que liga resposta a campo do fabricante)."""
    for m in spec.marcas_para(TIPO):
        if any(s.get("chave") for s in spec.POR_FABRICANTE.get(m, [])):
            return m
    raise AssertionError("nenhuma marca do inversor com chave no spec")


MARCA = _marca_com_chaves()
INSPECAO = {"folio": "19234", "code": "TST-UFV100-INVR1.1", "nome_ativo": "Inversor 1.1", "tipo": TIPO, "os_pai": "19100",
            "event_date": EVENTO}


def _mapa_do_app(tipo_ativo, marca):
    """A referência: o `_mapa_chaves` do servidor do App (v332, function_app.py), copiado."""
    grupo = spec.grupo_de(tipo_ativo)
    blocos = (spec.BASE + spec.POR_TIPO.get(grupo, []) + spec.POR_FABRICANTE.get((marca or "").strip(), []))
    out, vistos = {}, set()
    for s in blocos:
        if s.get("so_para") and grupo not in s["so_para"]:
            continue
        k = s["desc"].strip().lower()
        if k in vistos:
            continue
        vistos.add(k)
        out[k] = s.get("chave") or ""
    return out


def _nota_do_app(checklist, itens, marca, tipo, inspecao):
    """A referência: o laço e a nota do `_acompanhamento_se_chamado` do App (v332), copiados."""
    mapa = _mapa_do_app(tipo, marca)
    trad = {1: "Aprovado", 2: "Alerta", 3: "Falhou", "1": "Aprovado", "2": "Alerta", "3": "Falhou"}
    com_chave, extras = [], []
    for c in checklist:
        desc = str(c.get("desc") or "").strip()
        v = itens.get(c.get("id"))
        if v in (None, "", False):
            continue
        if c.get("tipo") == "verif":
            v = trad.get(v, v)
        elif v is True:
            v = "Sim"
        ch = mapa.get(desc.lower())
        (com_chave if ch else extras).append((ch or desc, str(v)[:300]))
    der = cg.derivados({"tipo": tipo}, inspecao["event_date"])
    linhas = ["[CHAMADO] Acompanhamento — %s · %s" % (marca or "marca a confirmar", tipo),
              "OS de campo: %s · Inspeção: %s · Ativo: %s" % (inspecao["os_pai"] or "-", inspecao["folio"], inspecao["code"]),
              "Data da falha: %s · Menos de 7 dias: %s" % (der.get("data_falha", "-"), der.get("menos_7d", "-")), ""]
    if com_chave:
        linhas.append("Campos do formulário do fabricante (coletados na inspeção):")
        linhas += ["  %s: %s" % kv for kv in com_chave]
    if extras:
        linhas.append("Demais respostas:")
        linhas += ["  %s: %s" % kv for kv in extras]
    return "\n".join(linhas)[:3800], len(com_chave), len(extras)


def _checklist():
    """As subtarefas da Inspeção (as do pacote) como o App manda no fechamento, com respostas variadas."""
    subs = cg.subtarefas(TIPO, MARCA)
    checklist, itens = [], {}
    for n, s in enumerate(subs):
        tipo = {4: "verif"}.get(s["id_task_form_item_type"], "texto")
        checklist.append({"id": "f%d" % n, "desc": s["description"], "tipo": tipo})
        itens["f%d" % n] = ("2" if tipo == "verif" else ("" if n % 5 == 4 else ("resposta %d" % n)))
    checklist.append({"id": "x1", "desc": "Pergunta fora do modelo", "tipo": "texto"})
    itens["x1"] = True
    checklist.append({"id": "x2", "desc": "Outra sem resposta", "tipo": "texto"})
    itens["x2"] = False
    return checklist, itens


def test_versao_e_o_que_o_pacote_expoe():
    assert cg.__version__ == "1.3.0"
    for nome in ("montar_acompanhamento", "mapa_chaves", "respostas_de", "nota_aguardando", "AGUARDANDO_INSPECAO",
                 "SUBTAREFA_TICKET"):
        assert nome in cg.__all__ and hasattr(cg, nome), nome
    assert cg.AGUARDANDO_INSPECAO == "aguardando a inspeção"


def test_mapa_chaves_e_o_do_app():
    for tipo in ("Inversor", "Estrutura Trackers", "NCU"):
        for marca in [""] + list(spec.marcas_para(tipo)):
            assert cg.mapa_chaves(tipo, marca) == _mapa_do_app(tipo, marca), (tipo, marca)


def test_a_nota_com_as_respostas_sai_igual_a_do_app():
    checklist, itens = _checklist()
    esperada, n_ch, n_ex = _nota_do_app(checklist, itens, MARCA, TIPO, INSPECAO)
    d = cg.montar_acompanhamento(INSPECAO, MARCA, cg.respostas_de(checklist, itens))
    assert d["nota"] == esperada and (d["campos"], d["extras"]) == (n_ch, n_ex) and n_ch > 0 and n_ex > 0
    assert d["aguardando"] is False and not cg.nota_aguardando(d["nota"])
    assert "  Pergunta fora do modelo: Sim" in d["nota"] and "Outra sem resposta" not in d["nota"]
    assert "Aprovado" not in d["nota"] or "Alerta" in d["nota"]          # a Verificação "2" vira Alerta
    # quem já traduziu para a chave do formulário recebe a mesma nota
    mapa = cg.mapa_chaves(TIPO, MARCA)
    pelas_chaves = [((mapa.get(k.lower()) or k), v) for k, v in cg.respostas_de(checklist, itens)]
    assert cg.montar_acompanhamento(INSPECAO, MARCA, pelas_chaves)["nota"] == esperada


def test_nascida_com_a_inspecao_diz_aguardando():
    d = cg.montar_acompanhamento(INSPECAO, MARCA)
    linhas = d["nota"].split("\n")
    assert linhas[0] == "[CHAMADO] Acompanhamento — %s · %s" % (MARCA, TIPO)
    assert linhas[1] == "OS de campo: 19100 · Inspeção: 19234 · Ativo: TST-UFV100-INVR1.1"
    assert linhas[2].startswith("Data da falha: 03/11/2026 ") and linhas[3] == ""
    assert linhas[4] == "Campos do formulário do fabricante: aguardando a inspeção" and len(linhas) == 5
    assert d["aguardando"] is True and cg.nota_aguardando(d["nota"]) and (d["campos"], d["extras"]) == (0, 0)
    assert d["titulo"] == "[Inversor 1.1] - Acompanhamento de chamado %s" % MARCA
    assert (d["tipo_tarefa"], d["etiqueta"]) == ("Administrativa", "CHAMADOS")
    assert d["subtarefas"] == [{"description": "Nº do ticket / protocolo aberto no fabricante", "id_task_form_item_type": 1,
                                "is_required": False, "attachments_required": False}]


def test_sem_marca_sem_pai_e_sem_tipo():
    """Marca vazia vira "marca a confirmar" (como no App); sem OS pai, "-"; sem tipo, o do código do ativo."""
    insp = dict(INSPECAO, os_pai="", tipo="", nome_ativo="", code="TST-UFV100-ETKR1.100")
    d = cg.montar_acompanhamento(insp, "")
    assert d["nota"].startswith("[CHAMADO] Acompanhamento — marca a confirmar · %s\nOS de campo: - · Inspeção: 19234"
                                % cg.tipo_do_ativo("TST-UFV100-ETKR1.100"))
    assert d["titulo"] == "[TST-UFV100-ETKR1.100] - Acompanhamento de chamado"


def test_nota_longa_e_cortada_e_resposta_vazia_fica_fora():
    respostas = [("Pergunta %d" % n, "x" * 400) for n in range(30)] + [("Vazia", ""), ("Nada", None)]
    d = cg.montar_acompanhamento(INSPECAO, MARCA, respostas)
    assert len(d["nota"]) == 3800 and "Vazia" not in d["nota"] and "Nada" not in d["nota"]
    assert "x" * 301 not in d["nota"]                                     # cada resposta até 300, como no App


def test_o_quadro_do_acompanhamento_reconhece_a_os():
    """A 1ª linha e a subtarefa são as que o `acomp_web` lê: a marca da nota e o ticket pelo texto."""
    from os_web import acomp_web
    d = cg.montar_acompanhamento(INSPECAO, MARCA)
    assert d["nota"].startswith(acomp_web.MARCA_NOTA)
    item = acomp_web.item_do_ticket([{"descricao": d["subtarefas"][0]["description"], "resposta": ""}])
    assert item is not None
