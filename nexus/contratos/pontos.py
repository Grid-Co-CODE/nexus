"""Os pontos de atenção e de divergência de cada contrato (Comando > Contratos, 19/11/2026).

O pedido (19/11/2026), olhando o painel "Zeladoria Contratual por Cliente" do Radar da Zeladoria:
"tem uma parte bacana também de ponto de atenção e pontos de divergência do contrato". No Radar, quem levantou os
contratos de zeladoria escreveu à mão, por usina, o nível (Atenção ou Divergência) e o motivo ("documentos do mesmo
contrato dizem coisas diferentes (alinhar com o cliente qual vale)"; "vencido ou vencendo, falta documento"). Aqui o
contrato inteiro, de todos os setores, junta quatro fontes, sem copiar nenhuma:

- **as contas** (Atenção): a vigência vencida ou que vence em até `VENCENDO_DIAS` (Levi escolheu 60 em 19/11/2026; o Radar
  usa 90), o prazo de avisar a renovação que passou ou que chega nesses dias, o cliente sem contrato assinado na pasta
  (só minuta, ou só anexo) e o cliente sem PDF de contrato lido;
- **os leitores dos PDFs** (Divergência): o que eles anotaram em `divergencias` de cada contrato (a proposta diz uma
  coisa, o contrato outra, e qual prevalece);
- **a planilha de controle e o PDF** (Divergência): fim da vigência, aviso prévio e índice diferentes (o bloco que ficava
  no fim das Regras);
- **o Radar da Zeladoria** (Atenção ou Divergência): as linhas de `zeladoria_contratual` com alerta, lidas do banco na hora
  (o Radar segue dono delas), casadas com o contrato pelo nome do cliente sem acento e sem caixa, nunca por palpite: o
  cliente do Radar que não casa aparece em Todos os contratos, para alguém acertar o nome;
- e o que o gestor inclui à mão (item `ponto`).

**Resolver** grava um item `resolucao` com o que se decidiu, o motivo e a prova (Levi, 19/11/2026: "Com motivo e prova":
decidir com o cliente qual documento vale é mudança de contrato). Reabrir é retirar a resolução, com motivo e prova também.
O id de cada ponto é fixo e leva o dado que o criou (a data do fim da vigência, o contrato e a posição da divergência):
mudou o dado, nasce outro ponto, e a resolução velha não esconde o novo.

Puro: nada de rede nem Flask.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date

from .controle import _chave
from .fichas import clausula_curta

VENCENDO_DIAS = 60
NIVEIS = ("atencao", "divergencia")
# o id de um ponto: o das fontes ("c:vigencia:2026-12-10", "d:<contrato>:0") ou o do incluído ("p" + 11 hexas, edicao.gravar)
ID_PONTO = re.compile(r"^([a-z]:[\w:.|-]{1,160}|p[0-9a-f]{11})$")


def _dbr(iso) -> str:
    s = str(iso or "")[:10]
    return f"{s[8:10]}/{s[5:7]}/{s[:4]}" if re.match(r"^\d{4}-\d{2}-\d{2}$", s) else s


def _h(*partes) -> str:
    return hashlib.sha1("|".join(str(p) for p in partes).encode("utf-8")).hexdigest()[:10]


def _dias(n: int) -> str:
    n = abs(int(n))
    return f"{n} dia" if n == 1 else f"{n} dias"


def _ref_txt(ref) -> str:
    if not isinstance(ref, dict):
        return ""
    partes = [str(ref.get("arquivo") or "").strip()]
    if ref.get("clausula"):
        partes.append(f"cl. {ref['clausula']}")
    if ref.get("pagina"):
        partes.append(f"p. {ref['pagina']}")
    return ", ".join(p for p in partes if p)


def _ref_curta(ref) -> str:
    """A referência na etiqueta curta da cláusula e a página ("Anx II · 6.1, p. 39"); a inteira vai na dica (`onde_inteiro`)."""
    if not isinstance(ref, dict):
        return ""
    partes = [clausula_curta(ref.get("clausula")) if ref.get("clausula") else "", f"p. {ref['pagina']}" if ref.get("pagina") else ""]
    return ", ".join(p for p in partes if p)


def _ponto(pid, nivel, tema, texto, origem, onde="", setor="", extra=None, refs=()) -> dict:
    """`onde` curto na tela; `onde_inteiro`, o arquivo, a cláusula e a página por extenso, na dica."""
    refs = [r for r in refs if isinstance(r, dict)]
    return {"id": pid, "nivel": nivel, "tema": tema, "texto": texto, "origem": origem,
            "onde": "; ".join(x for x in (_ref_curta(r) for r in refs) if x) if refs else onde,
            "onde_inteiro": "; ".join(x for x in (_ref_txt(r) for r in refs) if x) if refs else onde, "setor": setor,
            **(extra or {})}


def _das_contas(c: dict, ficha: dict | None, hoje: date) -> list[dict]:
    out = []
    fim, dias_fim = c.get("fim"), c.get("dias_fim")
    vencida = dias_fim is not None and dias_fim < 0
    if fim and dias_fim is not None:
        if vencida:
            out.append(_ponto(f"c:vigencia:{fim}", "atencao", "Vigência vencida",
                              f"A vigência venceu em {_dbr(fim)}, há {_dias(dias_fim)}: confirmar a renovação ou o aditivo de prazo.",
                              "conta"))
        elif dias_fim <= VENCENDO_DIAS:
            out.append(_ponto(f"c:vigencia:{fim}", "atencao", "Vigência vencendo",
                              f"A vigência vence em {_dbr(fim)}, em {_dias(dias_fim)}.", "conta"))
    avisar, dias_aviso = c.get("avisar_ate"), c.get("dias_aviso")
    if avisar and dias_aviso is not None and not vencida:
        if dias_aviso < 0:
            out.append(_ponto(f"c:renovacao:{avisar}", "atencao", "Aviso de renovação",
                              f"O prazo para avisar a renovação passou em {_dbr(avisar)}"
                              f" (aviso prévio de {c.get('aviso_dias')} dias antes do fim).", "conta"))
        elif dias_aviso <= VENCENDO_DIAS:
            out.append(_ponto(f"c:renovacao:{avisar}", "atencao", "Aviso de renovação",
                              f"Avisar a renovação até {_dbr(avisar)}, em {_dias(dias_aviso)}.", "conta"))
    if not ficha:
        out.append(_ponto("c:sem_pdf", "atencao", "Sem contrato lido",
                          "Nenhum PDF de contrato deste cliente foi lido: localizar e mandar o contrato assinado.", "conta"))
    else:
        # o contrato assinado: um contrato ou aditivo com assinatura na pasta. O anexo e a proposta sem assinatura são o normal
        # (na 1ª prévia, um cliente com o contrato assinado e oito anexos sem assinatura ganhou oito pontos de "minuta")
        docs = [d for d in ficha.get("documentos") or [] if isinstance(d, dict)]
        if docs and not any(d.get("tipo") in ("contrato", "aditivo") and d.get("assinado") is True for d in docs):
            minutas = [str(d.get("arquivo") or "documento") for d in docs if d.get("assinado") is False]
            if minutas:
                out.append(_ponto(f"c:minuta:{_h(*minutas)}", "atencao", "Sem contrato assinado",
                                  "Não há contrato assinado na pasta: o que existe é minuta (" + "; ".join(minutas) + ").", "conta"))
            else:
                out.append(_ponto(f"c:sem_assinado:{_h(*(str(d.get('arquivo')) for d in docs))}", "atencao", "Sem contrato assinado",
                                  f"Não há contrato assinado na pasta: só {len(docs)} {'anexo ou proposta' if len(docs) == 1 else 'anexos ou propostas'}; localizar o contrato.",
                                  "conta"))
    return out


def _dos_leitores(ficha: dict | None) -> list[dict]:
    out = []
    for k in (ficha or {}).get("contratos") or []:
        for i, d in enumerate(k.get("divergencias") or []):
            if not isinstance(d, dict):
                continue
            if d.get("texto"):
                texto = str(d["texto"])
            else:
                lados = [f"{str(a).capitalize()}: {v}" for a, v in d.items()
                         if a not in ("tema", "prevalece", "ref", "refs", "texto") and isinstance(v, str) and v.strip()]
                texto = " · ".join(lados)
            refs = d.get("refs") if isinstance(d.get("refs"), list) else [d.get("ref")] if d.get("ref") else []
            out.append(_ponto(f"d:{k.get('_id')}:{i}", "divergencia", str(d.get("tema") or "Documentos divergentes"), texto,
                              "leitor", refs=refs,
                              extra={"prevalece": str(d.get("prevalece") or ""), "contrato": str(k.get("id") or k.get("arquivo") or "")}))
    return out


def _planilha_e_pdf(c: dict, ficha: dict | None) -> list[dict]:
    """O mesmo cruzamento que a aba Regras fazia em "Os dados do contrato e o PDF não batem"."""
    out = []
    ks = [k for k in (ficha or {}).get("contratos") or [] if k.get("_id") != "geral"]
    for k in ks:
        nome = f" ({k.get('id') or k.get('arquivo')})" if len(ks) > 1 else ""
        fim = (k.get("vigencia") or {}).get("fim")
        aviso = (k.get("renovacao") or {}).get("aviso_previo_dias")
        ind = (k.get("reajuste") or {}).get("indice")
        if fim and fim != c.get("fim"):
            out.append(_ponto(f"p:{k.get('_id')}:fim:{fim}", "divergencia", "Fim da vigência" + nome,
                              f"Os dados do contrato dizem {_dbr(c.get('fim')) or 'nada'}; o PDF diz {_dbr(fim)}.",
                              "planilha", refs=[(k.get("vigencia") or {}).get("ref")]))
        if aviso is not None and aviso != c.get("aviso_dias"):
            antes = f"{c.get('aviso_dias')} dias" if c.get("aviso_dias") is not None else "nada"
            out.append(_ponto(f"p:{k.get('_id')}:aviso:{aviso}", "divergencia", "Aviso prévio de renovação" + nome,
                              f"Os dados do contrato dizem {antes}; o PDF diz {aviso} dias.", "planilha",
                              refs=[(k.get("renovacao") or {}).get("ref")]))
        a, b = _chave(c.get("indice") or ""), _chave(ind or "")
        if ind and b not in a and (a or "@") not in b:
            out.append(_ponto(f"p:{k.get('_id')}:indice:{_h(ind)}", "divergencia", "Índice de reajuste" + nome,
                              f"Os dados do contrato dizem {c.get('indice') or 'nada'}; o PDF diz {ind}.", "planilha",
                              refs=[(k.get("reajuste") or {}).get("ref")]))
    return out


def _do_radar(linhas: list[dict]) -> list[dict]:
    """As linhas com alerta de um cliente no Radar: o mesmo motivo em várias usinas vira um ponto, como no painel."""
    grupos, ordem = {}, []
    for r in linhas:
        nivel = str(r.get("nivel_alerta") or "")
        if nivel not in NIVEIS:
            continue
        txt = re.sub(r"^\s*(aten[cç][aã]o|diverg[eê]ncia)\s*:\s*", "", str(r.get("status") or ""), flags=re.I).strip()
        txt = txt or "Sem detalhe no levantamento."
        ch = (nivel, txt)
        if ch not in grupos:
            grupos[ch] = []
            ordem.append(ch)
        ufv = str(r.get("ufv") or "").strip()
        if ufv and not re.fullmatch(r"[-—]?", ufv):
            grupos[ch].append(ufv)
    out = []
    for nivel, txt in ordem:
        ufvs = grupos[(nivel, txt)]
        out.append(_ponto(f"z:{_h(nivel, txt)}", nivel, "Zeladoria (Radar)", txt, "radar",
                          ("UFVs: " + ", ".join(ufvs[:6]) + (f" e mais {len(ufvs) - 6}" if len(ufvs) > 6 else "")) if ufvs else "",
                          "Zeladoria"))
    return out


def todos(contratos: list[dict], fichas: dict, radar: list[dict] | None, incluidos: dict, resolucoes: dict,
          hoje: date) -> dict:
    """{"por_cliente": {cliente: [ponto]}, "radar_sem_contrato": [cliente do Radar sem contrato de mesmo nome],
    "radar_lido": bool}. Cada ponto leva `resolvido` (a resolução de agora, ou None). Na lista do cliente, o aberto antes
    do resolvido, a Atenção antes da Divergência; dentro disso, a ordem das fontes."""
    por_chave = {_chave(c["cliente"]): c["cliente"] for c in contratos}
    radar_cli, sem = {}, set()
    for r in radar or []:
        cli = por_chave.get(_chave(r.get("cliente") or ""))
        if cli:
            radar_cli.setdefault(cli, []).append(r)
        elif str(r.get("nivel_alerta") or "") in NIVEIS:
            sem.add(str(r.get("cliente") or "").strip() or "—")
    out = {}
    for c in contratos:
        cli, f = c["cliente"], fichas.get(c["cliente"])
        lista = (_das_contas(c, f, hoje) + _dos_leitores(f) + _planilha_e_pdf(c, f) + _do_radar(radar_cli.get(cli, []))
                 + [_ponto(pid, "atencao" if p.get("nivel") == "Atenção" else "divergencia", "Incluído pelo gestor",
                           str(p.get("texto") or ""), "incluido", setor=str(p.get("setor") or ""),
                           extra={"quem": p.get("_quem") or "", "quando": p.get("_quando") or ""})
                    for pid, p in incluidos.items() if p.get("_cliente") == cli])
        for p in lista:
            p["resolvido"] = resolucoes.get(p["id"])
        ordem = {id(p): i for i, p in enumerate(lista)}
        lista.sort(key=lambda p: (p["resolvido"] is not None, NIVEIS.index(p["nivel"]), ordem[id(p)]))
        out[cli] = lista
    return {"por_cliente": out, "radar_sem_contrato": sorted(sem), "radar_lido": radar is not None}
