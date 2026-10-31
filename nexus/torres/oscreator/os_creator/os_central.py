"""os_central.py: a lista de OS do OS Creator, UMA para todas as telas (31/10/2026, etapa 3 do canto central).

Levi, 30/10/2026: "o histórico de OS pega só os mais recentes, atualizando os mais antigos 1 vez por dia pela noite [...] a
ideia é não ter um carregamento novo por atividade e sim um ecossistema onde as coisas se aproveitam" (desenho:
`docs/superpowers/specs/2026-10-30-oscreator-canto-central-design.md`, "Etapa 3"). Até aqui cada visão do Histórico era uma
lista no `historico_store` (a de "Todos" por quem vê o mesmo; "criadas por mim" e "atribuídas a mim" por pessoa), o Garantias
tinha a dele (365 dias), a marcação verde dos Ativos relia a janela de 30 dias, e o nº da OS virava id com 1 a 5 pedidos a
cada vez. As telas passam a ler daqui na 3.3; esta peça é a lista e quem a enche (o leitor em faixas, `os_leitor.py`).

O QUE A LISTA GUARDA (decisão AC): as OS CRIADAS nos últimos `JANELA_DIAS` (365: o Garantias lê 365, e o REST não filtra pela
etiqueta) mais toda OS aberta (status 1 e 2) de qualquer idade. Um registro enxuto por OS (`RegistroOS`, uma tupla com nome,
só leitura), com os campos que o Histórico, o Garantias e o card mostram, montado das linhas do REST `work_orders` (uma por
TAREFA, juntadas pelo `id_work_order`) ou da leitura que a ação do OS Creator faz pela sessão da pessoa. A descrição vai
cortada em 90 caracteres e o ativo em 60, como o `api._shape_wo_row` sempre entregou ao Histórico; a nota só da OS que traz o
bloco do chamado (o Garantias lê a OS de acompanhamento por ela). O cliente, a usina e o tipo do ativo NÃO são guardados: saem
do catálogo de ativos na hora (`RegistroOS.linha`), sempre em dia com ele. A MEMÓRIA (medida com 36 mil OS sintéticas da forma
real, tracemalloc; README do OS Creator): as cinco datas de cada OS vão juntas em 20 bytes (`datas`, segundos desde 2000; o
registro as devolve em ISO, como o Fracttal grava), os textos de pouca variedade (pessoas, tipos, gatilhos, etiquetas) são um
objeto só para todas as OS (`_TEXTOS`), e os que se repetem numa mesma leitura (o código e o nome do ativo, a descrição do
plano) também, sem tabela guardada.

UMA VERSÃO IMUTÁVEL (`Lista`), como o catálogo de ativos: os índices por id, por nº (`por_folio`) e por código de ativo, a
ordem pela data de criação, a janela lida inteira e as OS "a conferir". Troca-se o objeto inteiro: quem está lendo a de antes
termina com ela. Poucas OS mudadas (a ação, as novas) refazem só os pedaços delas nos índices (`_aplicar`); muitas (a noite),
tudo (`_indexar`). O registro não aceita escrita (é o mesmo para todas as telas); quem quer mexer pede a linha
(`RegistroOS.linha()`, um dicionário novo) e recebe uma lista nova de `filtrar`.

CADA LEITURA DIZ O QUE COBRE (`receber(linhas, faixa)`; a "faixa que sai" das decisões): a OS que a lista tinha dentro do que
a faixa cobre e que não veio nela mudou (de status, ou sumiu). Ela fica "a conferir" (a tela diz e o card lê ao vivo; nunca
se mostra como certo um status que a lista sabe velho) até uma faixa trazê-la de novo; a noite tira de vez o que não voltou.
O que cada faixa cobre e o que ela troca:
- `novas`: só SOMA as OS que a lista não tem (a leitura para numa página inteira de OS conhecidas, e as conhecidas dessa
  página podem vir pela metade: uma OS de várias tarefas atravessa a borda da página);
- `sete_dias` e `noite`: trocam as OS criadas desde o `desde` (a leitura vai até uma página INTEIRA mais velha que ele); a
  linha mais velha que o piso, da página que encerra a leitura, não entra (pode estar pela metade). A noite tira de vez a que
  não voltou e as fechadas que saíram da janela;
- `abertas` (status 1 e 2 inteiros, a leitura que o `tarefas_os` já faz de hora em hora): troca as que vieram; a que a lista
  tinha aberta e não veio fica "a conferir";
- `finalizadas` (status 3, pela data de fim): só ANOTA o status e a data fim nas OS que a lista já tem (a leitura é pela data
  de fim de cada TAREFA, então uma OS pode vir com parte das tarefas);
- `os`: as OS lidas uma a uma (as pendentes, pelo nº); a que não veio segue "a conferir".
Leitura que falha no meio não chega aqui (quem lê não chama `receber`): a lista fica como estava. E a leitura só julga o que
existia quando ELA começou (`lido_em` é o começo): a noite inteira leva minutos, e a ação do OS Creator e a entrega das abertas
(outra thread) não esperam por ela. A OS que uma ação mexeu depois do começo da leitura não é trocada pelo que a leitura leu
(o status velho voltaria) nem julgada por ela; a OS criada depois do começo (com `MARGEM_RELOGIO_S` de folga para o relógio
do Fracttal) não sai nem fica "a conferir" por não ter vindo.

A AÇÃO DO OS CREATOR ENTRA NA HORA (`atualizar_os`): com o registro na mão, na hora; sem ele, dentro de um pedido do OS Creator,
lê a OS ao vivo pela sessão da pessoa (as tarefas e o cabeçalho, o que o card já lê: 1 a 3 pedidos); fora de um pedido (ou
com o Fracttal recusando), a OS fica "a conferir" e pendente para a próxima faixa. A OS criada pelo OS Creator não some do
Histórico até a próxima volta, e o reinício logo depois não a apaga (a cópia em disco chega em até 30 s).

A JANELA (`Lista.janela`, decisão AC): as datas de criação que a lista leu INTEIRAS, (de, até): `de` é o dia mais velho de uma
leitura de cima para baixo (os 7 dias, a noite) emendada com a seguinte, e `até` é o começo da última leitura que chegou ao
topo (as novas que pararam numa página conhecida também). A tela que pede um período fora dela vai ao vivo (`cobre`).

O DISCO (decisão AH): `<pasta>/os_central.json.gz`, escrita em fluxo (uma linha JSON por OS, com o cabeçalho na 1ª e o fecho
na última: nem a escrita nem a leitura montam o arquivo inteiro na memória), trocada de uma vez (`canto_disco`), no máximo uma
escrita a cada `GRAVAR_A_CADA_S` (as ações seguidas viram uma). O boot só lê o disco: nenhum pedido ao Fracttal (meta 3). A
cópia ilegível, cortada ou de outro formato é ignorada, a lista começa vazia e o estado diz por quê. É cache do Fracttal, com
texto de OS e nomes: não vai ao banco nem ao git (decisão AE).

Só o `servir.py` liga o leitor (`os_leitor.ligar`); no PC e nos testes a lista só se enche pelo disco e pelas ações, e as
telas seguem ao vivo, como hoje.
"""
from __future__ import annotations

import bisect
import gzip
import json
import logging
import os
import struct
import sys
import threading
import time
import unicodedata
import zlib
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import NamedTuple

# a troca de uma vez (rascunho ao lado + `os.replace`), a mesma da cópia dos ativos; pelo nome do módulo, para o teste contar
from canto_disco import trocar_de_uma_vez as _trocar_de_uma_vez

log = logging.getLogger("oscreator.os_central")

JANELA_DIAS = 365               # as OS criadas nesta janela ficam (o Garantias lê 365 dias); as abertas, de qualquer idade
FORMATO = 1                     # o formato da cópia em disco; outro número = arquivo de outra versão do código, ignorado
NOME_ARQUIVO = "os_central.json.gz"
GRAVAR_A_CADA_S = 30            # no máximo uma escrita da cópia a cada 30 s: as ações seguidas viram uma (decisão AH)
FRESCA_S = 30 * 60              # o período que chega a hoje só vale com a última leitura até o topo de no máximo 30 min
DESCRICAO_MAX = 90              # como o `api._shape_wo_row` entrega ao Histórico
ATIVO_MAX = 60
NOTA_MAX = 4000                 # a nota com o bloco do chamado (o Garantias a lê); a OS sem ele não guarda nota
CAMPOS_MIN_OS = 50              # a medida dos campos do REST só vale numa leitura de pelo menos tantas OS
POR_PARTES_MIN = 50             # até tantas OS mudadas (ou 1/10 da lista), os índices se refazem só nelas
MARGEM_RELOGIO_S = 120          # a OS criada perto do começo de uma leitura (o relógio do Fracttal e o nosso) não é julgada por ela
TOCADAS_GUARDA_S = 86400        # quanto tempo a lista lembra que uma ação mexeu numa OS (uma leitura nunca dura isso)
STATUS = {1: "Em Processo", 2: "Em Verificação", 3: "Concluída", 4: "Cancelada"}     # o `api.WO_STATUS` (um teste confere)
ABERTOS = frozenset({1, 2})
# as marcas do bloco do chamado na nota da OS: a do `api._CHAMADO_MK` (o bloco do chamado) e a do `acomp_web.MARCA_NOTA` (a OS
# de acompanhamento do Garantias); um teste confere que são as mesmas
MARCAS_DA_NOTA = ("━━━ CHAMADO ━━━", "[CHAMADO] Acompanhamento")
NOVAS, SETE_DIAS, ABERTAS, FINALIZADAS, NOITE, UMA_OS = "novas", "sete_dias", "abertas", "finalizadas", "noite", "os"
FAIXAS = (NOVAS, SETE_DIAS, ABERTAS, FINALIZADAS, NOITE, UMA_OS)
VISOES = ("todos", "criadas", "atribuidas")
_FIM_DA_TAREFA = ("final_date", "date_end", "end_date", "real_final_date", "finished_date", "date_finished", "closing_date")

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


_LEGIVEIS = frozenset(RegistroOS._fields) | frozenset(_DATAS) | {"status", "code"}
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


def _nota(textos) -> str:
    """A nota da OS só quando ela traz o bloco do chamado (o Garantias lê a OS de acompanhamento por ele): a de todas as
    outras não é mostrada pela lista, e guardá-la seria texto à toa na memória."""
    junta = "\n".join(_distintos(_txt(t) for t in textos if _txt(t).lower() != "none"))
    return junta[:NOTA_MAX] if any(m in junta for m in MARCAS_DA_NOTA) else ""


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


_I_DATAS = RegistroOS._fields.index("datas")


def _para_disco(r: RegistroOS) -> list:
    v = list(r)
    v[_I_DATAS] = list(_PACOTE.unpack(r.datas))
    return v


def _do_disco(v: list, j) -> RegistroOS:
    """Uma linha da cópia em disco (os campos na ordem do registro; as datas, os cinco inteiros) de volta ao registro, com as
    tuplas e os textos repetidos num objeto só."""
    if not isinstance(v, list) or len(v) != len(RegistroOS._fields):
        raise ValueError("linha da cópia com %r campos, o registro tem %d" % (
            len(v) if isinstance(v, list) else None, len(RegistroOS._fields)))
    d = dict(zip(RegistroOS._fields, v))
    if not isinstance(d["id"], int):
        raise ValueError("linha da cópia sem o id da OS")
    d["datas"] = _PACOTE.pack(*d["datas"])
    d["codigos"] = j(tuple(j(c) for c in d["codigos"] or ()))
    d["etiquetas"] = _p(tuple(_p((_p(e[0]), _p(e[1]))) for e in d["etiquetas"] or ()))
    d["ativo"], d["descricao"] = j(d["ativo"]), j(d["descricao"])
    for k in ("criado_por", "cod_criador", "id_criador", "atribuido_a", "id_atribuido", "equipe", "gatilho", "tipo_tarefa"):
        d[k] = _p(d[k])
    return RegistroOS(**d)


# ── a lista (imutável por versão) ──────────────────────────────────────────────────────────────────────────────────────
def _epoca(iso) -> float:
    try:
        return datetime.fromisoformat(str(iso)[:19]).replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return 0.0


def _iso(epoca: float) -> str:
    return datetime.fromtimestamp(epoca, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


@dataclass(frozen=True, slots=True, eq=False)
class Lista:
    """Uma versão da lista: pronta, imutável e compartilhada. `por_id` ({id: registro}), `por_folio` ({nº: registro}) e
    `por_codigo_ativo` ({código: (registros, da criação mais nova para a mais velha)}) guardam os MESMOS registros (nada é
    copiado); `ordem` são os registros pela criação, da mais nova para a mais velha; `nomes_criadores` é {nome normalizado de
    quem criou: os códigos de pessoa vistos com ele} (o homônimo de `filtrar`). `lido_em` é a última leitura do Fracttal que
    chegou aqui (qualquer faixa); `janela` = (de, até) das datas de criação lidas INTEIRAS (ver o topo); `a_conferir`, as OS
    que uma faixa deveria ter trazido e não trouxe; `versao` muda a cada troca de conteúdo."""
    por_id: Mapping
    por_folio: Mapping
    por_codigo_ativo: Mapping
    ordem: tuple
    nomes_criadores: Mapping
    lido_em: float
    janela: tuple
    versao: int
    a_conferir: frozenset

    def cobre(self, de=None, ate=None, agora: float | None = None) -> bool:
        """A lista responde por este período de criação (`de` e `ate` em 'AAAA-MM-DD', como as telas pedem)? Só se ele está
        dentro da janela lida inteira; o período que chega ao fim da janela (hoje) só com a última leitura até o topo de no
        máximo `FRESCA_S`. Fora disso a tela vai ao vivo."""
        jde, jate = self.janela
        if not jde or not jate or not de or str(de)[:10] < jde:
            return False
        if ate is None or str(ate)[:10] >= jate[:10]:
            return ((time.time() if agora is None else agora) - _epoca(jate)) <= FRESCA_S
        return True

    def conferir(self, wid) -> bool:
        """A OS está "a conferir" (uma faixa deveria tê-la trazido e não trouxe: o status dela pode ter mudado)."""
        return wid in self.a_conferir


def _chave(r: RegistroOS) -> tuple:
    """A ordem da lista ao contrário (a criação mais nova primeiro), para o `bisect`, que só sabe a ordem crescente."""
    return (-_s(r), -r.id)


def _indexar(por_id: dict, *, lido_em: float, janela: tuple, versao: int, a_conferir) -> Lista:
    """A versão pronta, com todos os índices montados de novo: CONSOME o dicionário `por_id` (ele vira o índice, sem cópia)."""
    ordem = sorted(por_id.values(), key=_chave)
    por_folio: dict = {}
    por_cod: dict = {}
    nomes: dict = {}
    for r in ordem:
        if r.folio:
            por_folio.setdefault(r.folio, r)
        for c in r.codigos:
            por_cod.setdefault(c, []).append(r)
        if r.criado_por:
            nomes.setdefault(_norm(r.criado_por), set()).add(_cod(r.cod_criador))
    return Lista(por_id=MappingProxyType(por_id), por_folio=MappingProxyType(por_folio),
                 por_codigo_ativo=MappingProxyType({c: tuple(v) for c, v in por_cod.items()}), ordem=tuple(ordem),
                 nomes_criadores=MappingProxyType({n: frozenset(c) for n, c in nomes.items()}), lido_em=float(lido_em),
                 janela=tuple(janela), versao=int(versao), a_conferir=frozenset(a_conferir))


def _aplicar(base: Lista, mudancas: dict, *, lido_em: float, janela: tuple, versao: int, a_conferir) -> Lista:
    """A versão nova com POUCAS OS mudadas (`mudancas`: {id: o registro novo, ou None para tirar}), refazendo nos índices só
    os pedaços delas: a ação do OS Creator, que roda dentro do pedido de alguém, não espera a lista inteira ser montada de novo
    (medido com 36 mil OS: ~0,25 s inteira). O resultado é o mesmo do `_indexar` (um teste confere), menos os
    `nomes_criadores`, que só ganham códigos aqui (o código de quem saiu fica até a noite refazer tudo: só pode deixar um nome
    "ambíguo" a mais, e a tela vai ao vivo, nunca o contrário)."""
    por_id = dict(base.por_id)
    por_folio = dict(base.por_folio)
    por_cod = dict(base.por_codigo_ativo)
    nomes = dict(base.nomes_criadores)
    saem = [base.por_id[w] for w in mudancas if w in base.por_id]
    ordem = list(base.ordem)
    if saem:
        fora = {id(r) for r in saem}
        ordem = [r for r in ordem if id(r) not in fora]
        for velho in saem:
            if por_folio.get(velho.folio) is velho:
                del por_folio[velho.folio]
            for c in velho.codigos:
                resto = tuple(x for x in por_cod.get(c, ()) if x is not velho)
                if resto:
                    por_cod[c] = resto
                else:
                    por_cod.pop(c, None)
            del por_id[velho.id]
    for wid, r in mudancas.items():
        if r is None:
            continue
        por_id[wid] = r
        bisect.insort(ordem, r, key=_chave)
        if r.folio:
            por_folio.setdefault(r.folio, r)
        for c in r.codigos:
            t = list(por_cod.get(c, ()))
            bisect.insort(t, r, key=_chave)
            por_cod[c] = tuple(t)
        if r.criado_por:
            n = _norm(r.criado_por)
            nomes[n] = nomes.get(n, frozenset()) | {_cod(r.cod_criador)}
    return Lista(por_id=MappingProxyType(por_id), por_folio=MappingProxyType(por_folio),
                 por_codigo_ativo=MappingProxyType(por_cod), ordem=tuple(ordem), nomes_criadores=MappingProxyType(nomes),
                 lido_em=float(lido_em), janela=tuple(janela), versao=int(versao), a_conferir=frozenset(a_conferir))


def _vazia() -> Lista:
    return _indexar({}, lido_em=0.0, janela=(None, None), versao=0, a_conferir=())


# ── o estado do processo ───────────────────────────────────────────────────────────────────────────────────────────────
_ATUAL: Lista | None = None
_TRAVA = threading.Lock()               # a troca da versão
_TRAVA_BOOT = threading.Lock()          # o boot pelo disco uma vez só, mesmo com vários pedidos juntos
_TRAVA_DISCO = threading.Lock()         # uma gravação por vez
_CONFIG: dict = {"pasta": None}
_BOOT = {"feito": False}
_SEQ = {"versao": 0}
_LEITOR: dict = {"estado": None}
_TOCADAS: dict = {}                     # {id da OS: quando a ação do OS Creator a pôs na lista} (a leitura não a desfaz)
_AGENDA = {"pendente": False, "escrevendo": False, "ultima": 0.0, "timer": None}
_AGENDA_COND = threading.Condition()


def _estado_limpo() -> dict:
    # `faixas`: a última entrega de cada faixa (quando, quem, quantas OS e linhas, o que entrou, mudou, ficou a conferir e
    # saiu); `pendentes`: {id da OS: desde quando} que a ação deixou para a próxima faixa; `campos`: a medida dos campos que o
    # REST trouxe na última leitura grande (a sondagem da 1ª noite, que não pôde ser feita antes de construir)
    return {"faixas": {}, "pendentes": {}, "campos": None,
            "disco": {"lido": None, "gravado_em": 0.0, "versao": None, "bytes": None, "erro": None}}


_ESTADO: dict = _estado_limpo()


def configurar(pasta: str | None) -> None:
    """Onde mora a cópia em disco (`<pasta>/os_central.json.gz`). Quem chama é a ponte do Nexus (`ponte.ligar_lista_de_os`);
    nos testes ela não chama: sem pasta, a lista vive só na memória. O boot acontece na primeira leitura depois disto."""
    with _TRAVA:
        if _CONFIG["pasta"] != pasta:
            _CONFIG["pasta"] = pasta
            _BOOT["feito"] = _ATUAL is not None and bool(_ATUAL.por_id)    # a lista que já tem OS não volta ao disco


def reiniciar(pasta: str | None = None) -> None:
    """Volta ao processo recém-subido (os testes): sem lista, sem leitor, sem gravação agendada, com a pasta que vier."""
    global _ATUAL
    with _AGENDA_COND:
        t = _AGENDA["timer"]
        if t is not None:
            t.cancel()
        _AGENDA.update(pendente=False, escrevendo=False, ultima=0.0, timer=None)
        _AGENDA_COND.notify_all()
    with _TRAVA:
        _ATUAL = None
        _CONFIG["pasta"] = pasta
        _BOOT["feito"] = False
        _SEQ["versao"] = 0
        _LEITOR["estado"] = None
        _TOCADAS.clear()
        _ESTADO.clear()
        _ESTADO.update(_estado_limpo())
        _TEXTOS.clear()


def ligar_leitor(estado=None) -> None:
    """O leitor em faixas do servidor (`os_leitor.ligar`) se registra aqui, para o `estado()` mostrar o que ele fez."""
    _LEITOR["estado"] = estado


def atual() -> Lista:
    """A versão de agora (vazia, sem janela, se esta máquina ainda não tem nada). A 1ª chamada do processo faz o boot pela
    cópia em disco: sem rede, nenhum pedido ao Fracttal."""
    if not _BOOT["feito"]:
        _boot()
    return _ATUAL if _ATUAL is not None else _vazia()


def _instalar(base: Lista, mudancas: dict, *, lido_em: float, janela: tuple, a_conferir, mudou: bool) -> Lista:
    """Põe a versão nova no lugar (dentro da `_TRAVA`). Sem mudança de conteúdo: a mesma versão com a hora e o fim da janela
    trocados, sem índice nenhum montado e sem regravar o disco (eles vão junto da próxima mudança). Só o "a conferir" mudou:
    os mesmos índices. Poucas OS mudadas: os pedaços delas (`_aplicar`); muitas: tudo (`_indexar`)."""
    global _ATUAL
    lido_em = max(base.lido_em, lido_em)
    if not mudou:
        _ATUAL = replace(base, lido_em=lido_em, janela=janela)
        return _ATUAL
    _SEQ["versao"] += 1
    versao = _SEQ["versao"]
    if not mudancas:
        _ATUAL = replace(base, lido_em=lido_em, janela=janela, versao=versao, a_conferir=frozenset(a_conferir))
    elif len(mudancas) <= max(POR_PARTES_MIN, len(base.por_id) // 10):
        _ATUAL = _aplicar(base, mudancas, lido_em=lido_em, janela=janela, versao=versao, a_conferir=a_conferir)
    else:
        por_id = dict(base.por_id)
        for wid, r in mudancas.items():
            if r is None:
                por_id.pop(wid, None)
            else:
                por_id[wid] = r
        _ATUAL = _indexar(por_id, lido_em=lido_em, janela=janela, versao=versao, a_conferir=a_conferir)
    return _ATUAL


def _piso_da_janela(agora: float) -> str:
    return (datetime.fromtimestamp(agora, timezone.utc) - timedelta(days=JANELA_DIAS)).strftime("%Y-%m-%d")


def _dia_inteiro(desde) -> str:
    """O 1º dia lido INTEIRO por uma leitura que foi até `desde`: o próprio dia se ele começa à meia-noite (ou veio só a
    data), senão o seguinte."""
    s = _txt(desde)
    if len(s) <= 10 or s[11:19] in ("", "00:00:00"):
        return s[:10]
    return (datetime.fromisoformat(s[:10]) + timedelta(days=1)).strftime("%Y-%m-%d")


def _janela_nova(janela: tuple, faixa: str, desde, inicio: float, agora: float) -> tuple:
    """A janela depois de uma leitura (ver o topo): os 7 dias e a noite cobrem [desde, começo da leitura] e emendam com a de
    antes quando chegam até ela; as novas só avançam o fim, e só emendadas (`desde` é a criação mais velha da página conhecida
    em que pararam). As outras faixas não mexem na janela."""
    jde, jate = janela
    ate = _iso(inicio)
    if faixa in (SETE_DIAS, NOITE) and desde:
        de = _dia_inteiro(desde)
        if jde and jate and _txt(desde)[:19] <= jate and jde < de:
            de = jde
        return max(de, _piso_da_janela(agora)), max(ate, jate or "")
    if faixa == NOVAS and desde and jde and jate and _txt(desde)[:19] <= jate:
        return jde, max(ate, jate)
    return janela


def _fica(r: RegistroOS, piso_s: int, a_conferir) -> bool:
    """A OS fica na lista: criada dentro da janela, ou aberta (de qualquer idade) e não "a conferir"."""
    return _s(r) >= piso_s or (r.status_id in ABERTOS and r.id not in a_conferir)


def _medir_campos(novos: dict, faixa: str, agora: float) -> None:
    """Quantas OS da leitura trouxeram cada campo que as telas usam (só contagens): é a sondagem do REST que não pôde ser
    feita antes de construir; o Raio-X mostra."""
    if len(novos) < CAMPOS_MIN_OS:
        return
    n = len(novos)
    rs = novos.values()
    conta = {"nº": sum(1 for r in rs if r.folio), "criação": sum(1 for r in rs if _s(r)),
             "quem criou": sum(1 for r in rs if r.criado_por),
             "código de quem criou": sum(1 for r in rs if r.cod_criador),
             "responsável (id)": sum(1 for r in rs if r.id_atribuido is not None),
             "tipo da tarefa": sum(1 for r in rs if r.tipo_tarefa), "código do ativo": sum(1 for r in rs if r.codigos),
             "programada": sum(1 for r in rs if _s(r, 3)), "gatilho": sum(1 for r in rs if r.gatilho),
             "etiqueta com id": sum(1 for r in rs if any(i is not None for i, _ in r.etiquetas)),
             "com etiqueta": sum(1 for r in rs if r.etiquetas)}
    _ESTADO["campos"] = {"faixa": faixa, "em": agora, "n": n,
                         "pct": {k: round(100.0 * v / n, 1) for k, v in conta.items()}}


def receber(linhas_rest, faixa: str, *, desde=None, lido_em: float | None = None, quem: str | None = None,
            ids=None) -> dict:
    """Uma leitura do REST `work_orders` (as linhas, uma por tarefa) entra na lista pela regra da `faixa` (ver o topo):
    `desde` é o piso da leitura (a criação, nas novas, nos 7 dias e na noite; a data de fim, nas finalizadas), `lido_em` o
    COMEÇO dela (padrão: agora; é o fim da janela), `quem` quem leu (as abertas vêm do `tarefas_os` ou do próprio leitor), e
    `ids` as OS que a faixa `os` pediu. Devolve o relatório (só contagens), que também fica em `estado()["faixas"]`."""
    if faixa not in FAIXAS:
        raise ValueError("faixa desconhecida: %r (as válidas: %s)" % (faixa, ", ".join(FAIXAS)))
    agora = time.time()
    inicio = agora if lido_em is None else float(lido_em)
    atual()                                                          # o boot pelo disco antes (sem ele, a cópia se perderia)
    if faixa == NOITE:
        _TEXTOS.clear()                                              # a noite refaz a tabela dos textos repetidos
    novos = registros_do_rest(linhas_rest)
    _medir_campos(novos, faixa, agora)
    piso_s = _seg(_piso_da_janela(agora))
    desde_s = _seg(desde) if desde else None
    rel = {"faixa": faixa, "em": agora, "inicio": inicio, "quem": quem or "", "linhas": len(linhas_rest or ()),
           "os": len(novos), "entraram": 0, "mudaram": 0, "a_conferir": 0, "sairam": 0, "fora": 0}
    # o que mudou depois do começo da leitura não é julgado por ela (ver o topo): a OS que a ação mexeu, e a criada no meio
    limite_s = int(inicio) - _EPOCA0 - MARGEM_RELOGIO_S

    def mexida_depois(wid) -> bool:
        return _TOCADAS.get(wid, 0.0) >= inicio
    with _TRAVA:
        # os dicionários que outras threads mexem são percorridos só dentro da trava, ou pela cópia (`list`, de uma vez só)
        for wid in [w for w, quando in list(_TOCADAS.items()) if agora - quando > TOCADAS_GUARDA_S]:
            _TOCADAS.pop(wid, None)
        base = _ATUAL if _ATUAL is not None else _vazia()
        conferir = set(base.a_conferir)
        pendentes = _ESTADO["pendentes"]
        if faixa in (SETE_DIAS, NOITE):
            cobre = (lambda r: desde_s <= _s(r) < limite_s) if desde_s is not None else (lambda r: False)
        elif faixa == ABERTAS:
            cobre = lambda r: r.status_id in ABERTOS and _s(r) < limite_s                 # noqa: E731
        elif faixa == UMA_OS:
            pedidos = {_int(i) for i in (ids or ())} | set(novos)
            cobre = lambda r: r.id in pedidos                                               # noqa: E731
        else:
            cobre = None
        mudancas: dict = {}
        for wid, r in novos.items():
            velho = base.por_id.get(wid)
            if mexida_depois(wid):
                rel["fora"] += 1                                     # a ação mexeu nela depois: o que a leitura leu é velho
                continue
            if faixa == NOVAS:
                if velho is not None or not _fica(r, piso_s, ()):
                    continue
            elif faixa == FINALIZADAS:
                if velho is None:
                    rel["fora"] += 1                                 # a lista não tem: a OS pode ter vindo pela metade
                    continue
                r = velho._replace(status_id=r.status_id, datas=_PACOTE.pack(
                    *(max(a, b) if i == 2 else a for i, (a, b) in enumerate(zip(_PACOTE.unpack(velho.datas),
                                                                                _PACOTE.unpack(r.datas))))))
            elif faixa in (SETE_DIAS, NOITE) and (desde_s is None or _s(r) < desde_s):
                rel["fora"] += 1                                     # mais velha que o piso: a página da borda
                continue
            elif faixa == ABERTAS and velho is None and r.status_id not in ABERTOS:
                continue
            conferir.discard(wid)
            pendentes.pop(wid, None)
            if velho is None:
                if _fica(r, piso_s, conferir):
                    mudancas[wid] = r
                    rel["entraram"] += 1
            elif r != velho:
                mudancas[wid] = r
                rel["mudaram"] += 1
        if cobre is not None:
            for wid, r in base.por_id.items():
                if wid in novos or mexida_depois(wid) or not cobre(r):
                    continue
                if faixa == NOITE:
                    mudancas[wid] = None                             # a noite tira de vez o que não voltou
                    conferir.discard(wid)
                    rel["sairam"] += 1
                elif wid not in conferir:
                    conferir.add(wid)
                    rel["a_conferir"] += 1
        if faixa == NOITE:
            for wid, r in base.por_id.items():
                r = mudancas.get(wid, r)
                if r is not None and not _fica(r, piso_s, conferir):
                    mudancas[wid] = None                             # as fechadas que saíram da janela
                    conferir.discard(wid)
                    rel["sairam"] += 1
        janela = _janela_nova(base.janela, faixa, desde, inicio, agora)
        mudou = bool(mudancas) or conferir != base.a_conferir or janela[0] != base.janela[0]
        lista = _instalar(base, mudancas, lido_em=inicio, janela=janela, a_conferir=conferir, mudou=mudou)
        _ESTADO["faixas"][faixa] = rel
    if mudou:
        _agendar_gravacao()
    log.info("lista central de OS: faixa %s (%s): %d OS em %d linhas; %d entraram, %d mudaram, %d a conferir, %d saíram; "
             "a lista tem %d", faixa, quem or "-", rel["os"], rel["linhas"], rel["entraram"], rel["mudaram"],
             rel["a_conferir"], rel["sairam"], len(lista.por_id))
    return rel


# ── a ação do OS Creator ───────────────────────────────────────────────────────────────────────────────────────────────
def _em_pedido() -> bool:
    """Dentro de um pedido do OS Creator, com a sessão do Fracttal da pessoa (o JWT no contexto)."""
    try:
        from os_web import sessao
    except Exception:                                                # noqa: BLE001 — sem o clone, não há sessão
        return False
    return bool(sessao.jwt_atual())


def _ler_ao_vivo(wid: int) -> RegistroOS | None:
    """A OS lida agora pela sessão da pessoa, com o que o card já lê: as tarefas (`_leitura_da_os`, que reaproveita a leitura
    que o card acabou de fazer e é esquecida por toda gravação na OS) e o cabeçalho. 1 a 3 pedidos."""
    import api
    tarefas = api._leitura_da_os(api.RPC_WO_TASKS, wid, {"id_work_order": wid, "sort": []})
    cab = api._cabecalho_os(wid)
    return registro_do_card(wid, tarefas, cab)


def _como_registro(wid: int, registro) -> RegistroOS | None:
    if isinstance(registro, RegistroOS):
        return registro
    if isinstance(registro, (list, tuple)):
        return registros_do_rest(registro).get(wid)                  # as linhas do REST (uma por tarefa)
    if isinstance(registro, dict):
        if "wo_folio" in registro and "folio" not in registro:       # a linha crua do RPC: o formato do Histórico primeiro
            import api
            return registro_da_linha(api._shape_wo_row(registro))
        return registro_da_linha(dict(registro, id=registro.get("id", wid)))
    return None


def _marcar_pendente(wid: int) -> None:
    with _TRAVA:
        base = _ATUAL if _ATUAL is not None else _vazia()
        _ESTADO["pendentes"][wid] = time.time()
        if wid in base.por_id and wid not in base.a_conferir:
            _instalar(base, {}, lido_em=base.lido_em, janela=base.janela, a_conferir=set(base.a_conferir) | {wid},
                      mudou=True)
    _agendar_gravacao()


def atualizar_os(id_work_order, registro=None) -> bool:
    """A OS que o OS Creator acabou de criar ou mudar entra na lista NA HORA. `registro`: o registro pronto, as linhas do REST
    da OS, a linha do Histórico (`api.list_minhas_os`) ou a linha crua do RPC. Sem ele, dentro de um pedido do OS Creator, a
    OS é lida ao vivo pela sessão da pessoa (o que o card já lê, 1 a 3 pedidos); fora de um pedido, ou com a leitura falhando,
    ela fica "a conferir" e pendente para a próxima faixa (nada vai ao Fracttal daqui). True se entrou."""
    wid = _int(id_work_order)
    if wid is None:
        return False
    atual()                                                          # o boot pelo disco antes de mexer
    if registro is None:
        if not _em_pedido():
            _marcar_pendente(wid)
            return False
        try:
            reg = _ler_ao_vivo(wid)
        except Exception as e:                                       # noqa: BLE001 — a ação já deu certo; a lista espera a faixa
            log.warning("lista central de OS: não li a OS %s ao vivo (%s: %s); fica para a próxima faixa", wid,
                        type(e).__name__, str(e)[:120])
            reg = None
    else:
        reg = _como_registro(wid, registro)
    if reg is None or reg.id != wid:
        _marcar_pendente(wid)
        return False
    with _TRAVA:
        base = _ATUAL if _ATUAL is not None else _vazia()
        velho = base.por_id.get(wid)
        if not _s(reg):                                              # a criação que a leitura não trouxe: a de antes, ou agora
            reg = reg.com(data=velho.data if velho is not None else _iso(time.time()))
        _ESTADO["pendentes"].pop(wid, None)
        _TOCADAS[wid] = time.time()                                  # a leitura que começou antes não a desfaz
        _instalar(base, {wid: reg}, lido_em=base.lido_em, janela=base.janela,
                  a_conferir=set(base.a_conferir) - {wid}, mudou=True)
    _agendar_gravacao()
    return True


# ── as visões viram filtros ────────────────────────────────────────────────────────────────────────────────────────────
def _quem_casa(lista: Lista, visao: str, pessoa):
    """(casa(registro) -> (casou, só pelo nome), o nome é ambíguo) da visão, ou None quando a pessoa não se identifica para
    ela. "criadas por mim": pelo id da conta (o que o RPC traz) quando os dois lados o têm; senão pelo código da pessoa no
    Fracttal (o `code_create_by` do REST); senão pelo nome, que só vale sem homônimo. "atribuídas a mim": pelo id da pessoa."""
    p = pessoa if isinstance(pessoa, dict) else {}
    if visao == "todos":
        return (lambda r: (True, False)), False
    if visao == "atribuidas":
        idp = _int(p.get("id_personnel"))
        if idp is None:
            return None
        return (lambda r: (r.id_atribuido == idp, False)), False
    ida, cod, nome = _int(p.get("id_account")), _cod(p.get("codigo")), _norm(p.get("nome"))
    if ida is None and not cod and not nome:
        return None
    codigos = set(lista.nomes_criadores.get(nome, ())) - {""} if nome else set()
    ambiguo = bool(codigos - {cod}) if cod else len(codigos) > 1

    def casa(r):
        if ida is not None and r.id_criador is not None:
            return r.id_criador == ida, False
        if cod and r.cod_criador:
            return _cod(r.cod_criador) == cod, False
        if nome and r.criado_por:
            return _norm(r.criado_por) == nome, True
        return False, False
    return casa, ambiguo


def _selecionar(visao, pessoa, de, ate, etiqueta, status):
    lista = atual()
    if visao not in VISOES or not lista.cobre(de, ate):
        return None
    q = _quem_casa(lista, visao, pessoa)
    if q is None:
        return None
    casa, ambiguo = q
    de_s = _seg(str(de)[:10])
    ate_s = _seg(str(ate)[:10] + "T23:59:59") if ate else None
    st = {_int(s) for s in status} if status else None
    etq = None if etiqueta is None else (_int(etiqueta) if _int(etiqueta) is not None else _norm(etiqueta))
    out, pelo_nome = [], False
    for r in lista.ordem:                                            # da criação mais nova para a mais velha
        criada = _s(r)
        if criada < de_s:
            break
        if ate_s is not None and criada > ate_s:
            continue
        casou, so_nome = casa(r)
        if not casou:
            continue
        if st is not None and (r.status_id not in st or r.id in lista.a_conferir):
            continue                                                 # "a conferir": o status dela é velho
        if etq is not None and not any((i == etq) if isinstance(etq, int) else (_norm(n) == etq)
                                       for i, n in r.etiquetas):
            continue
        pelo_nome = pelo_nome or so_nome
        out.append(r)
    if visao == "criadas":
        if pelo_nome and ambiguo:
            return None                                              # o homônimo: só a leitura ao vivo diz qual
        p = pessoa if isinstance(pessoa, dict) else {}
        if not out and _int(p.get("id_account")) is None and not _cod(p.get("codigo")):
            return None                                              # pelo nome, zero pode ser o nome escrito de outro jeito
    return out


def filtrar(visao: str = "todos", pessoa=None, de=None, ate=None, *, etiqueta=None, status=None) -> list | None:
    """As OS da visão ("todos", "criadas", "atribuidas") criadas no período [de, ate] ('AAAA-MM-DD'), da mais nova para a mais
    velha: uma lista NOVA, de quem pediu, com os registros da lista central (só leitura; `linha()` dá a cópia mutável).
    `pessoa`: {"id_account", "codigo", "nome"} para "criadas", {"id_personnel"} para "atribuidas". `etiqueta`: o id (ou o
    nome); `status`: os ids aceitos (a OS "a conferir" fica de fora, o status dela é velho). None quando a lista não responde
    por isso e a tela tem de ir ao vivo: o período fora da janela lida inteira (`Lista.cobre`), a pessoa que não se identifica
    para a visão, o nome com homônimo, ou o nome que não casou com nenhuma OS."""
    return _selecionar(visao, pessoa, de, ate, etiqueta, status)


def contar(visao: str = "todos", pessoa=None, de=None, ate=None, *, etiqueta=None, status=None) -> int | None:
    """Quantas OS `filtrar` daria (a guarda da lista pela metade, decisão AI: a 3.3 compara com o total que o Fracttal dá à
    pessoa). None nos mesmos casos de `filtrar`."""
    sel = _selecionar(visao, pessoa, de, ate, etiqueta, status)
    return None if sel is None else len(sel)


def folio_para_id(folio) -> int | None:
    """O id da OS pelo nº (wo_folio), pelo índice: sem pedido nenhum ao Fracttal. None se a lista não tem esse nº (a tela
    segue com a leitura ao vivo para o resto)."""
    f = _txt(folio)
    if not f:
        return None
    lista = atual()
    r = lista.por_folio.get(f)
    if r is None and f.isdigit():
        r = lista.por_folio.get(str(int(f)))
    return r.id if r is not None else None


def mais_nova_data_fim() -> str:
    """A data de fim mais nova que a lista conhece entre as concluídas (o piso das finalizadas é ela menos 2 dias), ou ""."""
    return _iso_seg(max((_s(r, 2) for r in atual().ordem if r.status_id == 3), default=0))


def entrega(faixa: str) -> dict | None:
    """A última entrega desta faixa (`estado()["faixas"]`), ou None."""
    atual()
    e = _ESTADO["faixas"].get(faixa)
    return dict(e) if e else None


def pendentes() -> dict:
    """{id da OS: desde quando} das OS que a ação deixou para a próxima faixa."""
    atual()
    return dict(_ESTADO["pendentes"])


# ── a cópia em disco ───────────────────────────────────────────────────────────────────────────────────────────────────
def _caminho() -> str | None:
    return os.path.join(_CONFIG["pasta"], NOME_ARQUIVO) if _CONFIG["pasta"] else None


def _agendar_gravacao() -> None:
    """A cópia em disco no máximo uma vez a cada `GRAVAR_A_CADA_S`, numa thread à parte: a gravação agendada escreve a versão
    do momento em que ela roda, então as mudanças seguidas viram uma escrita só, e a última chega ao disco em até 30 s."""
    if not _CONFIG["pasta"]:
        return
    with _AGENDA_COND:
        if _AGENDA["pendente"]:
            return
        espera = max(0.0, _AGENDA["ultima"] + GRAVAR_A_CADA_S - time.time())
        t = threading.Timer(espera, _gravar_agendada)
        t.daemon = True
        t.name = "nexus-os-central-disco"
        _AGENDA.update(pendente=True, timer=t)
        t.start()


def _gravar_agendada() -> None:
    with _AGENDA_COND:
        if not _AGENDA["pendente"]:
            return                                                   # cancelada (o reinício dos testes)
        _AGENDA.update(pendente=False, escrevendo=True, ultima=time.time(), timer=None)
    try:
        _gravar_agora()
    except Exception:                                                # noqa: BLE001 — o disco nunca derruba a lista
        log.exception("lista central de OS: a gravação em disco quebrou")
    finally:
        with _AGENDA_COND:
            _AGENDA["escrevendo"] = False
            _AGENDA_COND.notify_all()


def esperar_gravacao(teto: float = 60.0) -> bool:
    """Espera a gravação agendada (e a que está escrevendo) terminar, até `teto` segundos. True se não ficou nenhuma."""
    fim = time.monotonic() + max(0.0, float(teto))
    with _AGENDA_COND:
        while _AGENDA["pendente"] or _AGENDA["escrevendo"]:
            resta = fim - time.monotonic()
            if resta <= 0:
                return False
            _AGENDA_COND.wait(resta)
    return True


def _gravar_agora() -> bool:
    """A cópia da versão VIGENTE (lida dentro da trava do disco), em fluxo: o cabeçalho, uma linha JSON por OS e o fecho com
    a conta (a cópia sem ele, ou com outra conta, foi cortada no meio e é ignorada no boot). Pula se o disco já tem esta
    versão. Falha de disco vai ao log e ao estado; a lista segue na memória."""
    destino = _caminho()
    if destino is None:
        return False
    with _TRAVA_DISCO:
        lista = _ATUAL
        if lista is None or _ESTADO["disco"].get("versao") == lista.versao:
            return False
        # as cópias de uma vez só (`list`, `dict`): a faixa e a ação mexem nesses dicionários em outras threads
        cab = {"formato": FORMATO, "versao": lista.versao, "lido_em": lista.lido_em, "janela": list(lista.janela),
               "a_conferir": sorted(lista.a_conferir),
               "pendentes": {str(k): v for k, v in list(_ESTADO["pendentes"].items())},
               "faixas": {k: dict(v) for k, v in list(_ESTADO["faixas"].items())}, "n": len(lista.ordem),
               "gravado_em": time.time(), "campos": list(RegistroOS._fields)}

        def escrever(tmp):
            with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=5, newline="\n") as f:
                f.write(json.dumps(cab, ensure_ascii=False, separators=(",", ":"), default=str) + "\n")
                for r in lista.ordem:
                    f.write(json.dumps(_para_disco(r), ensure_ascii=False, separators=(",", ":")) + "\n")
                f.write(json.dumps({"fim": len(lista.ordem)}) + "\n")
        try:
            _trocar_de_uma_vez(destino, escrever)
        except Exception as e:                                       # noqa: BLE001 — o disco não derruba a lista
            _ESTADO["disco"]["erro"] = "gravar: %s: %s" % (type(e).__name__, str(e)[:120])
            log.warning("lista central de OS: não gravei a cópia em disco (%s)", _ESTADO["disco"]["erro"])
            return False
        try:
            tamanho = os.path.getsize(destino)
        except OSError:
            tamanho = None
        _ESTADO["disco"].update(gravado_em=cab["gravado_em"], versao=lista.versao, bytes=tamanho, erro=None)
        return True


def _ler_disco():
    """(cabeçalho, {id: registro}) da cópia em disco, ou None: sem arquivo, ilegível, de outro formato, cortada no meio (o
    motivo fica no estado). Lida linha a linha: nunca o arquivo inteiro na memória. Nunca levanta."""
    arq = _caminho()
    if arq is None or not os.path.exists(arq):
        return None
    try:
        j = _Juntar()
        with gzip.open(arq, "rt", encoding="utf-8") as f:
            cab = json.loads(f.readline() or "null")
            if not isinstance(cab, dict) or cab.get("formato") != FORMATO:
                raise ValueError("formato %r, o esperado é %d" % (cab.get("formato") if isinstance(cab, dict) else None,
                                                                  FORMATO))
            if cab.get("campos") != list(RegistroOS._fields):
                raise ValueError("os campos do registro mudaram desde a gravação")
            n = int(cab.get("n"))
            por_id: dict = {}
            for _ in range(n):
                linha = f.readline()
                if not linha:
                    raise ValueError("a cópia acabou antes das %d OS que o cabeçalho diz" % n)
                r = _do_disco(json.loads(linha), j)
                por_id[r.id] = r
            if json.loads(f.readline() or "null") != {"fim": n}:
                raise ValueError("a cópia não tem o fecho (foi cortada no meio)")
        return cab, por_id
    except (OSError, EOFError, ValueError, TypeError, KeyError, IndexError, struct.error, zlib.error) as e:
        _ESTADO["disco"]["erro"] = "ler: %s: %s" % (type(e).__name__, str(e)[:120])
        log.warning("lista central de OS: ignorei a cópia em disco (%s)", _ESTADO["disco"]["erro"])
        return None


def _boot() -> None:
    """A cópia em disco, uma vez só (quem chega com o boot em curso espera nele). Sem cópia, a lista nasce vazia e sem
    janela: as telas vão ao vivo até as faixas a encherem."""
    global _ATUAL
    with _TRAVA_BOOT:
        if _BOOT["feito"]:
            return
        try:
            carga = _ler_disco()
            if carga is not None:
                cab, por_id = carga
                versao = int(cab.get("versao") or 0)
                ids = set(por_id)
                lista = _indexar(por_id, lido_em=float(cab.get("lido_em") or 0.0),
                                 janela=tuple((cab.get("janela") or [None, None])[:2]), versao=versao,
                                 a_conferir={i for i in (cab.get("a_conferir") or ()) if i in ids})
                with _TRAVA:
                    if _ATUAL is None or not _ATUAL.por_id:
                        _ATUAL = lista
                        _SEQ["versao"] = max(_SEQ["versao"], versao)
                        _ESTADO["pendentes"].update({int(k): float(v) for k, v in (cab.get("pendentes") or {}).items()})
                        if isinstance(cab.get("faixas"), dict):
                            _ESTADO["faixas"].update(cab["faixas"])
                        _ESTADO["disco"].update(lido="cópia gravada em %s" % _hora(cab.get("gravado_em")),
                                                versao=versao, gravado_em=float(cab.get("gravado_em") or 0.0))
                log.info("lista central de OS: %d OS da cópia em disco", len(lista.por_id))
        except Exception as e:                                       # noqa: BLE001 — o boot não derruba quem só quer ler
            _ESTADO["disco"]["erro"] = "boot: %s: %s" % (type(e).__name__, str(e)[:120])
            log.warning("lista central de OS: o boot pelo disco falhou (%s)", _ESTADO["disco"]["erro"])
        finally:
            with _TRAVA:
                if _ATUAL is None:
                    _ATUAL = _vazia()
            _BOOT["feito"] = True


def _hora(ts) -> str:
    try:
        return datetime.fromtimestamp(float(ts), timezone(timedelta(hours=-3))).strftime("%d/%m %H:%M")
    except (TypeError, ValueError, OverflowError, OSError):
        return "?"


# ── o estado, para o Raio-X ────────────────────────────────────────────────────────────────────────────────────────────
def memoria_estimada(lista: Lista | None = None) -> float:
    """Os MB da lista: cada registro, texto e tupla contados UMA vez (os índices guardam os mesmos registros, e os textos que se
    repetem são um objeto só), mais o esqueleto dos índices. A amostra do "Dentro do Nexus" contaria os mesmos registros em
    cada índice e os textos repetidos em cada registro (o dobro, ou mais). Percorre a lista inteira: ~0,4 s com 36 mil OS; só o
    Raio-X chama. Perto do tracemalloc (medido com 36 mil OS sintéticas: 25,8 MB aqui, 23,9 MB nele; os índices copiados para
    medir saem um pouco maiores que os de verdade)."""
    lista = atual() if lista is None else lista
    vistos: set = set()
    total = 0

    def conta(o):
        nonlocal total
        if o is None or isinstance(o, bool) or id(o) in vistos or (isinstance(o, int) and -5 <= o <= 256):
            return
        vistos.add(id(o))
        total += sys.getsizeof(o)
        if isinstance(o, tuple):
            for x in o:
                conta(x)
    for r in lista.ordem:
        conta(r)
    for t in lista.por_codigo_ativo.values():
        conta(t)
    for indice in (lista.por_id, lista.por_folio, lista.por_codigo_ativo, lista.nomes_criadores):
        total += sys.getsizeof(dict(indice))
    total += sys.getsizeof(lista.ordem) + sys.getsizeof(lista.a_conferir)
    return round(total / 2**20, 1)


def estado(medir_memoria: bool = False) -> dict:
    """O que se sabe da lista, só com contagens, datas e ids (nunca o texto de uma OS nem o nome de alguém): quantas OS, quantas
    abertas (fora as "a conferir", cujo status é velho), "a conferir" e pendentes; a versão, a última leitura e a janela lida
    inteira; a última entrega de cada faixa; a medida dos campos que o REST trouxe; o disco; com `medir_memoria`, a memória da
    lista (`memoria_estimada`); e, com o leitor do servidor ligado, o que ele fez."""
    lista = atual()
    leitor = None
    if _LEITOR["estado"] is not None:
        try:
            leitor = _LEITOR["estado"]()
        except Exception as e:                                       # noqa: BLE001 — o estado nunca derruba quem o lê
            leitor = {"erro": "%s: %s" % (type(e).__name__, str(e)[:120])}
    memoria = None
    if medir_memoria:
        try:
            memoria = memoria_estimada(lista)
        except Exception:                                            # noqa: BLE001 — a medida nunca derruba o estado
            memoria = None
    pend = dict(_ESTADO["pendentes"])
    return {"n": len(lista.por_id),
            "abertas": sum(1 for r in lista.ordem if r.status_id in ABERTOS and r.id not in lista.a_conferir),
            "a_conferir": len(lista.a_conferir), "a_conferir_ids": sorted(lista.a_conferir)[:20],
            "pendentes": len(pend), "pendentes_ids": sorted(pend)[:20], "versao": lista.versao,
            "lido_em": lista.lido_em or None, "janela": lista.janela,
            "faixas": {k: dict(v) for k, v in list(_ESTADO["faixas"].items())},
            "campos": dict(_ESTADO["campos"]) if _ESTADO["campos"] else None, "disco": dict(_ESTADO["disco"]),
            "memoria_mb": memoria, "leitor": leitor}
