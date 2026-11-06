"""O pré-filtro da Aprovação de OS: as regras de FATOS que separam a fila em Pronta, Em dúvida e Não OK (Levi, 04/11/2026:
"vamos se basear na interpretação dos fatos"; "sem interpretar fotos e sim fatos"; "refaça com essas regras e deixe algo
bem fácil e dinâmico para os supervisores!"). Só regras puras: quem lê os anexos no Fracttal e no S3 é o
`prefiltro_fundo.py`; quem monta o quadro é a rota da Aprovação (`nexus/torres/campo`).

A medida que escolheu as regras (as 30 OS da medição de 26/10, contra a decisão do supervisor; o relatório "Pré-filtro
da Verificação: fatos primeiro"):
- **Foto anexada mais de 24 h depois do fechamento no App** pegou 4 devolvidas e NENHUMA aprovada: é Não OK. A hora de
  anexação é a do arquivo no S3 (o REST de anexos do Fracttal não dá data); o fechamento é o último da OS no App (a hora
  do celular do livro de fechamentos). Caso que a criou: a OS fechada no App 18 s depois de aberta, com as 5 capturas
  anexadas 2 dias depois.
- **Foto repetida** pegou 11 devolvidas e 6 aprovadas: é Em dúvida (o supervisor aceita repetição às vezes; ele decide).
  Comparada SEM o carimbo do App: a mesma foto anexada em dois campos ganha carimbos diferentes, e comparar o arquivo
  inteiro achou só metade. Capturas de tela parecidas (os prints de geração do mês) enganam: pedem diferença menor.
- **Fechada fora do App**: sem fotos e horários do App para conferir, fica Em dúvida.
- "Menos de 5 min no App" (4 devolvidas e 5 aprovadas: o técnico fecha no App depois do serviço) e "subtarefas
  respondidas" (o App já não deixa fechar em branco) não separaram e ficaram de fora.

**As quatro regras de 05/11/2026** (Levi: "Tempo curto, resposta vazia, GPS fora da usina, foto faltando / consegue
adicionar"; "pode seguir!"), medidas nas mesmas 30 OS, lidas do Fracttal em 05/11 (15 devolvidas, 15 aprovadas). Os fatos
vêm da leitura RÁPIDA de fundo (`prefiltro_fundo.conferir_meta`: os anexos e as respostas no Fracttal, sem baixar foto) e
do tempo de execução da tarefa na fila (o `real_duration` do Fracttal):
- **Tempo curto** (Não OK): tarefa do App executada em menos de `NEXUS_PREFILTRO_MIN_EXEC_S` (120 s) com foto anexada:
  2 devolvidas (10 s com 9 fotos; 59 s), nenhuma aprovada. Execução 0 ou sem dado não julga.
- **Resposta vazia** (Não OK com 2 ou mais NA MESMA tarefa, Em dúvida com uma por tarefa): obrigatória de texto
  respondida só com "N/A", "ok", "sim", "positivo", "feito"... ou com o nome da tarefa; o "Não se aplica" marcado não
  conta. 6 devolvidas e 2 aprovadas com alguma; contada por OS, a MPM aprovada de 13 tarefas (um "N/A" em cada uma de 3)
  caía em Não OK, e por tarefa só a devolvida com quatro "N/A" numa tarefa cai. O "menos de 12 caracteres" do desenho
  saiu: pegava resposta boa (número de série, "Motor", "QGBT"). Vale também para a OS fechada fora do App (as respostas
  estão no Fracttal).
No código final, nas 30 OS: das 15 devolvidas, 3 em Não OK e 6 em Em dúvida; das 15 aprovadas, nenhuma em Não OK e 4 em
Em dúvida.
- **GPS** (Em dúvida): foto do App com o GPS fora do Brasil, ou a mais de `NEXUS_PREFILTRO_GPS_KM` (5 km) das outras
  fotos da OS (a mediana delas). NÃO contra o ponto da usina no cadastro: em 7 das 30 OS todas as fotos davam de 12 a
  2.058 km dele, com as fotos batendo com a tarefa (o ponto do cadastro é que está errado). A 2 km do desenho, uma usina
  grande aprovada caía (fotos a 2,02 km da mediana). 2 devolvidas (a foto a 199 km; fotos a 18 km) e 1 aprovada (Bogotá).
- **Foto faltando** (Em dúvida): campo cuja pergunta pede "mínimo N fotos" com menos fotos do campo (a foto do App leva no
  nome os 80 primeiros caracteres do campo). 2 devolvidas e 2 aprovadas: sinal fraco, por isso só Em dúvida. Só nas
  tarefas do App: a foto anexada pelo Fracttal não diz o campo.
- **Fora do pré-filtro** (Levi, 04/11: "religamento remoto ou religamento real não entra, nem OSs com etiqueta de
  performance!"): religamento e a etiqueta PERFORMANCE; e, como nas "OSs em verificação" do Painel (Levi, 29/10), a
  etiqueta CHAMADOS e as OS criadas pelo COS. A ENGENHARIA entra (Levi, 05/11/2026: "Engenharia entra no pré filtro");
  no Painel ela segue de fora (`verificacao.etiqueta_fora`, a regra dele de 29/10).
"""
import math
import re
import statistics
from datetime import datetime, timezone

from . import nota_fracttal, regras_app, verificacao

PADRAO = {"horas_tarde": 24, "dif": 12, "dif_print": 4, "por_volta": 150, "pausa_s": 2.0, "min_exec_s": 120,
          "gps_km": 5.0}
_CHAVES = {"horas_tarde": "NEXUS_PREFILTRO_HORAS_TARDE", "dif": "NEXUS_PREFILTRO_DIF",
           "dif_print": "NEXUS_PREFILTRO_DIF_PRINT", "por_volta": "NEXUS_PREFILTRO_POR_VOLTA",
           "pausa_s": "NEXUS_PREFILTRO_PAUSA_S", "min_exec_s": "NEXUS_PREFILTRO_MIN_EXEC_S",
           "gps_km": "NEXUS_PREFILTRO_GPS_KM"}
COLUNAS = ("pronta", "duvida", "nao_ok")
# as etiquetas que tiram a OS do pré-filtro: as do Painel menos a ENGENHARIA (Levi, 05/11/2026: "Engenharia entra no pré
# filtro"). Olha todas as etiquetas da OS: a OS com ENGENHARIA e PERFORMANCE fica fora pela PERFORMANCE
ETIQUETAS_FORA = ("PERFORMANCE", "CHAMADOS", "CHAMADO")
# o fato que decide a coluna (o motivo em destaque no cartão, 05/11/2026: "Sempre destacar o motivo de estar em dúvida ou
# não OK!"); os outros avisos (a regra do App, as fotos por ler) não mudam a coluna
TIPOS_DO_MOTIVO = ("tarde", "tempo", "vazia", "repetida", "gps", "foto_faltando", "nao_abriu", "fora_app", "nota")
# a resposta que não diz nada (a regra da resposta vazia, 05/11/2026), comparada sem acento, caixa e pontuação no fim
RASAS = frozenset({"n/a", "na", "ok", "sim", "positivo", "feito", "realizado", "x"})
TIPOS_TEXTO = (1, 6)              # os campos de texto do Fracttal (o TIPO_DO_FRACTTAL de nota_fracttal.py)
NOME_DO_CAMPO = 60                # a foto do App leva os 80 primeiros caracteres do campo; 60 bastam para casar
_MINIMO = re.compile(r"\bmin(?:imo|\.)?\s*(?:de\s+)?(\d+)\s*(?:fotos?|imagens?|evidencias?)\b")
# o Brasil numa caixa (a do mapa de risco, nexus/performance/clima/mapa.py): o GPS fora dela é de outro país
LON_MIN, LAT_MIN, LON_MAX, LAT_MAX = -74.0, -33.8, -34.7, 5.3
# o hash: 16 x 16 diferenças de brilho (256 bits) da parte de CIMA da foto; o carimbo do App (data, GPS, nome, campo) é
# uma faixa no pé que muda a cada anexo (medido nas fotos da medição: até ~21% da altura)
LADO, CORTE = 16, 0.75


def parametros(config) -> dict:
    """Os limites, do `config` (variáveis NEXUS_PREFILTRO_*) ou o padrão; valor ilegível vale o padrão."""
    out = {}
    for k, padrao in PADRAO.items():
        v = (config or {}).get(_CHAVES[k])
        try:
            out[k] = type(padrao)(float(v)) if v not in (None, "") else padrao
        except (TypeError, ValueError):
            out[k] = padrao
    return out


def dhash(img) -> int:
    """O hash da imagem sem o pé (o carimbo): 256 bits, cada um "o pixel é mais claro que o vizinho da direita"."""
    im = img.convert("L")
    w, h = im.size
    im = im.crop((0, 0, w, max(1, int(h * CORTE)))).resize((LADO + 1, LADO))
    px, bits = im.tobytes(), 0
    for y in range(LADO):
        for x in range(LADO):
            bits = (bits << 1) | (px[y * (LADO + 1) + x] > px[y * (LADO + 1) + x + 1])
    return bits


def pares_repetidos(anexos: list[dict], dif: int, dif_print: int) -> list[list[str]]:
    """[id da primeira igual, id da repetida] para cada foto que repete uma anterior (na ordem de anexação). Com uma
    captura de tela no par (`print`: sem GPS na descrição), vale a diferença menor."""
    pares = []
    for j, b in enumerate(anexos):
        for a in anexos[:j]:
            limite = dif_print if (a.get("print") or b.get("print")) else dif
            if bin(int(a["hash"]) ^ int(b["hash"])).count("1") <= limite:
                pares.append([a["id"], b["id"]])
                break
    return pares


def fora_do_escopo(cruas: list[dict], cos: dict | None) -> str:
    """Por que a OS fica fora do pré-filtro, pelas linhas cruas da fila (as tarefas dela no REST do Fracttal), ou ""."""
    for w in cruas:
        tipo, texto = verificacao._norm(w.get("tasks_log_task_type_main")), verificacao._norm(regras_app._txt_tarefa(w))
        if tipo.startswith("RELIGAMENTO") or "RELIGAMENTO" in texto:
            return "Religamento"
    for w in cruas:
        for x in w.get("labels") or ():
            e = verificacao._norm(x.get("description") if isinstance(x, dict) else x)
            if e in ETIQUETAS_FORA:
                return "CHAMADOS" if e.startswith("CHAMADO") else e
    if any(verificacao.criada_pelo_cos(w, cos) for w in cruas):
        return "Criada pelo COS"
    return ""


def _rasa(v: str) -> str:
    return regras_app._norm(v).rstrip(" .!;,-")


def respostas_vazias(subtarefas: list[dict], nomes: dict) -> list[dict]:
    """[{tarefa, campo, valor}] das obrigatórias de texto respondidas sem conteúdo ("N/A", "ok", "sim", "positivo",
    "feito", só pontuação) ou com o nome da tarefa (`nomes` = {id da tarefa: o texto dela}). O "Não se aplica" marcado
    não conta, nem o campo vazio (o App não deixa fechar assim) e os campos que não são texto."""
    out = []
    for s in subtarefas or ():
        if not s.get("is_required") or regras_app._int0(s.get("id_task_form_item_type")) not in TIPOS_TEXTO:
            continue
        valor, na = nota_fracttal.separar_nao_se_aplica(s.get("value"))
        v = str(valor or "").strip()
        if na or not v:
            continue
        tarefa = str(s.get("id_work_order_task") or "")
        if not _rasa(v) or _rasa(v) in RASAS or regras_app._norm(v) == regras_app._norm(nomes.get(tarefa)):
            out.append({"tarefa": tarefa, "campo": str(s.get("description") or "")[:80], "valor": v[:40]})
    return out


def fotos_faltando(subtarefas: list[dict], fotos: list[dict]) -> list[dict]:
    """[{tarefa, campo, tem, pede}] dos campos cuja pergunta pede "mínimo N fotos" e têm menos fotos do campo. A foto é do
    campo pelo nome que o App põe nela (os 80 primeiros caracteres do campo; casam os 60 primeiros). Campo marcado "Não se
    aplica" (ou com a foto marcada assim) não conta."""
    out = []
    for s in subtarefas or ():
        campo = str(s.get("description") or "")
        m = _MINIMO.search(regras_app._norm(campo))
        if not m or nota_fracttal.separar_nao_se_aplica(s.get("value"))[1]:
            continue
        tarefa, chave = str(s.get("id_work_order_task") or ""), regras_app._norm(campo)[:NOME_DO_CAMPO]
        tem = sum(1 for f in fotos or () if str(f.get("tarefa") or "") == tarefa
                  and regras_app._norm(f.get("desc"))[:NOME_DO_CAMPO] == chave)
        if tem < int(m.group(1)):
            out.append({"tarefa": tarefa, "campo": campo[:80], "tem": tem, "pede": int(m.group(1))})
    return out


def _km(a, b) -> float:
    """Haversine, em km (a mesma conta da geometria do mapa de risco)."""
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(h)))


def _no_brasil(g) -> bool:
    return LAT_MIN <= g[0] <= LAT_MAX and LON_MIN <= g[1] <= LON_MAX


def _km_txt(d: float) -> str:
    return f"{d:.0f}" if d >= 10 else f"{d:.1f}".replace(".", ",")


def _duracao(s: int) -> str:
    return f"{s // 60} min" if s >= 60 and s % 60 == 0 else f"{s} s"


def _curto(txt, n=60) -> str:
    t = str(txt or "").strip()
    return t if len(t) <= n else t[:n].rstrip() + "…"


def _quando(v) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(v or "").strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _s(n: int) -> str:
    return "s" if n > 1 else ""


def _regras_rapidas(tarefas: list[dict], meta: dict, julgada, p: dict) -> tuple[list[dict], bool, bool]:
    """(avisos, nao_ok, duvida) das quatro regras de 05/11/2026, com o que a leitura rápida achou (`meta`): o tempo curto,
    a resposta vazia, o GPS e a foto faltando. `julgada(foto)` diz se a foto é de tarefa do App."""
    avisos, nao_ok, duvida = [], False, False
    fotos = meta.get("fotos") or []
    # tempo curto: tarefa do App executada em menos de 2 min, com foto (o `real_duration` do Fracttal, em segundos)
    por_tarefa: dict = {}
    for f in fotos:
        por_tarefa[str(f.get("tarefa") or "")] = por_tarefa.get(str(f.get("tarefa") or ""), 0) + 1
    curtas = []
    for t in tarefas:
        s, n = regras_app._int0(t.get("exec_s")), por_tarefa.get(str(t.get("id_wt") or ""), 0)
        if t.get("pelo_app") and 0 < s < p["min_exec_s"] and n:
            curtas.append((s, n, str(t.get("id_wt"))))
    if curtas:
        nao_ok = True
        curtas.sort()
        s, n, _ = curtas[0]
        texto = (f"Tarefa executada em {s} s no App, com {n} foto{_s(n)}" if len(curtas) == 1 else
                 f"{len(curtas)} tarefas executadas em menos de {_duracao(p['min_exec_s'])} no App, com fotos (a mais "
                 f"curta: {s} s, {n} foto{_s(n)})")
        avisos.append({"tipo": "tempo", "nivel": "critico", "texto": texto, "fotos": [], "tarefas": [x[2] for x in curtas],
                       "segundos": {x[2]: [x[0], x[1]] for x in curtas}})
    # resposta vazia: vale para toda tarefa (as respostas estão no Fracttal). Não OK com 2 ou mais NA MESMA tarefa; uma
    # por tarefa é Em dúvida: na medição, a MPM aprovada de 13 tarefas tinha um "N/A" em cada uma de 3 delas, e a
    # devolvida, quatro "N/A" numa tarefa só
    vazias = meta.get("vazias") or []
    if vazias:
        por: dict = {}
        for x in vazias:
            por[x["tarefa"]] = por.get(x["tarefa"], 0) + 1
        n, k = len(vazias), max(por.values())
        grave = k >= 2
        nao_ok, duvida = nao_ok or grave, duvida or not grave
        valores = list(dict.fromkeys(x["valor"] for x in vazias))
        onde = ("" if n == 1 else " da mesma tarefa" if grave and n == k else f" ({k} na mesma tarefa)" if grave
                else ", um por tarefa")
        avisos.append({"tipo": "vazia", "nivel": "critico" if grave else "alerta", "fotos": [], "vazias": vazias[:12],
                       "texto": f"Resposta vazia em {n} campo{_s(n)} obrigatório{_s(n)}{onde}: "
                                + ", ".join(f'"{v}"' for v in valores[:3]) + (", …" if len(valores) > 3 else "")})
    # GPS: só as fotos do App (a anexada pelo Fracttal não tem GPS), contra as outras fotos da OS (não o cadastro)
    com_gps = [f for f in fotos if f.get("gps") and julgada(f)]
    fora_br = [f["id"] for f in com_gps if not _no_brasil(f["gps"])]
    if fora_br:
        duvida, n = True, len(fora_br)
        avisos.append({"tipo": "gps", "nivel": "alerta", "fotos": fora_br, "longe": {},
                       "texto": f"{n} foto{_s(n)} com o GPS fora do Brasil"})
    elif len(com_gps) >= 2:
        meio = (statistics.median(f["gps"][0] for f in com_gps), statistics.median(f["gps"][1] for f in com_gps))
        longe = {f["id"]: _km(f["gps"], meio) for f in com_gps if _km(f["gps"], meio) > p["gps_km"]}
        if longe:
            duvida, n, d = True, len(longe), max(longe.values())
            avisos.append({"tipo": "gps", "nivel": "alerta", "fotos": list(longe),
                           "longe": {k: round(v, 1) for k, v in longe.items()},
                           "texto": (f"1 foto a {_km_txt(d)} km das outras fotos da OS" if n == 1 else
                                     f"{n} fotos a até {_km_txt(d)} km das outras fotos da OS")})
    # foto faltando: o campo que pede "mínimo N fotos" com menos, só nas tarefas do App (a foto anexada pelo Fracttal não
    # leva o nome do campo: toda tarefa fora do App daria "0 fotos")
    falt = [x for x in meta.get("faltando") or [] if julgada(x)]
    if falt:
        duvida, x = True, falt[0]
        avisos.append({"tipo": "foto_faltando", "nivel": "alerta", "fotos": [], "faltando": falt[:12],
                       "texto": (f'Campo pede {x["pede"]} fotos e tem {x["tem"]}: "{_curto(x["campo"])}"' if len(falt) == 1
                                 else f'{len(falt)} campos com menos fotos que o pedido (o primeiro: {x["tem"]} de '
                                      f'{x["pede"]}, "{_curto(x["campo"])}")')})
    return avisos, nao_ok, duvida


def classificar(o: dict, fatos: dict | None, fechado_app: str, p: dict, meta: dict | None = None) -> dict:
    """A coluna da OS e os avisos com a prova. `o` = a OS da fila (as tarefas com a regra do App); `fatos` = o que a
    leitura de fundo achou nos anexos (None = ainda não lidos); `fechado_app` = o último fechamento da OS no App; `meta` =
    o que a leitura rápida achou (os anexos e as respostas no Fracttal; None = ainda não lida). Cada aviso diz o `tipo`
    (tarde, tempo, vazia, repetida, gps, foto_faltando, nao_abriu, fora_app, faltam, app), que o cartão do quadro usa
    para mostrar a prova."""
    avisos, tarde, repetidas, nao_ok, duvida = [], 0, 0, False, False
    tarefas = o.get("tarefas") or []
    # a hora do App só julga as fotos das tarefas do App (pelo id da tarefa): na OS mista, a tarefa fechada fora do App
    # tem as fotos anexadas no Fracttal na hora dela, e julgá-las pela do App dava Não OK falso (revisão de 05/11/2026).
    # Foto sem tarefa (da OS) ou de tarefa desconhecida, só quando a OS inteira foi pelo App.
    ids_app = {str(t["id_wt"]) for t in tarefas if t.get("pelo_app") and t.get("id_wt")}
    ids_fora = {str(t["id_wt"]) for t in tarefas if not t.get("pelo_app") and t.get("id_wt")}
    toda_pelo_app = all(t.get("pelo_app") for t in tarefas)

    def julgada(a) -> bool:
        tarefa = str(a.get("tarefa") or "")
        return tarefa in ids_app or (tarefa not in ids_fora and toda_pelo_app)

    if fatos is not None:
        anexos = fatos.get("anexos") or []
        num = {a["id"]: f"p{n:02d}" for n, a in enumerate(anexos, 1)}
        fim = _quando(fechado_app)
        if fim:
            atrasadas = [(a["id"], (q - fim).total_seconds()) for a in anexos
                         if julgada(a) and (q := _quando(a.get("anexada")))
                         and (q - fim).total_seconds() > p["horas_tarde"] * 3600]
            if atrasadas:
                tarde, nao_ok = len(atrasadas), True
                dias = max(1, int(max(s for _, s in atrasadas) // 86400))
                avisos.append({"tipo": "tarde", "nivel": "critico", "fotos": [i for i, _ in atrasadas],
                               "texto": f"{tarde} foto{_s(tarde)} anexada{_s(tarde)} {dias} dia{_s(dias)} depois do "
                                        "fechamento no App"})
        pares = fatos.get("pares") or []
        if pares:
            repetidas, duvida = len(pares), True
            if len(pares) == 1:
                a, b = pares[0]
                texto = f"Foto repetida: {num.get(b, '?')} é a mesma imagem de {num.get(a, '?')}"
            else:
                lista = ", ".join(f"{num.get(b, '?')} = {num.get(a, '?')}" for a, b in pares[:4])
                texto = f"{len(pares)} fotos repetidas: {lista}{', …' if len(pares) > 4 else ''}"
            # os pares vão juntos para o cartão mostrar o nome das duas fotos (o número e o campo), que abre o card da OS
            # (Levi, 05/11/2026: "nem precisa mostrar a foto de cara não... pode mostrar o nome das fotos")
            campo = {x["id"]: x.get("desc") or "" for x in anexos}
            avisos.append({"tipo": "repetida", "nivel": "alerta", "texto": texto, "fotos": [x for par in pares for x in par],
                           "pares": [{"a": a, "b": b, "ra": num.get(a, "?"), "rb": num.get(b, "?"),
                                      "da": campo.get(a, ""), "db": campo.get(b, "")} for a, b in pares[:4]]})
        # a foto que baixou e não abriu (upload cortado) não foi conferida: a OS não vai calada para Pronta e o lote
        nao_abriu = [a["id"] for a in anexos if "hash" in a and a["hash"] is None]
        if nao_abriu:
            duvida, n = True, len(nao_abriu)
            avisos.append({"tipo": "nao_abriu", "nivel": "alerta", "fotos": nao_abriu,
                           "texto": f"{n} foto{_s(n)} não {'abriram' if n > 1 else 'abriu'} no Nexus: confira no card da OS"})
    if meta is not None:
        rapidas, n_ok, dv = _regras_rapidas(tarefas, meta, julgada, p)
        avisos += rapidas
        nao_ok, duvida = nao_ok or n_ok, duvida or dv
    fora = sum(1 for t in tarefas if not t.get("pelo_app"))
    if fora:
        duvida = True
        avisos.append({"tipo": "fora_app", "nivel": "alerta", "fotos": [],
                       "texto": f"{fora} tarefa{_s(fora)} fechada{_s(fora)} fora do App: sem as fotos e os horários do "
                                "App para conferir"})
    # as fotos só mudam a coluna da OS que tem tarefa pelo App (a foto atrasada se mede contra o fechamento no App); a OS
    # fechada inteira fora do App não espera foto nenhuma (05/11/2026: 522 OS assim seguravam a leitura de fundo). As
    # respostas valem para toda OS: sem a leitura rápida, a OS fora do App também espera (a resposta vazia a põe em Não OK)
    tem_app = any(t.get("pelo_app") for t in tarefas)
    sem_fotos, sem_meta = fatos is None and tem_app, meta is None
    falta = ("Faltam as fotos, as respostas e o GPS por ler" if sem_fotos and sem_meta else
             "Faltam fotos por ler" if sem_fotos else
             ("Faltam as respostas e o GPS por ler" if tem_app else "Faltam as respostas por ler") if sem_meta else "")
    if falta and (nao_ok or duvida):
        avisos.append({"tipo": "faltam", "nivel": "neutro", "texto": falta, "fotos": []})
    # a nota do App abaixo de 80 (09/11/2026, Levi, pelo Scrum master: "Em OS 8159 aprovação de OS diz que está aprovado
    # porém a OS tem nota 50 no app, o interessante é ele saber o motivo da nota, tem que ter 'motivo da nota abaixo de
    # 80'"): era só aviso e a OS caía em Pronta; agora é motivo de Em dúvida, com o porquê pela Composição da nota do App.
    # Só a tarefa do App que não é ronda: a ronda tem a nota dela com as falhas (outro aviso)
    from . import nota_app
    vistos = set()
    baixas = [t for t in tarefas if t.get("pelo_app") and not t.get("ronda") and t.get("qualidade") is not None
              and int(t["qualidade"]) < nota_app.NOTA_OK]
    if baixas:
        pior = min(baixas, key=lambda t: int(t["qualidade"]))
        duvida, texto = True, nota_app.frase(pior["qualidade"], pior.get("nota_itens"))
        vistos.add(texto)
        avisos.append({"tipo": "nota", "nivel": "alerta", "texto": texto, "fotos": []})
    # o resto da regra do App de antes (devolvida, foto divergente, ronda com pendência) vira só aviso: a coluna é dos
    # fatos
    from .aprovacao import motivos
    for t in o.get("tarefas") or []:
        if not t.get("pelo_app"):
            continue
        for cor, texto in motivos(t):
            if cor != "ok" and texto not in vistos:
                vistos.add(texto)
                avisos.append({"tipo": "app", "nivel": "alerta" if cor == "alerta" else "neutro", "texto": texto,
                               "fotos": []})
    coluna = "nao_ok" if nao_ok else ("duvida" if duvida else ("conferindo" if falta else "pronta"))
    # o que o cartão em "Ainda conferindo" diz que falta (dado pela metade não vai para a tela como inteiro)
    ainda = ("Fotos, respostas e GPS ainda não conferidos" if sem_fotos and sem_meta else
             "Fotos ainda não conferidas" if sem_fotos else "Respostas e GPS ainda não conferidos" if sem_meta else "")
    return {"coluna": coluna, "avisos": avisos, "tarde": tarde, "repetidas": repetidas, "ainda": ainda}
