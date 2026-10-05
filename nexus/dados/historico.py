"""O histórico das dimensões que mudam com o tempo (no método Kimball, "SCD tipo 2": válido de / até).

O cadastro do Nexus guarda só o ESTADO ATUAL: quando um técnico muda de equipe ou de supervisor, a nota de agosto dele
passaria a contar para o supervisor novo. Aqui cada mudança fecha a linha vigente (`valido_ate` = dia da mudança) e
abre outra (`valido_de` = o mesmo dia). Para saber de quem era o fechamento de 12/08: a linha da pessoa com
valido_de <= 12/08 < valido_ate.

- O histórico anda a cada carga (de hora em hora): mudança feita e desfeita entre duas cargas não fica.
- Na 1ª carga não há passado: a linha vigente começa no `alterado_em` do cadastro (o que se sabia em 05/10/2026).
- Só os campos que mudam a análise são acompanhados (RASTREADOS); mudar o resto não abre linha nova.
- Nada sensível: só IDs e campos que já vão em claro no `cadastro_nexus`.
"""

RASTREADOS = {
    "pessoas": ("pessoa_id", ("equipe_id", "supervisor_id", "cargo", "vinculo", "status")),
    "usinas": ("usina_id", ("cliente_id", "equipe_id", "status", "responsavel_om_id", "tecnico_om_id", "cluster",
                            "regiao")),
}
ABERTO = None          # valido_ate de quem está vigente


def cabecalho(entidade: str) -> list:
    col_id, cols = RASTREADOS[entidade]
    return [col_id, *cols, "valido_de", "valido_ate", "vigente"]


def _v(x):
    """O mesmo valor, venha a API com 12, 12.0 ou "12": a mudança é do dado, não do tipo."""
    if x is None or (isinstance(x, str) and not x.strip()):
        return None
    if isinstance(x, float) and x.is_integer():
        return int(x)
    if isinstance(x, str):
        s = x.strip()
        try:
            f = float(s)
            return int(f) if f.is_integer() else s
        except ValueError:
            return s
    return x


def atualizar(entidade: str, atuais: list[dict], anteriores: list[dict], hoje: str) -> list[list]:
    """O histórico novo: o anterior com as linhas que mudaram fechadas em `hoje` e as novas abertas."""
    col_id, cols = RASTREADOS[entidade]
    fechadas, abertas = [], {}
    for h in anteriores:
        rid = _v(h.get(col_id))
        if rid is None:
            continue
        if str(h.get("vigente") or "").strip().lower() == "sim":
            abertas[rid] = h
        else:
            fechadas.append([rid, *(_v(h.get(c)) for c in cols), h.get("valido_de"), h.get("valido_ate"), "não"])
    out = list(fechadas)
    vistos = set()
    for a in atuais:
        rid = _v(a.get(col_id))
        if rid is None or rid in vistos or str(a.get("excluido") or "").strip().lower() == "sim":
            continue
        vistos.add(rid)
        agora = [_v(a.get(c)) for c in cols]
        ab = abertas.pop(rid, None)
        if ab is not None and [_v(ab.get(c)) for c in cols] == agora:
            out.append([rid, *agora, ab.get("valido_de"), ABERTO, "sim"])
            continue
        if ab is not None:
            out.append([rid, *(_v(ab.get(c)) for c in cols), ab.get("valido_de"), hoje, "não"])
            de = hoje
        else:
            de = str(a.get("alterado_em") or "")[:10] or hoje
        out.append([rid, *agora, de, ABERTO, "sim"])
    for rid, ab in abertas.items():           # saiu do cadastro (ou foi excluída): fecha
        out.append([rid, *(_v(ab.get(c)) for c in cols), ab.get("valido_de"), hoje, "não"])
    out.sort(key=lambda l: (l[0], str(l[-3] or "")))
    return out
