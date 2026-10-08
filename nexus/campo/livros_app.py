"""Os livros que o próprio App de Campo grava no banco (Levi, 05/10/2026: "operador faz ronda > após ronda input é dado
na API do PG > Nexus lê"), no formato das tabelas do App, para as regras copiadas rodarem sem mudar linha.

O App (v226, timer `nexus_workbooks_sync`, de hora em hora aos :25) sobe o registro de cada fechamento (`qualidadelog`,
90 dias) em `fechamentos_app_campo`; o v210 já subia as OS de ronda em `rondas_app_campo`. Isto substitui o coletor do
Fracttal (`coletor.py`): medido em 05/10, nas 1.807 tarefas que os dois tinham, a nota que o coletor recalculava pelo
Fracttal batia com a do painel do App em só 14% (11,8 pontos de diferença média; 124 fechamentos do App dados como
"fora do App" e 223 que o coletor não tinha). Aqui a nota É a do painel.

A pessoa vem como HMAC do e-mail (`NEXUS_PESSOA_HMAC`, a mesma chave no App e no Nexus): o Nexus calcula o mesmo código
para cada e-mail do cadastro do App (`identidades.json`) e troca pelo e-mail e pelo nome. Nada disso volta ao banco.

Ainda NÃO vêm no livro (o App guarda, de madrugada, no `_enriquecer_qlog`, e não manda): a situação da OS no Fracttal,
as durações do Fracttal (prevista e real), a data de aprovação e a avaliação do supervisor. Ficam DESCONHECIDAS (0), não
aproximadas: medido em 05/10, com a duração do celular no lugar da do Fracttal o "tempo vs. previsto" dava 5.726%, e com
a situação tirada da revisão do painel, 402 de 447 OS apareciam "em verificação" (as aprovadas direto no Fracttal não
passam pela revisão do painel). A tela que mostrava esses cartões (Ordens de serviço) saiu em 08/10/2026; a
Triagem não acusa demora nem divergência de supervisor até o App mandar. Aprovada pelo painel conta como aprovada.
"""
import hashlib
from datetime import datetime, timezone

from . import banco_campo, regras_app
from .ligacao_cadastro import codigo_da_pessoa

LIVRO_FECHAMENTOS = "fechamentos_app_campo"
LIVRO_RONDAS = "rondas_app_campo"
STATUS_EM_VERIFICACAO, STATUS_APROVADA, STATUS_DEVOLVIDA = 2, 3, 1


def _sim(v) -> bool:
    return str(v or "").strip().lower() in ("sim", "true", "1", "verdadeiro")


def _int(v) -> int:
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return 0


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def _epoch(iso) -> int:
    try:
        return int(datetime.fromisoformat(_txt(iso).replace("Z", "+00:00")).astimezone(timezone.utc).timestamp())
    except ValueError:
        return 0


def ler(base, sessao, livro) -> list[dict]:
    """As linhas da 1ª aba do livro, como dicionários. Livro que ainda não existe = vazio."""
    r = sessao.get(f"{base}/api/sheets", timeout=60)
    r.raise_for_status()
    abas = [x["id"] for x in r.json() if x.get("workbook_key") == livro]
    return banco_campo._linhas_da_aba(base, sessao, abas[0]) if abas else []


def pessoas_por_codigo(chave) -> dict:
    """{código do App: (e-mail, nome)} pelo cadastro do App. Código que bate em dois e-mails não liga."""
    if not chave:
        return {}
    donos = {}
    for em, p in (regras_app.ident().get("porEmail") or {}).items():
        em = str(em or "").strip().lower()
        cod = codigo_da_pessoa(chave, em)
        if cod:
            donos.setdefault(cod, []).append((em, _txt((p or {}).get("nome"))))
    return {c: v[0] for c, v in donos.items() if len(v) == 1}


def status(a: dict) -> int:
    rev = _txt(a.get("Revisão")).lower()
    if rev == "aprovada":
        return STATUS_APROVADA
    if rev == "devolvida":
        return STATUS_DEVOLVIDA
    return STATUS_EM_VERIFICACAO


def registro(a: dict, email: str = "", nome: str = "") -> dict:
    """A linha do livro no formato da tabela `qualidadelog` do App (`_registrar_qualidade_log` + `_enriquecer_qlog`),
    na ordem em que o `_nexus_linhas_fechamentos` do App monta a linha."""
    ts, folio, tarefa = _txt(a.get("Registrado em")), _txt(a.get("OS")), _txt(a.get("Tarefa"))
    usina, cluster, codigo = _txt(a.get("Usina")), _txt(a.get("Região")), _txt(a.get("Código do ativo"))
    tipo, crit = _txt(a.get("Tipo da OS")), _txt(a.get("Criticidade"))
    prev, real = _int(a.get("Previsto (min)")), _int(a.get("Execução (min)"))
    fim = _txt(a.get("Hora do celular")) or ts
    rev = _txt(a.get("Revisão"))
    return {
        "PartitionKey": "q", "RowKey": "%013d_%s_%s" % (_epoch(ts), folio, hashlib.sha1(tarefa.encode("utf-8")).hexdigest()[:8]),
        "server_ts": ts, "os": folio, "id_wo": _txt(a.get("ID da OS no Fracttal")), "tarefa": tarefa,
        "codigo": codigo, "usina": usina, "cluster": cluster, "tipo_os": tipo, "criticidade": crit,
        "email": email, "nome": nome, "qualidade": _int(a.get("Nota do painel")),
        "nota_itens": _txt(a.get("Composição da nota")) or "[]", "obs_app": _txt(a.get("Observação no App")),
        "obs_ok": _sim(a.get("Observação suficiente")), "geo_ok": _sim(a.get("GPS no início e no fim")),
        "pontual": _sim(a.get("Pontual")), "offline": _sim(a.get("Offline")), "n_fotos": _int(a.get("Fotos")),
        "n_desc": _int(a.get("Fotos com descrição")), "assinou": _sim(a.get("Assinou")),
        "sub_ok": _sim(a.get("Obrigatórias respondidas")), "todas_sub": _sim(a.get("Todas respondidas")),
        "n_pecas": _int(a.get("Peças")), "xp": _int(a.get("XP")), "rev": rev,
        "foi_devolvida": _sim(a.get("Devolvida")), "dur_prev": prev, "exec_min": real,
        "reprog": _sim(a.get("Reprogramada")), "vezes": _int(a.get("Vezes reprogramada")), "dev_ts": fim,
        # o que o `_enriquecer_qlog` do App põe, com o que o livro traz (ver o docstring do módulo)
        "fx": "ok", "fx_tipo": tipo, "fx_crit": crit, "fx_area": cluster, "fx_ativo": usina, "fx_codigo": codigo,
        "fx_dur_prev_min": 0, "fx_dur_real_min": 0, "fx_final": fim,
        "fx_status": STATUS_APROVADA if status(a) == STATUS_APROVADA else 0, "fx_aprov": "", "fx_rating": 0}


def ronda_os(r: dict) -> dict:
    """A OS de ronda (`rondaos`), para o par OS ↔ ronda da fila de verificação (`_rondas_os_pares`)."""
    return {"PartitionKey": "os", "RowKey": _txt(r.get("OS")), "folio": _txt(r.get("OS")),
            "id_work_order": _txt(r.get("ID da OS no Fracttal")), "usina": _txt(r.get("Usina")),
            "data": _txt(r.get("Data")), "tipo": _txt(r.get("Tipo")), "email": "",
            "ativo": _txt(r.get("Ativo da usina no Fracttal"))}


def nome_do_tecnico(r: dict, quem: dict | None) -> str:
    """O técnico da linha do livro de rondas: `Técnico` (o nome em claro, até a versão do App de 07/10/2026) ou
    `Técnico (HMAC)` (o código do e-mail, pacote `rondas-tecnico-hmac` do App, 08/10), traduzido pelo cadastro do App
    (`pessoas_por_codigo`) como nos outros livros. As DUAS colunas valem: na troca, uma leitura no meio do `sync-xlsx`
    pega linha com o cabeçalho velho e linha com o novo. Código sem dono (pessoa fora do cadastro do App) ou sem a
    chave NEXUS_PESSOA_HMAC: vazio, nunca o código."""
    nome = _txt(r.get("Técnico"))
    if nome:
        return nome
    codigo = _txt(r.get("Técnico (HMAC)")).split(";")[0].strip()
    return _txt(((quem or {}).get(codigo) or ("", ""))[1]) if codigo else ""


def ronda(r: dict, quem: dict | None = None) -> dict:
    """`quem` = {código do App: (e-mail, nome)} (`pessoas_por_codigo`), para a linha que já vem com o código."""
    # sem `finalizada`, como antes: o par serve à fila; a ronda inteira (zonas, trackers) não vem no livro
    return {"PartitionKey": _txt(r.get("Data")), "RowKey": f"nexus-{_txt(r.get('OS'))}", "email": "",
            "nome": nome_do_tecnico(r, quem), "usina": _txt(r.get("Usina")), "cluster": _txt(r.get("Região")),
            "qualidade": _int(r.get("Nota da ronda")), "falhas": "[]", "tipo": _txt(r.get("Tipo"))}
