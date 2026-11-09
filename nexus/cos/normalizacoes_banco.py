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

**O relato ao cliente** (09/11/2026, o dono: "precisamos, de alguma forma, unir todas as informações para uma informação
final e completa pro cliente"): `relato_cliente` (o parágrafo do primeiro dia) e `relato_continuacao` (a linha curta dos
dias seguintes) entram, para a Plataforma mostrar no Comentário do dia em vez da linha montada só com o tipo, as horas,
a proteção e a OS. Eles NÃO são texto livre: a Ronda COS os monta por regras fixas, só com frases-modelo e valores
(horários, protocolos, códigos de proteção, a causa reconhecida), sem copiar nada das notas, então nome, telefone e
bastidor não passam (`apps/andamento/src/regras/relato-cliente.ts` da Ronda COS). Vazio: sem hora real da volta, ou o
Andamento de antes de 09/11/2026.

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
       "geracao_parou", "protecoes", "fora_do_escopo_oem", "mudou_em", "relato_cliente", "relato_continuacao")
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
# o comentário de cada dia para a Plataforma de Performance (09/11/2026): ver `comentarios_do_dia`
ABA_COMENTARIOS = "fato_comentario_dia"
TIPO_COMENTARIOS = "snapshot_acumulado"
GRAO_COMENTARIOS = ("1 linha = 1 usina (o código do Fracttal) × 1 dia de Brasília em que uma ocorrência da Ronda COS "
                    "tocou o horário de sol (06h às 18h)")
CAB_COMENTARIO = ("usina_codigo", "usina_id", "usina_ligada_por", "cliente", "data_id", "dia", "relato_do_dia",
                  "registros", "os", "ocorrencias_qtd")
# O horário de sol do comentário: a parada que fica toda fora dele (a noite) não explica a disponibilidade do dia
JANELA_DO_SOL_H = (6, 18)
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
# O Atualizar do Dashboard Thopen (03/11/2026, Levi: "sinto falta do botão 'Atualizar' para puxar os dados (...) fiz umas
# alterações nas normalizações e precisava trazer"): a correção feita no Andamento esperava até a volta da hora. O 5080
# grava o pedido (o clique da conta da Grid) no livro dele; o laço confere de minuto em minuto, e o pedido mais novo que a
# última gravação faz a volta na hora, sem a espera dos 50 min. Entre duas voltas pedidas, PEDIDO_INTERVALO_S
PEDIDO_LIVRO = "thopen_pedidos"
PEDIDO_ABA = "atualizacao"
PEDIDO_CHECA_S = 60
PEDIDO_INTERVALO_S = 120
TENTATIVAS_MEMORIA = 8      # pedidos para a memória completar (4 páginas de 500 por pedido)
# a proteção como o time escreve ("27ABC", "59C", "86", "78/81"): só o código curto; frase não entra (regra 8)
PROTECAO = re.compile(r"^[0-9A-Z][0-9A-Z/ .+-]{0,19}$")
_BRT = timezone(timedelta(hours=-3))
_LACO = {"thread": None, "parar": threading.Event(), "ultimo": None, "quando": None,
         # o pedido do Atualizar: a versão do livro do 5080 já vista sem nada novo, o último pedido gravado e a hora da
         # última volta pedida (o intervalo entre duas)
         "pedido_visto": None, "pedido_feito": None, "pedida_em": None}
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
            int(bool(n.get("fora_do_escopo_oem"))), _iso(AND.instante(n.get("mudou_em"))),
            _txt(n.get("relato_cliente")), _txt(n.get("relato_continuacao"))]


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


# O evento da ocorrência ainda aberta, em palavras (a aberta não tem relato: o relato precisa da volta)
_EVENTO_ABERTO = {
    "DESLIGAMENTO_USINA": "Usina desligada", "DESLIGAMENTO_CABINE": "Cabine desligada",
    "DESLIGAMENTO_SKID": "SKID desligado", "DESLIGAMENTO_QGBT": "QGBT desligado",
    "DESLIGAMENTO_INVERSOR": "Inversor desligado", "FALHA_COMUNICACAO": "Perda de comunicação com a usina",
    "ATUACAO_PROTECAO": "Usina desligada por atuação de proteção",
    "FALHA_CONCESSIONARIA": "Usina desligada por falta de energia da concessionária",
}
_PARTES = ("DESLIGAMENTO_CABINE", "DESLIGAMENTO_SKID", "DESLIGAMENTO_QGBT", "DESLIGAMENTO_INVERSOR")
_CITADO = ((re.compile(r"^CAB(\d+)$"), "Cabine {}"), (re.compile(r"^INV(.+)$"), "Inversor {}"),
           (re.compile(r"^SKID(\d+)$"), "SKID {}"), (re.compile(r"^QGBT(\d*)$"), "QGBT {}"))


def _evento_aberto(r: dict) -> str:
    """"Cabine 2 desligada" pela referência curta que o COS citou (CAB2); sem ela, o tipo ("Cabine desligada")."""
    tipo = str(r.get("tipo_falha") or "").upper()
    base = _EVENTO_ABERTO.get(tipo, "Ocorrência")
    citados = [c for c in str(r.get("equipamentos_citados") or "").split(";") if c]
    if tipo in _PARTES and citados:
        nomes = []
        for c in citados:
            for padrao, modelo in _CITADO:
                m = padrao.match(c)
                if m:
                    nomes.append(" ".join(modelo.format(m.group(1)).split()))
                    break
        if nomes:
            fim = base.split(" ", 1)[1] + ("s" if len(nomes) > 1 else "")
            return " e ".join(nomes) + " " + fim
    return base


def _dias_no_sol(inicio: datetime, fim: datetime, desde: datetime) -> list:
    """Os dias de Brasília em que [inicio, fim) toca o horário de sol, a partir de `desde`."""
    de_h, ate_h = JANELA_DO_SOL_H
    dias, d = [], max(inicio, desde).astimezone(_BRT).date()
    while d <= fim.astimezone(_BRT).date():
        sol_de = datetime(d.year, d.month, d.day, de_h, tzinfo=_BRT)
        sol_ate = datetime(d.year, d.month, d.day, ate_h, tzinfo=_BRT)
        if inicio < sol_ate and fim > sol_de:
            dias.append(d)
        d += timedelta(days=1)
    return dias


def comentarios_do_dia(fato_linhas, abertas_linhas, agora: datetime, desde: datetime) -> list:
    """O COMENTÁRIO DE CADA DIA para a Plataforma de Performance (09/11/2026). O dono: "Eu só preciso que os comentários
    cheguem ao cliente pra explicar corretamente porque a disponibilidade está baixa naquele dia". A Plataforma montava
    o comentário só com o tipo, as horas, a proteção e a OS ("Desligamento Usina de 25/10 às 12:41h a 27/10 às 11:25h;
    Proteção: Sem proteção ativa; OS 17470"); aqui ele sai PRONTO, por usina e por dia, e a Plataforma só mostra.

    - O dia da ocorrência é o dia de Brasília em que a parada tocou o horário de sol (`JANELA_DO_SOL_H`): a parada da
      noite não explica a disponibilidade do dia (a OS 15789 de Primavera, de 07/10 19:27 a 08/10 07:40, é de 08/10).
    - No 1º dia da ocorrência vai o `relato_cliente` (o parágrafo da Ronda COS); nos seguintes, o `relato_continuacao`.
      A normalizada sem relato (sem hora real da volta, ou gravada antes de 09/11/2026) não entra: o dia fica sem
      comentário do Nexus, e a Plataforma usa a linha dela.
    - A ocorrência ainda aberta entra com "<evento> desde <início>, em atendimento pelo COS".
    - Várias no mesmo dia: uma por linha, pela hora de início. Só a partir de `desde` (o que a memória guarda)."""
    por_dia: dict = {}

    def junta(r, d, texto, inicio):
        k = (str(r.get("usina_codigo") or ""), d)
        if not k[0] or not texto:
            return
        g = por_dia.setdefault(k, {"usina_id": r.get("usina_id") or "", "ligada_por": r.get("usina_ligada_por") or "",
                                   "cliente": r.get("cliente") or "", "itens": []})
        g["itens"].append((inicio, str(r.get("registro") or ""), str(r.get("os") or ""), texto))

    for linha in fato_linhas or ():
        r = dict(zip(CAB, linha))
        if str(r.get("normalizada")) in ("0", "False") or not r.get("relato_cliente"):
            continue
        ini, fim = AND.instante(r.get("inicio")), AND.instante(r.get("normalizado_em"))
        if not ini or not fim or fim <= ini:
            continue
        for i, d in enumerate(_dias_no_sol(ini, fim, desde)):
            junta(r, d, r["relato_cliente"] if i == 0 else (r.get("relato_continuacao") or r["relato_cliente"]), ini)
    for linha in abertas_linhas or ():
        r = dict(zip(CAB_ABERTA, linha))
        ini = AND.instante(r.get("inicio"))
        if not ini:
            continue
        evento = _evento_aberto(r)
        quando = f"{ini.strftime('%d/%m')} às {ini.strftime('%H:%M')}"
        for i, d in enumerate(_dias_no_sol(ini, agora, desde)):
            texto = (f"{evento} desde {quando}, em atendimento pelo COS." if i == 0
                     else f"Continuação: {evento} desde {quando}, em atendimento pelo COS.")
            junta(r, d, texto, ini)
    linhas = []
    for (cod, d), g in sorted(por_dia.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        itens = sorted(g["itens"], key=lambda x: (x[0], x[1]))
        linhas.append([cod, g["usina_id"], g["ligada_por"], g["cliente"], int(d.strftime("%Y%m%d")), d.isoformat(),
                       "\n".join(x[3] for x in itens), ";".join(x[1] for x in itens),
                       ";".join(dict.fromkeys(x[2] for x in itens if x[2])), len(itens)])
    return linhas


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
    comentarios = comentarios_do_dia(todas, ab, agora, desde)
    rel["comentarios_dias"] = len(comentarios)
    atu = [agora.isoformat(timespec="seconds"), len(todas), desde.date().isoformat(), rel["ligadas"] + sum(
        1 for l in antes if l[5]), ab_em, len(ab)]
    rel["gravado"] = livros.publicar(LIVRO, NOME_LIVRO, {ABA: (CAB, todas), ABA_ABERTAS: (CAB_ABERTA, ab),
                                                         ABA_COMENTARIOS: (CAB_COMENTARIO, comentarios),
                                                         "atualizacao": (CAB_ATUALIZACAO, [atu])},
                                     base=base, token=config["GRIDCO_SQL_TOKEN"], sessao=s)
    return rel


def estado() -> dict:
    """O resultado da última volta deste processo, quando foi e o último pedido do Atualizar que virou gravação."""
    return {"ultimo": _LACO["ultimo"], "quando": _LACO["quando"], "pedido": _iso(_LACO["pedido_feito"])}


def pedido_a_atender(linhas, ultima: datetime | None, feito: datetime | None) -> datetime | None:
    """O pedido do Atualizar ainda sem gravação: o `pedido_em` mais novo do livro do 5080, se for depois da última
    gravação do livro das normalizações e do último pedido já gravado. A data que não se lê não conta."""
    datas = [d for d in (AND.instante(r.get("pedido_em")) for r in linhas or ()) if d]
    if not datas:
        return None
    novo = max(datas)
    return None if any(x and novo <= x for x in (ultima, feito)) else novo


def _pedido(config, sessao, agora_s: float) -> datetime | None:
    """O pedido a atender agora, ou None. Quase sempre custa uma leitura só (a listagem dos livros, pela versão do livro
    do 5080); onde a fonte do Andamento não está ligada (o PC), nem isso."""
    if not AND.fonte(config).ligada:
        return None
    if _LACO["pedida_em"] is not None and agora_s - _LACO["pedida_em"] < PEDIDO_INTERVALO_S:
        return None
    base = _base(config)
    versao = livros.atualizado_em(base, sessao, PEDIDO_LIVRO)
    if not versao or versao == _LACO["pedido_visto"]:
        return None
    p = pedido_a_atender(livros.ler(base, sessao, PEDIDO_LIVRO, PEDIDO_ABA), _ultima(base, sessao),
                         _LACO["pedido_feito"])
    if p is None:
        _LACO["pedido_visto"] = versao          # nada novo nesta versão do livro: só relê quando ela mudar
    return p


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
        import requests
        sessao = requests.Session()
        proxima = time.monotonic() + PRIMEIRA_S
        # acorda de minuto em minuto para o pedido do Atualizar; a volta da hora segue no horário dela
        while not _LACO["parar"].wait(max(1.0, min(PEDIDO_CHECA_S, proxima - time.monotonic()))):
            pedido = None
            if time.monotonic() < proxima:
                try:
                    with app.app_context():
                        pedido = _pedido(app.config, sessao, time.monotonic())
                except Exception as e:      # noqa: BLE001 — o banco fora não para a volta da hora
                    log.warning("pedido do Atualizar não lido: %s: %s", type(e).__name__, e)
                if pedido is None:
                    continue
                _LACO["pedida_em"] = time.monotonic()
            with app.app_context():
                try:
                    _LACO["ultimo"] = publicar(app.config, forcar=pedido is not None)
                    log.info("normalizações no banco%s: %s", " (pedido do Atualizar)" if pedido else "",
                             {k: v for k, v in _LACO["ultimo"].items() if k != "gravado"})
                except Exception as e:      # noqa: BLE001 — o laço não morre por uma volta
                    _LACO["ultimo"] = {"erro": f"{type(e).__name__}: {e}"[:300]}
                    log.exception("normalizações no banco")
                _LACO["quando"] = datetime.now(_BRT).isoformat(timespec="minutes")
            if pedido is None:
                proxima = time.monotonic() + _espera_s(desencontro_s=desencontro)
            elif _LACO["ultimo"].get("gravado"):
                _LACO["pedido_feito"] = pedido  # a volta que não gravou (a memória carregando) tenta de novo depois

    _LACO["thread"] = threading.Thread(target=laco, name="nexus-cos-normalizacoes-banco", daemon=True)
    _LACO["thread"].start()
