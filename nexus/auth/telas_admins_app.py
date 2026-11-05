"""Base → Acessos, aba Administradores do App de Campo (05/11/2026): quem administra o App de Campo, escolhido no Nexus.

Levi, 05/11/2026: "os administradores do App de Campo e os técnicos por usina têm de ser escolhidos no Nexus". O dado e as
regras moram em `nexus/pcm/admins_app.py` (a aba `fato_admin_app` do livro dos técnicos por usina, que o App lê de 5 em 5
minutos); aqui ficam as contas da aba e o pôr e o tirar. A página e o POST são os de Base → Acessos
(`telas_acessos.py`): só o administrador do Nexus vê e grava, e o POST confere o código do formulário e a origem.

- **Quem dá para escolher:** as fichas do cadastro de pessoas do banco que não estão desligadas nem excluídas.
- **O código da pessoa** (por onde o App a acha) é o do `responsaveis.codigos`: o do usuário do Fracttal ligado à pessoa
  em Pessoas e setores e, sem ele, o do e-mail da ficha. Sem código, a pessoa não vira administrador (409 com a frase).
- **Quem decidiu** sai do código do e-mail do login: pela ficha que o tem ou, sem ficha (quem é do escritório ainda não
  tem), pelo e-mail que este Nexus conhece (os administradores e quem entrou em 30 dias). Vazio = a senha de administrador.
"""
import json
import unicodedata
from types import SimpleNamespace

from ..dados import fatos as D
from ..pcm import admins_app as AA
from ..pcm import atribuicoes as A

SEM_HMAC = ("Este Nexus não tem a NEXUS_PESSOA_HMAC: a linha iria sem assinatura e o App não a aplicaria. Nada foi "
            "gravado.")


class SemCadastro(Exception):
    """O cadastro de pessoas do banco não foi lido: a aba mostra o que já está no livro, e o Pôr fica travado."""


def _cadastro(cfg) -> dict:
    """{"fichas": {pessoa_id: {"nome", "cargo", "vinculo", "ativa"}}, "codigos": {pessoa_id: código}} do cadastro de
    pessoas do banco, decifrado uma vez. Sem a chave do cadastro, os nomes pelo número (e só os códigos de Pessoas e
    setores, que não dependem dela)."""
    from ..campo import visao
    from ..pcm import responsaveis as RP
    try:
        linhas = visao._livro("cadastro_nexus", "pessoas")
    except Exception as ex:      # noqa: BLE001 — banco fora, ou o teste sem banco
        raise SemCadastro(type(ex).__name__) from ex
    chave = cfg.get("NEXUS_CHAVE_CADASTRO")
    cofre = None
    if chave:
        from ..cadastro.cifra import Cofre
        cofre = Cofre(chave)
    fichas = {}
    for p in linhas:
        pid = D._id(p.get("pessoa_id"))
        if not pid:
            continue
        nome = ""
        if cofre and p.get("sensivel_cifrado"):
            try:
                s = json.loads(cofre.decifrar(p["sensivel_cifrado"], f"banco/pessoas/{pid}"))
                nome = visao.nome_curto(s.get("nome_padrao") or s.get("nome"))
            except Exception:    # noqa: BLE001 — cifra de outra chave: pelo número
                pass
        fora = D._txt(p.get("excluido")).lower() == "sim" or D._txt(p.get("status")).lower() == "desligado"
        fichas[pid] = {"pessoa_id": pid, "nome": nome or f"Pessoa {pid}", "cargo": D._txt(p.get("cargo")),
                       "vinculo": D._txt(p.get("vinculo")), "ativa": not fora}
    return {"fichas": fichas, "codigos": RP.codigos(cfg, SimpleNamespace(pessoas=linhas))}


def _emails_conhecidos(cfg) -> dict:
    """{código: e-mail} dos administradores do Nexus e de quem entrou em 30 dias: quem decide aqui é administrador, e o
    do escritório não tem ficha no cadastro (o e-mail só aparece nesta tela, que já é de administrador)."""
    from ..campo.ligacao_cadastro import codigo_da_pessoa
    from . import acessos as AC
    from . import admins_do_servidor
    chave = cfg.get("NEXUS_PESSOA_HMAC")
    if not chave:
        return {}
    emails = set(admins_do_servidor())
    try:
        emails |= {a["email"] for a in AC.estado(cfg)["admins"]} | {x["email"] for x in AC.logins_recentes(cfg)}
    except Exception:            # noqa: BLE001 — a lista da tela fora não tira a aba do ar
        pass
    emails.discard(AC.SENHA_DE_ADMIN)
    return {c: e for e in sorted(emails) if (c := codigo_da_pessoa(chave, e))}


def _dm(d) -> str:
    return f"{str(d)[6:8]}/{str(d)[4:6]}/{str(d)[:4]}" if d else ""


def _sem_acento(s) -> str:
    """Sem acento, sem caixa, espaço único: o que a busca da página compara (o JavaScript tira o acento do digitado)."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def contexto(cfg) -> dict:
    """O que a aba mostra: os administradores do App que valem hoje, as fichas para escolher, o histórico e os avisos.
    Tudo com o prefixo `app_` (a página de Acessos é uma só, com as três abas)."""
    from .acessos import hora_br
    est = AA.ler(cfg)
    hoje = A.hoje_id()
    erro_cadastro = ""
    try:
        cad = _cadastro(cfg)
    except SemCadastro as ex:
        cad, erro_cadastro = {"fichas": {}, "codigos": {}}, str(ex) or "erro"
    fichas, codigos = cad["fichas"], cad["codigos"]
    por_codigo = {c: pid for pid, c in codigos.items()}
    emails = _emails_conhecidos(cfg)

    def nome(pid):
        return (fichas.get(pid) or {}).get("nome") or (f"Pessoa {pid}" if pid else "")

    def quem(h):
        if not h:
            return "administrador (senha)"
        if h in por_codigo:
            return nome(por_codigo[h])
        return emails.get(h) or "alguém fora do cadastro"

    atuais = AA.atuais(est, hoje)
    vigentes = []
    for (codigo, _papel), x in atuais.items():
        pid = A._int_ou_none(x.get("pessoa_id"))
        vigentes.append({"pessoa_id": pid, "nome": nome(pid), "pessoa_hmac": codigo, "status": x["status"],
                         "desde": hora_br(x.get("decidida_em")), "de": _dm(A._int_ou_none(x.get("de_data_id"))),
                         "ate": _dm(A._int_ou_none(x.get("ate_data_id"))), "quem": quem(D._txt(x.get("decidida_por_hmac"))),
                         # o e-mail da ficha mudou depois: o App acha a pessoa pelo código de antes, e pode não achar mais
                         "codigo_mudou": bool(codigos.get(pid)) and codigos.get(pid) != codigo})
    vigentes.sort(key=lambda v: (v["nome"].lower(), v["pessoa_hmac"]))
    ja = {c for c, _p in atuais}
    escolher = []
    for pid, f in fichas.items():
        if not f["ativa"] or (codigos.get(pid) and codigos[pid] in ja):
            continue
        escolher.append(dict(f, tem_codigo=bool(codigos.get(pid)),
                             busca=_sem_acento(" ".join((f["nome"], f["cargo"], f["vinculo"])))))
    escolher.sort(key=lambda f: (f["nome"].lower(), f["pessoa_id"]))
    historico = [dict(h, nome=nome(h["pessoa_id"]), quem=quem(h["quem_hmac"]), quando_br=hora_br(h["quando"]),
                      de=_dm(h["de"]), ate=_dm(h["ate"]))
                 for h in AA.historico(cfg, est)]
    tem_hmac = bool(str(cfg.get("NEXUS_PESSOA_HMAC") or "").strip())
    grava = bool(A._arquivo_local(cfg) or cfg.get("GRIDCO_SQL_TOKEN"))
    pode = tem_hmac and grava and not est.get("erro")
    return {"app_vigentes": vigentes, "app_escolher": escolher, "app_historico": historico,
            "app_erro": est.get("erro") or "", "app_velha": bool(est.get("velha")), "app_erro_cadastro": erro_cadastro,
            "app_sem_hmac": not tem_hmac, "app_sem_token": not grava,
            "app_sem_chave": not cfg.get("NEXUS_CHAVE_CADASTRO"),
            "app_pode_tirar": pode, "app_pode_por": pode and not erro_cadastro,
            "app_sem_codigo": sum(1 for f in escolher if not f["tem_codigo"])}


def por(cfg, pessoa_id, obs, usuario) -> str:
    """Põe a pessoa (uma ficha ativa) nos administradores do App. O texto do aviso, ou `AA.Recusada`."""
    if not str(cfg.get("NEXUS_PESSOA_HMAC") or "").strip():
        raise AA.Recusada(SEM_HMAC)
    pid = D._id(pessoa_id)
    try:
        cad = _cadastro(cfg)
    except SemCadastro as ex:
        raise AA.Recusada(f"Não consegui ler o cadastro de pessoas no banco ({ex}): nada foi gravado.") from ex
    f = cad["fichas"].get(pid)
    if not f or not f["ativa"]:
        raise AA.Recusada("Essa pessoa não está entre as fichas ativas do cadastro (desligada ou excluída): atualize a "
                          "página. Nada foi gravado.")
    codigo = cad["codigos"].get(pid)
    if not codigo:
        raise AA.Recusada(f"{f['nome']}: {AA.SEM_CODIGO}.")
    r = AA.decidir(cfg, pessoa_id=pid, pessoa_hmac=codigo, ativo=True, usuario=usuario, obs=obs or "")
    if not r["gravou"]:
        return f"Nada mudou: {f['nome']} já é administrador do App de Campo."
    return f"{f['nome']} agora é administrador do App de Campo. O App lê a lista de 5 em 5 minutos."


def tirar(cfg, pessoa_hmac, usuario) -> str:
    """Tira dos administradores do App quem vale hoje com este código (o da linha que pôs: é por ele que o App acha)."""
    if not str(cfg.get("NEXUS_PESSOA_HMAC") or "").strip():
        raise AA.Recusada(SEM_HMAC)
    est = AA.ler(cfg, forcar=True)
    if est.get("erro"):
        raise AA.Recusada(f"Não consegui ler os administradores do App no banco ({est['erro'][:80]}): nada foi gravado.")
    codigo = D._txt(pessoa_hmac)
    x = AA.atuais(est, A.hoje_id()).get((codigo, "admin")) if codigo else None
    if not x:
        raise AA.Recusada("Essa pessoa já não é administradora do App de Campo (alguém mudou agora): atualize a página.")
    pid = A._int_ou_none(x.get("pessoa_id"))
    AA.decidir(cfg, pessoa_id=pid, pessoa_hmac=codigo, ativo=False, usuario=usuario)
    try:
        nome = (_cadastro(cfg)["fichas"].get(pid) or {}).get("nome") or f"Pessoa {pid}"
    except SemCadastro:
        nome = f"Pessoa {pid}"
    return f"{nome} deixou de ser administrador do App de Campo. O App lê a lista de 5 em 5 minutos."
