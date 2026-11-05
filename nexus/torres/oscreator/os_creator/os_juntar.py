"""os_juntar.py: UM caminho só para juntar tarefas numa OS numerada (31/10/2026, etapa 5, tarefa 5.1 do canto central).

O CASO QUE CRIOU A REGRA. Em 30/10/2026 o PCM reclamou do tempo da OS ("agora criando do zero o tempo na OS continua 10 min igual
na Fila, só na tarefa que o tempo é o que a gente colocou"): o `_work_order_insert` punha 600 s fixos, e QUATRO caminhos de
criação tinham a sua cópia da fase 2 (ler o kanban, inserir a OS, pôr as etiquetas, anexar), cada uma com a sua regra. A conta
foi consertada caminho por caminho, mas as cópias seguiam ali. Agora a fase 2 é esta, e quem cria (a Clonagem de planos, a
Clonagem de OS, a Fila do PCM, o Criar OS do zero, a Performance, o COS, a Engenharia) só cria as tarefas pendentes e a entrega.

O QUE ELE FAZ (`juntar_em_os`), nesta ordem:
1. o registro de cada tarefa no kanban (`_kanban_records`; a tarefa recém-criada pode demorar 1-2 s para aparecer). Quem já leu o
   registro (a retomada da Fila, "uma OS por ativo" que lê o kanban uma vez para todas) o entrega em `registros`, e ele não é lido de novo;
2. a OS (`_work_order_insert`) com o tempo igual à SOMA do tempo das tarefas que ENTRARAM nela (`_tempo_da_os`): a tarefa sem tempo
   conhecido conta os 10 min com que nasce, e a que o kanban não trouxe não está na OS e não conta;
3. as etiquetas (a OS já existe: a que falha vira aviso, nunca derruba a OS);
4. as fotos, cada uma na tarefa do ativo dela.
Devolve `{"id_tasks", "id_work_order", "wo_folio", "nao_entraram"[, "etiquetas"][, "aviso"][, "n_img_ok", "img_erro"]}`. Sem
`id_work_order` nem `wo_folio` = a OS NÃO saiu (o kanban caiu, ou não trouxe nenhuma tarefa): as tarefas ficam pendentes no
Fracttal e o `aviso` diz o que fazer. A OS que não fecha (o `work_order_insert` recusado) SOBE como `FracttalError`: cada tela
decide o que dizer (o Criar OS agrupado a transforma em aviso; as outras mostram o erro).

O QUE ELE NÃO FAZ. Não põe a OS na lista central de OS (`os_central.atualizar_os`): as telas de criar chamam
`lista_central.criadas`, que tem a guarda de "lista em uso" e o limite de OS por pedido (3.3); chamar daqui pularia a guarda. E
não confere a pessoa nem a etiqueta ao vivo: a criação da Engenharia faz isso na rota, antes de criar a primeira tarefa
(`api.responsaveis_ao_vivo`, `api.get_labels`).

AS FRASES. O que a tela diz quando algo falha mudou de caminho para caminho com o tempo (a mesma falha dita de quatro jeitos), e
mudar o que as telas mostram não é desta etapa: o padrão é o do Criar OS e da Clonagem de planos, e cada chamador que dizia
outra coisa passa a sua em `frases` (`FRASES_CLONAR`, `FRASES_PERFORMANCE`, `FRASES_UMA_POR_TAREFA`).

Este módulo não importa o `api` ao carregar (quem o importa é o `os_criar`, e o `api` importa o `os_criar` no fim do arquivo, a
fachada; o `api` não o importa mais): as funções do `api` são chamadas pelo nome, na hora (`_api()`), e os testes que trocam o
`api._kanban_records`, o `api._work_order_insert` ou o `api.apply_labels` valem aqui."""
from __future__ import annotations

# O que cada tela diz quando a fase 2 não sai inteira. {erro} = o texto do erro, {n} = quantas tarefas foram criadas, {folio} = o
# número da OS. O padrão é o do Criar OS (agrupado) e da Clonagem de planos do PCM.
FRASES = {
    "kanban": "tarefas criadas; não gerei a OS numerada ({erro}).",
    "nao_achadas": "tarefas criadas, mas não as achei no kanban p/ gerar a OS.",
    "etiqueta": "OS {folio} criada, mas a etiqueta falhou: {erro}",
    "os_pai": "OS {folio} criada, mas o Fracttal não gravou a OS pai: confira no Fluxo da OS e avise o administrador do Nexus.",
}
# A Clonagem de OS (`api.clonar_os`, que a Fila do PCM e a OS sem plano também usam)
FRASES_CLONAR = {
    "kanban": "tarefas criadas; não consegui gerar a OS numerada ({erro}).",
    "etiqueta": "etiqueta falhou: {erro}",
}
# A Performance agrupada: o texto da tela dela diz que as tarefas ficaram pendentes (e o erro vem cortado em 80 letras)
FRASES_PERFORMANCE = {
    "kanban": "as {n} tarefas foram criadas, mas não consegui juntá-las numa OS ({erro}). "
              "Elas estão pendentes no kanban do Fracttal.",
    "nao_achadas": "as {n} tarefas foram criadas mas não as achei no kanban para gerar a OS numerada.",
    "etiqueta": "etiqueta falhou: {erro:.80}",
}
# "Uma OS por ativo" e "por data" (uma tarefa em cada OS): o aviso fica na OS daquela tarefa
FRASES_UMA_POR_TAREFA = {
    "etiqueta": "WO {folio} criada, mas etiqueta falhou: {erro}",
}

_CHAVES_DA_OS = ("id_work_order", "wo_folio", "id_tasks", "etiquetas")


def _api():
    import api                                      # na hora da chamada: o `os_criar` importa este módulo, e o `api` importa o `os_criar`
    return api


def _frase(texto: str, **campos) -> str:
    """A frase com os campos no lugar; o erro entra como texto (o `{erro:.80}` corta)."""
    if "erro" in campos:
        campos["erro"] = str(campos["erro"])
    return texto.format(**campos)


def da_os(resultado: dict) -> dict:
    """O `os` que as telas leem: `{id_work_order, wo_folio, id_tasks[, etiquetas]}`; sem os dois primeiros quando a OS não saiu."""
    return {k: resultado[k] for k in _CHAVES_DA_OS if k in resultado}


def conferir_os_pai(id_work_order, pai, folio, texto: str = "") -> str:
    """A OS pai conferida no Fracttal, depois de gravar (04/11/2026, Levi: "quero que sane esses problemas de construirmos algo e
    quando vão usar não presta!"): o Fracttal aceita o campo e ignora calado, e foi assim que a OS pai sumiu por semanas sem
    ninguém ver. Devolve o aviso da tela, ou "" (sem OS pai pedida, sem a OS, ou sem a leitura: a que não dá para ler não vira
    aviso). 1 leitura do cabeçalho, só quando há OS pai. Vale para a fase 2 (`juntar_em_os`) e para os caminhos que criam a OS
    numerada de uma vez, sem a fase 2 (`to_work_order`: a OS já realizada, a Performance de uma OS por ativo e a inspeção do
    chamado; Levi, no mesmo dia: "Performance e engenharia também tem OS pai, veja se está funcionando normalmente!")."""
    if not (id_work_order and pai):
        return ""
    try:
        gravado = (_api()._cabecalho_os(id_work_order) or {}).get("id_parent_wo")
    except Exception:                                        # noqa: BLE001 — sem a leitura, sem a conferência
        return ""
    return "" if str(gravado or "") == str(pai) else _frase(texto or FRASES["os_pai"], folio=folio)


def juntar_em_os(id_tasks, duracoes, id_responsible, responsible_name: str = "", *, id_parent=None, note: str = "",
                 etiqueta_ids=None, imagens=None, registros=None, frases=None) -> dict:
    """Junta as tarefas PENDENTES `id_tasks` (na ordem dada) numa OS numerada, com o responsável, e devolve o que houve (ver o topo).

    - `duracoes`: {id_task: segundos} (None ou 0 = a tarefa sem tempo conhecido: conta os 10 min com que nasce);
    - `id_parent`: o id da OS pai, ou uma função sem argumentos que o descobre (chamada só quando a OS vai ser inserida, depois
      do kanban: a Performance procura a OS pai pelo número, e a busca não deve ir se a OS nem vai sair);
    - `note`: a observação da OS inteira (separada da nota de cada tarefa);
    - `etiqueta_ids`: as etiquetas da OS; `imagens`: {id_task: [{"bytes", "nome"}]}, cada foto na tarefa da OS que veio daquela;
    - `registros`: {id_task: registro do kanban} que quem chama já leu; o que faltar neles vai ao kanban;
    - `frases`: o texto dos avisos deste chamador (ver `FRASES`)."""
    a = _api()
    id_tasks = list(id_tasks)
    textos = {**FRASES, **(frases or {})}
    saida: dict = {"id_tasks": id_tasks}
    # 1. o registro de cada tarefa no kanban
    achados = dict(registros or {})
    faltam = [i for i in id_tasks if i not in achados]
    if faltam:
        try:
            achados.update(a._kanban_records(set(faltam)))
        except a.FracttalError as e:
            saida["aviso"] = _frase(textos["kanban"], erro=e, n=len(id_tasks))
            return saida
    na_os = [i for i in id_tasks if i in achados]          # as que entram na OS, na ordem em que foram criadas
    if not na_os:
        saida["aviso"] = _frase(textos["nao_achadas"], n=len(id_tasks))
        return saida
    # 2. a OS. Só o que a chamada tem entra nos argumentos. A OS pai vai AQUI, no pedido que cria a OS numerada (sondado em
    # 26/08/2026: na tarefa pendente o Fracttal a ignora): até 04/11/2026 só a Performance agrupada a passava, e o Criar OS, a
    # Fila do PCM e as Clonagens criavam a OS sem pai (a OS 18561, com a 18560 de pai, nasceu sem pai)
    kw = {"duration": a._tempo_da_os((duracoes or {}).get(i) for i in na_os)}
    pai = id_parent() if callable(id_parent) else id_parent
    if pai:
        kw["id_parent"] = pai
    if note:
        kw["note"] = note
    wo = a._work_order_insert([achados[i] for i in na_os], id_responsible, responsible_name, **kw)
    idwo = wo.get("id_work_order")
    saida.update(id_work_order=idwo, wo_folio=wo.get("wo_folio"), nao_entraram=len(id_tasks) - len(na_os))
    # 2b. a OS pai conferida no Fracttal, depois de gravar
    aviso_pai = conferir_os_pai(idwo, pai, wo.get("wo_folio"), textos["os_pai"])
    if aviso_pai:
        saida["aviso"] = aviso_pai
    # 3. as etiquetas. Qualquer falha vira aviso, e não só a do Fracttal: a OS já existe, e a etiqueta é o acabamento (a Performance
    # já engolia tudo; as outras só o `FracttalError`, e um erro de programa aqui faria a pessoa criar a mesma OS de novo)
    if idwo and etiqueta_ids:
        try:
            a.apply_labels(idwo, etiqueta_ids)
            saida["etiquetas"] = list(etiqueta_ids)
        except Exception as e:                              # noqa: BLE001
            saida["aviso"] = " ".join(x for x in (saida.get("aviso"),
                                                  _frase(textos["etiqueta"], erro=e, folio=wo.get("wo_folio"))) if x)
    # 4. as fotos
    if idwo and imagens:
        saida.update(_anexar(a, idwo, na_os, imagens))
    return saida


def _anexar(a, idwo, na_os: list, imagens: dict) -> dict:
    """Cada foto na tarefa da OS que veio do ativo dela. A OS não devolve o id de cada tarefa, então as tarefas dela são lidas e
    casadas pela ORDEM: a i-ésima tarefa da OS é a i-ésima que ENTROU nela (`na_os`). Até 31/10/2026 o Criar OS agrupado casava
    pela ordem das tarefas CRIADAS, e se o kanban não trazia a 1ª a foto do ativo 1 ia para a tarefa do ativo 2. Falha de foto
    não derruba a OS: fica contada em `img_erro`."""
    try:
        tarefas = a._ids_tarefas_da_os(idwo)
    except Exception:                                       # noqa: BLE001 — sem as tarefas, nenhuma foto sobe
        tarefas = []
    ok, erros = 0, []
    for i, tid in enumerate(tarefas):
        for im in (imagens.get(na_os[i] if i < len(na_os) else None) or []):
            try:
                a.attach_imagem_os(idwo, tid, im.get("bytes"), im.get("nome") or "imagem.png")
                ok += 1
            except Exception as e:                          # noqa: BLE001
                erros.append(str(e)[:600])
    return {"n_img_ok": ok, "img_erro": erros}


def uma_os_por_tarefa(fase1: list, id_responsible, responsible_name: str = "", etiqueta_ids=None, id_parent=None) -> None:
    """A fase 2 de "uma OS por ativo" (`api.create_work_orders_bulk`: o Criar OS do zero, o COS e a Engenharia) e "uma OS por data"
    (`api.create_work_orders_datas`): cada tarefa criada vira a sua OS. O kanban é lido UMA vez para todas (50 OS do COS não são 50
    leituras), e cada OS sai pelo `juntar_em_os` com o registro já lido. Escreve o resultado em `r["os"]` de cada item de `fase1`
    (o `id_work_order`, o `wo_folio`, as `etiquetas` e o `aviso`). Sem responsável, as tarefas ficam pendentes (nada a fazer aqui)."""
    a = _api()
    pend = [r for r in fase1 if r.get("ok") and r["os"].get("id_task")]
    if not (id_responsible and pend):
        return
    try:
        recs = a._kanban_records({r["os"]["id_task"] for r in pend})
    except a.FracttalError as e:
        recs = {}
        for r in pend:
            r["os"]["aviso"] = f"tarefa criada; não converti em WO ({e})."
    for r in pend:
        if "aviso" in r["os"]:
            continue
        idt = r["os"]["id_task"]
        rec = recs.get(idt)
        if not rec:
            r["os"]["aviso"] = "tarefa criada, mas não a achei no kanban p/ virar WO."
            continue
        try:
            jun = juntar_em_os([idt], {idt: r["os"].get("duracao")}, id_responsible, responsible_name, id_parent=id_parent,
                               etiqueta_ids=etiqueta_ids, registros={idt: rec}, frases=FRASES_UMA_POR_TAREFA)
        except a.FracttalError as e:
            r["os"]["aviso"] = f"tarefa criada, mas falhou virar WO: {e}"
            continue
        r["os"]["id_work_order"] = jun.get("id_work_order") or r["os"].get("id_work_order")
        r["os"]["wo_folio"] = jun.get("wo_folio") or r["os"].get("wo_folio")
        if "etiquetas" in jun:
            r["os"]["etiquetas"] = jun["etiquetas"]
        if jun.get("aviso"):
            r["os"]["aviso"] = jun["aviso"]
