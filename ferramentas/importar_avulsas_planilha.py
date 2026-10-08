"""Importa a "criticidade validada pela foto" de uma planilha para o livro das rondas avulsas (Levi, 08/10/2026: "Use
esse arquivo em excel para subir as rondas avulsas dessas usinas, utilize a data de vegetação e sujidade, escolha a data
mais recente entre as duas, suba no nome de <quem validou>").

Cada linha da planilha (uma usina com os níveis de sujidade e vegetação revisados a partir das fotos das rondas) vira UM
lançamento no livro `nexus_rondas_avulsas · fato_ronda_avulsa`, pelo MESMO caminho de gravação da tela
(`ronda_avulsa.montar_linha` + `acrescentar`): o mesmo cabeçalho, o nome e o comentário cifrados pelo Cofre
(NEXUS_CHAVE_CADASTRO), a pessoa como `pessoa_id` do cadastro + `pessoa_hmac` (o código do e-mail, NEXUS_PESSOA_HMAC).
`origem = "validacao_foto"`: NÃO é ronda realizada (fica fora do `fato_ronda`, da cobertura e da duração; as telas a
mostram como níveis validados pela foto).

As regras (as do pedido, e por quê):
- Usina pelo de-para "Fracttal · Classificação 1" do cadastro, casamento EXATO do texto (só sem os espaços das pontas).
  A que não casa não entra e sai em "fora" com o porquê; quando o nome normalizado casaria, diz com qual usina, para o
  conserto ir ao cadastro (tela Base -> Ligações) e não a um mapa escondido aqui. Nunca chuta (regra 4).
- Data = a mais recente entre "Data das fotos de sujidade" e "Data das fotos de vegetação" (só uma: ela). Data no futuro
  é recusada. Sem o limite de 30 dias da tela: é a importação de um registro, não um lançamento de campo.
- Sujidade e vegetação = as colunas "correta" (1 a 5; "Sem foto" = vazio). Linha sem nenhum dos dois não entra.
- Vala, sombreamento, sensores e tipo vazios (a planilha não diz; vazio = não informado, nunca "limpo"). Início = a data
  às 00:00 de Brasília: não há hora real.
- A pessoa vem por ARGUMENTO (o repositório é público: nenhum nome aqui) e é achada no cadastro pelo nome ou pelo nome
  padrão, decifrados só na memória. Se não for exatamente UMA ficha, ou se a ficha não tiver e-mail (sem ele não há o
  código do App), PARA e diz: não chuta.
- Idempotente: a mesma usina + data + pessoa + origem que já vale no livro é pulada (rodar de novo não duplica).
- Conferência DEPOIS de gravar: relê o livro e bate linha a linha com o que foi enviado (usina, data, níveis, origem,
  pessoa), decifra o nome e o comentário de cada uma, procura nome, e-mail e comentário em claro em todas as células e
  confere que as linhas que já estavam no livro continuam lá (a gravação troca o livro inteiro).

    python ferramentas/importar_avulsas_planilha.py <planilha.xlsx> --pessoa "<nome>" [--comentario "<texto>"]
                                                    [--aba "Criticidade validada"]      ensaio: mede e NÃO grava
    python ferramentas/importar_avulsas_planilha.py <planilha.xlsx> --pessoa "<nome>" ... --gravar   grava e confere

O relatório (JSON) sai só com IDs, contagens e os nomes das usinas da planilha; nunca o nome nem o e-mail da pessoa.
"""
import argparse
import json
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nexus.cadastro.cifra import Cofre  # noqa: E402
from nexus.campo import ronda_avulsa as RA  # noqa: E402
from nexus.campo import visao  # noqa: E402
from nexus.campo.ligacao_cadastro import _norm as norm_fracttal  # noqa: E402
from nexus.campo.ligacao_cadastro import codigo_da_pessoa  # noqa: E402
from nexus.dados import dominios as DOM  # noqa: E402
from nexus.dados import fatos as D  # noqa: E402
from nexus.dados import livros  # noqa: E402
from nexus.dados.fato_ronda import ORIGEM_VALIDACAO_FOTO  # noqa: E402

ABA_PADRAO = "Criticidade validada"
CADASTRO = "cadastro_nexus"
# as colunas do pedido, achadas pelo nome do cabeçalho (a ordem pode mudar de uma planilha para outra)
COLUNAS = {"usina": "Usina", "sujidade": "Sujidade correta", "vegetacao": "Vegetação correta",
           "data_sujidade": "Data das fotos de sujidade", "data_vegetacao": "Data das fotos de vegetação"}
SEM_FOTO = "sem foto"
LINHAS_DE_CABECALHO = 20        # o cabeçalho é procurado nas 20 primeiras linhas (a planilha tem título em cima)
_BRT = timezone(timedelta(hours=-3))


class Parada(RuntimeError):
    """A importação não pode seguir: o texto diz por quê (pessoa não achada, chave faltando, planilha sem as colunas)."""


# ── A planilha ───────────────────────────────────────────────────────────────────────────────────────────────────
def ler_planilha(caminho, aba: str = ABA_PADRAO) -> tuple[int, list[dict]]:
    """(número da linha do cabeçalho, linhas). Cada linha leva o número dela na planilha e as 5 colunas do pedido.
    Linha toda em branco não conta."""
    from openpyxl import load_workbook
    wb = load_workbook(caminho, data_only=True, read_only=True)
    try:
        if aba not in wb.sheetnames:
            raise Parada(f'A planilha não tem a aba "{aba}" (abas: {", ".join(wb.sheetnames)}).')
        todas = list(wb[aba].iter_rows(values_only=True))
    finally:
        wb.close()
    alvo = {DOM.norm(v): k for k, v in COLUNAS.items()}
    for i, l in enumerate(todas[:LINHAS_DE_CABECALHO]):
        idx = {alvo[DOM.norm(v)]: j for j, v in enumerate(l) if DOM.norm(v) in alvo}
        if len(idx) == len(COLUNAS):
            break
    else:
        raise Parada("Não achei o cabeçalho com as colunas " + ", ".join(f'"{c}"' for c in COLUNAS.values()) + ".")
    linhas = []
    for n, l in enumerate(todas[i + 1:], start=i + 2):
        if all(v is None or str(v).strip() == "" for v in l):
            continue
        linhas.append({"linha": n, **{k: (l[j] if j < len(l) else None) for k, j in idx.items()}})
    return i + 1, linhas


def nivel(v) -> tuple[int | None, str]:
    """(nível, situação): 1 a 5 = "ok"; "Sem foto" = (None, "sem_foto"); vazio = (None, "vazio"); outro valor (3,5;
    "alto") = (None, "fora"): fora do domínio vira vazio e é contado, nunca arredondado para o vizinho (regra 4)."""
    if v is None or str(v).strip() == "":
        return None, "vazio"
    if DOM.norm(v) == SEM_FOTO:
        return None, "sem_foto"
    try:
        f = float(str(v).strip().replace(",", "."))
    except ValueError:
        return None, "fora"
    return (int(f), "ok") if f.is_integer() and 1 <= f <= 5 else (None, "fora")


def data(v) -> tuple[date | None, str]:
    """(data, situação). A célula de data do Excel chega como datetime; texto aceito em AAAA-MM-DD ou DD/MM/AAAA."""
    if v is None or str(v).strip() == "":
        return None, "vazio"
    if isinstance(v, datetime):
        return v.date(), "ok"
    if isinstance(v, date):
        return v, "ok"
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).date(), "ok"
        except ValueError:
            continue
    return None, "ilegivel"


# ── O cadastro ───────────────────────────────────────────────────────────────────────────────────────────────────
def _espacos(v) -> str:
    """O texto com os espaços repetidos reduzidos a um. Não é casamento frouxo: maiúscula, acento e pontuação continuam
    contando. Motivo (08/10/2026): no de-para do Fracttal, "Belo Jardim  1" e "Saturnino 1  - RJ" têm espaço duplo que
    a planilha não tem, e as duas validações ficavam de fora por isso."""
    return " ".join(D._txt(v).split())


def _de_para_exato(de_para) -> dict[str, set]:
    out = {}
    for d in de_para:
        if (D._txt(d.get("sistema")) == D.SISTEMA_FRACTTAL and D._id(d.get("usina_id"))
                and D._txt(d.get("excluido")).lower() != "sim"):
            out.setdefault(_espacos(d.get("chave_externa")), set()).add(D._id(d.get("usina_id")))
    return out


def _de_para_normalizado(de_para) -> dict[str, dict]:
    """{nome normalizado: {usina_id: a chave do de-para}}: só para dizer, na lista "fora", com qual usina a linha
    casaria se o texto fosse igual. Não liga nada."""
    out = {}
    for d in de_para:
        if D._txt(d.get("sistema")) == D.SISTEMA_FRACTTAL and D._id(d.get("usina_id")):
            out.setdefault(norm_fracttal(d.get("chave_externa")), {})[D._id(d.get("usina_id"))] = D._txt(
                d.get("chave_externa"))
    return out


def achar_pessoa(pessoas, nome: str, cofre) -> dict:
    """{"pessoa_id", "nome", "email", "fichas"}: a ficha cujo nome ou nome padrão (sem acento, sem caixa) é o nome
    pedido. `fichas` = quantas casaram; `pessoa_id` só quando é exatamente UMA (homônimo não liga: regra 4)."""
    alvo = visao._norm_nome(nome)
    achados = []
    for p in pessoas:
        pid = D._id(p.get("pessoa_id"))
        if not pid or not p.get("sensivel_cifrado") or D._txt(p.get("excluido")).lower() == "sim":
            continue
        try:
            s = json.loads(cofre.decifrar(p["sensivel_cifrado"], f"banco/pessoas/{pid}"))
        except Exception:           # noqa: BLE001 — ficha de outra chave: não é dela que se trata
            continue
        if alvo and alvo in {visao._norm_nome(s.get("nome")), visao._norm_nome(s.get("nome_padrao"))}:
            achados.append((pid, s))
    if len(achados) != 1:
        return {"pessoa_id": None, "nome": "", "email": "", "fichas": len(achados)}
    pid, s = achados[0]
    return {"pessoa_id": pid, "nome": " ".join(str(s.get("nome") or nome).split()),
            "email": D._txt(s.get("email")).lower(), "fichas": 1}


# ── O plano ──────────────────────────────────────────────────────────────────────────────────────────────────────
def _inicio(dia: date) -> str:
    return datetime.combine(dia, time(0, 0), tzinfo=_BRT).isoformat()


def planejar(linhas: list[dict], usinas: list[dict], de_para: list[dict], hoje: date) -> tuple[list[dict], list[dict]]:
    """(entram, fora). `entram`: as linhas que casaram usina e têm nível e data, já com usina_id, equipe_id, dia e os
    níveis. `fora`: a linha da planilha, a usina como a planilha escreve e o motivo."""
    exato, normalizado = _de_para_exato(de_para), _de_para_normalizado(de_para)
    por_id = {D._id(u.get("usina_id")): u for u in usinas if D._id(u.get("usina_id"))}
    entram, fora = [], []
    for l in linhas:
        nome = D._txt(l.get("usina"))
        base = {"linha": l["linha"], "usina": nome}
        if not nome:
            fora.append({**base, "motivo": "linha sem usina"})
            continue
        ids = exato.get(_espacos(nome)) or set()
        if len(ids) != 1:
            item = {**base, "motivo": ("o mesmo texto é de-para de mais de uma usina (não chuta)" if ids else
                                       'sem de-para "Fracttal · Classificação 1" com este texto exato')}
            parecidas = normalizado.get(norm_fracttal(nome)) or {}
            if not ids and parecidas:
                item["casaria_sem_acento_e_espacos"] = [
                    {"usina_id": uid, "nome_no_cadastro": D._txt((por_id.get(uid) or {}).get("nome")),
                     "chave_no_de_para": chave} for uid, chave in sorted(parecidas.items())]
            fora.append(item)
            continue
        uid = next(iter(ids))
        u = por_id.get(uid)
        if not u:
            fora.append({**base, "usina_id": uid, "motivo": "o de-para aponta uma usina que não está no cadastro"})
            continue
        if D._txt(u.get("excluido")).lower() == "sim":
            fora.append({**base, "usina_id": uid, "motivo": "usina excluída no cadastro"})
            continue
        (suj, sit_s), (veg, sit_v) = nivel(l.get("sujidade")), nivel(l.get("vegetacao"))
        (ds, sit_ds), (dv, sit_dv) = data(l.get("data_sujidade")), data(l.get("data_vegetacao"))
        if suj is None and veg is None:
            fora.append({**base, "usina_id": uid, "motivo": f"sem nível validado (sujidade: {sit_s}; vegetação: {sit_v})"})
            continue
        dias = [d for d in (ds, dv) if d]
        if not dias:
            fora.append({**base, "usina_id": uid, "motivo": "sem data das fotos (nem de sujidade nem de vegetação)"})
            continue
        dia = max(dias)
        if dia > hoje:
            fora.append({**base, "usina_id": uid, "motivo": f"data das fotos no futuro ({dia.isoformat()})"})
            continue
        entram.append({**base, "usina_id": uid, "equipe_id": D._id(u.get("equipe_id")), "dia": dia,
                       "sujidade": suj, "vegetacao": veg, "data_sujidade": ds, "data_vegetacao": dv,
                       "situacao": {"sujidade": sit_s, "vegetacao": sit_v, "data_sujidade": sit_ds,
                                    "data_vegetacao": sit_dv},
                       # só informa (a tela conta a cobertura pelas mobilizadas); não barra a importação
                       "mobilizada": visao._mobilizada(u, hoje.isoformat())})
    return entram, fora


def _ja_validada(nova, vistas) -> bool:
    """Idempotência: a mesma usina, no mesmo dia, pela mesma pessoa, com a mesma origem, já vale no livro."""
    return any(RA._origem(v) == nova["origem"] and D._id(v.get("usina_id")) == nova["usina_id"]
               and D._id(v.get("data_id")) == nova["data_id"] and D._id(v.get("pessoa_id")) == nova["pessoa_id"]
               for v in vistas)


def _resumo(entram, fora, linhas) -> dict:
    dias = [e["dia"] for e in entram]
    so_s = sum(1 for e in entram if e["data_sujidade"] and not e["data_vegetacao"])
    so_v = sum(1 for e in entram if e["data_vegetacao"] and not e["data_sujidade"])
    duas = [e for e in entram if e["data_sujidade"] and e["data_vegetacao"]]
    return {
        "usinas": {"linhas": len(linhas), "casaram": len(entram) + sum(1 for f in fora if "usina_id" in f),
                   "entram": len(entram), "fora": len(fora),
                   "nao_mobilizadas_entre_as_que_entram": sum(1 for e in entram if not e["mobilizada"])},
        "datas": {"min": min(dias).isoformat() if dias else None, "max": max(dias).isoformat() if dias else None,
                  "so_data_de_sujidade": so_s, "so_data_de_vegetacao": so_v, "as_duas": len(duas),
                  "as_duas_diferentes_vale_a_mais_recente": sum(1 for e in duas
                                                               if e["data_sujidade"] != e["data_vegetacao"])},
        "niveis": {"com_sujidade": sum(1 for e in entram if e["sujidade"] is not None),
                   "com_vegetacao": sum(1 for e in entram if e["vegetacao"] is not None),
                   "com_os_dois": sum(1 for e in entram if e["sujidade"] is not None and e["vegetacao"] is not None),
                   "sem_foto_sujidade": sum(1 for e in entram if e["situacao"]["sujidade"] == "sem_foto"),
                   "sem_foto_vegetacao": sum(1 for e in entram if e["situacao"]["vegetacao"] == "sem_foto"),
                   "fora_do_dominio": sum(1 for e in entram for k in ("sujidade", "vegetacao")
                                          if e["situacao"][k] == "fora"),
                   "sem_foto_mas_com_data": sum(1 for e in entram for k in ("sujidade", "vegetacao")
                                                if e["situacao"][k] == "sem_foto" and e[f"data_{k}"])},
    }


# ── Executar ─────────────────────────────────────────────────────────────────────────────────────────────────────
def executar(planilha, pessoa: str, *, comentario: str | None = None, aba: str = ABA_PADRAO, gravar: bool = False,
             hoje: date | None = None, fora_do_cadastro: bool = False, email: str = "") -> dict:
    """Monta (e, com `gravar`, grava e confere) dentro do contexto do app: o banco, as chaves e a sessão são os do
    Nexus (`current_app`). Sobe `Parada` quando não pode seguir; no ensaio, a pessoa não achada só é relatada."""
    from flask import current_app
    cfg = current_app.config
    hoje = hoje or datetime.now(_BRT).date()
    cab, linhas = ler_planilha(planilha, aba)
    base, sessao = visao._base(), visao._sessao()
    cad = {a: livros.ler(base, sessao, CADASTRO, a) for a in ("usinas", "de_para", "pessoas")}
    if not cad["usinas"] or not cad["de_para"]:
        raise Parada("Não consegui ler as usinas e o de-para do cadastro (cadastro_nexus) no banco.")
    entram, fora = planejar(linhas, cad["usinas"], cad["de_para"], hoje)
    comentario = " ".join((comentario or (f"Níveis validados pela foto (planilha {Path(planilha).name}); importados "
                                          f"em {hoje.strftime('%d/%m/%Y')}")).split())[:RA.COMENTARIO_MAX]
    faltam = [k for k in ("NEXUS_CHAVE_CADASTRO", "NEXUS_PESSOA_HMAC") if not cfg.get(k)]
    if gravar and not cfg.get("GRIDCO_SQL_TOKEN"):
        faltam.append("GRIDCO_SQL_TOKEN")
    quem = {"pessoa_id": None, "fichas": None, "nome": "", "email": ""}
    cofre = None
    if cfg.get("NEXUS_CHAVE_CADASTRO"):
        cofre = RA._cofre()
        quem = achar_pessoa(cad["pessoas"], pessoa, cofre)
        if fora_do_cadastro:
            # quem validou não tem ficha (Levi, 08/10/2026: quem validou a planilha de 07/10 "fora do cadastro"): o nome vai só cifrado,
            # sem pessoa_id; com o e-mail, o código da pessoa (pessoa_hmac) liga quando a ficha existir. Se o nome
            # casar com uma ficha, não é "fora do cadastro": para, para não gravar a mesma pessoa de dois jeitos
            if quem["fichas"]:
                raise Parada(f"--fora-do-cadastro, mas o nome casa com {quem['fichas']} ficha(s) do cadastro.")
            quem = {"pessoa_id": None, "nome": " ".join(pessoa.split()), "email": D._txt(email).lower(), "fichas": 0}
    codigo = codigo_da_pessoa(cfg.get("NEXUS_PESSOA_HMAC"), quem["email"]) if quem["email"] else None
    impede = []
    if faltam:
        impede.append("faltam no .env: " + ", ".join(faltam))
    if not fora_do_cadastro and quem["fichas"] is not None and quem["fichas"] != 1:
        impede.append(f"a pessoa pedida casa com {quem['fichas']} fichas do cadastro (precisa ser exatamente 1; "
                      "nome e nome padrão comparados sem acento e sem caixa)")
    elif quem["pessoa_id"] and not quem["email"]:
        impede.append(f"a ficha da pessoa (pessoa_id {quem['pessoa_id']}) não tem e-mail: sem ele não há o código "
                      "da pessoa (pessoa_hmac) que o App e a tela usam")
    antes = RA.ler_todas()
    rel = {"modo": "gravar" if gravar else "ensaio",
           "planilha": {"arquivo": Path(planilha).name, "aba": aba, "cabecalho_na_linha": cab, "linhas": len(linhas)},
           **_resumo(entram, fora, linhas),
           "pessoa": {"fichas_com_o_nome": quem["fichas"], "pessoa_id": quem["pessoa_id"],
                      "fora_do_cadastro": fora_do_cadastro, "tem_email": bool(quem["email"])},
           "livro": {"existe_no_banco": bool(antes) or RA.LIVRO in _livros_no_banco(base, sessao),
                     "linhas_antes": len(antes), "validas_antes": len(RA.validas(antes))},
           "fora": fora, "impede_gravar": impede}
    novas = []
    if cofre and ((quem["pessoa_id"] and quem["email"]) or (fora_do_cadastro and quem["nome"])):
        novas = [RA.montar_linha(cofre, origem=ORIGEM_VALIDACAO_FOTO, dia=e["dia"], usina_id=e["usina_id"],
                                 equipe_id=e["equipe_id"], pessoa_id=quem["pessoa_id"], codigo=codigo,
                                 nome=quem["nome"], email=quem["email"], inicio=_inicio(e["dia"]),
                                 sujidade=e["sujidade"], vegetacao=e["vegetacao"], comentario=comentario)
                 for e in entram]
        vistas, pular = RA.validas(antes), 0
        for n in novas:
            if _ja_validada(n, vistas):
                pular += 1
            else:
                vistas.append(n)
        rel["gravaria"], rel["pulariam_por_ja_estar_no_livro"] = len(novas) - pular, pular
    else:
        rel["gravaria"] = 0          # sem a pessoa não há linha (as prontas estão em usinas.entram)
    rel["exemplo"] = [{"linha": e["linha"], "usina_id": e["usina_id"], "data": e["dia"].isoformat(),
                       "sujidade": e["sujidade"], "vegetacao": e["vegetacao"]} for e in entram[:3]]
    if not gravar:
        return rel
    if impede:
        raise Parada("Não gravei nada: " + "; ".join(impede) + ".")
    entraram, puladas = RA.acrescentar(novas, _ja_validada)
    rel["gravado"] = {"entraram": len(entraram), "puladas_por_ja_estar_no_livro": len(puladas)}
    rel["conferencia"] = conferir(entraram, antes, livros.ler(base, sessao, RA.LIVRO, RA.ABA), cofre,
                                  quem, comentario)
    return rel


def _livros_no_banco(base, sessao) -> set:
    r = sessao.get(f"{base}/api/workbooks", timeout=60)
    r.raise_for_status()
    return {w.get("key") for w in r.json()}


def conferir(enviadas: list[dict], antes: list[dict], depois: list[dict], cofre, quem: dict, comentario: str) -> dict:
    """Relê e bate linha a linha. Volta os problemas achados (vazio = conferido)."""
    por_id = {}
    for l in depois:
        por_id.setdefault(D._txt(l.get("id")), []).append(l)
    problemas, certas = [], 0
    for n in enviadas:
        achadas = por_id.get(n["id"]) or []
        if len(achadas) != 1:
            problemas.append(f"{n['id']}: {len(achadas)} linhas no banco")
            continue
        g, erros = achadas[0], []
        for c in ("usina_id", "equipe_id", "data_id", "sujidade", "vegetacao", "pessoa_id"):
            if D._int(g.get(c)) != D._int(n.get(c)):
                erros.append(c)
        for c in ("data", "inicio", "origem", "pessoa_hmac"):
            if D._txt(g.get(c)) != D._txt(n.get(c)):
                erros.append(c)
        for c in ("tipo", "fim", "duracao_min", "vala", "sombreamento", "anula_id", *(c for c, _n in RA.SENSORES)):
            if D._txt(g.get(c)):
                erros.append(f"{c} deveria estar vazio")
        try:
            q = json.loads(cofre.decifrar(D._txt(g.get("quem_cifrado")), RA._ctx(n["id"], "quem")))
            if (q.get("nome"), q.get("email")) != (quem["nome"], quem["email"]):
                erros.append("quem_cifrado decifra para outra pessoa")
        except Exception:           # noqa: BLE001
            erros.append("quem_cifrado não decifra")
        try:
            if cofre.decifrar(D._txt(g.get("comentario_cifrado")), RA._ctx(n["id"], "comentario")) != comentario:
                erros.append("comentario_cifrado decifra para outro texto")
        except Exception:           # noqa: BLE001
            erros.append("comentario_cifrado não decifra")
        if erros:
            problemas.append(f"{n['id']}: " + ", ".join(erros))
        else:
            certas += 1
    sumiram = {D._txt(l.get("id")) for l in antes} - set(por_id)
    if sumiram:
        problemas.append(f"{len(sumiram)} linhas que já estavam no livro sumiram")
    # nada pessoal em claro em célula nenhuma do livro (a API tem leitura aberta)
    pedacos = {p for p in visao._norm_nome(quem["nome"]).split() if len(p) > 3}
    claros = [x for x in (quem["email"], comentario) if x]
    em_claro = 0
    for l in depois:
        for v in l.values():
            t = D._txt(v)
            if t and not Cofre.eh_cifrado(t) and (
                    any(p in visao._norm_nome(t).split() for p in pedacos) or any(x in t for x in claros)):
                em_claro += 1
    if em_claro:
        problemas.append(f"{em_claro} células com nome, e-mail ou comentário em claro")
    return {"enviadas": len(enviadas), "no_livro_depois": len(depois), "linhas_antes": len(antes),
            "batem": certas, "problemas": problemas}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Importa a criticidade validada pela foto para o livro das rondas "
                                             "avulsas (ensaio por padrão).")
    ap.add_argument("planilha")
    ap.add_argument("--pessoa", required=True, help="o nome de quem validou, como está no cadastro")
    ap.add_argument("--comentario", help="o texto que vai cifrado em cada linha")
    ap.add_argument("--aba", default=ABA_PADRAO)
    ap.add_argument("--gravar", action="store_true", help="grava e confere (sem isto, só o ensaio)")
    ap.add_argument("--fora-do-cadastro", action="store_true",
                    help="quem validou não tem ficha no cadastro: o nome vai só cifrado, sem pessoa_id")
    ap.add_argument("--email", default="", help="com --fora-do-cadastro: o e-mail, para o código da pessoa")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    import requests

    from nexus import create_app
    app = create_app()
    app.extensions["nexus_dados_sessao"] = requests.Session()
    with app.app_context():
        try:
            rel = executar(a.planilha, a.pessoa, comentario=a.comentario, aba=a.aba, gravar=a.gravar,
                           fora_do_cadastro=a.fora_do_cadastro, email=a.email)
        except Parada as e:
            print(json.dumps({"parou": str(e)}, ensure_ascii=False, indent=1))
            return 2
    print(json.dumps(rel, ensure_ascii=False, indent=1, default=str))
    return 1 if (rel.get("conferencia") or {}).get("problemas") else 0


if __name__ == "__main__":
    sys.exit(main())
