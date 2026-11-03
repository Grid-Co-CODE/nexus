"""As três funções do financeiro do Radar, em Python (etapa 4, 03/11/2026).

No Supabase elas eram funções do banco (`fin_promover`, `fin_definir_fornecedor`, `fin_editar_provisao`, em
`docs/financeiro/*.sql` do Radar), porque mexem em várias tabelas de uma vez e têm de ser tudo ou nada. Aqui cada uma lê o
estado do gravador, confere a mesma regra com a mesma mensagem e devolve os pedidos de gravação mais a resposta que o app
espera; o gravador aplica os pedidos num salvamento só (`Gravador.chamar`), então continua tudo ou nada.

Só o HEAD aprovado chama qualquer uma das três, como no banco do Radar.
"""
import re
from datetime import datetime, timezone

MES = re.compile(r"^\d{4}-\d{2}$")


class FinErro(ValueError):
    """A regra do financeiro recusou. Vira `Recusa` no gravador; a mensagem é a mesma do banco do Radar."""


def _num(v) -> float:
    if v is None or v == "":
        return 0.0
    return float(v)


def _por_id(est: dict, aba: str) -> dict:
    return {str(l.get("id")): l for l in est["abas"].get(aba, [])}


def _proximo_prv(est: dict) -> int:
    nums = [int(d) for l in est["abas"].get("fin_provisao", []) if str(l.get("id") or "").startswith("PRV-")
            for d in [re.sub(r"\D", "", str(l["id"]))] if d]
    return max(nums + [0])


def _prv(n: int) -> str:
    return f"PRV-{n:04d}"


def _head(nome: str, quem: dict) -> str:
    if quem.get("status") != "aprovado":
        raise FinErro(f"{nome}: usuário não aprovado")
    if quem.get("papel") != "HEAD":
        acao = {"fin_promover": "promover", "fin_definir_fornecedor": "definir o fornecedor",
                "fin_editar_provisao": "editar provisão"}[nome]
        raise FinErro(f"{nome}: só o HEAD pode {acao}")
    return quem.get("email")


def _upsert(view: str, linhas: list) -> dict:
    return {"op": "upsert", "view": view, "linhas": linhas}


def _historico(item_id, mes, campo, motivo, quem, agora, **resto) -> dict:
    return {"item_id": item_id, "mes": mes, "campo": campo, "valor_antigo": resto.get("valor_antigo"),
            "valor_novo": resto.get("valor_novo"), "texto_antigo": resto.get("texto_antigo"),
            "texto_novo": resto.get("texto_novo"), "minimo_conciliado": resto.get("minimo_conciliado"),
            "motivo": motivo, "quem": quem, "em": agora}


def _total_do_item(it: dict) -> float:
    forma = it.get("forma")
    if forma == "mensal":
        return _num(it.get("valor")) * _num(it.get("n_meses"))
    if forma == "personalizado":
        return sum(_num(a.get("valor")) for a in (it.get("agenda") or []))
    return _num(it.get("valor"))


def fin_promover(est: dict, quem: dict, args: dict, agora: str | None = None):
    nome = "fin_promover"
    eu = _head(nome, quem)
    agora = agora or datetime.now(timezone.utc).isoformat(timespec="seconds")
    cen_id, item_ids, provs = args.get("p_cenario_id"), args.get("p_item_ids"), args.get("p_provisoes")
    cen = _por_id(est, "fin_cenario").get(str(cen_id))
    if cen is None or cen.get("excluido"):
        raise FinErro(f"{nome}: cenário {cen_id} não encontrado")
    if cen.get("arquivado"):
        raise FinErro(f'{nome}: cenário "{cen.get("nome")}" está arquivado')
    if not item_ids:
        raise FinErro(f"{nome}: nenhum item escolhido")
    if not isinstance(provs, list):
        raise FinErro(f"{nome}: provisões inválidas")
    if any(str(e.get("item_id")) not in {str(i) for i in item_ids} for e in provs):
        raise FinErro(f"{nome}: há provisão de item que não foi escolhido")
    if any(not MES.match(str(e.get("mes") or "")) for e in provs):
        raise FinErro(f"{nome}: mês fora do formato AAAA-MM")
    pares = [(str(e.get("item_id")), e.get("mes")) for e in provs]
    if len(pares) != len(set(pares)):
        raise FinErro(f"{nome}: mês repetido para o mesmo item")
    ruins = sorted(e.get("mes") for e in provs if _num(e.get("valor")) <= 0)
    if ruins:
        raise FinErro(f"{nome}: valor inválido no mês {ruins[0]}")

    itens = _por_id(est, "fin_cenario_item")
    abertas = {(str(p.get("item_id")), p.get("mes")) for p in est["abas"].get("fin_provisao", []) if not p.get("excluido")}
    prox = _proximo_prv(est)
    promovidos, ignorados, novas, linhas_prv, linhas_item = [], [], [], [], []
    for item_id in sorted({str(i) for i in item_ids}):
        it = itens.get(item_id)
        if it is None:
            raise FinErro(f"{nome}: item {item_id} não existe")
        if str(it.get("cenario_id")) != str(cen_id):
            raise FinErro(f"{nome}: item {item_id} é de outro cenário")
        if it.get("excluido"):
            raise FinErro(f'{nome}: item "{it.get("descricao")}" está excluído')
        if it.get("promovido_em"):
            ignorados.append({"item_id": item_id, "motivo": "já promovido", "promovido_em": it.get("promovido_em")})
            continue
        if it.get("tipo") == "T" and not it.get("fornecedor_id") and not it.get("fornecedor_a_definir"):
            raise FinErro(f'{nome}: ligue o item "{it.get("descricao")}" a um fornecedor do cadastro antes de promover')
        do_item = sorted((e for e in provs if str(e.get("item_id")) == item_id), key=lambda e: e.get("mes"))
        if not do_item:
            raise FinErro(f'{nome}: item "{it.get("descricao")}" sem provisões')
        total, soma = round(_total_do_item(it), 2), round(sum(_num(e.get("valor")) for e in do_item), 2)
        if abs(total - soma) > 0.01:
            raise FinErro(f'{nome}: item "{it.get("descricao")}": as provisões somam {soma} mas o total do item é {total}')
        for e in do_item:
            if (item_id, e.get("mes")) in abertas:
                continue
            prox += 1
            valor = round(_num(e.get("valor")), 2)
            linhas_prv.append({"id": _prv(prox), "item_id": item_id, "cenario_id": it.get("cenario_id"),
                               "tipo": it.get("tipo"), "fornecedor_id": it.get("fornecedor_id"),
                               "fornecedor_nome": it.get("fornecedor_nome"),
                               "fornecedor_a_definir": bool(it.get("fornecedor_a_definir")), "via": it.get("via"),
                               "mes": e.get("mes"), "valor": valor, "promovido_em": agora, "promovido_por": eu})
            abertas.add((item_id, e.get("mes")))
            novas.append({"id": _prv(prox), "item_id": item_id, "mes": e.get("mes"), "valor": valor})
        linhas_item.append({"id": item_id, "promovido_em": agora, "promovido_por": eu})
        promovidos.append(item_id)
    ops = [_upsert("rf_fin_provisao", linhas_prv)] if linhas_prv else []
    ops += [_upsert("rf_fin_cenario_item", linhas_item)] if linhas_item else []
    return ops, {"promovido_em": agora, "promovidos": promovidos, "ignorados": ignorados, "provisoes": novas}


def fin_definir_fornecedor(est: dict, quem: dict, args: dict, agora: str | None = None):
    nome = "fin_definir_fornecedor"
    eu = _head(nome, quem)
    agora = agora or datetime.now(timezone.utc).isoformat(timespec="seconds")
    item_id, forn_id = str(args.get("p_item_id")), str(args.get("p_fornecedor_id"))
    it = _por_id(est, "fin_cenario_item").get(item_id)
    if it is None or it.get("excluido"):
        raise FinErro(f"{nome}: item {item_id} não encontrado")
    if not it.get("fornecedor_a_definir"):
        raise FinErro(f'{nome}: o item "{it.get("descricao")}" não está com fornecedor a definir')
    f = _por_id(est, "fornecedores").get(forn_id)
    if f is None or f.get("excluido"):
        raise FinErro(f"{nome}: fornecedor {forn_id} não encontrado no cadastro")
    if (it.get("tipo") == "T" and f.get("tipo") == "Primarizado") or (it.get("tipo") == "P" and f.get("tipo") != "Primarizado"):
        tipo = "terceirizado" if it.get("tipo") == "T" else "primarizado"
        raise FinErro(f'{nome}: "{f.get("empresa")}" não serve para um item {tipo}')
    item = {"id": item_id, "fornecedor_id": forn_id, "fornecedor_nome": f.get("empresa"), "fornecedor_a_definir": False,
            "fornecedor_definido_por": eu, "fornecedor_definido_em": agora}
    provs = [{"id": p["id"], "fornecedor_id": forn_id, "fornecedor_nome": f.get("empresa"), "fornecedor_a_definir": False,
              "conciliar_a_partir_de": agora}
             for p in est["abas"].get("fin_provisao", [])
             if str(p.get("item_id")) == item_id and not p.get("excluido") and not p.get("fechamento")
             and p.get("fornecedor_a_definir")]
    ops = [_upsert("rf_fin_cenario_item", [item])] + ([_upsert("rf_fin_provisao", provs)] if provs else [])
    return ops, {"item_id": item_id, "fornecedor_id": forn_id, "fornecedor": f.get("empresa"),
                 "provisoes_atualizadas": len(provs), "definido_por": eu, "definido_em": agora}


def _limpo(v):
    v = (v or "").strip() if isinstance(v, str) or v is None else v
    return v or None


def fin_editar_provisao(est: dict, quem: dict, args: dict, agora: str | None = None):
    nome = "fin_editar_provisao"
    eu = _head(nome, quem)
    agora = agora or datetime.now(timezone.utc).isoformat(timespec="seconds")
    item_id, provs, motivo = str(args.get("p_item_id")), args.get("p_provisoes"), args.get("p_motivo")
    usina, cliente = _limpo(args.get("p_usina")), _limpo(args.get("p_cliente"))
    if not (motivo or "").strip():
        raise FinErro(f"{nome}: o motivo é obrigatório")
    it = _por_id(est, "fin_cenario_item").get(item_id)
    if it is None or it.get("excluido"):
        raise FinErro(f"{nome}: item {item_id} não encontrado")
    if not it.get("promovido_em"):
        raise FinErro(f'{nome}: o item "{it.get("descricao")}" ainda não foi promovido (não tem provisão)')

    linhas_prv, hist, item, n = [], [], {}, 0
    tot_antigo = tot_novo = 0.0
    if provs is not None:
        if not isinstance(provs, list) or not provs:
            raise FinErro(f"{nome}: informe ao menos um mês (para tirar tudo, use Cancelar provisão)")
        if any(not MES.match(str(e.get("mes") or "")) for e in provs):
            raise FinErro(f"{nome}: mês fora do formato AAAA-MM")
        meses = [e.get("mes") for e in provs]
        if len(meses) != len(set(meses)):
            raise FinErro(f"{nome}: mês repetido")
        ruins = sorted(e.get("mes") for e in provs if _num(e.get("valor")) <= 0)
        if ruins:
            raise FinErro(f"{nome}: valor inválido no mês {ruins[0]}")
        abaixo = sorted((e for e in provs if _num(e.get("valor")) + 0.005 < _num(e.get("minimo"))), key=lambda e: e["mes"])
        if abaixo:
            raise FinErro(f"{nome}: o mês {abaixo[0]['mes']} ficaria abaixo do que já foi conciliado "
                          f"(R$ {round(_num(abaixo[0].get('minimo')), 2)})")
        do_item = [p for p in est["abas"].get("fin_provisao", []) if str(p.get("item_id")) == item_id and not p.get("excluido")]
        fechado = next((p["mes"] for p in do_item if p.get("fechamento") and p.get("mes") in meses), None)
        if fechado:
            raise FinErro(f"{nome}: o mês {fechado} tem provisão alinhada ou cancelada e não pode ser editado")
        abertas = {p.get("mes"): p for p in do_item if not p.get("fechamento")}
        tot_antigo = sum(_num(p.get("valor")) for p in abertas.values())
        tot_novo = sum(_num(e.get("valor")) for e in provs)
        for mes in sorted(m for m in abertas if m not in meses):            # meses que saem: lixeira + histórico
            p = abertas[mes]
            linhas_prv.append({"id": p["id"], "excluido": True, "excluido_em": agora, "excluido_por": eu})
            hist.append(_historico(item_id, mes, "mes_removido", motivo, eu, agora, valor_antigo=p.get("valor")))
            n += 1
        prox = _proximo_prv(est)
        for e in sorted(provs, key=lambda e: e["mes"]):
            mes, valor, minimo = e["mes"], round(_num(e.get("valor")), 2), _num(e.get("minimo"))
            p = abertas.get(mes)
            if p is not None:
                if abs(_num(p.get("valor")) - valor) > 0.005:
                    linhas_prv.append({"id": p["id"], "valor": valor})
                    hist.append(_historico(item_id, mes, "valor", motivo, eu, agora, valor_antigo=p.get("valor"),
                                           valor_novo=valor, minimo_conciliado=minimo))
                    n += 1
            else:
                prox += 1
                linhas_prv.append({"id": _prv(prox), "item_id": item_id, "cenario_id": it.get("cenario_id"),
                                   "tipo": it.get("tipo"), "fornecedor_id": it.get("fornecedor_id"),
                                   "fornecedor_nome": it.get("fornecedor_nome"),
                                   "fornecedor_a_definir": bool(it.get("fornecedor_a_definir")), "via": it.get("via"),
                                   "mes": mes, "valor": valor, "promovido_em": it.get("promovido_em"),
                                   "promovido_por": it.get("promovido_por"),
                                   "conciliar_a_partir_de": it.get("fornecedor_definido_em")})
                hist.append(_historico(item_id, mes, "mes_incluido", motivo, eu, agora, valor_novo=valor))
                n += 1
    for campo, novo in (("usina", usina), ("cliente", cliente)):
        if novo != it.get(campo):                       # o `is distinct from` do banco: compara com o gravado cru
            item[campo] = novo
            hist.append(_historico(item_id, None, campo, motivo, eu, agora, texto_antigo=it.get(campo), texto_novo=novo))
            n += 1
    if n == 0:
        raise FinErro(f"{nome}: nada mudou")
    ops = [_upsert("rf_fin_provisao", linhas_prv)] if linhas_prv else []
    ops += [_upsert("rf_fin_cenario_item", [{"id": item_id, **item}])] if item else []
    ops += [{"op": "insert", "view": "rf_fin_provisao_historico", "linhas": hist}]
    return ops, {"item_id": item_id, "alteracoes": n, "total_antigo": round(tot_antigo, 2),
                 "total_novo": round(tot_novo, 2), "quem": eu, "em": agora}


FUNCOES = {"fin_promover": fin_promover, "fin_definir_fornecedor": fin_definir_fornecedor,
           "fin_editar_provisao": fin_editar_provisao}
