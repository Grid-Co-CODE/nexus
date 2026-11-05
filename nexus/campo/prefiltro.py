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
- **Fora do pré-filtro** (Levi, 04/11: "religamento remoto ou religamento real não entra, nem OSs com etiqueta de
  performance!"): religamento e a etiqueta PERFORMANCE; e, como nas "OSs em verificação" do Painel (Levi, 29/10), a
  etiqueta CHAMADOS e as OS criadas pelo COS. A ENGENHARIA entra (Levi, 05/11/2026: "Engenharia entra no pré filtro");
  no Painel ela segue de fora (`verificacao.etiqueta_fora`, a regra dele de 29/10).
"""
from datetime import datetime, timezone

from . import regras_app, verificacao

PADRAO = {"horas_tarde": 24, "dif": 12, "dif_print": 4, "por_volta": 150, "pausa_s": 2.0}
_CHAVES = {"horas_tarde": "NEXUS_PREFILTRO_HORAS_TARDE", "dif": "NEXUS_PREFILTRO_DIF",
           "dif_print": "NEXUS_PREFILTRO_DIF_PRINT", "por_volta": "NEXUS_PREFILTRO_POR_VOLTA",
           "pausa_s": "NEXUS_PREFILTRO_PAUSA_S"}
COLUNAS = ("pronta", "duvida", "nao_ok")
# as etiquetas que tiram a OS do pré-filtro: as do Painel menos a ENGENHARIA (Levi, 05/11/2026: "Engenharia entra no pré
# filtro"). Olha todas as etiquetas da OS: a OS com ENGENHARIA e PERFORMANCE fica fora pela PERFORMANCE
ETIQUETAS_FORA = ("PERFORMANCE", "CHAMADOS", "CHAMADO")
# o fato que decide a coluna (o motivo em destaque no cartão, 05/11/2026: "Sempre destacar o motivo de estar em dúvida ou
# não OK!"); os outros avisos (a regra do App, as fotos por ler) não mudam a coluna
TIPOS_DO_MOTIVO = ("tarde", "repetida", "nao_abriu", "fora_app")
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


def _quando(v) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(v or "").strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _s(n: int) -> str:
    return "s" if n > 1 else ""


def classificar(o: dict, fatos: dict | None, fechado_app: str, p: dict) -> dict:
    """A coluna da OS e os avisos com a prova. `o` = a OS da fila (as tarefas com a regra do App); `fatos` = o que a
    leitura de fundo achou nos anexos (None = ainda não lidos); `fechado_app` = o último fechamento da OS no App. Cada aviso
    diz o `tipo` (tarde, repetida, nao_abriu, fora_app, faltam, app), que o cartão do quadro usa para mostrar a prova."""
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
    fora = sum(1 for t in tarefas if not t.get("pelo_app"))
    if fora:
        duvida = True
        avisos.append({"tipo": "fora_app", "nivel": "alerta", "fotos": [],
                       "texto": f"{fora} tarefa{_s(fora)} fechada{_s(fora)} fora do App: sem as fotos e os horários do "
                                "App para conferir"})
    if fatos is None and (nao_ok or duvida):
        avisos.append({"tipo": "faltam", "nivel": "neutro", "texto": "Faltam fotos por ler", "fotos": []})
    # a regra do App de antes (nota, devolvida, foto divergente, ronda com pendência) vira só aviso: a coluna é dos fatos
    from .aprovacao import motivos
    vistos = set()
    for t in o.get("tarefas") or []:
        if not t.get("pelo_app"):
            continue
        for cor, texto in motivos(t):
            if cor != "ok" and texto not in vistos:
                vistos.add(texto)
                avisos.append({"tipo": "app", "nivel": "alerta" if cor == "alerta" else "neutro", "texto": texto,
                               "fotos": []})
    coluna = "nao_ok" if nao_ok else ("duvida" if duvida else ("conferindo" if fatos is None else "pronta"))
    return {"coluna": coluna, "avisos": avisos, "tarde": tarde, "repetidas": repetidas}
