"""O cadastro do Nexus no PostgreSQL (API db_performace), workbook `cadastro_nexus`: uma aba por tabela, ID numérico
na 1ª coluna e ligação por ID.

Decisão do Levi (04/10/2026): a chave é o ID, não o código da usina — "puxar ID é mais leve e fica mais fácil entender
os inner joins". O código e os nomes de cada sistema ficam na aba `de_para`, que diz qual usina_id cada base chama de
quê. Assim qualquer setor faz `usinas.cliente_id = clientes.cliente_id` sem casar nome.

O que vai cifrado (a leitura da API não pede credencial): na usina, os campos marcados `sensivel` no esquema (receita,
CNPJ, contatos, endereço, CEP, coordenadas); da pessoa, tudo menos vínculo, cargo, equipe, status e supervisor. Vão
juntos, numa coluna `sensivel_cifrado` por linha, que só o Nexus abre (chave NEXUS_CHAVE_CADASTRO). Referência que não
casou com ninguém (o nome do Excel que não tem ficha) fica sem ID e com o texto lá dentro.

Estrutura de O&M de 10/2026: a aba `regioes_campo` (nome, base, `supervisor_campo_id` e `coordenador_campo_id`, com a
vaga escrita em `*_vaga` = sim/não) e, na `equipes`, `codigo` e `regiao_campo_id`. Pessoa só por ID: o nome do
supervisor e do coordenador fica no `sensivel_cifrado` da ficha dele, como o de todo mundo. As colunas novas das abas que
já existiam vão no FIM (depois do `sensivel_cifrado`): quem lê por posição não se perde.

A cifra usa nonce aleatório: cifrar de novo o mesmo texto daria outro valor, e a API guarda histórico por linha. Por
isso o texto cifrado que já está no banco é reaproveitado quando o conteúdo não mudou.

Gravação: o caminho provado do `falhas_performance` e do `de_para_trackers` — xlsx com a linha 1 de cabeçalho, célula
vazia = None, POST /api/workbooks/<chave>/sync-xlsx?replace=true. A API não apaga workbook: ele é criado uma vez só.
"""
import io
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone

from .calculos import ERRO
from .esquema import CLIENTES, EQUIPES, PESSOAS, REGIOES_CAMPO, USINAS
from .tipos import TIPOS_COM_MARCADOR, Legado, marcador, para_api

WORKBOOK = "cadastro_nexus"
NOME = "Cadastro Nexus (BD_Operações): IDs e ligações"
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
COL_CIFRA = "sensivel_cifrado"
_BRT = timezone(timedelta(hours=-3))

# (entidade, aba, coluna do ID). A ordem é a dos inner joins: quem é apontado vem antes. A região de campo (estrutura de
# O&M de 10/2026) entrou por último: aba nova no fim, as de antes ficam onde estavam.
TABELAS = ((CLIENTES, "clientes", "cliente_id"), (EQUIPES, "equipes", "equipe_id"),
           (PESSOAS, "pessoas", "pessoa_id"), (USINAS, "usinas", "usina_id"),
           (REGIOES_CAMPO, "regioes_campo", "regiao_campo_id"))
# Da pessoa, só isto sai em claro: nada aqui identifica alguém sozinho.
PESSOA_EM_CLARO = ("vinculo", "cargo", "equipe", "status", "supervisor")
# Na usina, além dos `sensivel` do esquema: a coluna "Ucs" do BD guarda o NÚMERO da UC (7 a 10 dígitos, igual à
# "Instalação", que é sensível), não a quantidade. Achado na conferência do 1º envio (04/10/2026): iria em claro em 9 usinas.
USINA_CIFRADA_NO_BANCO = ("ucs",)
# Para onde aponta cada referência (campo "ref" -> coluna de ID da tabela apontada).
ID_DE = {"clientes": "cliente_id", "equipes": "equipe_id", "pessoas": "pessoa_id", "usinas": "usina_id",
         "regioes_campo": "regiao_campo_id"}
CAB_DE_PARA = ["usina_id", "sistema", "chave_externa", "casou_por"]
# o `casou_por` da linha do BD_Operações: a chave é o ID do BD da ficha da usina (Registro mestre), não passa pelas
# decisões da tela Ligações (a troca dela na publicação não tem o "Manter a do banco": corrige-se na ficha)
COMO_ID_BD = "id do BD"
# `regioes_campo` (quantas regiões) entrou no fim da linha em 10/2026, pelo mesmo motivo das colunas novas
CAB_ATUALIZACAO = ["publicado_em", "clientes", "equipes", "pessoas", "usinas", "de_para", "sem_id_na_referencia",
                   "como_ler", "regioes_campo"]
# Campo que entrou depois da 1ª publicação vai no FIM da aba, depois do `sensivel_cifrado` (estrutura de O&M de 10/2026):
# a posição das colunas de antes não muda para quem lê por posição.
COLUNAS_NO_FIM = {"equipes": ("codigo", "regiao_campo"), "usinas": ("responsavel_om_vaga",)}


def _vaga(v) -> str:
    """A vaga escrita ("sim" = ninguém no cargo). Sem ela, quem lê o banco teria de deduzir a vaga do ID vazio."""
    return "sim" if v is None or v == "" else "não"


# Colunas que não são campo do esquema, calculadas na publicação: a vaga de cada cargo da região e a ordem da região na
# estrutura (a ordem da carga única: a das telas que listam as regiões).
DERIVADAS = {"regioes_campo": (("supervisor_campo_vaga", lambda r: _vaga(r.valor("supervisor_campo"))),
                               ("coordenador_campo_vaga", lambda r: _vaga(r.valor("coordenador_campo"))),
                               ("ordem", lambda r: r.ordem))}


class BancoErro(RuntimeError):
    pass


def _id(v):
    """ID do cadastro (texto "17") -> 17. Marcador, Legado ou vazio -> None (a ligação não existe)."""
    if v is None or isinstance(v, Legado) or marcador(v) or v == "":
        return None
    s = str(v).strip()
    if not s.isdigit():
        raise BancoErro(f"ID não numérico no cadastro: {s!r}")
    return int(s)


def _valor(c, v):
    if v is None:
        return None
    if isinstance(v, str) and marcador(v) and c.tipo in TIPOS_COM_MARCADOR:
        return None                     # "N/A" numa coluna de número ou data: no banco é vazio
    v = para_api(c.tipo, v)
    if isinstance(v, bool):
        return "sim" if v else "não"
    return v


def _coluna(c) -> str:
    return f"{c.id}_id" if c.tipo == "ref" and not c.id.endswith("_id") else c.id


def _em_claro(ent, c) -> bool:
    if c.sensivel:
        return False
    if ent is PESSOAS:
        return c.id in PESSOA_EM_CLARO
    return not (ent is USINAS and c.id in USINA_CIFRADA_NO_BANCO)


def _cabecalho(ent, col_id, aba=None):
    no_fim = COLUNAS_NO_FIM.get(aba, ())
    cab = [col_id]
    for c in ent.campos:
        if _em_claro(ent, c) and c.id not in no_fim:
            cab.append(_coluna(c))
    cab += [col for col, _ in DERIVADAS.get(aba, ())]
    return (cab + ["excluido", "versao", "alterado_em", COL_CIFRA]
            + [_coluna(ent.campo(cid)) for cid in no_fim if _em_claro(ent, ent.campo(cid))])


def _cifra(cofre, ent, id_, segredo: dict, anteriores: dict):
    if not segredo:
        return None
    texto = json.dumps(segredo, ensure_ascii=False, sort_keys=True)
    contexto = f"banco/{ent.id}/{id_}"
    antigo = anteriores.get(id_)
    if antigo and cofre.eh_cifrado(antigo):
        try:
            if cofre.decifrar(antigo, contexto) == texto:
                return antigo               # nada mudou: a linha do banco fica intocada
        except Exception:                   # noqa: BLE001 — cifrado com outra chave ou outro contexto: refaz
            pass
    return cofre.cifrar(texto, contexto)


def tabelas(srv, cofre, anteriores: dict | None = None) -> dict:
    """{aba: (cabecalho, linhas)} do cadastro inteiro. `anteriores` = {aba: {id: sensivel_cifrado}} do banco."""
    anteriores = anteriores or {}
    out, sem_id = {}, 0
    for ent, aba, col_id in TABELAS:
        cab = _cabecalho(ent, col_id, aba)
        linhas = []
        regs = sorted(srv.registros(ent.id, incluir_excluidos=True), key=lambda r: _id(r.id))
        for r in regs:
            if r.ilegivel:
                raise BancoErro(f"{ent.plural} {r.id} não abre com a chave atual: não publico um cadastro pela metade")
            id_ = _id(r.id)
            linha, segredo = {col_id: id_}, {}
            for c in ent.campos:
                v = r.valor(c.id)
                if v is ERRO:       # fórmula que no Excel dava #ERRO (ex.: base da equipe sem endereço legível)
                    v = None
                if not _em_claro(ent, c):
                    if v is not None:
                        segredo[c.id] = para_api(c.tipo, v)
                    continue
                if c.tipo == "ref":
                    linha[_coluna(c)] = _id(v)
                    if isinstance(v, Legado):
                        segredo[f"{c.id}_texto"] = v.texto      # nome que não casou: guarda, mas não em claro
                        sem_id += 1
                    continue
                linha[_coluna(c)] = _valor(c, v)
            for col, f in DERIVADAS.get(aba, ()):
                linha[col] = f(r)
            linha.update({"excluido": "sim" if r.excluido else "não", "versao": r.versao,
                          "alterado_em": r.alterado_em or None,
                          COL_CIFRA: _cifra(cofre, ent, id_, segredo, anteriores.get(aba, {}))})
            linhas.append([linha.get(k) for k in cab])
        out[aba] = (cab, linhas)
    out["_sem_id"] = sem_id
    return out


# ── de-para: o que cada base chama de cada usina ───────────────────────────────────────────────────────────────

def norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\s*-\s*[a-z]{2}\s*$", "", s.strip())          # " - SP" do Fracttal
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def sufixo_codigo(c) -> str:
    """"ATHN-MAB100" e "MAB100" -> "MAB100": as bases da API gravam com e sem o prefixo do cliente."""
    c = str(c or "").strip().upper()
    return c.split("-", 1)[1] if "-" in c else c


def codigo_do_equipamento(c) -> str | None:
    """Código da usina dentro do código de equipamento do Fracttal, que vem em dois formatos: "MAB100-INVR2.4" e
    "THPN-SDI100-INVR11.1" (com o prefixo do cliente). Devolve "MAB100" ou "THPN-SDI100". Ler só o 1º pedaço tomava o
    prefixo "THPN" por código e derrubou a medição de 04/10 para 47%; lendo os dois formatos, casam 132 de 142."""
    partes = str(c or "").strip().upper().split("-")
    if re.fullmatch(r"[A-Z]{3}\d{3}", partes[0]):
        return partes[0]
    if len(partes) > 1 and re.fullmatch(r"[A-Z]{3}\d{3}", partes[1]):
        return f"{partes[0]}-{partes[1]}"
    return None


SEM_PAR = "sem par no cadastro"
# a chave que só liga pela decisão da tela (`so_decisao` no item: os projetos da FAMA, 11/11/2026, `ligacao_fama.py`)
A_DECIDIR = "a decidir na tela (só a ligação decidida vale)"


def ignorado(regras, sistema, chave) -> str | None:
    """Decisões que tiram uma linha da conta ("TESTE é teste", "Porteiras não entra no BD"). Cada regra:
    {"contem": texto, "sistema": opcional, "motivo": texto} ou, vinda da tela, {"chave": a chave exata, ...}."""
    k = norm(chave)
    for r in regras or ():
        if r.get("sistema") and r["sistema"] != sistema:
            continue
        if r.get("chave") is not None:
            if str(r["chave"]) == str(chave):
                return f"ignorado: {r['motivo']}"
            continue
        if norm(r.get("contem")) and norm(r["contem"]) in k:
            return f"ignorado: {r['motivo']}"
    return None


def _decisoes(regras):
    """Aceita a lista antiga (só "ignorar") ou o dicionário da tela de Ligações (ligar, desligar, ignorar)."""
    if isinstance(regras, dict):
        return regras.get("ignorar") or [], regras.get("ligar") or [], regras.get("desligar") or []
    return regras or [], [], []


def _quando_curto(iso) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m")
    except (TypeError, ValueError):
        return ""


def _pela_ponte(it: dict, ids: list, como, ligado: dict, por_norma: dict) -> tuple[list, str | None]:
    """A `ponte` = (sistema, chave, via): a chave que OUTRA base dá a este item (a tabela de equipamentos do
    BD_Performance dá à aba de geração o nome da usina no Fracttal). O item liga à usina a que aquele sistema ligou a
    chave, se for UMA (Levi, 08/10/2026: "se liga ao fractall e aí você ligaria o fractal as usinas do BD_Operações e
    fecharia esse ciclo"). `ids`/`como` = o que os caminhos antigos (igual_a, código, nome) deram.
    - A ponte liga e o caminho antigo não diz nada, diz a mesma usina ou diz duas usinas entre as quais está a da ponte
      (o casamento por potência que soma "X 1" e "X 2" numa linha não decide; a tabela decide): vale a ponte
      (`casou_por` = o caminho).
    - Os dois discordam: ninguém liga e o `casou_por` mostra os dois (ligação errada é pior que faltando).
    - A ponte não fecha (sem linha na tabela, nome fora do de-para, chave do Fracttal ignorada, de 2 usinas ou sem par):
      vale o caminho antigo; se ele também não liga, o `casou_por` diz o motivo da ponte.
    O nome acha a chave exata ou, sem ela, a ÚNICA chave do sistema com o mesmo nome normalizado ("Athon -  Timon 1"
    com dois espaços na tabela do Fracttal)."""
    motivo = it.get("ponte_motivo")
    ids_p, como_p = [], None
    if it.get("ponte"):
        sistema, nome, via = (str(x) for x in it["ponte"])
        chave = nome if (sistema, nome) in ligado else None
        if chave is None:
            cands = por_norma.get((sistema, norm(nome)), set())
            if len(cands) == 1:
                chave = next(iter(cands))
            else:
                motivo = (f"nome do Fracttal casa {len(cands)} chaves do de-para" if cands
                          else "nome do Fracttal fora do de-para")
        if chave is not None:
            ids_f, como_f = ligado[(sistema, chave)]
            if str(como_f or "").startswith("ignorado"):
                motivo = f"chave do Fracttal {como_f}"
            elif len(ids_f) == 1:
                ids_p, como_p = list(ids_f), f"{via} ({como_f})"
            elif ids_f:
                motivo = f"chave do Fracttal de {len(ids_f)} usinas"
            else:
                motivo = f"chave do Fracttal {como_f or SEM_PAR}"
        motivo = f"{via}: {motivo}" if motivo else None
    if ids_p:
        if not ids or set(ids_p) <= set(ids):
            return ids_p, como_p
        return [], f"conflito: {como_p} = usina {ids_p[0]}; {como} = usina {'/'.join(str(i) for i in sorted(ids))}"
    if ids:
        return ids, como
    return [], (f"{como or SEM_PAR} ({motivo})" if motivo else como)


def de_para(srv, fontes: dict, regras=None) -> list[list]:
    """Uma linha por chave externa de cada base: a usina_id a que ela liga e COMO ligou, ou por que não ligou.
    `fontes` = {sistema: [{"chave", "codigo", "nome", "cliente", "nomes", "cidade", "uf", "mwp", "dica"}]}.

    Ordem: regra de ignorar; código (o inteiro, com o prefixo do cliente, depois só o "AAA999": "IPX100" é de duas
    usinas, "2C-IPX100" de uma); nome do Fracttal ("Cliente - Usina - UF"); e, para base sem código, o casamento por
    nome de `casamento.py` (só dentro do cliente: E1 e Thopen têm usinas de mesmo nome e são usinas diferentes). A
    `dica` é a usina que outra fonte já conferida aponta (o de-para de trackers): sem casamento, ela liga; contra o
    casamento, não liga ninguém. Nome ou código que serve a duas usinas não casa: ligação errada é pior que faltando.

    Geração em linhas (08/10/2026): a aba do BD_Thopen que é a mesma usina de uma chave já casada de outro sistema traz
    `igual_a` = (sistema, chave) e herda a ligação dela, decisões da tela inclusas (a fonte de referência vem antes em
    `fontes`); o código achado em outra aba da mesma base (a "Info Geral" do BD_Performance) traz `codigo_de`, que fica
    escrito no `casou_por` ("código (Info Geral)"), para a linhagem dizer de onde veio. A `ponte` (a tabela de
    equipamentos do BD_Performance: aba -> nome no Fracttal) vem antes desses caminhos: ver `_pela_ponte`."""
    from . import casamento as K
    ignorar, ligar, desligar = _decisoes(regras)
    manual = {(d["sistema"], str(d["chave"])): d for d in ligar}
    vetado = {(d["sistema"], str(d["chave"]), int(d["usina_id"])) for d in desligar}
    existe = {_id(u.id) for u in srv.registros("usinas")}
    por_cod, por_cheio, por_nome, por_cliente = {}, {}, {}, {}
    for u in srv.registros("usinas"):
        uid = _id(u.id)
        cheio = str(u.valor("codigo") or "").strip().upper()
        cod = sufixo_codigo(cheio)
        if cod and not marcador(cod) and re.fullmatch(r"[A-Z]{3}\d{3}", cod):
            por_cod.setdefault(cod, set()).add(uid)
            por_cheio.setdefault(cheio, set()).add(uid)
        cliente = srv.titulo_de("clientes", u.valor("cliente"))
        por_nome.setdefault(norm(f"{cliente} - {u.valor('nome')}"), set()).add(uid)
        pot = u.valor("potencia_contratual")
        por_cliente.setdefault(norm(cliente), []).append({
            "id": uid, "nome": u.valor("nome"), "cidade": u.valor("cidade"), "uf": u.valor("uf"),
            "mwp": float(pot) if isinstance(pot, (int, float)) and not isinstance(pot, bool) else None})
    linhas = [[_id(u.id), "BD_Operações", u.valor("id_bd"), COMO_ID_BD]
              for u in srv.registros("usinas") if u.valor("id_bd")]
    ligado_por_nome = {}                    # chave externa (ex.: nome no Fracttal) -> usina_id, para as dicas
    ligado = {}                             # (sistema, chave) -> ([usina_id], como), para o `igual_a` de outra fonte
    por_norma = {}                          # (sistema, chave normalizada) -> {chaves}, para a `ponte` achar a chave
    for sistema, itens in fontes.items():
        vistos = set()
        for it in itens:
            m = manual.get((sistema, str(it["chave"])))
            ids, como = [], None if m else ignorado(ignorar, sistema, it["chave"])
            cheio = str(it.get("codigo") or "").strip().upper()
            cod = sufixo_codigo(cheio)
            ref = tuple(str(x) for x in it["igual_a"]) if it.get("igual_a") else None
            ids_ref, como_ref = ligado.get(ref, ([], None)) if ref else ([], None)
            if m:                                   # quem corrigiu na tela vence qualquer regra automática
                if int(m["usina_id"]) in existe:
                    # só o dia, nunca quem: o de_para é publicado, e a API do banco tem leitura aberta (regra 8; até
                    # 13/10/2026 ia o "quem" da decisão, que no login pelo Fracttal é o e-mail e o nome). Quem decidiu
                    # fica na decisão local (de_para_regras.json), que a seção Ligações mostra.
                    dia = _quando_curto(m.get("quando"))
                    ids, como = [int(m["usina_id"])], f"manual ({dia})" if dia else "manual"
                else:
                    como = "manual aponta usina que não existe mais"
            elif como:
                pass
            elif it.get("so_decisao"):              # a FAMA (11/11/2026): a proposta pelo nome é só sugestão na tela
                como = A_DECIDIR
            elif it.get("pela_estrutura") and int(it["pela_estrutura"]) in existe:
                # o plant_id da plataforma (12/11/2026): a usina da chave do supervisório na estrutura das usinas
                ids, como = [int(it["pela_estrutura"])], "chave do supervisório"
            elif ids_ref:                           # a mesma usina de uma chave já casada: herda (1 ou 2 usinas)
                ids, como = list(ids_ref), f"igual a {ref[0]}"
            elif como_ref and como_ref.startswith("ignorado"):
                como = como_ref                     # a chave de referência foi tirada da conta: a aba também
            elif "-" in cheio and len(por_cheio.get(cheio, ())) == 1:
                ids, como = list(por_cheio[cheio]), "código"
            elif cod and len(por_cod.get(cod, ())) == 1:
                ids, como = list(por_cod[cod]), "código"
            elif it.get("nomes") and it.get("cliente"):
                r = K.casar(it, por_cliente.get(norm(it["cliente"]), []))
                dica = it.get("dica")
                if dica is not None and isinstance(dica, str):
                    dica = ligado_por_nome.get(dica) or next(iter(por_nome.get(norm(dica), ())), None)
                if r and (dica is None or dica in r[0]):
                    ids, como = r
                    como += " + de-para de trackers" if dica is not None else ""
                elif r is None and dica is not None:
                    ids, como = [dica], "de-para de trackers"
                else:
                    como = "conflito com o de-para de trackers" if r else None
            elif it.get("nome"):
                nome = norm(f"{it['cliente']} - {it['nome']}") if it.get("cliente") else norm(it["nome"])
                if len(por_nome.get(nome, ())) == 1:
                    ids, como = list(por_nome[nome]), "nome"
            if not m and (it.get("ponte") or it.get("ponte_motivo")) and not str(como or "").startswith("ignorado"):
                ids, como = _pela_ponte(it, ids, como, ligado, por_norma)
            if ids and not m and any((sistema, str(it["chave"]), i) in vetado for i in ids):
                ids = [i for i in ids if (sistema, str(it["chave"]), i) not in vetado]
                como = como if ids else "desligado à mão"
            if ids and it.get("origem") and not como.startswith(("código", "manual")):
                como = f"{como} ({it['origem']})"       # o nome veio de outro campo (ex.: a localização no Fracttal)
            if ids and como == "código" and it.get("codigo_de"):
                como = f"código ({it['codigo_de']})"    # o código não é a chave: veio de outra aba da mesma base
            ligado[(sistema, str(it["chave"]))] = (ids, como)
            por_norma.setdefault((sistema, norm(it["chave"])), set()).add(str(it["chave"]))
            if len(ids) == 1:
                ligado_por_nome[it["chave"]] = ids[0]
            for uid in ids or [None]:
                if (uid, it["chave"]) not in vistos:
                    vistos.add((uid, it["chave"]))
                    linhas.append([uid, sistema, it["chave"], como or SEM_PAR])
    return sorted(linhas, key=lambda l: (l[1], l[0] if l[0] is not None else 10 ** 9, str(l[2])))


# ── arquivo e envio ────────────────────────────────────────────────────────────────────────────────────────────

def montar(srv, cofre, fontes: dict | None = None, anteriores: dict | None = None, regras=None) -> dict:
    t = tabelas(srv, cofre, anteriores)
    sem_id = t.pop("_sem_id")
    dp = de_para(srv, fontes or {}, regras)
    t["de_para"] = (CAB_DE_PARA, dp)
    agora = datetime.now(_BRT).isoformat(timespec="seconds")
    t["atualizacao"] = (CAB_ATUALIZACAO, [[agora, len(t["clientes"][1]), len(t["equipes"][1]), len(t["pessoas"][1]),
                                           len(t["usinas"][1]), len(dp), sem_id,
                                           "liga por ID: usinas.cliente_id = clientes.cliente_id; "
                                           "equipes.regiao_campo_id = regioes_campo.regiao_campo_id; "
                                           "sensivel_cifrado só abre no Nexus", len(t["regioes_campo"][1])]])
    return t


def xlsx_bytes(t: dict) -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)
    for aba, (cab, linhas) in t.items():
        ws = wb.create_sheet(aba)
        ws.append(cab)
        for l in linhas:
            ws.append([None if v == "" else v for v in l])    # o sync recusa texto vazio
        ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def ler_anteriores(base: str, sessao=None) -> dict:
    """{aba: {id: sensivel_cifrado}} do que já está no banco, para não recifrar o que não mudou."""
    import requests
    s = sessao or requests
    base = base.rstrip("/")
    abas = {x["sheet_name"]: x["id"] for x in s.get(f"{base}/api/sheets", timeout=60).json()
            if x.get("workbook_key") == WORKBOOK}
    out = {}
    for aba, col_id in ((a, c) for _, a, c in TABELAS):
        if aba not in abas:
            continue
        m, offset = {}, 0
        while True:
            r = s.get(f"{base}/api/sheets/{abas[aba]}/rows", params={"limit": 1000, "offset": offset}, timeout=60)
            r.raise_for_status()
            rows = r.json()
            rows = rows.get("rows", rows) if isinstance(rows, dict) else rows
            for x in rows:
                d = dict(zip(x.get("headers") or [], x.get("values") or []))
                if d.get(col_id) is not None and d.get(COL_CIFRA):
                    m[int(d[col_id])] = d[COL_CIFRA]
            if len(rows) < 1000:
                break
            offset += 1000
        out[aba] = m
    return out


def ler_de_para(base: str, sessao=None) -> list[dict]:
    """As linhas do de-para que o banco tem agora (`cadastro_nexus · de_para`); o livro sem a aba = []. A leitura que
    falha SOBE: sem saber o que o banco tem, a publicação não compara e não sai."""
    import requests
    s = sessao or requests
    base = base.rstrip("/")
    sid = next((x["id"] for x in s.get(f"{base}/api/sheets", timeout=60).json()
                if x.get("workbook_key") == WORKBOOK and x.get("sheet_name") == "de_para"), None)
    if sid is None:
        return []
    out, offset = [], 0
    while True:
        r = s.get(f"{base}/api/sheets/{sid}/rows", params={"limit": 1000, "offset": offset}, timeout=60)
        r.raise_for_status()
        rows = r.json()
        rows = rows.get("rows", rows) if isinstance(rows, dict) else rows
        out += [dict(zip(x.get("headers") or [], x.get("values") or [])) for x in rows]
        if len(rows) < 1000:
            return out
        offset += 1000


def _ligada(v) -> bool:
    return v not in (None, "", "None")


def _chave_comparavel(v) -> str:
    """A chave externa como o banco pode devolvê-la: o número inteiro em qualquer forma ("10.0", 10, " 10 ") é "10", a
    regra do `fato_os_fama.id_fama` (a chave da FAMA é o id do projeto, 11/11/2026: com "10.0" de volta do banco, toda
    publicação depois da 1ª ligação travaria em "perderia N ligações"). Nome e código ficam exatamente como eram."""
    s = str(v)
    try:
        f = float(s)
    except ValueError:
        return s
    return str(int(f)) if f.is_integer() else s


def perdas_de_para(novas: list[list], no_banco: list[dict]):
    """As ligações que o banco tem (a chave ligada a uma usina) e que a publicação `novas` (linhas de CAB_DE_PARA)
    perderia: a chave some, ou fica sem usina. Counter {sistema: quantas}. A troca de usina não conta aqui: tem a regra
    dela (`chaves_que_trocariam`). O caso que criou a regra: 09/11/2026, 16:44, o "Publicar no banco" do servidor recalculou o de-para
    com as bases que ele lera em 07/10, sem as abas do BD_Thopen e do BD_Performance, e 187 ligações sumiram do banco;
    a geração do Nexus, que acha a usina só por elas, ficou sem usina em todas as linhas na remontagem seguinte."""
    from collections import Counter
    return Counter(str(d.get("sistema")) for d in chaves_que_perderia(novas, no_banco))


def chaves_que_perderia(novas: list[list], no_banco: list[dict]) -> list[dict]:
    """As linhas do de-para do banco (ligadas a uma usina) que a publicação `novas` perderia, uma a uma: é o que a tela
    mostra (12/11/2026: a mensagem só dizia quantas e de que base, e não havia como saber qual chave ligar)."""
    nova = {(str(l[1]), _chave_comparavel(l[2])): l[0] for l in novas}
    return [d for d in no_banco if _ligada(d.get("usina_id"))
            and not _ligada(nova.get((str(d.get("sistema")), _chave_comparavel(d.get("chave_externa")))))]


def chaves_que_trocariam(novas: list[list], no_banco: list[dict]) -> list[dict]:
    """As chaves que o banco liga a usina e que a publicação `novas` ligaria a um conjunto DIFERENTE de usinas (outra,
    uma a menos ou uma a mais) por regra automática: [{"sistema", "chave_externa" (como esta máquina a escreve), "de":
    [usinas no banco], "para": [usinas na publicação], "casou_por" (o da publicação)}], por sistema e chave. Não entra: a
    chave que fica sem usina (é perda, `chaves_que_perderia`) e a que alguém ligou à mão nesta máquina (o "manual" já é
    escolha de alguém; a troca que ninguém escolheu é que não pode passar calada). `novas` são as linhas que ESTA máquina
    calculou (`de_para`), sem as mantidas do banco: a chave que ela não leu não é decisão dela, e a tela e a rota têm de
    contar o mesmo conjunto (revisão de 12/11/2026: a rota contava depois de juntar as mantidas e recusava uma troca que
    a tela não mostrava). A usina a mais também conta: a 2ª usina errada é o mesmo erro, somado em vez de trocado.

    O caso (12/11/2026): a trava só barrava a chave que ficava SEM usina. Na primeira publicação do servidor depois do
    conserto das mantidas, a chave do Fracttal de um cliente saiu da usina dele para a usina de outro cliente na mesma
    cidade: a usina certa não tinha código no cadastro, e o código do local no Fracttal casou pelo sufixo com o da outra.
    As OS daquele local iriam para a usina errada, e só a conferência com a cópia de antes mostrou."""
    antes: dict = {}
    for d in no_banco:
        uid = _inteiro(d.get("usina_id"))
        if uid is not None:
            antes.setdefault((str(d.get("sistema")), _chave_comparavel(d.get("chave_externa"))), set()).add(uid)
    agora: dict = {}
    for l in novas:
        a = agora.setdefault((str(l[1]), _chave_comparavel(l[2])), {"ids": set(), "chave": l[2], "como": None})
        uid = _inteiro(l[0])
        if uid is not None:
            a["ids"].add(uid)
            a["como"] = a["como"] or l[3]
    out = []
    for k in sorted(agora):
        a, de = agora[k], antes.get(k) or set()
        if not a["ids"] or not de or de == a["ids"] or str(a["como"] or "").startswith("manual"):
            continue
        out.append({"sistema": k[0], "chave_externa": a["chave"], "de": sorted(de), "para": sorted(a["ids"]),
                    "casou_por": a["como"]})
    return out


def assinatura_das_trocas(trocas: list[dict]) -> str:
    """A marca do conjunto de trocas (16 hex de um sha256). O "Publicar com as trocas" da tela a devolve, e o aceite só
    vale se o conjunto calculado na hora do clique for o que a tela mostrou: a ordem não muda a marca; outra chave, outra
    usina de antes ou outra usina de depois, muda."""
    import hashlib
    itens = sorted(json.dumps([str(t["sistema"]), _chave_comparavel(t["chave_externa"]), sorted(t["de"]),
                               sorted(t["para"])], ensure_ascii=False) for t in trocas)
    return hashlib.sha256("\n".join(itens).encode("utf-8")).hexdigest()[:16]


def _inteiro(v) -> int | None:
    """O id como o banco pode devolvê-lo ("7.0", 7, " 7 ") em inteiro; o que não é número inteiro, None."""
    try:
        f = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return int(f) if f.is_integer() else None


def ligacoes_que_nao_li(novas: list[list], no_banco: list[dict], usinas) -> list[list]:
    """As ligações que o banco tem para chaves que ESTA máquina não leu (o par sistema e chave não aparece nas `novas`, nem
    ligado nem sem usina), como linhas de CAB_DE_PARA, para voltarem ao banco como estavam. Só a ligada, e só se a usina
    ainda está em `usinas` (os ids do cadastro que vai ser publicado); a que esta máquina leu e deixaria sem usina NÃO
    entra aqui: essa é a perda de verdade, e continua travando (`chaves_que_perderia`). A chave que o banco liga a duas
    usinas volta com as duas (revisão de 12/11/2026: voltava só a 1ª linha da chave, e a 2ª ligação sumia calada); a
    linha repetida no banco volta uma vez.

    O caso (12/11/2026): o banco tinha ligações publicadas pelo PC, de chaves que o servidor não lê (a usina que só a
    árvore de ativos do PC traz, o nome que mudou na fonte), e a trava de 10/11 recusava a publicação do servidor inteira,
    sem saída: não há o que ligar na tela para uma chave que a máquina não tem. O que a máquina não leu, ela não apaga."""
    lidas = {(str(l[1]), _chave_comparavel(l[2])) for l in novas}
    existe = {int(u) for u in usinas}
    out, vistas = [], set()
    for d in no_banco:
        uid = _inteiro(d.get("usina_id"))
        chave = (str(d.get("sistema")), _chave_comparavel(d.get("chave_externa")))
        if uid is None or uid not in existe or chave in lidas or (chave, uid) in vistas:
            continue
        vistas.add((chave, uid))
        out.append([uid, d.get("sistema"), d.get("chave_externa"), d.get("casou_por")])
    return out


def ids_das_usinas(t: dict) -> set[int]:
    """Os ids das usinas das tabelas que vão ser publicadas (`montar`)."""
    cab, linhas = t["usinas"]
    i = cab.index("usina_id")
    return {n for n in (_inteiro(l[i]) for l in linhas) if n is not None}


def juntar_ao_de_para(t: dict, mantidas: list[list]) -> None:
    """Põe as `mantidas` (`ligacoes_que_nao_li`) no de-para que vai ser publicado e acerta a conta dele na `atualizacao`."""
    t["de_para"][1].extend(mantidas)
    cab, linhas = t["atualizacao"]
    linhas[0][cab.index("de_para")] = len(t["de_para"][1])


def conferir_com_o_banco(t: dict, no_banco: list[dict]) -> dict:
    """As três regras da publicação contra o de-para que o banco tem, num lugar só, para TODO caminho que publica (o
    botão da tela e a `ferramentas/publicar_cadastro.py`): junta ao `t` as ligações de chaves que esta máquina não leu
    e devolve {"mantidas": linhas que voltaram como estavam, "perdidas": linhas do banco que ficariam sem usina (não
    publica), "trocas": chaves que mudariam de usina por regra automática (não publica sem o aceite da marca,
    `assinatura_das_trocas`)}. As trocas são contadas ANTES de juntar as mantidas: só nas chaves que esta máquina leu.

    O caso (12/11/2026): a ferramenta do PC enviava direto, sem regra nenhuma. Depois da publicação do servidor daquela
    noite o banco tinha ligações que só o servidor conhece (os projetos da FAMA, o plant_id da plataforma), e a
    ferramenta rodada no PC as apagaria todas; a regra que mora em uma rota só protege quem passa por ela."""
    trocas = chaves_que_trocariam(t["de_para"][1], no_banco)
    mantidas = ligacoes_que_nao_li(t["de_para"][1], no_banco, ids_das_usinas(t))
    if mantidas:
        juntar_ao_de_para(t, mantidas)
    return {"mantidas": mantidas, "perdidas": chaves_que_perderia(t["de_para"][1], no_banco), "trocas": trocas}


def sincronizar(conteudo: bytes, *, base: str, token: str, sessao=None) -> dict:
    """Cria o workbook só se faltar (a API não apaga workbook) e sincroniza com replace=true."""
    import requests
    s = sessao or requests
    base = base.rstrip("/")
    h = {"Authorization": f"Bearer {token}"}
    r = s.get(f"{base}/api/workbooks", headers=h, timeout=60)
    r.raise_for_status()
    if WORKBOOK not in {w.get("key") for w in r.json()}:
        s.post(f"{base}/api/workbooks", headers=h, json={"key": WORKBOOK, "display_name": NOME},
               timeout=60).raise_for_status()
    r = s.post(f"{base}/api/workbooks/{WORKBOOK}/sync-xlsx", headers=h, params={"replace": "true"},
               files={"file": (f"{WORKBOOK}.xlsx", conteudo, MIME_XLSX)}, timeout=300)
    r.raise_for_status()
    return r.json()
