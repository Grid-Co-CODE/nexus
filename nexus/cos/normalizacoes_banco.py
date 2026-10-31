"""As normalizações da Ronda COS no banco (29/10/2026): `nexus_cos_normalizacoes · fato_normalizacao` (1 linha = 1
ocorrência normalizada, o `registro` da Ronda COS, no estado mais recente) e `atualizacao` (uma linha: quando, quantas,
desde quando; quem lê confere que leu a gravação inteira).

Levi, 29/10/2026: "Quero uma adaptação para a disponibilidade da Thopen [...] calcule a disponibilidade por lá usando o
de-para como referência"; "o que for falha de comunicação tem a coluna Geração Parou, se sim então deve contar na
disponibilidade e entrar nos comentários. Nos comentários tem que vir as proteções atuadas". As decisões dele, no mesmo
dia: o Nexus grava no banco (a chave da API só está no servidor do Nexus) e a plataforma e o dashboard leem de lá; vale
só para a Thopen; conta só o que está nas normalizações. Até aqui a tela COS → Normalizações só lia (27/10: "a tela, sem
guardar").

O fato é o da Ronda COS, sem a régua: a disponibilidade (que tipo conta, a janela solar, o kWp) é da plataforma. A usina
liga pelo código do Fracttal (`usina_codigo`, o campo que o guia da API manda usar para cruzar) contra o código do
Registro mestre (`equipamento.usina_do_codigo`, a mesma ligação dos fatos do Campo: só o código de UMA usina liga).
Regra 8: os dois nomes de pessoa da API (`os_aberta_por`, `tecnico`) e o texto livre (`impacto`, `detalhes`,
`informe`) não entram; as proteções entram como o time as escreve, só os códigos curtos (`PROTECAO`).

**As ocorrências ainda abertas** (30/10/2026, Levi: "para as em aberto contar na disponibilidade precisamos puxar os
dados dessa fonte"): a parada que o COS ainda não normalizou não está na API de normalizações, e a Thopen só contava
quando a usina voltava (a OS 16958 de Santarém, inversor parado desde 12/07 aguardando peça, não contava nada). A aba
`fato_ocorrencia_aberta` é o retrato da hora das abertas da Thopen, pela fotografia do Andamento
(`GET /api/nexus/<cliente>`, a lista `ocorrencias` de cada usina, a mesma da tela Ronda); as tags dos equipamentos, o
código do tipo e o início da falha vêm dela ou, quando ela não manda, da rota das ocorrências de 30 dias, pelo registro.
Quando a ocorrência normaliza, sai daqui e entra no `fato_normalizacao` (a mesma chave, o registro). Na falha da leitura,
o retrato de antes fica, com a hora dele (`abertas_em` na `atualizacao`): quem conta sabe de quando é.

**Só a máquina que lê a API grava** (regra 12: só o servidor tem a chave do Andamento; no PC a fonte não está ligada e
a volta não faz nada). Grava só com a memória completa e sem erro (`normalizacoes.ler`), e se a última gravação tiver
mais de 50 min; a volta acorda num minuto seu entre :22 e :27, longe da carga de dados (:40). A memória guarda desde o
1º dia de `normalizacoes.PRIMEIRO_MES`; as linhas do banco de antes disso ficam como estão (o livro não perde o
passado se a memória um dia guardar menos). `NEXUS_NORMALIZACOES_PUBLICAR=0` desliga.
"""
import logging
import random
import re
import threading
import time
import unicodedata
from collections import Counter
from datetime import datetime, timedelta, timezone

from ..dados import equipamento as EQ
from ..dados import livros
from . import andamento as AND
from . import normalizacoes as NO

LIVRO = "nexus_cos_normalizacoes"
ABA = "fato_normalizacao"
NOME_LIVRO = "Nexus · COS: normalizações da Ronda COS (a hora da volta, o tipo de falha e as proteções)"
TIPO = "snapshot_acumulado"
GRAO = "1 linha = 1 ocorrência normalizada da Ronda COS (o registro), no estado mais recente"
CHAVE = ("registro",)
CAB = ("registro", "os", "os_relacionadas", "cliente", "usina_codigo", "usina_id", "usina_ligada_por",
       "equipamentos_codigos", "equipamentos_qtd", "tipo_falha", "severidade", "estado", "normalizada", "hora_real",
       "fim_corrigido", "declarada_por", "inicio", "normalizado_em", "data_id_inicio", "data_id_volta", "fora_min",
       "geracao_parou", "protecoes", "fora_do_escopo_oem", "mudou_em")
MEDIDAS = (("fora_min", "min", "aditiva"), ("equipamentos_qtd", "qtd", "nao"), ("normalizada", "1/0", "aditiva"),
           ("hora_real", "1/0", "aditiva"), ("geracao_parou", "1/0", "aditiva"))
CAB_ATUALIZACAO = ("atualizado_em", "linhas_qtd", "desde", "ligadas_qtd", "abertas_em", "abertas_qtd")
# as ocorrências ainda abertas (30/10/2026): o retrato da hora, trocado inteiro a cada volta
ABA_ABERTAS = "fato_ocorrencia_aberta"
TIPO_ABERTAS = "snapshot_periodico"
GRAO_ABERTAS = "1 linha = 1 ocorrência ainda aberta na Ronda COS (o registro), no retrato da última volta"
CAB_ABERTA = ("registro", "os", "cliente", "usina_codigo", "usina_id", "usina_ligada_por", "equipamentos_codigos",
              "equipamentos_qtd", "equipamentos_de", "equipamentos_citados", "tipo_falha", "severidade", "etapa", "inicio",
              "data_id_inicio",
              "dias_aberta_qtd", "geracao_parou", "protecoes")
MEDIDAS_ABERTAS = (("equipamentos_qtd", "qtd", "nao"), ("dias_aberta_qtd", "dias", "nao"),
                   ("geracao_parou", "1/0", "aditiva"))
# Só a Thopen (a disponibilidade pelo COS é só dela, decisão do Levi em 29/10/2026); o nome é o da rota do Andamento
CLIENTE_ABERTAS = "Thopen"
# a rota das ocorrências completa o que a fotografia não manda (as tags, o código do tipo, o início): 30 dias é o teto dela
DIAS_COMPLEMENTO = 30
# O equipamento que o COS cita pelo nome, em referência curta (30/10/2026: a OS 16958 de Santarém vem só com "Inversor
# 2.7", sem a tag, e é mais velha que os 30 dias da rota que manda a tag; sem a referência, a régua contava um inversor de
# potência média na usina errada). "Inversor 2.7" → INV2.7, "Cabine 2"/"Skid 2"/"QGBT 2" → CAB2; o nome não vai ao banco
CITADO = ((re.compile(r"\binv(?:ersor)?\.?\s*(\d+(?:\.\d+)?)\b", re.I), "INV"),
          (re.compile(r"\b(?:cabine|skid|qgbt)\s*(\d+)\b", re.I), "CAB"))
INTERVALO_MIN = 50
PRIMEIRA_S = 600            # a 1ª volta 10 min depois de subir: a 1ª carga da memória vem em páginas
MINUTO_DA_HORA = 22
DESENCONTRO_MAX_S = 300
TENTATIVAS_MEMORIA = 8      # pedidos para a memória completar (4 páginas de 500 por pedido)
# a proteção como o time escreve ("27ABC", "59C", "86", "78/81"): só o código curto; frase não entra (regra 8)
PROTECAO = re.compile(r"^[0-9A-Z][0-9A-Z/ .+-]{0,19}$")
_BRT = timezone(timedelta(hours=-3))
_LACO = {"thread": None, "parar": threading.Event(), "ultimo": None, "quando": None}
log = logging.getLogger("nexus.cos")


def _txt(v) -> str:
    return " ".join(str(v or "").split())


def _um_zero(v) -> str | int:
    return "" if not isinstance(v, bool) else int(v)


def _data_id(d: datetime | None) -> str | int:
    return int(d.astimezone(_BRT).strftime("%Y%m%d")) if d else ""


def _iso(d: datetime | None) -> str:
    return d.astimezone(_BRT).isoformat(timespec="seconds") if d else ""


def protecoes(lista) -> str:
    """As proteções que atuaram, em códigos curtos, sem repetir, separadas por ";"."""
    out = []
    for x in lista or ():
        p = _txt(x).upper()
        if p and PROTECAO.match(p) and p not in out:
            out.append(p)
    return ";".join(out)


def linha(n: dict, idx) -> list:
    """A linha do fato (CAB) de uma normalização da API. `idx`: `equipamento.IndiceUsinas` do Registro mestre."""
    inicio, volta = AND.instante(n.get("inicio")), AND.instante(n.get("normalizado_em"))
    cod = _txt(n.get("usina_codigo"))
    uid, por = EQ.usina_do_codigo(cod, idx) if cod else (None, EQ.SEM_CODIGO_USINA)
    equip = [EQ.canon(e.get("codigo")) for e in n.get("equipamentos") or [] if isinstance(e, dict)]
    equip = [c for c in equip if c]
    try:
        fora = int(n.get("fora_min")) if n.get("fora_min") is not None else ""
    except (TypeError, ValueError):
        fora = ""
    return [str(n.get("registro")), _txt(n.get("os")), ";".join(_txt(x) for x in n.get("os_relacionadas") or []
                                                               if _txt(x)),
            _txt(n.get("cliente")).upper(), cod, uid or "", (por if uid else ""), ";".join(equip), len(equip),
            _txt(n.get("tipo_falha")).upper(), _txt(n.get("severidade")).upper(), _txt(n.get("estado")).upper(),
            int(n.get("normalizada") is not False), int(n.get("hora_real") is not False),
            int(bool(n.get("fim_corrigido"))), _txt(n.get("declarada_por")), _iso(inicio), _iso(volta),
            _data_id(inicio), _data_id(volta), fora, _um_zero(n.get("geracao_parou")), protecoes(n.get("protecoes")),
            int(bool(n.get("fora_do_escopo_oem"))), _iso(AND.instante(n.get("mudou_em")))]


def fato(itens, usinas) -> tuple[list, dict]:
    """(linhas, relatório). `usinas`: a aba `usinas` do cadastro. Ordenado pelo registro: o mesmo conteúdo dá a mesma
    gravação em qualquer máquina (regra 11)."""
    idx = EQ.IndiceUsinas(usinas)
    linhas = sorted((linha(n, idx) for n in itens or () if isinstance(n, dict) and n.get("registro")),
                    key=lambda l: l[0])
    ligadas = sum(1 for l in linhas if l[5])
    sem = sorted({l[4] or "(sem código)" for l in linhas if not l[5]})
    return linhas, {"linhas": len(linhas), "ligadas": ligadas, "sem_usina": sem[:30]}


def _rotulo(v) -> str:
    return unicodedata.normalize("NFKD", _txt(v)).encode("ascii", "ignore").decode().upper()


def tipos_por_rotulo(normalizacoes) -> dict:
    """{rótulo sem acento em maiúsculas: código do tipo}, pelas normalizações (a API delas manda os dois): a fotografia
    do Andamento manda o tipo pelo rótulo ("Desligamento de usina"), e a régua da plataforma lê o código."""
    out = {}
    for n in normalizacoes or ():
        if isinstance(n, dict) and n.get("tipo_falha_rotulo") and n.get("tipo_falha"):
            out.setdefault(_rotulo(n["tipo_falha_rotulo"]), _txt(n["tipo_falha"]).upper())
    return out


def _tipo_aberta(o: dict, extra: dict, tipos: dict) -> str:
    cod = _txt(o.get("tipo_falha_codigo") or extra.get("tipo_falha_codigo")).upper()
    if cod:
        return cod
    rot = _rotulo(o.get("tipo_falha") or extra.get("tipo_falha"))
    # o rótulo que nenhuma normalização trouxe ainda vira código pelo próprio texto ("DESLIGAMENTO_DE_SKID"): a régua
    # lê "DESLIG" nele, e o tipo fica à vista na aba
    return tipos.get(rot) or re.sub(r"[^A-Z0-9]+", "_", rot).strip("_")


def citados(nomes) -> str:
    """As referências curtas dos equipamentos que o COS cita pelo nome, sem repetir, separadas por ";"."""
    out = []
    for n in nomes if isinstance(nomes, list) else ():
        for rx, pref in CITADO:
            m = rx.search(_txt(n))
            if m and pref + m.group(1) not in out:
                out.append(pref + m.group(1))
                break
    return ";".join(out)


def linha_aberta(u: dict, o: dict, extra: dict, idx, tipos: dict) -> list:
    """A linha (CAB_ABERTA) de uma ocorrência aberta da fotografia: `u` a usina dela, `extra` a mesma ocorrência na
    rota de 30 dias ({} quando não está lá)."""
    cod = _txt(u.get("codigo") or o.get("usina_codigo") or extra.get("usina_codigo"))
    uid, por = EQ.usina_do_codigo(cod, idx) if cod else (None, EQ.SEM_CODIGO_USINA)
    equip, de = [], ""
    for origem, tags in (("fotografia", o.get("ativos")), ("ocorrencias", extra.get("ativos"))):
        equip = [c for c in (EQ.canon(t) for t in (tags if isinstance(tags, list) else ())) if c]
        if equip:
            de = origem
            break
    inicio = AND.instante(extra.get("inicio")) or AND.instante(o.get("inicio")) or AND.instante(o.get("abertura"))
    prot = o.get("protecoes") if isinstance(o.get("protecoes"), list) else [o.get("protecao")]
    gp = o.get("geracao_parou") if isinstance(o.get("geracao_parou"), bool) else extra.get("geracao_parou")
    os_ = _txt(o.get("os") or extra.get("os"))
    try:
        dias = int(o.get("dias_aberta")) if o.get("dias_aberta") is not None else ""
    except (TypeError, ValueError):
        dias = ""
    return [str(o.get("registro")), os_ if os_.isdigit() else "", CLIENTE_ABERTAS.upper(), cod, uid or "",
            (por if uid else ""), ";".join(equip), len(equip), de,
            citados(o.get("equipamentos") if isinstance(o.get("equipamentos"), list) else extra.get("equipamentos")),
            _tipo_aberta(o, extra, tipos),
            _txt(o.get("severidade")).upper(), _txt(o.get("etapa")), _iso(inicio), _data_id(inicio), dias,
            _um_zero(gp), protecoes([*(prot or ()), *(extra.get("protecoes") or ())])]


def abertas(fotografia: dict | None, ocorrencias, normalizacoes, usinas) -> tuple[list, dict]:
    """(linhas, relatório) das ocorrências abertas da fotografia. A que já está normalizada na memória sai (a
    fotografia pode estar um minuto atrás): a ocorrência conta uma vez, pela normalização. Sem registro não entra."""
    idx = EQ.IndiceUsinas(usinas)
    tipos = tipos_por_rotulo(normalizacoes)
    fechadas = {str(n.get("registro")) for n in normalizacoes or ()
                if isinstance(n, dict) and n.get("registro") and n.get("normalizada") is not False}
    extra = {str(o.get("registro")): o for o in ocorrencias or () if isinstance(o, dict) and o.get("registro")}
    linhas, vistos, ja = [], set(), 0
    for u in (fotografia or {}).get("usinas") or ():
        for o in (u.get("ocorrencias") or ()) if isinstance(u, dict) else ():
            reg = str(o.get("registro") or "") if isinstance(o, dict) else ""
            if not reg or reg in vistos:
                continue
            vistos.add(reg)
            if reg in fechadas:
                ja += 1
                continue
            linhas.append(linha_aberta(u, o, extra.get(reg, {}), idx, tipos))
    linhas.sort(key=lambda l: l[0])
    de = Counter(l[8] or "sem" for l in linhas)
    return linhas, {"abertas": len(linhas), "abertas_ligadas": sum(1 for l in linhas if l[4]),
                    "abertas_ja_normalizadas": ja, "abertas_equipamentos_de": dict(de)}


def ler_abertas(config, normalizacoes, usinas, agora) -> tuple[list | None, str, dict]:
    """(linhas, quando a fotografia foi lida, relatório) ou (None, "", relatório com o motivo): a fotografia velha ou
    que falhou não grava retrato novo. A rota de 30 dias que falhar só deixa de completar (fica no relatório)."""
    foto = AND.ler(config, CLIENTE_ABERTAS)
    if foto.velha or not foto.dados:
        return None, "", {"abertas_mantidas": f"a fotografia do Andamento: {foto.erro or 'sem dados'}"}
    oc = AND.ler_ocorrencias(config, CLIENTE_ABERTAS, DIAS_COMPLEMENTO)
    linhas, rel = abertas(foto.dados, (oc.dados or {}).get("ocorrencias") if not oc.velha else None, normalizacoes,
                          usinas)
    if oc.velha or not oc.dados:
        rel["abertas_sem_complemento"] = oc.erro or "sem dados"
    lida = datetime.fromtimestamp(foto.lido_em, _BRT) if foto.lido_em else agora
    return linhas, lida.isoformat(timespec="seconds"), rel


def _do_banco_antes(linhas_banco, desde_id: int) -> list:
    """As linhas já gravadas de antes do que a memória guarda (pela volta ou, sem ela, pelo início): ficam como estão."""
    out = []
    for r in linhas_banco or ():
        try:
            d = int(str(r.get("data_id_volta") or r.get("data_id_inicio") or "0").split(".")[0])
        except ValueError:
            continue
        if 0 < d < desde_id and r.get("registro"):
            out.append([r.get(c, "") for c in CAB])
    return out


def _base(config) -> str:
    from ..cadastro.ligacoes import BASE_API
    return (config.get("GRIDCO_DB_API") or BASE_API).rstrip("/")


def _ultima(base, sessao) -> datetime | None:
    v = livros.atualizado_em(base, sessao, LIVRO)
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00")) if v else None
    except ValueError:
        return None
    return d if d is None or d.tzinfo else d.replace(tzinfo=timezone.utc)


def memoria_completa(config, agora=None, espera_s: float = 2.0):
    """A leitura das normalizações completa e sem erro, ou (None, o motivo). Pede até a 1ª carga terminar."""
    for i in range(TENTATIVAS_MEMORIA):
        leitura = NO.ler(config, agora)
        if leitura.erro and not leitura.dados:
            return None, f"o Andamento: {leitura.erro}"
        if leitura.velha:
            return None, f"a memória das normalizações está velha ({leitura.erro})"
        if leitura.dados and not leitura.dados.get("carregando"):
            return leitura, ""
        if i + 1 < TENTATIVAS_MEMORIA:
            time.sleep(espera_s)
    return None, "a 1ª carga das normalizações ainda não terminou"


def publicar(config, sessao=None, *, agora=None, forcar=False, leitura=None, abertas_lidas=None) -> dict:
    """Uma volta: confere a última gravação e a memória, monta os fatos e grava as três abas (conferidas depois,
    `livros.publicar`). Devolve o relatório (só contagens). `leitura` e `abertas_lidas` ((linhas, quando, relatório),
    o que `ler_abertas` devolve) são para os testes."""
    import requests
    if not AND.fonte(config).ligada and leitura is None:
        return {"pulou": "a fonte do Andamento não está ligada nesta máquina"}
    s = sessao or requests.Session()
    base = _base(config)
    agora = agora or datetime.now(_BRT)

    def gravou_ha_pouco():
        u = None if forcar else _ultima(base, s)
        if u and agora - u < timedelta(minutes=INTERVALO_MIN):
            return f"a última gravação é de {u.astimezone(_BRT).isoformat(timespec='minutes')}"
    if pulou := gravou_ha_pouco():
        return {"pulou": pulou}
    if not config.get("GRIDCO_SQL_TOKEN"):
        return {"erro": "sem GRIDCO_SQL_TOKEN: não grava"}
    if leitura is None:
        leitura, motivo = memoria_completa(config, agora)
        if leitura is None:
            return {"recusou": f"{motivo}; o livro fica como está"}
    usinas = livros.ler(base, s, "cadastro_nexus", "usinas")
    if not usinas:
        return {"recusou": "o cadastro de usinas não veio do banco: nada ligaria; o livro fica como está"}
    linhas, rel = fato(leitura.dados.get("itens"), usinas)
    if len({l[0] for l in linhas}) != len(linhas):
        return dict(rel, recusou="registro repetido: o grão quebrou; o livro fica como está")
    desde = NO.inicio_da_guarda(agora)
    antes = _do_banco_antes(livros.ler(base, s, LIVRO, ABA), int(desde.strftime("%Y%m%d")))
    if not linhas and not antes and livros.ler(base, s, LIVRO, ABA):
        return dict(rel, recusou="a memória saiu vazia e o banco tem linhas: o livro fica como está")
    if pulou := gravou_ha_pouco():          # outra volta gravou enquanto esta fazia a conta
        return dict(rel, pulou=pulou)
    todas = sorted(antes + linhas, key=lambda l: str(l[0]))
    rel["antes_mantidas"] = len(antes)
    ab, ab_em, rel_ab = abertas_lidas or ler_abertas(config, leitura.dados.get("itens"), usinas, agora)
    rel.update(rel_ab)
    if ab is None:
        # a fotografia não veio: o retrato de antes fica, com a hora dele (o livro é trocado inteiro a cada gravação)
        ab = [[r.get(c, "") for c in CAB_ABERTA] for r in livros.ler(base, s, LIVRO, ABA_ABERTAS) if r.get("registro")]
        ab_em = next((str(r.get("abertas_em") or "") for r in livros.ler(base, s, LIVRO, "atualizacao")), "")
    atu = [agora.isoformat(timespec="seconds"), len(todas), desde.date().isoformat(), rel["ligadas"] + sum(
        1 for l in antes if l[5]), ab_em, len(ab)]
    rel["gravado"] = livros.publicar(LIVRO, NOME_LIVRO, {ABA: (CAB, todas), ABA_ABERTAS: (CAB_ABERTA, ab),
                                                         "atualizacao": (CAB_ATUALIZACAO, [atu])},
                                     base=base, token=config["GRIDCO_SQL_TOKEN"], sessao=s)
    return rel


def estado() -> dict:
    """O resultado da última volta deste processo e quando foi."""
    return {"ultimo": _LACO["ultimo"], "quando": _LACO["quando"]}


def _espera_s(agora=None, desencontro_s: float = 0.0) -> float:
    agora = agora or datetime.now(_BRT)
    alvo = agora.replace(minute=MINUTO_DA_HORA, second=0, microsecond=0) + timedelta(seconds=desencontro_s)
    if alvo <= agora:
        alvo += timedelta(hours=1)
    return (alvo - agora).total_seconds()


def ligar(app):
    """O laço: a 1ª volta 10 min depois de subir, depois a cada hora, no :22 mais o atraso que este processo sorteou.
    Não liga onde `NEXUS_NORMALIZACOES_PUBLICAR=0`; onde a fonte do Andamento não está ligada (o PC), cada volta só diz
    que pulou. Quem chama é o app.py e o servir.py, nunca o create_app: teste não fala com a rede."""
    if _LACO["thread"] is not None or str(app.config.get("NEXUS_NORMALIZACOES_PUBLICAR", "1")).strip() == "0":
        return
    desencontro = random.uniform(0, DESENCONTRO_MAX_S)

    def laco():
        espera = PRIMEIRA_S
        while not _LACO["parar"].wait(espera):
            with app.app_context():
                try:
                    _LACO["ultimo"] = publicar(app.config)
                    log.info("normalizações no banco: %s", {k: v for k, v in _LACO["ultimo"].items() if k != "gravado"})
                except Exception as e:      # noqa: BLE001 — o laço não morre por uma volta
                    _LACO["ultimo"] = {"erro": f"{type(e).__name__}: {e}"[:300]}
                    log.exception("normalizações no banco")
                _LACO["quando"] = datetime.now(_BRT).isoformat(timespec="minutes")
            espera = _espera_s(desencontro_s=desencontro)

    _LACO["thread"] = threading.Thread(target=laco, name="nexus-cos-normalizacoes-banco", daemon=True)
    _LACO["thread"].start()
