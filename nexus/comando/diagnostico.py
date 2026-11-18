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
- Enquanto o de hoje é feito, a tela mostra o último que deu certo, com a data dele (`anterior`; 18/11/2026, Levi:
  "demora 40 segundos para uma resposta após eu abrir a usina"; "faz o A"). Só o de até `MAX_DIAS_ANTERIOR` dias.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

from . import ia as IA

log = logging.getLogger(__name__)

MODELO_PADRAO = "nemotron"       # o grátis com a melhor nota no teste de 14/11/2026; NEXUS_IA_DIAGNOSTICO_MODELO troca
                                 # (com a chave da NVIDIA, o mesmo Nemotron vai por ela: `modelo`)
ESPERA_ERRO_S = 20 * 60          # o erro guardado vale isto; depois a próxima abertura tenta de novo
TRAVA_MORTA_S = 5 * 60           # a trava mais velha que isto é de um pedido que morreu (o servidor reiniciou)
# a versão do pedido e da conferência: o guardado de outra versão é refeito na próxima abertura (18/11/2026: o pedido
# trazia um exemplo com "16 desligamentos", e duas usinas saíram com 16 no lugar de 11 e de 3)
VERSAO = 5
# o diagnóstico vai em Busca, sem o pensamento do Claude (18/11/2026, Levi, com a 1ª abertura do dia em 40 s: "diagnóstico
# em busca, rode alguns diagnósticos e bata os dados para ver se a informação está confiável"). True volta a pensar
PENSAR = False
MAX_DIAS_ANTERIOR = 7            # o diagnóstico mais velho que isto não aparece enquanto o de hoje é feito (o de sexta
                                 # serve na segunda; o da semana retrasada já fala de outra usina)
MAX_ITENS = {"tem_que_fazer": 4, "pode_fazer": 3, "pendente": 4}
MAX_ITEM, MAX_SITUACAO, MAX_PEDIDO = 160, 320, 600

PEDIDO = """Faça o DIAGNÓSTICO DO DIA desta usina para o supervisor dela. A performance do dossiê vai até ontem (D-1); as pendências são as de agora. Seja direto: o supervisor lê em 20 segundos e sabe o que fazer hoje.
Responda SÓ com o bloco abaixo, em JSON válido, sem nada antes ou depois, sem markdown e sem citar as seções (§). Este formato vale acima do limite de palavras.
<diagnostico>{"situacao": "...", "tem_que_fazer": [{"acao": "...", "os": null, "destino": null, "pedido": null}], "pode_fazer": [{"acao": "...", "os": null, "destino": null, "pedido": null}], "pendente": [{"item": "...", "os": null, "destino": null, "pedido": null}]}</diagnostico>
- situacao: 1 ou 2 frases, a conclusão primeiro: como a usina está e por quê, com o número que sustenta (até 220 caracteres).
- O diagnóstico é do MÊS CORRENTE (o mês de hoje, que o dossiê marca como parcial): a situação e os números de meta, PR, geração, disponibilidade, desligamentos e o que foi feito no ativo são os deste mês. Não ponha na situação o que aconteceu em mês anterior. O que vem de mês anterior só entra se ainda está em aberto (OS, chamado, pendência), e entra como pendência, sem os números de performance daquele mês.
- tem_que_fazer: o que o supervisor TEM que fazer (obrigação vencida ou crítica: ronda atrasada, extintor vencido, OS crítica parada, desligamento que se repete), o mais urgente primeiro; até 4; cada um em até 110 caracteres, começando pelo verbo.
- pode_fazer: o que ele PODE fazer para melhorar (recomendação, não obrigação); até 3; até 110 caracteres, começando pelo verbo.
- pendente: o que está em aberto esperando alguém (fabricante, concessionária, outro setor, peça, chamado); até 4; até 110 caracteres.
- Cada número com o nome que o dossiê dá a ele. Desligamento é só a parada em que a geração parou (a perda de comunicação não conta): o número de desligamentos é o da coluna "Desligamentos (a geração parou)" da tabela por mês da seção do COS, na linha do mês corrente. Não conte as linhas das paradas e não use outro número no lugar.
- Ronda: só peça para programar a ronda quando o dossiê diz que ela está atrasada ou sem cobertura. Zeladoria vencida não é ronda: é pedido à Zeladoria.
- O que o dossiê marca como "sem dado" ou "sem leitura" não vira item nem conclusão: não é zero, nem "sem conferência", nem pendência.
- "os": o número de uma OS do dossiê ligada ao item, ou null. Nunca invente OS, pendência ou número.
- "destino": para onde o supervisor vai a partir do item, ou null:
  - {"pedir": "<nome exato de um setor da lista <setores>>", "tema": "<nome exato de um tema desse setor, da lista TEMAS abaixo, ou null>"} quando o item é pedir ou cobrar algo de outro setor (ex.: "Solicitar à Engenharia a revisão dos ajustes", "Cobrar o retorno dos chamados"). O que depende da concessionária (a rede, a tensão, o chamado com a distribuidora) é pedido ao COS, que abre o chamado com a rede. Os chamados de garantia (cobrar o retorno do fabricante, o andamento do chamado) são da área Chamados, dentro da Performance: peça a "Chamados" quando estiver na lista; senão, à Performance.
  - {"ver": "<onde>"} quando o item é olhar ou decidir algo numa tela: "aprovacao" (aprovar as OS em verificação), "engenharia" (a análise da Engenharia), "extintores" (a lista dos extintores vencidos, a vencer e sem conferência), ou uma parte do prontuário: "performance", "os", "rondas", "seguranca", "cos", "chamados", "insights", "demandas".
  - Os dois juntos quando servem: {"pedir": "...", "ver": "..."} (ex.: conferir os extintores: pedir à Segurança e ver a lista).
  - Quando o item já tem a OS, a OS abre sozinha: use "destino" só se houver também um pedido a um setor ou uma tela.
- "pedido": quando o destino tem "pedir", o texto do pedido ao setor, pronto para mandar (até 400 caracteres): o que pedir e os dados do dossiê que o setor precisa (as OS, o equipamento, o fabricante, há quantos dias, a situação). Sem "pedir", null.
- OS: executar, iniciar ou concluir uma OS é do técnico de campo, que o supervisor coordena: vai em "tem_que_fazer" como cobrança da equipe (com "ver": "os"), nunca como pedido a outro setor (nem à Manutenção). Das não iniciadas, só entram as urgentes (religamento, corretiva emergencial) e as atrasadas; as "no prazo" não entram em lista nenhuma.
- Tarefa pausada: o supervisor não libera a pausa. Diga o motivo e de quem depende ("Como ler a pausa", no §5); vai em "pendente", e só pede algo ao setor do motivo se a tarefa pesa (geração parada, equipamento em falha).
- Chamados de garantia: cobrar o fabricante, o andamento e juntar uma OS a um chamado é da área Chamados ("pedir": "Chamados", com o tema dela: "Cobrança ao fabricante", "Vincular OS ao chamado de garantia"...). Juntar a OS ao chamado é a sugestão do Insight pelo mesmo equipamento: o dossiê não diz se já estão ligadas, então o item é pedir a Chamados para avaliar, nunca afirmar que não estão.
- Demanda já aberta (a seção das demandas entre setores): não peça de novo o que já tem demanda aberta com o setor. O assunto vai em "pendente", dizendo que aguarda o setor (e que está vencida, quando estiver), com "destino": {"ver": "demandas"} e sem "pedido".
- Cada assunto numa lista só: o que o supervisor tem que fazer não se repete em "pendente"; "pendente" é só o que espera outra pessoa ou empresa.
- Lista vazia quando não houver nada."""

_RX_BLOCO = re.compile(r"[<‹]diagnostico>\s*(.*?)\s*(?:[<‹]/diagnostico>|$)", re.S | re.I)
_RX_SECAO = re.compile(r"\s*\((?:§\s*\d+[^()]*)\)")


def _limpo(txt, limite: int) -> str:
    t = _RX_SECAO.sub("", " ".join(str(txt or "").split())).strip()
    return t if len(t) <= limite else t[:limite - 1].rstrip() + "…"


VER = ("aprovacao", "engenharia", "extintores", "performance", "os", "rondas", "seguranca", "cos", "chamados", "insights",
       "demandas")


def _sem_acento(s) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", str(s or "")) if not unicodedata.combining(c)).lower().strip()


def _destino(x: dict, setores: list[dict]) -> dict | None:
    """{"tipo": "pedir", "setor_id", "setor", "tema_id", "tema"} | {"tipo": "ver", "onde"} | None. Só setor da lista,
    tema do setor e lugar da lista: o que a IA inventar (ou um texto injetado pedir) não vira botão nem tema."""
    d = x.get("destino")
    if not isinstance(d, dict):
        return None
    if d.get("pedir"):
        alvo = _sem_acento(d["pedir"])
        for s in setores or []:
            if _sem_acento(s.get("nome")) == alvo:
                quer = _sem_acento(d.get("tema"))
                tema = next((t for t in s.get("temas") or [] if quer and _sem_acento(t.get("nome")) == quer), None)
                return {"tipo": "pedir", "setor_id": s.get("setor_id"), "setor": s.get("nome"),
                        "tema_id": (tema or {}).get("tema_id", ""), "tema": (tema or {}).get("nome", "")}
        return None
    onde = _sem_acento(d.get("ver"))
    return {"tipo": "ver", "onde": onde} if onde in VER else None


def _ver(x: dict) -> str:
    """O "ver" do item, mesmo junto do "pedir" (15/11/2026, Levi: "além da pessoa clicar em fazer, também poder clicar em
    ver"): só lugar da lista."""
    d = x.get("destino")
    onde = _sem_acento(d.get("ver")) if isinstance(d, dict) else ""
    return onde if onde in VER else ""


# as situações da demanda em que ela ainda espera quem recebeu (`demandas_regras.ABERTAS`, pelo rótulo do dossiê)
_ESPERA_O_SETOR = ("nova", "em analise", "devolvida")


def demandas_abertas(dossie: str) -> dict[str, str]:
    """{OS: o setor que recebeu (sem acento)} das demandas da usina que ainda esperam o setor (Nova, Em análise,
    Devolvida) e têm OS, lidas da seção das demandas do dossiê. É por elas que o item que pediria a MESMA coisa de novo
    vira "pendente com o setor" (18/11/2026: o Insights sugeria mandar de novo o pedido que já estava na caixa)."""
    m = re.search(r"^## \d+\. Demandas entre setores[^\n]*\n(.*?)(?=^## |\Z)", dossie or "", re.S | re.M)
    out = {}
    for linha in (m.group(1).splitlines() if m else []):
        if not linha.startswith("- "):
            continue
        partes = [p.strip() for p in linha[2:].split(";")]
        setor = next((p.split(" para ", 1)[1] for p in partes if p.startswith("de ") and " para " in p), "")
        espera = any(_sem_acento(p.replace("(VENCIDA)", "")) in _ESPERA_O_SETOR for p in partes)
        os_ = next((p[3:].strip() for p in partes if re.fullmatch(r"OS \d{4,6}", p)), "")
        if setor and espera and os_:
            out[os_] = _sem_acento(setor)
    return out


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
    ja_abertas = demandas_abertas(dossie)
    out = {"situacao": _limpo(j.get("situacao"), MAX_SITUACAO)}
    # as OS da frase, com o tipo (a tela abre o card ou o Raio X): só as que o dossiê tem
    out["situacao_os"] = {n: mapa[n] for n in re.findall(r"(?<![\d.,])(\d{4,6})(?![\d.,]\d)", out["situacao"]) if n in mapa}
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
            destino = _destino(x, setores or [])
            # executar OS é do técnico: o "Fazer" que pediria isso a outro setor não sai (a mesma trava do chat)
            if destino and destino.get("tipo") == "pedir" and IA.acao_de_campo(destino.get("setor") or "", txt):
                destino = None
            # o pedido pronto ao setor (16/11/2026, Levi: "solicitar o time de chamados, cobrança de fabricante, STI [...]
            # Tudo isso já pronto"): só com o "pedir"
            pedido = _limpo(x.get("pedido"), MAX_PEDIDO) if destino and destino.get("tipo") == "pedir" else ""
            item = {"texto": txt, "os": os_, "os_tipo": mapa.get(os_, ""), "destino": destino, "ver": _ver(x),
                    "pedido": pedido}
            # a mesma OS já tem demanda aberta com o mesmo setor: não se pede de novo; o botão leva às demandas da usina
            if (destino and destino.get("tipo") == "pedir" and os_
                    and ja_abertas.get(os_) == _sem_acento(destino.get("setor"))):
                item.update(destino={"tipo": "ver", "onde": "demandas"}, ver="demandas", pedido="", ja_pedido=True)
            itens.append(item)
        out[lista] = itens
    return out


# ── a conferência contra o dossiê (18/11/2026) ───────────────────────────────────────────────────────────────────────
# Levi: "rode alguns diagnósticos e bata os dados para ver se a informação está confiável". Na prova, os 52 números de 4
# diagnósticos estavam no dossiê, e ainda assim dois erraram o número de desligamentos: "estar no dossiê" não prova que
# o número é o daquela conta. Esta conferência é da conta que errou: o número de desligamentos tem que ser um dos da
# tabela por mês, na linha do mês dito (na 2ª rodada, a Colíder 1 saiu com o 6 de outubro como se fosse de novembro, e
# com "2 strings fora" onde havia 1). Erro de outro tipo que aparecer ganha a conferência dele aqui, com o caso.
_RX_TABELA_MES = re.compile(r"^\| Mês \| Desligamentos \(a geração parou\)[^\n]*\n\|[ :|-]+\n((?:\|[^\n]*\n?)+)", re.M)
_RX_DESLIGAMENTOS = re.compile(r"(?<![\d.,])(\d{1,4})\s+desligamentos?\b", re.I)


def desligamentos_do_dossie(dossie: str) -> dict[str, int]:
    """{mês: desligamentos (a geração parou)} da tabela por mês da seção do COS. Vazio: o dossiê não trouxe a tabela."""
    m = _RX_TABELA_MES.search(dossie or "")
    out = {}
    for linha in (m.group(1).splitlines() if m else []):
        cel = [c.strip() for c in linha.strip().strip("|").split("|")]
        if len(cel) >= 2 and cel[1].isdigit():
            out[cel[0]] = int(cel[1])
    return out


_RX_STRINGS_AGORA = re.compile(r"^- Strings fora agora: (\d+)[^\n]*\n((?:  - [^\n]*\n?)*)", re.M)
_RX_STRINGS_DO_INVERSOR = re.compile(r"^  - [^:\n]+: (\d+) strings?\b", re.M)
_RX_STRINGS_FORA = re.compile(r"(?<![\d.,])(\d{1,3})\s+strings?\s+fora\b", re.I)
_MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro",
          "dezembro")


def strings_do_dossie(dossie: str) -> dict:
    """{"total", "por_inversor": [n de cada inversor]} das strings fora agora, da seção Strings e trackers. Vazio: o
    dossiê não trouxe a linha."""
    m = _RX_STRINGS_AGORA.search(dossie or "")
    if not m:
        return {}
    return {"total": int(m.group(1)), "por_inversor": [int(n) for n in _RX_STRINGS_DO_INVERSOR.findall(m.group(2))]}


def _frase(texto: str, ini: int, fim: int) -> str:
    """A frase em volta do trecho [ini, fim): do ponto final anterior ao próximo (o ponto de "1.065,4" não é fim)."""
    cortes = [m.end() for m in re.finditer(r"[.;!?](?=\s|$)", texto)]
    a = max([c for c in cortes if c <= ini], default=0)
    b = min([c for c in cortes if c >= fim], default=len(texto))
    return texto[a:b]


# ── o item que nasce de "sem dado" e o equipamento que não está no dossiê ─────────────────────────────────────────────
# Levi, 18/11/2026, quando soube que a IA ainda podia trocar o nome de um equipamento ou criar item a partir de "sem
# dado": "Não deve poder". Os casos da prova em produção: a Poconé ("Verificar os extintores, cuja situação o dossiê não
# traz"), a Colíder 1 ("Extintores sem conferência", com "Extintores: sem dado" no dossiê, e "Inversor 1 com falha de
# comunicação", onde o dossiê tinha o Inversor 2.8).
_RX_ASSUNTO_SEM_DADO = re.compile(r"^- ([^:\n]{2,25}): sem (?:dado|leitura)\.?[ \t]*$", re.M)
_RX_FALA_SEM_DADO = re.compile(r"\bsem dado\b|\bsem leitura\b|dossie nao (?:traz|diz|informa|tem)\b|"
                               r"nao (?:retornou|retornaram|traz|trazem) (?:leitura|dado)")
_EQUIPAMENTO = {"inversor": ("inversores", "inversor", "invr", "inv"), "cabine": ("cabines", "cabine", "cabn"),
                "tracker": ("trackers", "tracker", "etkr", "tkr")}
_RX_EQUIPAMENTO = re.compile(r"\b(inversor|cabine|tracker)(?:es|s)?\s+(\d{1,3}(?:\.\d{1,3})*)", re.I)


def _plano(txt) -> str:
    return _sem_acento(txt)


def assuntos_sem_dado(dossie: str) -> list[str]:
    """Os assuntos que o dossiê marca como "sem dado" ou "sem leitura" numa linha só deles ("- Extintores: sem dado."):
    no singular e sem acento ("extintor"); a sigla fica como é ("PR"). A linha que diz mais ("- Agora: sem leitura do
    COS (a fonte não respondeu...)") não entra: o assunto dela ("agora") é palavra de qualquer frase."""
    out = []
    for m in _RX_ASSUNTO_SEM_DADO.finditer(dossie or ""):
        bruto = m.group(1).strip()
        if bruto.isupper() and len(bruto) <= 4:
            a = bruto
        else:
            pal = _plano(bruto).split()
            if pal and len(pal[-1]) > 4:
                pal[-1] = pal[-1][:-2] if pal[-1].endswith("es") else pal[-1].rstrip("s")
            a = " ".join(pal)
        if a and a not in out:
            out.append(a)
    return out


def _nasce_de_sem_dado(texto: str, assuntos: list[str]) -> bool:
    plano = _plano(texto)
    if _RX_FALA_SEM_DADO.search(plano):
        return True
    return any(re.search(rf"\b{re.escape(a)}\b", texto) if a.isupper() else re.search(rf"\b{re.escape(a)}", plano)
               for a in assuntos)


def tirar_sem_dado(diag: dict | None, dossie: str) -> int:
    """Tira das três listas o item que nasce de dado que o dossiê não tem: o que diz isso com as próprias palavras ("sem
    dado", "o dossiê não traz") e o que fala de um assunto que o dossiê marca como sem dado. Devolve quantos saíram (e
    guarda em `sem_dado_tirados`). A situação fica: dizer que não há dado pode; virar tarefa de alguém, não."""
    if not diag:
        return 0
    assuntos = assuntos_sem_dado(dossie)
    n = 0
    for lista in MAX_ITENS:
        ficam = [x for x in diag.get(lista) or [] if not _nasce_de_sem_dado(x.get("texto") or "", assuntos)]
        n += len(diag.get(lista) or []) - len(ficam)
        diag[lista] = ficam
    diag["sem_dado_tirados"] = n
    return n


def equipamentos_fora(textos: list[str], dossie: str) -> list[str]:
    """Os inversores, as cabines e os trackers citados pelo número que o dossiê não tem com esse número (aceita o zero à
    esquerda e os apelidos das fontes: "INVR2.8", "ETKR1.103")."""
    baixo = (dossie or "").lower()
    fora = set()
    for t in textos:
        for m in _RX_EQUIPAMENTO.finditer(t or ""):
            tipo, ident = m.group(1).lower(), m.group(2)
            numero = r"\.".join("0*" + str(int(p)) for p in ident.split("."))
            if not re.search(r"(?:" + "|".join(_EQUIPAMENTO[tipo]) + r")\s*-?\s*" + numero + r"(?!\d|\.\d)", baixo):
                fora.add(f"{tipo.capitalize()} {ident}")
    return sorted(fora)


def conferir(diag: dict | None, dossie: str, dia: str | None = None) -> list[str]:
    """O que o diagnóstico diz e o dossiê não sustenta, em frases para a tela. Confere, na situação, nos itens e nos
    pedidos:
    - cada "N desligamentos" contra a tabela por mês do COS: o N tem que ser o do mês dito na mesma frase (dois meses
      ditos: o de um deles ou a soma); sem mês dito, o do mês corrente (o diagnóstico é do mês corrente); com o mês
      corrente fora da tabela, um número dela;
    - cada "N strings fora" contra as strings fora agora: o total ou o de um inversor;
    - cada inversor, cabine ou tracker citado pelo número: tem que estar no dossiê com esse número.
    Sem a tabela ou sem a linha no dossiê, aquela conferência não é feita."""
    if not diag:
        return []
    textos = [diag.get("situacao") or ""] + [x.get(k) or "" for lista in MAX_ITENS for x in diag.get(lista) or []
                                             for k in ("texto", "pedido")]
    falhas = []
    por_mes = desligamentos_do_dossie(dossie)
    corrente = _MESES[int((dia or hoje())[5:7]) - 1]
    fora = set()
    for t in textos if por_mes else ():
        for m in _RX_DESLIGAMENTOS.finditer(t):
            n, frase = int(m.group(1)), _frase(t, m.start(), m.end()).lower()
            ditos = [mes for mes in por_mes if mes in frase]
            if len(ditos) > 1:
                certos = {por_mes[x] for x in ditos} | {sum(por_mes[x] for x in ditos)}
            elif ditos:
                certos = {por_mes[ditos[0]]}
            elif corrente in por_mes:
                certos = {por_mes[corrente]}
            else:
                certos = set(por_mes.values())
            if n not in certos:
                fora.add(n)
    tabela = "; ".join(f"{mes}: {n}" for mes, n in por_mes.items())
    falhas += [f"{n} desligamento{'' if n == 1 else 's'}: não bate com a tabela por mês do dossiê ({tabela})"
               for n in sorted(fora)]
    st = strings_do_dossie(dossie)
    if st:
        certos = {st["total"], *st["por_inversor"]}
        fora = sorted({int(n) for t in textos for n in _RX_STRINGS_FORA.findall(t)} - certos)
        falhas += [f"{n} string{'' if n == 1 else 's'} fora: o dossiê tem {st['total']} fora agora"
                   + (f" ({', '.join(str(x) for x in st['por_inversor'])} por inversor)" if len(st["por_inversor"]) > 1 else "")
                   for n in fora]
    falhas += [f"{nome}: não está no dossiê com esse nome" for nome in equipamentos_fora(textos, dossie)]
    return falhas


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
    if int(d.get("versao") or 1) != VERSAO:          # feito com o pedido de outra versão: refaz na próxima abertura
        return None
    return d


def anterior(cfg, usina_id: int, dia: str | None = None) -> dict | None:
    """O último diagnóstico que deu certo ANTES do dia, de até `MAX_DIAS_ANTERIOR` dias: o que a tela mostra enquanto o
    de hoje é feito (18/11/2026: o primeiro a abrir a usina no dia esperava 40 s pela IA, com pensamento, olhando o
    parecer de sempre). O que falhou, o estragado e o do próprio dia não servem. None: não há."""
    dia = dia or hoje()
    try:
        base = datetime.fromisoformat(dia)
    except ValueError:
        return None
    for n in range(1, MAX_DIAS_ANTERIOR + 1):
        pasta = _pasta(cfg, f"{base - timedelta(days=n):%Y-%m-%d}")
        arq = pasta / f"{int(usina_id)}.json" if pasta else None
        if not arq or not arq.exists():
            continue
        try:
            d = json.loads(arq.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if d.get("ok") and (d.get("diag") or d.get("texto")):
            return d
    return None


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


def lista_de_temas(setores: list[dict] | None) -> str:
    """Os temas de cada setor, no fim do pedido: de onde a IA tira o "tema" do pedir."""
    linhas = [f"- {s['nome']}: " + "; ".join(t["nome"] for t in s.get("temas") or [])
              for s in setores or [] if s.get("temas")]
    return ("\nTEMAS de cada setor (o \"tema\" do pedir é o nome exato de um deles; sem tema que sirva, null):\n"
            + "\n".join(linhas)) if linhas else ""


def gerar(cfg, usina_id: int, dossie: str, dossie_tokens: int = 0, dia: str | None = None,
          setores: list[dict] | None = None) -> dict:
    """Faz o diagnóstico, guarda e solta a trava. Roda numa thread à parte (a rota não espera); no teste, na hora."""
    dia = dia or hoje()
    pasta = _pasta(cfg, dia)

    def uma_vez(pensar: bool):
        rs = IA.perguntar(cfg, [modelo(cfg)], dossie, PEDIDO + lista_de_temas(setores),
                          setores=[s["nome"] for s in setores or []], pensar=pensar)
        IA.registrar(cfg, usina_id, "[diagnóstico do dia]", rs, "diagnostico-do-dia", dossie_tokens)
        r = rs[0] if rs else {"ok": False, "erro": "Nenhuma IA ligada para o diagnóstico."}
        diag = ler(r.get("texto") or "", dossie, setores) if r.get("ok") else None
        tirar_sem_dado(diag, dossie)        # o item que nasce de "sem dado" não chega à tela (Levi: "Não deve poder")
        return r, diag

    try:
        r, diag = uma_vez(PENSAR)
        # o número que não bate com o dossiê: refaz UMA vez, pensando (mais lento e mais cuidadoso); se insistir, vale
        # o refeito, e a tela avisa o que ficou a conferir
        falhas, refeito = conferir(diag, dossie, dia), False
        if falhas and not PENSAR:
            r2, diag2 = uma_vez(True)
            if r2.get("ok") and diag2:
                r, diag, falhas, refeito = r2, diag2, conferir(diag2, dossie, dia), True
        agora = datetime.now(IA._BRT)
        d = {"usina_id": int(usina_id), "dia": dia, "ts": time.time(), "gerado_em": agora.isoformat(timespec="seconds"),
             "ok": bool(r.get("ok")), "modelo": r.get("id") or "", "rotulo": r.get("rotulo") or "",
             "troca": r.get("troca") or "", "erro": r.get("erro") or "", "ms": r.get("ms"), "versao": VERSAO}
        if r.get("ok"):
            d["diag"] = diag
            d["texto"] = "" if d["diag"] else IA.limpar_citacoes(r.get("texto") or "")[:3000]
            d["numeros"] = r.get("numeros")
            if refeito:
                d["refeito"] = True
            if falhas:
                d["conferir"] = falhas
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
            "hora": em[11:16], "data": f"{em[8:10]}/{em[5:7]}" if len(em) >= 10 else "",
            **({"conferir": d["conferir"]} if d.get("conferir") else {})}
