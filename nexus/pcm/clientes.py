"""O nome do cliente nas telas do PCM é o do cadastro do Nexus (Levi, 18/10/2026: "Use o nome do cliente no Nexus como
principal").

Os arquivos do PCM tiram o cliente do nome do site no Fracttal ("Cliente - Usina - UF", o `_extrair_cliente` do robô), e
a grafia de lá não é a do cadastro. Em 18/10/2026: "Utragaz" (Ultragaz), "RenoGrid" (Renogrid), "Greenyellow"
(GreenYellow) e "Semp" (SEMP). A semana passada da Visão do responsável (pelo cadastro) e o Fechamento do PCM (pelo
arquivo) batiam cliente a cliente nos números, não no nome.

A troca é por ID, não por palpite: o mesmo nome do cadastro sem diferenciar maiúscula, acento e espaço; e, para o erro
de grafia, o de-para do cadastro, que liga o nome do site do Fracttal à usina, cuja ficha tem o cliente (`cliente_id`):
o começo do nome do site vira o cliente da usina quando todas as usinas com aquele começo são do mesmo cliente. O que não
casa fica como veio (o nome composto da planilha de operações, "Thopen;#Renogrid", por exemplo).

Só o que o Nexus MOSTRA muda: o `fonte` troca o campo `cliente` dos arquivos na memória, depois de baixar; o arquivo do
PCM e o que o Nexus manda para o App e para o PCM não passam por aqui. Sem o banco (teste sem o banco falso, falha de
rede, fora do app), o mapa vem vazio e os nomes ficam como vieram.
"""
import logging
import time
import unicodedata

TTL_S = 600                 # o cadastro de clientes muda pouco; 10 min de cópia por app
ESPERA_FALHA_S = 300        # o banco que falhou é tentado de novo em 5 min, não a cada leitura das telas do PCM
log = logging.getLogger("nexus.pcm")


def norm(txt) -> str:
    s = unicodedata.normalize("NFKD", str(txt or "")).encode("ascii", "ignore").decode()
    return "".join(ch for ch in s.lower() if ch.isalnum())


def montar(clientes, usinas, de_para) -> dict[str, str]:
    """{nome normalizado: nome do cadastro}, pelo nome de cada cliente e pelo começo dos nomes de site do Fracttal no
    de-para (só o de-para do Fracttal: os outros sistemas têm outro formato de nome)."""
    from ..dados import fatos as D
    nome_cli = {D._id(c.get("cliente_id")): str(c.get("nome") or "").strip() for c in clientes or ()}
    nome_cli = {k: v for k, v in nome_cli.items() if k and v}
    mapa = {norm(n): n for n in nome_cli.values()}
    cli_da_usina = {D._id(u.get("usina_id")): D._id(u.get("cliente_id")) for u in usinas or ()}
    votos: dict[str, set] = {}
    for d in de_para or ():
        chave = str(d.get("chave_externa") or "")
        if "fracttal" not in norm(d.get("sistema")) or " - " not in chave:
            continue
        cid = cli_da_usina.get(D._id(d.get("usina_id")))
        if cid in nome_cli:
            votos.setdefault(norm(chave.split(" - ", 1)[0]), set()).add(nome_cli[cid])
    for comeco, nomes in votos.items():
        if comeco and comeco not in mapa and len(nomes) == 1:
            mapa[comeco] = next(iter(nomes))
    return mapa


def mapa() -> dict[str, str]:
    """O mapa do app atual, numa cópia de 10 min. Vazio sem o banco: nada muda."""
    try:
        from flask import current_app
        guarda = current_app.extensions.setdefault("nexus_pcm_clientes", {"ate": 0.0, "mapa": {}})
    except RuntimeError:                                    # fora do app
        return {}
    agora = time.monotonic()
    if agora < guarda["ate"]:
        return guarda["mapa"]
    try:
        from ..campo import visao
        m = montar(*(visao._livro("cadastro_nexus", aba) for aba in ("clientes", "usinas", "de_para")))
    except Exception as e:      # noqa: BLE001 — sem o cadastro, as telas seguem com o nome do arquivo
        log.info("nome do cliente pelo cadastro: sem o banco (%s); fica o nome do arquivo do PCM", type(e).__name__)
        guarda.update(ate=agora + ESPERA_FALHA_S, mapa={})
        return {}
    guarda.update(ate=agora + TTL_S, mapa=m)
    return m


def versao(m: dict) -> int:
    return hash(frozenset(m.items())) if m else 0


def nome(txt, m=None):
    """O nome do cadastro para o cliente `txt`; o que não casa volta como veio."""
    if not txt:
        return txt
    m = mapa() if m is None else m
    return m.get(norm(txt), txt)


def aplicar(dados, m) -> int:
    """Troca, na memória, o `cliente` de cada objeto de `dados` pelo nome do cadastro. Devolve quantos trocou."""
    if not m:
        return 0
    n, pilha = 0, [dados]
    while pilha:
        x = pilha.pop()
        if isinstance(x, dict):
            v = x.get("cliente")
            if isinstance(v, str) and v:
                novo = m.get(norm(v))
                if novo and novo != v:
                    x["cliente"] = novo
                    n += 1
            pilha.extend(y for y in x.values() if isinstance(y, (dict, list)))
        elif isinstance(x, list):
            pilha.extend(y for y in x if isinstance(y, (dict, list)))
    return n
