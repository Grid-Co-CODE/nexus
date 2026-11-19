"""Limitações de potência dos inversores (19/11/2026): o cadastro do time, em Usinas 360° › Limitações de potência.

Levi, 19/11/2026: "crie, na parte de usina 360, um campo onde as pessoas consigam colocar limitações de potência dos
inversores. E aí vai ser usado também para o cálculo dos expurgos. Aí aquela limitação de potência pode ser de todos os
inversores ou só de alguns, de acordo com os inversores do fractal, que é lido na disponibilidade". E, nas notas do mesmo
dia: "Limitação >> precisamos de um local onde o time consiga colocar isso". Até aqui morava na aba "Inv. com lim. de
potência" da planilha de tickets (90 linhas, parada desde 09/2026); os campos são os dela, para o time trocar a planilha
pelo Nexus sem perder nada: os inversores afetados ("Todos" ou alguns), a potência de cada um, o percentual liberado
(0,9 = 90%), a causa, a responsabilidade da Grid (sim, não, parcial), a clipagem, o início, o fim e os comentários.

O Nexus é a FONTE deste fato: livro `nexus_limitacao_inversor` · `fato_versao_limitacao` (no catálogo antes da 1ª
gravação, regra 10). 1 linha = 1 versão de um registro: registrou, alterou, encerrou (pôs o fim) ou excluiu; vale a última
versão de cada `limitacao_id`, e o histórico fica. Em claro: a usina, os códigos dos inversores do Fracttal (`*` = todos),
a potência, o limite, as datas, a responsabilidade e o código de quem registrou (`pessoa_hmac`). A causa, os comentários e
o nome de quem registrou, só cifrados (regra 8: texto livre e nome nunca em claro numa API de leitura aberta).

Quem registra: quem entrou com o login (Fracttal ou Microsoft), que diz quem é; a senha de administrador não diz.
Sem a potência nominal, a limitação é guardada, mas não entra no cálculo do expurgo (nada de potência inventada).
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from flask import current_app

from ..dados import livros

LIVRO, NOME_LIVRO, ABA = "nexus_limitacao_inversor", "Nexus · limitações de potência dos inversores", "fato_versao_limitacao"
CAB = ("versao_id", "limitacao_id", "evento", "registrado_em", "data_id", "usina_id", "inversores", "inversores_qtd",
       "potencia_nominal_kw", "limite_pct", "inicio", "fim", "data_id_inicio", "data_id_fim", "responsabilidade_grid",
       "clipagem", "pessoa_hmac", "dados_cifrados")
EVENTOS = ("registrou", "alterou", "encerrou", "excluiu")
TODOS = "*"
RESPONSABILIDADES = {"nao": "Não", "sim": "Sim", "parcial": "Parcial"}
# a "Gravidade" da planilha, que fala da clipagem do inversor
CLIPAGEM = {"": "—", "problemas": "Problemas na clipagem", "sem": "Sem clipagem", "conforme": "Clipagem em conformidade"}
TEXTO_MAX = 1500
TTL_S = 60
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()
_CACHE: dict = {}
AVISO_SEM_POTENCIA = "Sem a potência nominal, esta limitação não entra no cálculo do expurgo."


class Recusada(ValueError):
    """Nada foi gravado: o texto diz por quê."""


def limpar() -> None:
    _CACHE.clear()


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def _num(v):
    s = _txt(v).replace(" ", "")
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        raise Recusada("número ilegível") from None


def _id(v):
    try:
        return int(float(v)) if _txt(v) else None
    except (TypeError, ValueError):
        return None


def _quando(s: str) -> datetime | None:
    """O datetime-local do formulário ("2026-11-10T08:00"), no horário de Brasília; ou o ISO guardado."""
    s = _txt(s)
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.replace(tzinfo=_BRT) if d.tzinfo is None else d.astimezone(_BRT)


def _ctx(versao_id) -> str:
    return f"banco/limitacoes/{versao_id}"


def _cofre():
    chave = current_app.config.get("NEXUS_CHAVE_CADASTRO")
    if not chave:
        raise Recusada("Este Nexus não tem a chave do cadastro (NEXUS_CHAVE_CADASTRO): sem ela a causa e os comentários "
                       "não vão cifrados")
    from ..cadastro.cifra import Cofre
    return Cofre(chave)


def _banco():
    from ..dados import conexao
    return conexao.banco()


# ── a leitura ────────────────────────────────────────────────────────────────────────────────────────────────────────
def ler(forcar: bool = False) -> dict:
    """{"linhas", "erro", "lido_em"}: o livro, guardado por 1 minuto. A leitura que falha devolve a última boa com o erro."""
    agora = time.time()
    g = _CACHE.get("livro")
    if g and not forcar and agora - g["lido_em"] < TTL_S:
        return g
    try:
        linhas = livros.ler(*_banco(), LIVRO, ABA)
    except Exception as ex:      # noqa: BLE001 — banco fora (ou o livro antes da 1ª gravação): quem lê diz o que faltou
        _CACHE["livro"] = {"linhas": list((g or {}).get("linhas") or []), "erro": f"{type(ex).__name__}: {str(ex)[:160]}",
                           "lido_em": agora}
        return _CACHE["livro"]
    _CACHE["livro"] = {"linhas": linhas, "erro": "", "lido_em": agora}
    return _CACHE["livro"]


def _ultimas(linhas) -> dict:
    """{limitacao_id: a última versão}, pela hora em que foi registrada."""
    out = {}
    for l in linhas or []:
        lid = _txt(l.get("limitacao_id"))
        if lid and (lid not in out or _txt(l.get("registrado_em")) >= _txt(out[lid].get("registrado_em"))):
            out[lid] = l
    return out


def _abrir(l: dict, cofre) -> dict:
    d = {}
    if cofre and l.get("dados_cifrados"):
        try:
            d = json.loads(cofre.decifrar(l["dados_cifrados"], _ctx(l.get("versao_id"))))
        except Exception:        # noqa: BLE001 — linha mexida ou chave trocada: fica sem o texto
            d = {}
    ini, fim = _quando(l.get("inicio")), _quando(l.get("fim"))
    inv = _txt(l.get("inversores"))
    todos = inv == TODOS
    qtd, nom, pct = _id(l.get("inversores_qtd")), _num_ou_none(l.get("potencia_nominal_kw")), _num_ou_none(l.get("limite_pct"))
    kw = round(nom * qtd * (1 - pct / 100), 3) if nom is not None and qtd and pct is not None else None
    agora = datetime.now(_BRT)
    return {"limitacao_id": _txt(l.get("limitacao_id")), "versao_id": _txt(l.get("versao_id")), "evento": _txt(l.get("evento")),
            "usina_id": _id(l.get("usina_id")), "todos": todos, "inversores": [] if todos else [x for x in inv.split(";") if x],
            "inversores_qtd": qtd, "potencia_nominal_kw": nom, "limite_pct": pct, "kw_limitados": kw,
            "inicio": ini, "fim": fim, "inicio_txt": ini.strftime("%d/%m/%Y %H:%M") if ini else "—",
            "fim_txt": fim.strftime("%d/%m/%Y %H:%M") if fim else "",
            "situacao": "em_andamento" if fim is None or fim > agora else "encerrada",
            "responsabilidade": _txt(l.get("responsabilidade_grid")), "clipagem": _txt(l.get("clipagem")),
            "causa": d.get("causa") or "", "comentario_cliente": d.get("comentario_cliente") or "",
            "comentario_geral": d.get("comentario_geral") or "", "por": d.get("nome") or "",
            "registrado_em": _txt(l.get("registrado_em")), "aviso": "" if nom is not None else AVISO_SEM_POTENCIA}


def _num_ou_none(v):
    try:
        return float(v) if _txt(v) else None
    except (TypeError, ValueError):
        return None


def vigentes(lido: dict | None = None) -> list[dict]:
    """As limitações de agora (a última versão de cada uma, sem as excluídas), decifradas; as em andamento primeiro e,
    dentro delas, a que começou por último."""
    lido = lido or ler()
    try:
        cofre = _cofre()
    except Recusada:
        cofre = None
    out = [_abrir(l, cofre) for l in _ultimas(lido.get("linhas")).values() if _txt(l.get("evento")) != "excluiu"]
    return sorted(out, key=lambda v: (v["situacao"] != "em_andamento",
                                      -(v["inicio"].timestamp() if v["inicio"] else 0)))


def no_periodo(usina_id: int, inicio: datetime, fim: datetime, lido: dict | None = None) -> list[dict]:
    """As limitações da usina que tocam [inicio, fim): o que o cálculo do expurgo lê."""
    return [v for v in vigentes(lido) if v["usina_id"] == usina_id and v["inicio"] and v["inicio"] < fim
            and (v["fim"] is None or v["fim"] > inicio)]


# ── a gravação ───────────────────────────────────────────────────────────────────────────────────────────────────────
def usinas() -> dict:
    """{usina_id: nome} do cadastro do Nexus."""
    from . import visao
    return {_id(u.get("usina_id")): _txt(u.get("nome")) for u in visao._livro("cadastro_nexus", "usinas")
            if _id(u.get("usina_id"))}


def inversores_da_usina(usina_id: int) -> dict:
    """{"lista": [{codigo, descricao}], "erro"}: os inversores do Fracttal da usina (família INVR da dimensão de
    equipamento, a mesma dos ativos que a disponibilidade lê pelo código)."""
    from ..cadastro import estrutura_usina
    a = estrutura_usina.ativos_da_usina(*_banco(), usina_id)
    return {"lista": [{"codigo": x["codigo"], "descricao": x["descricao"]} for x in a["ativos"] if x.get("familia") == "INVR"],
            "erro": a.get("erro") or ""}


def _quem(conta: dict) -> tuple[str, str]:
    email = _txt((conta or {}).get("email")).lower()
    if not email:
        raise Recusada("Entre com o seu login (Fracttal ou Microsoft) para registrar: a senha de administrador não diz quem é")
    from ..cadastro.ligacao_campo import codigo_da_pessoa
    hmac_ = (codigo_da_pessoa(current_app.config.get("NEXUS_PESSOA_HMAC"), email) or "").lower()
    if not hmac_:
        raise Recusada("Este Nexus não tem a chave do código da pessoa (NEXUS_PESSOA_HMAC)")
    return hmac_, _txt((conta or {}).get("nome"))


def _gravar(nova: dict) -> None:
    if not current_app.config.get("GRIDCO_SQL_TOKEN"):
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN)")
    base, sessao = _banco()
    with _TRAVA:
        lido = livros.ler(base, sessao, LIVRO, ABA)
        if any(_txt(l.get("versao_id")) == nova["versao_id"] for l in lido):
            return
        livros.publicar(LIVRO, NOME_LIVRO, {ABA: (list(CAB), [[l.get(c) for c in CAB] for l in lido + [nova]])},
                        base=base, token=current_app.config["GRIDCO_SQL_TOKEN"], sessao=sessao)
        _CACHE["livro"] = {"linhas": list(lido) + [nova], "erro": "", "lido_em": time.time()}


def _linha(lid: str, evento: str, base: dict, dados_txt: dict, quem: str, nome: str, versao_id: str = "") -> dict:
    agora = datetime.now(timezone.utc)
    vid = versao_id or uuid.uuid4().hex[:16]
    l = dict(base, versao_id=vid, limitacao_id=lid, evento=evento,
             registrado_em=agora.strftime("%Y-%m-%dT%H:%M:%S.") + f"{agora.microsecond // 1000:03d}Z",
             data_id=int(agora.astimezone(_BRT).strftime("%Y%m%d")), pessoa_hmac=quem)
    l["dados_cifrados"] = _cofre().cifrar(json.dumps(dict(dados_txt, nome=nome), ensure_ascii=False), _ctx(vid))
    return {c: l.get(c) for c in CAB}


def salvar(dados: dict, conta: dict) -> dict:
    """Registra uma limitação nova (ou uma versão nova de `dados["limitacao_id"]`). Confere tudo antes; o que não fecha
    sobe como `Recusada`, com o motivo, e nada é gravado. Devolve {"limitacao_id"}."""
    quem, nome = _quem(conta)
    uid = _id(dados.get("usina_id"))
    if not uid or uid not in usinas():
        raise Recusada("Escolha a usina")
    inv_usina = [x["codigo"] for x in inversores_da_usina(uid)["lista"]]
    todos = _txt(dados.get("todos")) in ("1", "sim", "on", "true")
    escolhidos = [_txt(x) for x in (dados.get("inversores") or []) if _txt(x)]
    if todos:
        inversores, qtd = TODOS, (len(inv_usina) or None)
    else:
        if not escolhidos:
            raise Recusada("Marque os inversores limitados (ou Todos os inversores)")
        fora = [x for x in escolhidos if x not in inv_usina]
        if fora:
            raise Recusada(f"Inversor que não é desta usina no Fracttal: {', '.join(fora[:3])}")
        inversores, qtd = ";".join(sorted(set(escolhidos), key=escolhidos.index)), len(set(escolhidos))
    try:
        nominal = _num(dados.get("potencia_nominal_kw"))
    except Recusada:
        raise Recusada("A potência nominal tem de ser um número em kW") from None
    if nominal is not None and nominal <= 0:
        raise Recusada("A potência nominal tem de ser maior que zero (ou fique em branco)")
    try:
        pct = _num(dados.get("limite_pct"))
    except Recusada:
        pct = -1
    if pct is None or not 0 < pct < 100:
        raise Recusada("O limite é o percentual da potência nominal que fica liberado: entre 0 e 100 (90 = 90%)")
    resp = _txt(dados.get("responsabilidade"))
    if resp not in RESPONSABILIDADES:
        raise Recusada("Diga se a responsabilidade é da Grid Co. (sim, não ou parcial): é ela que decide o expurgo")
    clip = _txt(dados.get("clipagem"))
    if clip not in CLIPAGEM:
        clip = ""
    ini, fim = _quando(dados.get("inicio")), _quando(dados.get("fim"))
    if ini is None:
        raise Recusada("Diga o início da limitação (dia e hora)")
    if fim is not None and fim <= ini:
        raise Recusada("O fim tem de vir depois do início")
    textos = {k: _txt(dados.get(k))[:TEXTO_MAX] for k in ("causa", "comentario_cliente", "comentario_geral")}
    base = {"usina_id": uid, "inversores": inversores, "inversores_qtd": qtd, "potencia_nominal_kw": nominal,
            "limite_pct": pct, "inicio": ini.isoformat(timespec="minutes"), "fim": fim.isoformat(timespec="minutes") if fim else None,
            "data_id_inicio": int(ini.strftime("%Y%m%d")), "data_id_fim": int(fim.strftime("%Y%m%d")) if fim else None,
            "responsabilidade_grid": resp, "clipagem": clip}
    ultimas = _ultimas(ler(forcar=True)["linhas"])
    lid = _txt(dados.get("limitacao_id"))
    if lid:
        if lid not in ultimas or _txt(ultimas[lid].get("evento")) == "excluiu":
            raise Recusada("Esta limitação não está mais no cadastro: recarregue a página")
        _gravar(_linha(lid, "alterou", base, textos, quem, nome))
        return {"limitacao_id": lid}
    novo = re.sub(r"[^0-9a-f]", "", _txt(dados.get("novo_id")).lower())[:24]
    if novo and novo in ultimas:
        return {"limitacao_id": novo}            # o mesmo envio de novo (o duplo clique, o F5): não duplica
    lid = novo or uuid.uuid4().hex[:16]
    _gravar(_linha(lid, "registrou", base, textos, quem, nome))
    return {"limitacao_id": lid}


def _de_novo(lid: str, conta: dict, evento: str, **troca) -> None:
    quem, nome = _quem(conta)
    ultimas = _ultimas(ler(forcar=True)["linhas"])
    ult = ultimas.get(_txt(lid))
    if not ult or _txt(ult.get("evento")) == "excluiu":
        raise Recusada("Esta limitação não está mais no cadastro: recarregue a página")
    v = _abrir(ult, _cofre())
    base = {c: ult.get(c) for c in CAB if c not in ("versao_id", "limitacao_id", "evento", "registrado_em", "data_id",
                                                    "pessoa_hmac", "dados_cifrados")}
    base.update(troca)
    _gravar(_linha(_txt(lid), evento, base, {k: v[k] for k in ("causa", "comentario_cliente", "comentario_geral")}, quem, nome))


def encerrar(lid: str, conta: dict, quando: datetime | None = None) -> None:
    """Põe o fim (agora, ou o dado) numa limitação em andamento."""
    fim = (quando or datetime.now(_BRT)).astimezone(_BRT)
    _de_novo(lid, conta, "encerrou", fim=fim.isoformat(timespec="minutes"), data_id_fim=int(fim.strftime("%Y%m%d")))


def excluir(lid: str, conta: dict) -> None:
    """Tira do cadastro (o registro errado): a versão "excluiu" fica no histórico."""
    _de_novo(lid, conta, "excluiu")
