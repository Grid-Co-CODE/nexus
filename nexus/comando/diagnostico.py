"""O diagnóstico do dia da IA no prontuário (14/11/2026).

Levi: "Sempre que a pessoa for abrir o prontuário da usina, abrir o diagnóstico da IA [...] Se a pessoa abrir duas vezes
no mesmo dia, ou se uma pessoa abrir, uma pessoa diferente abrir também no mesmo dia, usar o mesmo diagnóstico [...] Para
não ficar gastando token à toa [...] a IA vai dar o diagnóstico dela, baseado em D-1. No lugar que tem esse parecer agora,
vai ter o diagnóstico da IA [...] o que é que está pendente, o que é que dá para fazer [...] direcione o supervisor: o que
é que ele pode fazer e o que é que ele tem que fazer".

- UM diagnóstico por usina por dia (o dia de Brasília), feito na primeira abertura do prontuário e guardado em
  `<NEXUS_DADOS>/ia/diagnosticos/AAAA-MM-DD/<usina>.json`: quem abrir depois, no mesmo dia, lê o guardado.
- Quem chega enquanto ele está sendo feito vê "preparando" (o arquivo `<usina>.andamento`, criado de forma exclusiva, é a
  trava entre pedidos e entre processos); a página não espera a IA.
- A IA é a do Nexus IA (`ia.perguntar`, a mesma troca entre as grátis quando uma bate o limite), com o dossiê de agora e o
  pedido `PEDIDO`; a resposta é um JSON (`ler`), e a OS citada só vale se está no dossiê.
- Falhou (limite, provedor fora): o erro fica guardado 20 minutos (`ESPERA_ERRO_S`) e depois tenta de novo; até lá vale o
  parecer de sempre.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path

from . import ia as IA

log = logging.getLogger(__name__)

MODELO_PADRAO = "nemotron"       # o grátis com a melhor nota no teste de 14/11/2026; NEXUS_IA_DIAGNOSTICO_MODELO troca
                                 # (com a chave da NVIDIA, o mesmo Nemotron vai por ela: `modelo`)
ESPERA_ERRO_S = 20 * 60          # o erro guardado vale isto; depois a próxima abertura tenta de novo
TRAVA_MORTA_S = 5 * 60           # a trava mais velha que isto é de um pedido que morreu (o servidor reiniciou)
MAX_ITENS = {"tem_que_fazer": 4, "pode_fazer": 3, "pendente": 4}
MAX_ITEM, MAX_SITUACAO = 160, 320

PEDIDO = """Faça o DIAGNÓSTICO DO DIA desta usina para o supervisor dela. A performance do dossiê vai até ontem (D-1); as pendências são as de agora. Seja direto: o supervisor lê em 20 segundos e sabe o que fazer hoje.
Responda SÓ com o bloco abaixo, em JSON válido, sem nada antes ou depois, sem markdown e sem citar as seções (§). Este formato vale acima do limite de palavras.
<diagnostico>{"situacao": "...", "tem_que_fazer": [{"acao": "...", "os": null, "destino": null}], "pode_fazer": [{"acao": "...", "os": null, "destino": null}], "pendente": [{"item": "...", "os": null, "destino": null}]}</diagnostico>
- situacao: 1 ou 2 frases, a conclusão primeiro: como a usina está e por quê, com o número que sustenta (até 220 caracteres).
- tem_que_fazer: o que o supervisor TEM que fazer (obrigação vencida ou crítica: ronda atrasada, extintor vencido, OS crítica parada, desligamento que se repete), o mais urgente primeiro; até 4; cada um em até 110 caracteres, começando pelo verbo.
- pode_fazer: o que ele PODE fazer para melhorar (recomendação, não obrigação); até 3; até 110 caracteres, começando pelo verbo.
- pendente: o que está em aberto esperando alguém (fabricante, concessionária, outro setor, peça, chamado); até 4; até 110 caracteres.
- Cada número com o nome que o dossiê dá a ele. Desligamento é só a parada em que a geração parou: com 17 normalizações e 16 com a geração parada, são 16 desligamentos (a perda de comunicação não conta).
- "os": o número de uma OS do dossiê ligada ao item, ou null. Nunca invente OS, pendência ou número.
- "destino": para onde o supervisor vai a partir do item, ou null:
  - {"pedir": "<nome exato de um setor da lista <setores>>"} quando o item é pedir ou cobrar algo de outro setor (ex.: "Solicitar à Engenharia a revisão dos ajustes", "Cobrar o retorno dos chamados"). O que depende da concessionária (a rede, a tensão, o chamado com a distribuidora) é pedido ao COS, que abre o chamado com a rede. Os chamados de garantia (cobrar o retorno do fabricante, o andamento do chamado) são da área Chamados, dentro da Performance: peça a "Chamados" quando estiver na lista; senão, à Performance.
  - {"ver": "<onde>"} quando o item é olhar ou decidir algo numa tela: "aprovacao" (aprovar as OS em verificação), "engenharia" (a análise da Engenharia), ou uma parte do prontuário: "performance", "os", "rondas", "seguranca", "cos", "chamados", "insights", "demandas".
  - Quando o item já tem a OS, a OS abre sozinha: use "destino" só se houver também um pedido a um setor.
- Lista vazia quando não houver nada."""

_RX_BLOCO = re.compile(r"[<‹]diagnostico>\s*(.*?)\s*(?:[<‹]/diagnostico>|$)", re.S | re.I)
_RX_SECAO = re.compile(r"\s*\((?:§\s*\d+[^()]*)\)")


def _limpo(txt, limite: int) -> str:
    t = _RX_SECAO.sub("", " ".join(str(txt or "").split())).strip()
    return t if len(t) <= limite else t[:limite - 1].rstrip() + "…"


VER = ("aprovacao", "engenharia", "performance", "os", "rondas", "seguranca", "cos", "chamados", "insights", "demandas")


def _sem_acento(s) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", str(s or "")) if not unicodedata.combining(c)).lower().strip()


def _destino(x: dict, setores: list[dict]) -> dict | None:
    """{"tipo": "pedir", "setor_id", "setor"} | {"tipo": "ver", "onde"} | None. Só setor da lista e lugar da lista: o
    que a IA inventar (ou um texto injetado pedir) não vira botão."""
    d = x.get("destino")
    if not isinstance(d, dict):
        return None
    if d.get("pedir"):
        alvo = _sem_acento(d["pedir"])
        for s in setores or []:
            if _sem_acento(s.get("nome")) == alvo:
                return {"tipo": "pedir", "setor_id": s.get("setor_id"), "setor": s.get("nome")}
        return None
    onde = _sem_acento(d.get("ver"))
    return {"tipo": "ver", "onde": onde} if onde in VER else None


def ler(texto: str, dossie: str, setores: list[dict] | None = None) -> dict | None:
    """O JSON da resposta -> {situacao, tem_que_fazer, pode_fazer, pendente}, cada item {texto, os, os_tipo}. None quando
    não veio o JSON (a tela mostra o texto como veio). A OS que não está no dossiê sai do item (uma OS inventada não vira
    link)."""
    m = _RX_BLOCO.search(texto or "")
    bruto = m.group(1) if m else (texto or "")
    i, f = bruto.find("{"), bruto.rfind("}")
    if i < 0 or f <= i:
        return None
    try:
        j = json.loads(bruto[i:f + 1])
    except ValueError:
        return None
    if not isinstance(j, dict) or not str(j.get("situacao") or "").strip():
        return None
    mapa = IA.os_do_dossie(dossie)
    out = {"situacao": _limpo(j.get("situacao"), MAX_SITUACAO)}
    for lista, campo in (("tem_que_fazer", "acao"), ("pode_fazer", "acao"), ("pendente", "item")):
        itens = []
        for x in (j.get(lista) or [])[:MAX_ITENS[lista]]:
            if isinstance(x, str):
                x = {campo: x}
            if not isinstance(x, dict):
                continue
            txt = _limpo(x.get(campo) or x.get("acao") or x.get("item"), MAX_ITEM)
            if not txt:
                continue
            os_ = str(x.get("os") or "").strip()
            os_ = os_ if os_ in mapa else ""
            itens.append({"texto": txt, "os": os_, "os_tipo": mapa.get(os_, ""), "destino": _destino(x, setores or [])})
        out[lista] = itens
    return out


# ── o guardado do dia ────────────────────────────────────────────────────────────────────────────────────────────────
def hoje(agora: datetime | None = None) -> str:
    return f"{(agora or datetime.now(IA._BRT)):%Y-%m-%d}"


def _pasta(cfg, dia: str) -> Path | None:
    p = IA._pasta(cfg)
    return p / "diagnosticos" / dia if p else None


def modelo(cfg) -> str:
    """O NEXUS_IA_DIAGNOSTICO_MODELO; sem ele, o padrão da Nexus IA (o Nemotron pela NVIDIA quando há a chave dela)."""
    return str(cfg.get("NEXUS_IA_DIAGNOSTICO_MODELO") or IA.padrao(cfg) or MODELO_PADRAO).strip()


def disponivel(cfg) -> bool:
    """Há o modelo do diagnóstico com chave, ou um grátis da troca com chave."""
    por_id = {m.id: m for m in IA.modelos(cfg)}
    return any(i in por_id and IA.chave(cfg, por_id[i].provedor) for i in (modelo(cfg),) + IA.TROCA_GRATIS)


def guardado(cfg, usina_id: int, dia: str | None = None) -> dict | None:
    """O diagnóstico do dia já feito (ou o erro dos últimos 20 minutos). None: falta fazer."""
    pasta = _pasta(cfg, dia or hoje())
    arq = pasta / f"{int(usina_id)}.json" if pasta else None
    if not arq or not arq.exists():
        return None
    try:
        d = json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not d.get("ok") and time.time() - float(d.get("ts") or 0) > ESPERA_ERRO_S:
        return None
    return d


def travar(cfg, usina_id: int, dia: str | None = None) -> bool:
    """Pega a vez de fazer o diagnóstico (o arquivo criado de forma exclusiva). False: outro pedido já está fazendo."""
    pasta = _pasta(cfg, dia or hoje())
    if not pasta:
        return True
    pasta.mkdir(parents=True, exist_ok=True)
    trava = pasta / f"{int(usina_id)}.andamento"
    for _ in range(2):
        try:
            os.close(os.open(trava, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return True
        except FileExistsError:
            try:
                if time.time() - trava.stat().st_mtime < TRAVA_MORTA_S:
                    return False
                trava.unlink()
            except OSError:
                return False
    return False


def soltar(cfg, usina_id: int, dia: str | None = None) -> None:
    pasta = _pasta(cfg, dia or hoje())
    if pasta:
        try:
            (pasta / f"{int(usina_id)}.andamento").unlink()
        except OSError:
            pass


def em_andamento(cfg, usina_id: int, dia: str | None = None) -> bool:
    pasta = _pasta(cfg, dia or hoje())
    trava = pasta / f"{int(usina_id)}.andamento" if pasta else None
    try:
        return bool(trava and trava.exists() and time.time() - trava.stat().st_mtime < TRAVA_MORTA_S)
    except OSError:
        return False


def gerar(cfg, usina_id: int, dossie: str, dossie_tokens: int = 0, dia: str | None = None,
          setores: list[dict] | None = None) -> dict:
    """Faz o diagnóstico, guarda e solta a trava. Roda numa thread à parte (a rota não espera); no teste, na hora."""
    dia = dia or hoje()
    pasta = _pasta(cfg, dia)
    try:
        rs = IA.perguntar(cfg, [modelo(cfg)], dossie, PEDIDO, setores=[s["nome"] for s in setores or []])
        r = rs[0] if rs else {"ok": False, "erro": "Nenhuma IA ligada para o diagnóstico."}
        IA.registrar(cfg, usina_id, "[diagnóstico do dia]", rs, "diagnostico-do-dia", dossie_tokens)
        agora = datetime.now(IA._BRT)
        d = {"usina_id": int(usina_id), "dia": dia, "ts": time.time(), "gerado_em": agora.isoformat(timespec="seconds"),
             "ok": bool(r.get("ok")), "modelo": r.get("id") or "", "rotulo": r.get("rotulo") or "",
             "troca": r.get("troca") or "", "erro": r.get("erro") or "", "ms": r.get("ms")}
        if r.get("ok"):
            d["diag"] = ler(r.get("texto") or "", dossie, setores)
            d["texto"] = "" if d["diag"] else IA.limpar_citacoes(r.get("texto") or "")[:3000]
            d["numeros"] = r.get("numeros")
        if pasta:
            pasta.mkdir(parents=True, exist_ok=True)
            (pasta / f"{int(usina_id)}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        return d
    except Exception as ex:      # noqa: BLE001 — a thread não pode morrer calada
        log.exception("Diagnóstico do dia: a usina %s falhou", usina_id)
        return {"ok": False, "erro": f"Falhou ({type(ex).__name__})."}
    finally:
        if pasta:
            try:
                (pasta / f"{int(usina_id)}.andamento").unlink()
            except OSError:
                pass


def para_tela(d: dict) -> dict:
    """O que a tela recebe: o estado e o diagnóstico (sem o registro interno)."""
    if not d.get("ok"):
        return {"estado": "erro", "erro": d.get("erro") or "A IA não respondeu."}
    em = d.get("gerado_em") or ""
    return {"estado": "pronto" if d.get("diag") else "texto", "diag": d.get("diag"), "texto": d.get("texto") or "",
            "rotulo": d.get("rotulo") or "", "troca": d.get("troca") or "", "dia": d.get("dia") or "",
            "hora": em[11:16], "data": f"{em[8:10]}/{em[5:7]}" if len(em) >= 10 else ""}
