"""os_registro.py: o registro enxuto de uma OS da lista central e quem o monta (31/10/2026, etapa 3 do canto central do OS
Creator).

Saiu do `os_central.py` na rodada 1 da revisão da 3.1+3.2 (Ruling AY: só mudança de lugar; o arquivo passava de 1.200 linhas e
a 3.3 vai mexer nele). A lista guarda e entrega (`os_central.py`); a cópia em disco é do `os_disco.py`; daqui saem:
- o `RegistroOS`: uma tupla com nome, só leitura, a mesma para todas as telas; as cinco datas de cada OS juntas em 20 bytes
  (`datas`, segundos desde 2000, UTC como o Fracttal grava), lidas em ISO pelas propriedades; `linha(local)` dá o dicionário
  novo no formato do `api.list_minhas_os`, com o cliente, a usina e o tipo tirados do catálogo de ativos na hora;
- quem o monta: das linhas do REST `work_orders` (uma por TAREFA, juntadas pelo `id_work_order`: `registros_do_rest`), da
  leitura ao vivo que o card faz (`registro_do_card`) e da linha do Histórico (`registro_da_linha`);
- os textos de pouca variedade num objeto só (`_TEXTOS`, que a noite da lista refaz) e o juntar de uma leitura (`_Juntar`).
As regras de cada campo (o que o REST traz e o que fica vazio) estão no README do OS Creator, "A lista central de OS e o leitor
em faixas".
"""
from __future__ import annotations

import struct
import sys
import time
import unicodedata
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import NamedTuple

DESCRICAO_MAX = 90              # como o `api._shape_wo_row` entrega ao Histórico
ATIVO_MAX = 60
# a nota com o bloco do chamado (o Garantias a lê); a OS sem ele não guarda nota. Era 4.000 até a rodada 1 da 3.3 (Ruling BR):
# o "parado há N dias" do quadro sai das linhas do histórico da retroativa, que ficam no FIM da nota, e a de ~10 mil caracteres
# perdia o fim sem aviso. A que ainda passa do teto fica marcada (`RegistroOS.nota_cortada`), e o quadro vai ao vivo
NOTA_MAX = 16000
STATUS = {1: "Em Processo", 2: "Em Verificação", 3: "Concluída", 4: "Cancelada"}     # o `api.WO_STATUS` (um teste confere)
# as marcas do bloco do chamado na nota da OS: a do `api._CHAMADO_MK` (o bloco do chamado) e a do `acomp_web.MARCA_NOTA` (a OS
# de acompanhamento do Garantias); um teste confere que são as mesmas
MARCAS_DA_NOTA = ("━━━ CHAMADO ━━━", "[CHAMADO] Acompanhamento")
_FIM_DA_TAREFA = ("final_date", "date_end", "end_date", "real_final_date", "finished_date", "date_finished", "closing_date")

# O QUE A LISTA LÊ DE CADA LINHA DO REST (Ruling AV, rodada 1 da revisão da 3.1+3.2): a noite de 365 dias junta de 75 a 90 mil
# tarefas antes do `receber`, e a linha do `work_orders` traz ~60 campos (custos, grupos, a nota da tarefa, datas, ids). O
# leitor corta cada página NA HORA (`enxuta`, o `projetar` do `tarefas_os._paginas`), como o leitor dos ativos (`CAMPOS_REST` e
# `_enxuto` de lá): só o que `registros_do_rest` e as paradas das faixas leem. As etiquetas ficam só com o id e o nome, e a nota
# (`task_note`, `note`) só quando traz o bloco do chamado. O registro montado da linha cortada é o MESMO da linha inteira (um
# teste confere). O fato do `tarefas_os` segue com a linha inteira: sem o `projetar`, nada muda lá.
# MEDIDO (36 mil OS sintéticas, ~99 por dia, 2,3 tarefas por OS, a linha com 67 campos: 2.371 bytes em JSON, ~4,3 KB na
# memória): o pico da noite de 365 dias era de 387 MB com as linhas inteiras e 216 MB só com os campos; sem os valores vazios
# (ausente e None são o mesmo para quem lê, que lê por `.get`: o dicionário cai para a classe de tamanho de baixo) e com os
# textos de pouca variedade num objeto só por valor (`sys.intern`; o JSON dá um por linha), ver o README.
CAMPOS_REST = ("id_work_order", "id_work_orders_tasks", "wo_folio", "id_status_work_order", "description",
               "items_log_description", "code", "tasks_log_task_type_main", "creation_date", "date_maintenance",
               "initial_date", "event_date", "wo_final_date", "created_by", "code_create_by", "id_created_by",
               "user_assigned", "personnel_description", "id_personnel", "id_assigned_user", "trigger_description",
               "labels", "task_note", "note") + _FIM_DA_TAREFA
_CAMPOS_DA_ETIQUETA = ("id", "id_label", "description", "name")
# os de pouca variedade (o status, o tipo, as ~150 pessoas, os gatilhos; e o nome da etiqueta): um objeto só por valor
_POUCA_VARIEDADE = frozenset(("id_status_work_order", "tasks_log_task_type_main", "created_by", "code_create_by",
                              "user_assigned", "personnel_description", "trigger_description"))

# AS DATAS DE UMA OS EM 20 BYTES: cinco inteiros de 4 bytes, os segundos desde 2000-01-01 (UTC, como o Fracttal grava; até 2068),
# 0 = vazia. Como texto ("2026-10-31T10:00:00") eram ~60 bytes cada, ~6,7 MB das 36 mil OS sintéticas
_DATAS = ("data", "event_date", "data_fim", "programada", "inicio")
_PACOTE = struct.Struct("<5i")
_I32 = struct.Struct("<i")
_EPOCA0 = 946684800


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def _data(v) -> str:
    """A data como o Fracttal grava, cortada em 19 ("2026-10-31T10:00:00"); vazio para None, "" e "None"."""
    s = _txt(v)
    return "" if not s or s.lower() == "none" else s[:19]


def _seg(v) -> int:
    """A data (ISO, com ou sem a hora) em segundos desde 2000 (UTC); 0 sem data ou fora do que cabe em 4 bytes."""
    s = _data(v)
    if not s:
        return 0
    try:
        n = int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()) - _EPOCA0
    except ValueError:
        return 0
    return n if -2**31 < n < 2**31 else 0


def _iso_seg(n: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(n + _EPOCA0)) if n else ""


def _pacote(datas: dict) -> bytes:
    return _PACOTE.pack(*(_seg(datas.get(k)) for k in _DATAS))


def _campo_data(i: int):
    def ler(self) -> str:
        return _iso_seg(_I32.unpack_from(self.datas, 4 * i)[0])
    ler.__doc__ = "A data `%s` da OS, em ISO (vazia: \"\")." % _DATAS[i]
    return property(ler)


def _s(r, i: int = 0) -> int:
    """A data `_DATAS[i]` de um registro em segundos (0 = vazia): a conta das faixas e dos filtros, sem passar por texto."""
    return _I32.unpack_from(r.datas, 4 * i)[0]


# ── o registro ─────────────────────────────────────────────────────────────────────────────────────────────────────────
class RegistroOS(NamedTuple):
    """Uma OS da lista central: uma tupla com nome (só leitura). `status` (o rótulo do `status_id`), `code` (o último dos
    `codigos`, como o `api._extrai_code`) e as datas (`data`, a criação; `event_date`, `data_fim`, `programada`, `inicio`, em
    ISO como o Fracttal grava, guardadas juntas em `datas`) se leem como campos; `get`, `r["campo"]` e o atributo funcionam
    (o template do Histórico usa os três). Os campos são os que as telas mostram; os que o REST não traz ficam vazios e o card
    lê ao vivo (README do OS Creator, "A lista central de OS"). Para trocar um campo: `com(...)`, que devolve outro."""
    id: int
    folio: str
    descricao: str
    ativo: str
    codigos: tuple
    criado_por: str
    cod_criador: str
    id_criador: int | None
    etiquetas: tuple            # ((id, nome), ...)
    atribuido_a: str
    id_atribuido: int | None
    equipe: str
    datas: bytes                # as cinco datas (`_DATAS`), 4 bytes cada
    gatilho: str
    status_id: int | None
    tipo_tarefa: str
    note: str

    data = _campo_data(0)
    event_date = _campo_data(1)
    data_fim = _campo_data(2)
    programada = _campo_data(3)
    inicio = _campo_data(4)

    @property
    def status(self) -> str:
        if self.status_id is None:
            return ""
        return STATUS.get(self.status_id) or "Status %s" % self.status_id

    @property
    def code(self) -> str:
        return self.codigos[-1] if self.codigos else ""

    @property
    def nota_cortada(self) -> bool:
        """A nota do chamado passou do teto e perdeu o fim (o histórico mais novo da retroativa): quem a lê para contar dias
        não a usa como inteira. A de exatamente `NOTA_MAX` caracteres também conta (o lado seguro)."""
        return len(self.note) >= NOTA_MAX

    def get(self, chave, padrao=None):
        return getattr(self, chave) if chave in _LEGIVEIS else padrao

    def __getitem__(self, chave):
        if isinstance(chave, str):
            if chave in _LEGIVEIS:
                return getattr(self, chave)
            raise KeyError(chave)
        return tuple.__getitem__(self, chave)

    def com(self, **mudancas) -> "RegistroOS":
        """Uma cópia com os campos trocados; as datas pelos nomes delas, em ISO."""
        if any(k in mudancas for k in _DATAS):
            v = list(_PACOTE.unpack(self.datas))
            for i, k in enumerate(_DATAS):
                if k in mudancas:
                    v[i] = _seg(mudancas.pop(k))
            mudancas["datas"] = _PACOTE.pack(*v)
        return self._replace(**mudancas)

    def linha(self, local: Mapping | None = None) -> dict:
        """A linha da tela, um dicionário NOVO no formato do `api.list_minhas_os` (o `_shape_wo_row` com o meta das tarefas):
        quem a recebe pode mexer à vontade. `local`: {código do ativo: (cliente, usina curta, tipo)}, o
        `ativos_central.atual().local_por_codigo` (sem ele, "—", como o `_shape_wo_row` sem catálogo)."""
        code = self.code
        cli, usi, tipo = (local.get(code) if local else None) or ("", "", "")
        return {"id": self.id, "folio": self.folio, "cliente": cli or "—", "usina": usi or "—", "ativo": self.ativo,
                "tipo": tipo or "—", "descricao": self.descricao or "—", "code": code, "codigos": list(self.codigos),
                "criado_por": self.criado_por, "etiquetas": [{"id": i, "nome": n} for i, n in self.etiquetas],
                "atribuido_a": self.atribuido_a, "id_atribuido": self.id_atribuido, "data": self.data,
                "event_date": self.event_date, "data_fim": self.data_fim, "programada": self.programada,
                "inicio": self.inicio, "equipe": self.equipe, "gatilho": self.gatilho, "status_id": self.status_id,
                "status": self.status, "tipo_tarefa": self.tipo_tarefa, "note": self.note}


_LEGIVEIS = frozenset(RegistroOS._fields) | frozenset(_DATAS) | {"status", "code", "nota_cortada"}
# um objeto só para os textos de POUCA variedade, que se repetem em milhares de OS (as ~150 pessoas, os tipos, os gatilhos,
# as etiquetas): é uma tabela pequena e guardada. Os de muita variedade que se repetem (o código e o nome do ativo, a descrição
# de um plano) se juntam só dentro de cada leitura (`_Juntar`): guardar a tabela deles custava mais que a repetição (medido:
# a tabela de tudo, ~195 mil entradas, eram 10 MB das 36 mil OS sintéticas)
_TEXTOS: dict = {}


def _p(v):
    return _TEXTOS.setdefault(v, v) if v else v


class _Juntar(dict):
    """O mesmo objeto para o mesmo valor dentro de UMA leitura (jogado fora no fim dela)."""

    def __call__(self, v):
        return self.setdefault(v, v) if v else v


def _int(v):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError, OverflowError):
        return None


def _norm(v) -> str:
    """Sem acento, minúsculo e com um espaço só: o nome do Fracttal vem com espaço a mais ("Nome Sobrenome ")."""
    s = unicodedata.normalize("NFKD", str(v or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def _cod(v) -> str:
    return _txt(v).upper()


def _distintos(valores) -> list:
    out = []
    for v in valores:
        if v and v not in out:
            out.append(v)
    return out


def _codigos(itens, linhas, j) -> tuple:
    """Os códigos dos ativos da OS, na ordem: o que vem entre chaves no nome de cada item ("... { CAL-GAM100-INVR1.1 }"), como
    o `api._extrai_codigos`; sem chaves, o `code` da linha."""
    out = []
    for it in itens:
        for pedaco in it.split("{")[1:]:
            c = pedaco.split("}")[0].strip()
            if c and c not in out:
                out.append(c)
    if not any("{" in it for it in itens):
        for w in linhas:
            c = _txt(w.get("code"))
            if c and c not in out:
                out.append(c)
    return j(tuple(j(c) for c in out))


def _gatilho(linhas) -> str:
    """O gatilho da OS em português (`api.decodifica_gatilho`), a agendada vencendo a "não agendada", como o meta das
    tarefas. O REST pode não trazer o `trigger_description` (a 1ª noite diz, nos campos medidos do estado): fica vazio."""
    brutos = _distintos(_txt(w.get("trigger_description")) for w in linhas)
    if not brutos:
        return ""
    melhor = next((g for g in brutos if g != "NO_SCHEDULE_TASK"), brutos[0])
    import api                                                       # aqui dentro: o api é pesado, e só o gatilho o usa
    return _p(api.decodifica_gatilho(melhor))


def _com_o_bloco(t) -> bool:
    return any(m in t for m in MARCAS_DA_NOTA)


def _nota(textos) -> str:
    """A nota da OS só com o bloco do chamado (o Garantias lê a OS de acompanhamento por ele): só os textos (a nota da OS e a
    de cada tarefa) que trazem a marca, juntos. O texto sem a marca não é mostrado pela lista, e guardá-lo seria texto à toa na
    memória, mesmo ao lado de um com a marca (rodada 1 da revisão: assim a linha cortada pela página, `enxuta`, monta a mesma
    nota; e o bloco do chamado não ganha linhas de outra nota que o `api.parse_bloco_chamado` leria como campo)."""
    return "\n".join(_distintos(t for t in (_txt(x) for x in textos) if t.lower() != "none" and _com_o_bloco(t)))[:NOTA_MAX]


def _junto(v):
    return sys.intern(v) if type(v) is str else v


def enxuta(w):
    """A linha do REST só com o que a lista lê (`CAMPOS_REST`), sem os valores vazios (quem lê, lê por `.get`: ausente e
    None são o mesmo) e com os textos de pouca variedade num objeto só por valor: as etiquetas só com o id e o nome, a nota só
    com o bloco do chamado. É o `projetar` de cada página do leitor (Ruling AV). O que não é dicionário passa como veio (quem
    lê decide)."""
    if not isinstance(w, dict):
        return w
    out = {}
    for k in CAMPOS_REST:
        v = w.get(k)
        if v is None:
            continue
        if k == "labels":
            if not isinstance(v, (list, tuple)):
                continue                                             # o `_do_rest` não tira etiqueta do que não é lista
            v = [{c: _junto(e[c]) for c in _CAMPOS_DA_ETIQUETA if e.get(c) is not None} for e in v if isinstance(e, dict)]
            if not v:
                continue
        elif k in ("task_note", "note"):
            if not _com_o_bloco(str(v)):
                continue
        elif k in _POUCA_VARIEDADE:
            v = _junto(v)
        out[k] = v
    return out


def _do_rest(wid: int, linhas: list, j) -> RegistroOS:
    """As tarefas de UMA OS (as linhas do REST, já sem repetição e na ordem do id da tarefa) no registro enxuto."""
    w0 = linhas[0]
    itens = _distintos(_txt(w.get("items_log_description")) for w in linhas)
    datas = {k: sorted(d for d in (_data(w.get(k)) for w in linhas) if d)
             for k in ("date_maintenance", "event_date", "initial_date")}
    fins = sorted(d for w in linhas for d in (_data(w.get(k)) for k in _FIM_DA_TAREFA) if d)
    etiquetas, vistas = [], set()
    for w in linhas:
        for e in w.get("labels") or ():
            if not isinstance(e, dict):
                continue
            nome = _txt(e.get("description") or e.get("name"))
            i = _int(e.get("id") if e.get("id") is not None else e.get("id_label"))
            if nome and (i, nome) not in vistas:
                vistas.add((i, nome))
                etiquetas.append(_p((_p(i), _p(nome))))
    id_resp = w0.get("id_personnel") if w0.get("id_personnel") is not None else w0.get("id_assigned_user")
    programada = datas["date_maintenance"][0] if datas["date_maintenance"] else ""
    return RegistroOS(
        id=wid, folio=_txt(w0.get("wo_folio")),
        descricao=j(", ".join(_distintos(_txt(w.get("description")) for w in linhas))[:DESCRICAO_MAX]),
        ativo=j(", ".join(itens).split("{")[0].strip()[:ATIVO_MAX]), codigos=_codigos(itens, linhas, j),
        criado_por=_p(_txt(w0.get("created_by"))), cod_criador=_p(_txt(w0.get("code_create_by"))),
        id_criador=_p(_int(w0.get("id_created_by"))), etiquetas=_p(tuple(etiquetas)),
        atribuido_a=_p(_txt(w0.get("user_assigned") or w0.get("personnel_description"))), id_atribuido=_p(_int(id_resp)),
        equipe=_p(_txt(w0.get("personnel_description") or w0.get("user_assigned"))),
        datas=_pacote({"data": w0.get("creation_date"),
                       "event_date": datas["event_date"][0] if datas["event_date"] else programada,
                       "data_fim": _data(w0.get("wo_final_date")) or (fins[-1] if fins else ""), "programada": programada,
                       "inicio": datas["initial_date"][0] if datas["initial_date"] else ""}),
        gatilho=_gatilho(linhas), status_id=_int(w0.get("id_status_work_order")),
        tipo_tarefa=_p(" / ".join(sorted({_txt(w.get("tasks_log_task_type_main")) for w in linhas} - {""}))),
        note=_nota(t for w in linhas for t in (w.get("task_note"), w.get("note"))))


def registros_do_rest(linhas, j: _Juntar | None = None) -> dict:
    """{id da OS: RegistroOS} das linhas do REST `work_orders` (uma por TAREFA): juntadas pelo `id_work_order`, a mesma tarefa
    uma vez só (a página repetida do REST traz a tarefa de novo), na ordem do id da tarefa."""
    j = _Juntar() if j is None else j
    grupos: dict = {}
    for w in linhas or ():
        if not isinstance(w, dict):
            continue
        wid = _int(w.get("id_work_order"))
        if wid is None:
            continue
        g = grupos.setdefault(wid, {})
        t = w.get("id_work_orders_tasks")
        g.setdefault(t if t not in (None, "") else ("sem tarefa", len(g)), w)
    return {wid: _do_rest(wid, sorted(g.values(), key=lambda w: _int(w.get("id_work_orders_tasks")) or 0), j)
            for wid, g in grupos.items()}


def registro_do_card(wid, tarefas, cabecalho) -> RegistroOS | None:
    """A OS lida ao vivo pela sessão da pessoa, com o que o card lê (`api.get_os_detalhes`: as tarefas do RPC e o cabeçalho
    da OS), no registro enxuto. Os nomes dos campos do RPC viram os do REST e o registro sai do mesmo `_do_rest`: uma regra
    só para os dois caminhos. None sem tarefa nem cabeçalho."""
    import api
    tarefas = [t for t in (tarefas or ()) if isinstance(t, dict)]
    cab = cabecalho if isinstance(cabecalho, dict) else {}
    if not tarefas and not cab:
        return None
    nome = api._nome_atribuido(tarefas + [cab])
    ids = api._ids_atribuido(tarefas + [cab])
    t0 = tarefas[0] if tarefas else {}
    criado_por = _txt(cab.get("created_by") or cab.get("creation_user") or cab.get("accounts_name") or t0.get("created_by"))
    linhas = []
    for i, t in enumerate(tarefas or [{}]):
        linhas.append({
            "id_work_orders_tasks": t.get("id") if t.get("id") is not None else i, "id_work_order": wid,
            "wo_folio": cab.get("wo_folio") or t0.get("wo_folio"),
            "id_status_work_order": cab.get("id_status_work_order") or t0.get("id_status_work_order"),
            "description": t.get("tasks_description"), "items_log_description": t.get("items_description"),
            "code": t.get("code_item"), "tasks_log_task_type_main": t.get("tasks_types_main_description"),
            "creation_date": cab.get("creation_date") or t0.get("creation_date"),
            "date_maintenance": t.get("date_maintenance") or t.get("cal_date_maintenance"),
            "initial_date": t.get("initial_date"), "event_date": t.get("event_date"),
            "final_date": next((t.get(k) for k in _FIM_DA_TAREFA if _data(t.get(k))), None),
            "created_by": criado_por, "code_create_by": cab.get("code_create_by"),
            "id_created_by": cab.get("id_created_by"), "user_assigned": nome,
            "personnel_description": t.get("personnel_description") or cab.get("personnel_description") or nome,
            "id_personnel": ids[0] if ids else None, "trigger_description": t.get("trigger_description"),
            "task_note": t.get("task_note"), "note": t.get("note"), "labels": cab.get("labels")})
    return _do_rest(wid, linhas, _Juntar())


def registro_da_linha(d: dict) -> RegistroOS:
    """A linha da tela (o formato do `api.list_minhas_os`, ou o que a ação já tem montado) no registro enxuto. O cliente, a
    usina e o tipo não entram: saem do catálogo de ativos na hora."""
    codigos = tuple(_txt(c) for c in (d.get("codigos") or ()) if _txt(c)) or (
        (_txt(d.get("code")),) if _txt(d.get("code")) else ())
    if _txt(d.get("code")) and codigos and codigos[-1] != _txt(d.get("code")):
        codigos = tuple(c for c in codigos if c != _txt(d.get("code"))) + (_txt(d.get("code")),)
    etq = tuple(_p((_p(_int(e.get("id"))), _p(_txt(e.get("nome") or e.get("description")))))
                for e in (d.get("etiquetas") or ()) if isinstance(e, dict) and _txt(e.get("nome") or e.get("description")))
    desc = _txt(d.get("descricao"))
    return RegistroOS(
        id=_int(d.get("id")), folio=_txt(d.get("folio")), descricao="" if desc == "—" else desc[:DESCRICAO_MAX],
        ativo=_txt(d.get("ativo"))[:ATIVO_MAX], codigos=codigos, criado_por=_p(_txt(d.get("criado_por"))),
        cod_criador=_p(_txt(d.get("cod_criador"))), id_criador=_p(_int(d.get("id_criador"))), etiquetas=_p(etq),
        atribuido_a=_p(_txt(d.get("atribuido_a"))), id_atribuido=_p(_int(d.get("id_atribuido"))),
        equipe=_p(_txt(d.get("equipe"))), datas=_pacote(d), gatilho=_p(_txt(d.get("gatilho"))),
        status_id=_int(d.get("status_id")), tipo_tarefa=_p(_txt(d.get("tipo_tarefa"))), note=_nota([d.get("note")]))
