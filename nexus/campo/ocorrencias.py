"""As ocorrências com plano de ação (Levi, 18/10/2026: "Próximas peças: o mapa das usinas e as ocorrências com plano de
ação. siga!"). A origem é o painel próprio de um supervisor (a ocorrência, o histórico e o plano de ação, em quadro e
lista); o objetivo é o de toda a Visão do responsável: largar o painel próprio e usar só o Nexus. Desenho e decisões em
docs/superpowers/specs/2026-10-18-ocorrencias-plano-de-acao-design.md; a tela em nexus/torres/campo/ocorrencias_tela.py.

O Nexus é a FONTE: livro `nexus_ocorrencias` · `fato_evento_ocorrencia`, registrado no catálogo antes da 1ª gravação
(regra 10), com a trava de livro que só cresce. 1 linha = 1 EVENTO sobre 1 ocorrência:
- `criou` e `dados`: a ocorrência inteira como ficou (título, usina, equipamento, criticidade, status, início, fim,
  descrição, OS do Fracttal e chamado); vale a última;
- `acao`: uma ação do plano (nova ou mudada, pelo `acao_id`) inteira como ficou (o texto, o responsável, o prazo e a
  situação); vale a última de cada ação;
- `andamento`: uma linha do histórico, com o dia e a hora.
Só acrescenta: nada se edita nem se apaga; o estado de agora sai dos eventos, na ordem da gravação (dois eventos no
mesmo segundo ficam na ordem em que foram gravados, como no acompanhamento da Engenharia).

A API do banco tem LEITURA ABERTA (nexus/dados/CLAUDE.md, regra 8): o título, a descrição, o chamado, o texto da ação, o
andamento, o nome do responsável da ação e quem fez vão só CIFRADOS (o Cofre, a chave do cadastro, como a observação do
responsável). Em claro só IDs, códigos e datas: a usina pelo `usina_id` do cadastro (escolhida na tela), o ativo pelo
código canônico e pelo `equipamento_id` da dimensão quando o código está lá (não liga = vazio), quem fez pelo `pessoa_id`
e pelo código do e-mail (`pessoa_hmac`), o responsável da ação pelo `pessoa_id` (escolhido na lista do cadastro), os
códigos de criticidade, status e situação, os dias (`data_id` e os papéis) e o número das OS do Fracttal.

Quem grava: o Responsável O&M (pelo login do Fracttal, em qualquer usina, como a observação: quem cobre as férias de
outro registra nas usinas dele) e o administrador, sempre com um login de pessoa (a senha de administrador não diz quem
é a pessoa, e o histórico guarda quem fez). Gravar troca o livro inteiro, relido do banco antes (leitura que falha não
grava: gravaria por cima do que há), uma gravação por vez neste processo (`_TRAVA`); `livros.publicar` confere antes e
depois. Duas máquinas gravando no mesmo segundo ainda podem perder um evento: o risco aceito nos outros livros do Nexus.
"""
import json
import re
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone

from flask import current_app

from ..dados import fatos as D
from ..dados import livros
from ..dados.equipamento import canon

LIVRO, NOME_LIVRO, ABA = "nexus_ocorrencias", "Nexus · ocorrências com plano de ação", "fato_evento_ocorrencia"
CAB = ("id", "registrado_em", "data_id", "ocorrencia_id", "evento", "acao_id", "usina_id", "usina_ligada_por",
       "codigo_ativo", "equipamento_id", "equipamento_ligado_por", "criticidade", "status", "data_id_inicio",
       "data_id_fim", "os", "pessoa_id", "pessoa_hmac", "responsavel_pessoa_id", "situacao", "data_id_prazo",
       "dados_cifrados")
EVENTOS = ("criou", "dados", "acao", "andamento")
# os domínios (o código vai ao banco; o rótulo, à tela). A criticidade e o status são os do painel do supervisor
CRITICIDADES = {"baixa": "Baixa", "media": "Média", "alta": "Alta", "muito_alta": "Muito alta"}
PESO = {"baixa": 1, "media": 2, "alta": 3, "muito_alta": 4}
STATUS = {"em_andamento": "Em andamento", "pausado": "Pausado", "finalizado": "Finalizado"}
SITUACOES = {"a_fazer": "A fazer", "em_andamento": "Em andamento", "concluida": "Concluída"}
TITULO_MAX, TEXTO_MAX, ACAO_MAX, CHAMADO_MAX, COD_MAX, OS_MAX = 120, 2000, 500, 120, 60, 10
# o piso das datas: "0202-10-15" (o ano com um dígito a menos, fácil de digitar no campo de data) virava um data_id de 7
# dígitos no acompanhamento da Engenharia, e o livro é para sempre. O prazo vai até 3 anos à frente pelo mesmo motivo
PISO = date(2024, 1, 1)
PRAZO_ANOS = 3
TTL_S = 60
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()
_CACHE: dict = {}


class Recusada(ValueError):
    """Nada foi gravado: o texto diz por quê, para a tela mostrar."""


def limpar() -> None:
    """Zera a cópia: quem acabou de gravar tem de se ver na próxima leitura."""
    _CACHE.clear()


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def _dia(v) -> date | None:
    """`data_id` (AAAAMMDD, número ou texto) -> date."""
    n = D._int(v)
    if not n:
        return None
    try:
        return datetime.strptime(str(n), "%Y%m%d").date()
    except ValueError:
        return None


def _id_dia(d: date | None) -> int | None:
    return int(d.strftime("%Y%m%d")) if d else None


def _quando(v) -> datetime | None:
    try:
        return datetime.fromisoformat(_txt(v).replace("Z", "+00:00")).astimezone(_BRT)
    except ValueError:
        return None


def _quando_txt(q: datetime | None) -> str:
    return q.strftime("%d/%m/%Y às %H:%M") if q else "—"


def _ctx(eid) -> str:
    return f"banco/ocorrencias/{eid}/dados"


def _cofre():
    chave = current_app.config.get("NEXUS_CHAVE_CADASTRO")
    if not chave:
        raise Recusada("Este Nexus não tem a chave do cadastro (NEXUS_CHAVE_CADASTRO): sem ela o texto não vai cifrado")
    from ..cadastro.cifra import Cofre
    return Cofre(chave)


def cofre_ou_nada():
    try:
        return _cofre()
    except Recusada:
        return None


def _banco():
    from . import visao
    return visao._base(), visao._sessao()


# ── ler ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
def ler(forcar: bool = False) -> dict:
    """{"eventos" (as linhas cruas), "lido_em", "erro"}, guardado por 1 minuto. Leitura que falha devolve a última boa com
    o erro; sem nenhuma, vazio com o erro (a tela diz que não leu, e não "nenhuma ocorrência")."""
    g = _CACHE.get("livro")
    if g and not forcar and time.time() - g["lido_em"] < TTL_S:
        return g
    try:
        eventos = livros.ler(*_banco(), LIVRO, ABA)
    except Exception as ex:      # noqa: BLE001 — banco fora, rede: a tela diz e segue
        erro = f"{type(ex).__name__}: {str(ex)[:160]}"
        if g:
            return dict(g, erro=erro, velha=True)
        return {"eventos": [], "lido_em": None, "erro": erro}
    g = {"eventos": eventos, "lido_em": time.time(), "erro": ""}
    _CACHE["livro"] = g
    return g


def _abre(cofre, l: dict) -> dict:
    if not cofre or not l.get("dados_cifrados"):
        return {}
    try:
        return json.loads(cofre.decifrar(_txt(l.get("dados_cifrados")), _ctx(_txt(l.get("id")))))
    except Exception:           # noqa: BLE001 — cifra de outra chave ou adulterada: sai sem nome nem texto
        return {}


def estado(eventos: list[dict], cofre=None, hoje: date | None = None) -> dict[str, dict]:
    """{ocorrencia_id: ocorrência} a partir dos eventos, na ordem da gravação. Evento sem o `criou` da ocorrência dele no
    livro fica fora (não há de que usina nem de que ocorrência ele é). Sem o `cofre` (sem a chave do cadastro), os
    códigos e as datas continuam e o texto sai vazio."""
    hoje = hoje or datetime.now(_BRT).date()
    ordem = {id(e): i for i, e in enumerate(eventos)}
    nunca = datetime.min.replace(tzinfo=_BRT)
    linhas = sorted(eventos, key=lambda e: (_quando(e.get("registrado_em")) or nunca, ordem[id(e)]))
    out: dict[str, dict] = {}
    for l in linhas:
        oid, ev = _txt(l.get("ocorrencia_id")), _txt(l.get("evento"))
        if not oid or ev not in EVENTOS:
            continue
        oc = out.get(oid)
        if oc is None and ev != "criou":
            continue
        dados, q = _abre(cofre, l), _quando(l.get("registrado_em"))
        quem = (dados.get("quem") or {}).get("nome") or ""
        if ev in ("criou", "dados"):
            if oc is None:
                oc = out[oid] = {"id": oid, "criada_em": q, "criada_por": quem, "acoes": [], "_acoes": {},
                                 "andamentos": []}
            oc.update(usina_id=D._id(l.get("usina_id")), cod=_txt(l.get("codigo_ativo")),
                      equipamento_id=D._int(l.get("equipamento_id")),
                      criticidade=_txt(l.get("criticidade")), status=_txt(l.get("status")),
                      inicio=_dia(l.get("data_id_inicio")), fim=_dia(l.get("data_id_fim")), os=_txt(l.get("os")),
                      titulo=dados.get("titulo") or "", descricao=dados.get("descricao") or "",
                      chamado=dados.get("chamado") or "", alterada_em=q, alterada_por=quem)
        elif ev == "acao":
            aid = _txt(l.get("acao_id"))
            if not aid:
                continue
            a = oc["_acoes"].get(aid)
            if a is None:
                a = oc["_acoes"][aid] = {"id": aid, "criada_em": q}
                oc["acoes"].append(a)
            a.update(texto=dados.get("texto") or "", responsavel_id=D._id(l.get("responsavel_pessoa_id")),
                     responsavel=dados.get("responsavel") or "", prazo=_dia(l.get("data_id_prazo")),
                     situacao=_txt(l.get("situacao")), alterada_em=q, alterada_por=quem)
            oc["alterada_em"] = q
        else:
            oc["andamentos"].insert(0, {"quando": q, "quando_txt": _quando_txt(q), "nome": quem,
                                        "texto": dados.get("texto") or ""})
            oc["alterada_em"] = q
    for oc in out.values():
        oc.pop("_acoes")
        oc["aberta"] = oc["status"] != "finalizado"
        for a in oc["acoes"]:
            a["aberta"] = a["situacao"] != "concluida"
            a["atrasada"] = bool(a["aberta"] and a["prazo"] and a["prazo"] < hoje)
        prazos = [a["prazo"] for a in oc["acoes"] if a["aberta"] and a["prazo"]]
        oc["proximo_prazo"] = min(prazos) if prazos else None
        oc["atrasada"] = bool(oc["aberta"] and oc["proximo_prazo"] and oc["proximo_prazo"] < hoje)
        oc["acoes_abertas"] = sum(a["aberta"] for a in oc["acoes"])
    return out


def ordenar(lista: list[dict]) -> list[dict]:
    """A ordem da lista (a do painel do supervisor): as abertas com prazo, a do prazo mais perto primeiro; as abertas sem
    prazo, a mais crítica e depois a mais antiga; as finalizadas no fim, a que terminou por último primeiro."""
    longe = date.max

    def chave(o):
        if not o["aberta"]:
            return (2, -(o["fim"] or o["inicio"] or date.min).toordinal(), o["id"])
        if o["proximo_prazo"]:
            return (0, o["proximo_prazo"].toordinal(), -PESO.get(o["criticidade"], 0), o["id"])
        return (1, -PESO.get(o["criticidade"], 0), (o["inicio"] or longe).toordinal(), o["id"])
    return sorted(lista, key=chave)


def abertas_por_usina(est: dict[str, dict]) -> dict[int, dict]:
    """{usina_id: {"n": quantas abertas, "pior": a criticidade mais alta delas}} (aberta = status diferente de
    finalizado), para a etiqueta da Visão geral."""
    out: dict[int, dict] = {}
    for o in est.values():
        if not o["aberta"] or not o["usina_id"]:
            continue
        u = out.setdefault(o["usina_id"], {"n": 0, "pior": o["criticidade"]})
        u["n"] += 1
        if PESO.get(o["criticidade"], 0) > PESO.get(u["pior"], 0):
            u["pior"] = o["criticidade"]
    return out


# ── gravar ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def pode_editar(admin: bool, responsavel_logado: str) -> bool:
    """Cria e edita: o administrador e quem é Responsável O&M de alguma usina mobilizada (pelo login do Fracttal)."""
    return bool(admin) or bool(responsavel_logado)


def _quem(usuario, pode: bool) -> dict:
    if not pode:
        raise Recusada("Só o Responsável O&M (pelo login do Fracttal) ou um administrador registra ocorrências")
    email = str((usuario or {}).get("email") or "").strip().lower()
    if not email:
        raise Recusada("Entre com o seu login (Fracttal ou Microsoft) para registrar: a senha de administrador não diz "
                       "quem é a pessoa")
    from .ligacao_cadastro import codigo_da_pessoa
    cfg = current_app.config
    codigo = codigo_da_pessoa(cfg.get("NEXUS_PESSOA_HMAC"), email)
    if not codigo:
        raise Recusada("Este Nexus não tem a chave do código da pessoa (NEXUS_PESSOA_HMAC)")
    if not cfg.get("GRIDCO_SQL_TOKEN"):
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN)")
    nome = " ".join(str((usuario or {}).get("nome") or "").split()) or email
    from . import visao
    try:
        pid = visao.pessoa_do_login(email, nome)
    except Exception:           # noqa: BLE001 — sem cadastro: fica o código do e-mail (regra 4: não liga = vazio)
        pid = None
    return {"email": email, "nome": nome, "hmac": codigo, "pessoa_id": pid}


def _linha(texto, maximo: int, falta: str, nome: str) -> str:
    """Uma linha só (o título, o chamado): os espaços repetidos viram um."""
    t = " ".join(str(texto or "").split())
    if falta and not t:
        raise Recusada(falta)
    if len(t) > maximo:
        raise Recusada(f"{nome} passou de {maximo} caracteres")
    return t


def _texto(texto, maximo: int, falta: str, nome: str) -> str:
    """Texto de várias linhas (a descrição, a ação, o andamento): as linhas ficam, os espaços repetidos de cada uma não."""
    t = "\n".join(" ".join(l.split()) for l in str(texto or "").strip().splitlines()).strip()
    if falta and not t:
        raise Recusada(falta)
    if len(t) > maximo:
        raise Recusada(f"{nome} passou de {maximo} caracteres")
    return t


def _data(v, campo: str, piso: date, teto: date, depois: str) -> date | None:
    """A data do <input type="date"> (AAAA-MM-DD); vazio = None; o resto é recusado com o porquê."""
    t = _txt(v)
    if not t:
        return None
    try:
        d = datetime.strptime(t, "%Y-%m-%d").date()
    except ValueError:
        raise Recusada(f"Data inválida no {campo}: escolha no calendário do campo") from None
    if d < piso:
        raise Recusada(f"Data inválida no {campo}: antes de {piso:%d/%m/%Y}")
    if d > teto:
        raise Recusada(depois)
    return d


def _os(v) -> str:
    """O número das OS do Fracttal: só algarismos, várias separadas por vírgula ("16034, 16040")."""
    t = _txt(v)
    if re.sub(r"[\d,;/\s]", "", t):
        raise Recusada("O número da OS do Fracttal só tem algarismos (separe várias com vírgula)")
    nums = re.findall(r"\d+", t)
    if len(nums) > OS_MAX or any(len(n) > 9 for n in nums):
        raise Recusada(f"Até {OS_MAX} OS do Fracttal, de até 9 algarismos cada")
    return ", ".join(nums)


def _codigo_ativo(v) -> str:
    c = canon(v)
    if "@" in c:              # vai em claro, e a API do banco tem leitura aberta
        raise Recusada("O código do ativo não pode ter e-mail: ele vai em claro no banco")
    if len(c) > COD_MAX:
        raise Recusada(f"O código do ativo passou de {COD_MAX} caracteres")
    return c


def _equipamento(cod: str) -> int | None:
    """O `equipamento_id` da dimensão de equipamento quando o código está lá; senão vazio (não liga = vazio: o código
    fica no fato, e a dimensão que crescer depois liga pelo código)."""
    if not cod:
        return None
    from . import visao
    try:
        dim = visao._livro("nexus_equipamentos", "dim_equipamento")
    except Exception:           # noqa: BLE001 — sem a dimensão, não liga
        return None
    return next((D._id(e.get("equipamento_id")) for e in dim if canon(e.get("codigo")) == cod), None)


def _campos(form: dict, hoje: date) -> dict:
    """Os campos da ocorrência validados, como vão ao estado (para comparar) e ao banco."""
    titulo = _linha(form.get("titulo"), TITULO_MAX, "Escreva o título da ocorrência", "O título")
    uid = D._id(form.get("usina_id"))
    if not uid:
        raise Recusada("Escolha a usina")
    from . import visao
    if uid not in visao._Base().mobilizadas:
        raise Recusada("Esta usina não está mobilizada no cadastro")
    crit, st = _txt(form.get("criticidade")), _txt(form.get("status"))
    if crit not in CRITICIDADES:
        raise Recusada("Escolha a criticidade")
    if st not in STATUS:
        raise Recusada("Escolha o status")
    ini = _data(form.get("inicio"), "início", PISO, hoje, "O início não pode ser depois de hoje")
    if not ini:
        raise Recusada("Escolha o início da ocorrência")
    fim = _data(form.get("fim"), "fim", PISO, hoje, "O fim não pode ser depois de hoje")
    if fim and fim < ini:
        raise Recusada("O fim não pode ser antes do início")
    if fim and st != "finalizado":
        raise Recusada("Com a data de fim, o status é Finalizado: mude o status ou apague o fim")
    if st == "finalizado" and not fim:
        fim = hoje                      # finalizada sem o fim termina hoje (o campo diz isso na tela)
    return {"titulo": titulo, "usina_id": uid, "cod": _codigo_ativo(form.get("codigo_ativo")), "criticidade": crit,
            "status": st, "inicio": ini, "fim": fim,
            "descricao": _texto(form.get("descricao"), TEXTO_MAX, "", "A descrição"),
            "chamado": _linha(form.get("chamado"), CHAMADO_MAX, "", "O chamado"), "os": _os(form.get("os"))}


def _evento(cofre, evento: str, quem: dict, oid: str, usina_id: int, dados: dict, **cols) -> dict:
    eid = uuid.uuid4().hex[:12]
    agora = datetime.now(timezone.utc)
    linha = {c: None for c in CAB}
    linha.update(id=eid, registrado_em=agora.strftime("%Y-%m-%dT%H:%M:%SZ"),
                 data_id=int(agora.astimezone(_BRT).strftime("%Y%m%d")), ocorrencia_id=oid, evento=evento,
                 usina_id=usina_id, pessoa_id=quem["pessoa_id"], pessoa_hmac=quem["hmac"], **cols)
    dados = dict(dados, quem={"nome": quem["nome"], "email": quem["email"]})
    linha["dados_cifrados"] = cofre.cifrar(json.dumps(dados, ensure_ascii=False), _ctx(eid))
    return linha


def _evento_ocorrencia(cofre, evento: str, quem: dict, oid: str, c: dict) -> dict:
    eq = _equipamento(c["cod"])
    return _evento(cofre, evento, quem, oid, c["usina_id"],
                   {"titulo": c["titulo"], "descricao": c["descricao"], "chamado": c["chamado"]},
                   usina_ligada_por="tela", codigo_ativo=c["cod"] or None, equipamento_id=eq,
                   equipamento_ligado_por="codigo_ativo" if eq else None, criticidade=c["criticidade"],
                   status=c["status"], data_id_inicio=_id_dia(c["inicio"]), data_id_fim=_id_dia(c["fim"]),
                   os=c["os"] or None)


def _reler() -> list[dict]:
    """O livro relido do banco agora, sem a cópia: gravar sobre uma leitura velha apagaria o que outra pessoa gravou. A
    leitura que falha sobe (não grava); a listagem que omitiu o livro a trava do `livros.publicar` recusa."""
    return livros.ler(*_banco(), LIVRO, ABA)


def _publicar(eventos: list[dict]) -> None:
    base, sessao = _banco()
    livros.publicar(LIVRO, NOME_LIVRO, {ABA: (list(CAB), [[e.get(c) for c in CAB] for e in eventos])},
                    base=base, token=current_app.config["GRIDCO_SQL_TOKEN"], sessao=sessao)
    limpar()


def _da_ocorrencia(lido: list[dict], oid, cofre=None) -> dict:
    o = estado(lido, cofre).get(_txt(oid))
    if not o:
        raise Recusada("Não achei esta ocorrência: recarregue a página")
    return o


def criar(form: dict, usuario, pode: bool, hoje: date | None = None) -> dict:
    """Uma ocorrência nova (evento `criou`). Devolve a linha gravada (o `ocorrencia_id` leva à página dela)."""
    quem = _quem(usuario, pode)
    hoje = hoje or datetime.now(_BRT).date()
    cofre = _cofre()
    c = _campos(form, hoje)
    with _TRAVA:
        lido = _reler()
        nova = _evento_ocorrencia(cofre, "criou", quem, uuid.uuid4().hex[:12], c)
        _publicar(lido + [nova])
    return nova


_COMPARA = ("titulo", "usina_id", "cod", "criticidade", "status", "inicio", "fim", "descricao", "chamado", "os")


def editar(oid: str, form: dict, usuario, pode: bool, hoje: date | None = None) -> dict:
    """A ocorrência mudada (evento `dados`, com todos os campos como ficaram). Nada mudou = recusa (não grava à toa)."""
    quem = _quem(usuario, pode)
    hoje = hoje or datetime.now(_BRT).date()
    cofre = _cofre()
    c = _campos(form, hoje)
    with _TRAVA:
        lido = _reler()
        o = _da_ocorrencia(lido, oid, cofre)
        if all(c[k] == o.get(k) for k in _COMPARA):
            raise Recusada("Nada mudou")
        nova = _evento_ocorrencia(cofre, "dados", quem, o["id"], c)
        _publicar(lido + [nova])
    return nova


def salvar_acao(oid: str, form: dict, usuario, pode: bool, pessoas: list[dict], hoje: date | None = None) -> dict:
    """Uma ação do plano, nova (`acao_id` vazio) ou mudada, inteira como ficou. O responsável é uma pessoa da lista do
    cadastro (`pessoas`, de `pessoas_do_cadastro`): fica o `pessoa_id`, e o nome vai cifrado."""
    quem = _quem(usuario, pode)
    hoje = hoje or datetime.now(_BRT).date()
    texto = _texto(form.get("texto"), ACAO_MAX, "Escreva a ação", "A ação")
    pid = D._id(form.get("responsavel_id"))
    resp = next((p for p in pessoas or [] if p.get("id") == pid), None) if pid else None
    if not resp:
        raise Recusada("Escolha o responsável da ação na lista")
    situacao = _txt(form.get("situacao"))
    if situacao not in SITUACOES:
        raise Recusada("Escolha a situação da ação")
    teto = hoje + timedelta(days=365 * PRAZO_ANOS)
    prazo = _data(form.get("prazo"), "prazo", PISO, teto, f"O prazo passou de {PRAZO_ANOS} anos")
    cofre = _cofre()
    with _TRAVA:
        lido = _reler()
        o = _da_ocorrencia(lido, oid, cofre)
        aid = _txt(form.get("acao_id"))
        if aid:
            a = next((x for x in o["acoes"] if x["id"] == aid), None)
            if not a:
                raise Recusada("Não achei esta ação: recarregue a página")
            if (a["texto"], a["responsavel_id"], a["prazo"], a["situacao"]) == (texto, pid, prazo, situacao):
                raise Recusada("Nada mudou")
        else:
            aid = uuid.uuid4().hex[:12]
        nova = _evento(cofre, "acao", quem, o["id"], o["usina_id"], {"texto": texto, "responsavel": resp["nome"]},
                       usina_ligada_por="ocorrencia", acao_id=aid, responsavel_pessoa_id=pid, situacao=situacao,
                       data_id_prazo=_id_dia(prazo))
        _publicar(lido + [nova])
    return nova


def registrar_andamento(oid: str, texto: str, usuario, pode: bool) -> dict:
    """Uma linha do histórico, com o dia e a hora de agora e quem escreveu; nunca se edita nem se apaga."""
    quem = _quem(usuario, pode)
    texto = _texto(texto, TEXTO_MAX, "Escreva o andamento antes de salvar", "O andamento")
    cofre = _cofre()
    with _TRAVA:
        lido = _reler()
        o = _da_ocorrencia(lido, oid)
        nova = _evento(cofre, "andamento", quem, o["id"], o["usina_id"], {"texto": texto},
                       usina_ligada_por="ocorrencia")
        _publicar(lido + [nova])
    return nova


def pessoas_do_cadastro() -> list[dict]:
    """[{"id", "nome"}]: as pessoas do cadastro com nome (o "Nome padrão", decifrado), fora as desligadas e as excluídas,
    em ordem de nome: a lista do responsável da ação. Sem a chave do cadastro, vazia (a tela diz)."""
    from . import visao
    b = visao._Base()
    ids = {D._id(p.get("pessoa_id")) for p in b.pessoas
           if D._id(p.get("pessoa_id")) and p.get("sensivel_cifrado")
           and str(p.get("excluido") or "").strip().lower() != "sim"
           and str(p.get("status") or "").strip().lower() != "desligado"}
    nomes = b.nomes(ids)
    return sorted(({"id": i, "nome": nomes[i]} for i in ids if nomes.get(i)),
                  key=lambda p: (visao._norm_nome(p["nome"]), p["id"]))
