"""A decisão da PT tomada no Nexus, gravada no banco (Levi, 05/10/2026: "Técnico faz APR e PT -> Chega no PG -> Atualiza
para os stakeholders -> Atualiza na aprovação de PT -> Supervisor faz -> Fica salvo!").

Quem assina entra com o login do Fracttal do OS Creator (Levi: "utilize o login do fractal do OS Creator Web que já dá
certo"): a sessão dele (cookie `os_sessao`, só em /os) traz o e-mail de quem entrou. Por isso as rotas que leem quem
assina moram em /os/_nexus/... (`nexus/torres/campo/assinatura.py`).

O livro `nexus_pt_decisoes` · `fato_decisao_pt` (grão: 1 linha = 1 decisão tomada no Nexus sobre UMA LINHA da PT, a
PT × ativo do `pt_app_campo`). A PT vai pelo número e a linha pelo `codigo_ativo`, o Código do ativo daquela linha no
livro do App (vazio na PT sem ativo, como a da APR do dia): o App decide POR LINHA, e a decisão gravada só pelo número
pegava a 1ª linha, que numa PT de 3 ativos não dizia a qual valia (auditoria de 08/10/2026, GR-4). Decisão 4 do Levi
(11/10/2026, registrada no catálogo): a aba é `fato_decisao_pt` (até ali `decisoes`, que nunca foi gravada e não é mais
lida) com as colunas de antes e o `codigo_ativo` no fim. É o contrato que o App lê. A API do banco tem LEITURA ABERTA:
a pessoa vai só como o código do e-mail (`decidida_por_hmac`, `NEXUS_PESSOA_HMAC`, o mesmo do App), nunca nome nem
e-mail; o motivo (o que o técnico lê quando a PT é negada) vai mascarado e curto.

Quem aplica a decisão no campo é o App (a v257, pronta; o deploy é do Levi): de 2 em 2 minutos ele lê este livro e
aplica como o painel dele (o mesmo status, a validade de 7 dias e o efeito no Fracttal: o PDF anexado no De acordo, a
pausa no Não autorizo). O que ele confere, e por isso o Nexus confere ANTES de gravar (decisão que o App descarta fica
gravada aqui, com a linha travada e o técnico esperando): (1) vale a 1ª decisão de cada linha, a mais antiga do livro
para a mesma PT × ativo, e as outras nunca são aplicadas (aqui: o primeiro que decide a linha vale); (2) a linha é
achada pela PT e pelo `codigo_ativo` e tem de ser uma só (aqui: `_linha`); (3) quem pediu a PT não a decide (aqui:
`pode_decidir`); (4) decisão com mais de 7 dias não é aplicada. QUEM pode decidir o App NÃO confere (não tem os papéis
da estrutura de O&M): a única trava é o `pode_decidir` daqui. Até a v257 entrar no ar, a decisão fica salva aqui e o
técnico continua esperando a decisão pelo App.

QUEM PODE DECIDIR (Levi, 09/10/2026: "A pessoa que pode aprovar a PT é: Supervisor de Campo, Gestor de contrato, admin
ou pessoa do COS"): o Supervisor de Campo da região da usina (com a vaga aberta, o Coordenador de Campo), o gestor de
contrato da usina, quem tem o vínculo COS no cadastro de pessoas e um administrador do Nexus (`aprovadores`,
`pode_decidir`). Quem assina é a pessoa do login do Fracttal, achada no cadastro pelo e-mail ou pelo nome de UMA pessoa
(`_Base.pessoa_do_login`); sem a chave do cadastro, só o administrador decide. Quem PEDIU a PT nunca a decide, nem sendo
administrador: é a regra do painel do App desde a 1ª PT real (28/09/2026, aprovada pelo próprio técnico, que também era
administrador), e a v257 descarta calada a decisão de quem pediu.
"""
import re
import threading
from datetime import datetime, timedelta, timezone

from flask import current_app

from ..cadastro.esquema import VINCULO_COS
from ..dados import fatos as D
from ..dados import livros
from . import visao
from .ligacao_cadastro import codigo_da_pessoa

LIVRO, NOME_LIVRO, ABA = "nexus_pt_decisoes", "Nexus · decisões de PT", "fato_decisao_pt"
# As colunas de 05/10/2026 e o `codigo_ativo` NO FIM (decisão 4, 11/10/2026): coluna nova entra depois das que existem,
# para quem lê por posição não se perder.
CAB = ("decidida_em", "data_id", "pt", "os", "usina_id", "decisao", "motivo", "decidida_por_hmac", "login", "origem",
       "codigo_ativo", "assinatura")
# `assinatura` (11/10/2026, prova do contrato com o App v257): sem ela o App não aplica a decisão — o livro é lido por GET
# público, e só a chave da pessoa (NEXUS_PESSOA_HMAC, a mesma do App) prova que a linha saiu do Nexus. Na prova, as duas
# decisões gravadas aqui voltaram do App como "nao_assinadas", e o técnico ficaria esperando para sempre.
DECISOES = {"de_acordo": "De acordo", "negada": "Não autorizo"}
MOTIVO_MAX = 400
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()      # um processo grava por vez: duas decisões juntas não se apagam (o livro é trocado inteiro)


class Recusada(ValueError):
    """A decisão não pode ser gravada: o texto diz por quê, para a tela mostrar."""


def mascarar(texto) -> str:
    """Tira do motivo o que é dado pessoal (e-mail, telefone, CPF): o livro é de leitura aberta."""
    s = " ".join(str(texto or "").split())
    s = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "[e-mail]", s)
    s = re.sub(r"\d[\d .()/-]{7,}\d", "[número]", s)
    return s[:MOTIVO_MAX]


def aprovadores(p: dict, b=None) -> dict:
    """Quem pode dar o De acordo nesta PT: {"ids": {papel: pessoa_id}, "cos": {pessoa_id}, "texto"}. O texto é o que a
    tela e a recusa dizem ("Supervisor de Campo da Sudeste 03 (Fulana), gestor de contrato Beltrano, alguém do COS ou
    um administrador")."""
    b = b or visao._Base()
    uid = D._id(p.get("usina_id"))
    rid = b.regiao_da_usina(uid) if uid else None
    r = b.regiao.get(rid) or {}
    u = b.por_id.get(uid) or {}
    ids = {"supervisor de campo": r.get("supervisor_id"),
           "coordenador de campo": None if r.get("supervisor_id") else r.get("coordenador_id"),
           "gestor de contrato": D._id(u.get("gestor_contrato_id"))}
    cos = {D._id(x.get("pessoa_id")) for x in b.pessoas
           if str(x.get("vinculo") or "").strip() == VINCULO_COS and str(x.get("excluido") or "").lower() != "sim"}
    partes = []
    if r:
        sup = b.nome_da_pessoa(r.get("supervisor_id"), "Supervisor") if r.get("supervisor_id") else ""
        coord = b.nome_da_pessoa(r.get("coordenador_id"), "Coordenador") if r.get("coordenador_id") else ""
        partes.append(f"o Supervisor de Campo da {r['nome']} ({sup})" if sup else
                      (f"o Coordenador de Campo da {r['nome']} ({coord}), com a vaga de supervisor aberta" if coord
                       else f"o Supervisor de Campo da {r['nome']} (vaga)"))
    if ids["gestor de contrato"]:
        partes.append(f"o gestor de contrato ({b.nome_da_pessoa(ids['gestor de contrato'], 'Gestor')})")
    partes.append("alguém do COS" if cos else "alguém do COS (ninguém com o vínculo COS no cadastro ainda)")
    partes.append("um administrador")
    texto = ", ".join(partes[:-1]) + " ou " + partes[-1]
    return {"ids": {k: v for k, v in ids.items() if v}, "cos": cos, "texto": texto[0].upper() + texto[1:]}


QUEM_PEDIU = ("Quem pediu a PT não a decide: o De acordo ou o Não autorizo precisa ser de outra pessoa que pode "
              "assinar.")


def pode_decidir(p: dict, email: str, nome: str = "", admin: bool = False, b=None) -> tuple[bool, str]:
    """(pode, papel ou o porquê não). Quem pediu a PT nunca a decide, nem sendo administrador; fora isso, o
    administrador do Nexus sempre pode.

    Quem pediu = o código do e-mail de quem assina igual ao `solicitante_hmac` da linha (o `Solicitante (HMAC)` do
    pt_app_campo, o mesmo código que o App compara na regra 3). Revisão adversarial de 11/10/2026: o Nexus gravava a
    decisão de quem pediu e dizia "salva"; o App a descartaria calado e, como só a 1ª decisão de cada linha vale, a do
    gestor de contrato depois era recusada aqui ("já tem decisão") e nunca chegaria ao campo: a linha ficava travada e o
    técnico, esperando."""
    sol = D._txt(p.get("solicitante_hmac")).lower()
    if sol and sol == (codigo_da_pessoa(current_app.config.get("NEXUS_PESSOA_HMAC"), email) or ""):
        return False, QUEM_PEDIU
    # também pela pessoa do cadastro (README da v257): quem tem um e-mail no Microsoft e outro no Fracttal passava pelo
    # HMAC acima e decidia a própria PT
    b = b or visao._Base()
    pid = b.pessoa_do_login(email, nome)
    if pid and p.get("solicitante_pessoa_id") and pid == p.get("solicitante_pessoa_id"):
        return False, QUEM_PEDIU
    if admin:
        return True, "administrador"
    a = aprovadores(p, b)
    papel = next((k for k, v in a["ids"].items() if pid and v == pid), None) or ("COS" if pid and pid in a["cos"] else None)
    if papel:
        return True, papel
    return False, f"Quem pode dar o De acordo nesta PT: {a['texto'][0].lower()}{a['texto'][1:]}."


def assinatura(linha: dict, chave: str) -> str:
    """HMAC-SHA256 em hex minúsculo, com a NEXUS_PESSOA_HMAC, do texto
    "decisao_pt|pt|codigo_ativo|os|decisao|decidida_em|decidida_por_hmac|motivo" — a MESMA conta do App
    (`_nexus_pt_assinatura` no function_app.py da v257; mudou lá, muda aqui no mesmo trabalho). Código do ativo vazio
    vira ""; o motivo entra como gravado (já mascarado), com os espaços normalizados como o App lê. Sem chave: ""."""
    import hashlib
    import hmac
    chave = (chave or "").strip()
    if not chave:
        return ""
    txt = "|".join(("decisao_pt", D._txt(linha.get("pt")), D._txt(linha.get("codigo_ativo")), D._txt(linha.get("os")),
                    D._txt(linha.get("decisao")), D._txt(linha.get("decidida_em")),
                    D._txt(linha.get("decidida_por_hmac")), " ".join(D._txt(linha.get("motivo")).split())))
    return hmac.new(chave.encode("utf-8"), txt.encode("utf-8"), hashlib.sha256).hexdigest()


def recusada_pelo_app(p: dict, decididas: list) -> bool:
    """O App recusou a decisão do Nexus nesta linha e nenhuma decisão daqui é mais nova que a recusa: a linha se decide de
    novo. O App escreve no pt_app_campo "Decisão do Nexus" = "recusada", a hora da decisão a que respondeu ("Decisão do
    Nexus em") e o porquê ("Motivo da recusa"; v257, 11/10/2026). Sem isso, a linha que o App recusou (por exemplo, a
    decisão com mais de 7 dias) ficava travada aqui ("já tem decisão") e só o painel do App a decidia."""
    em = D._txt(p.get("nexus_app_em"))
    return (D._txt(p.get("nexus_app")).lower() == "recusada" and bool(em)
            and all(D._txt(d.get("decidida_em")) <= em for d in decididas))


def decisoes() -> list[dict]:
    """As decisões já gravadas pelo Nexus (sem cópia: quem decide precisa ver a última). Só a aba `fato_decisao_pt`: a
    `decisoes` de antes da decisão 4 (11/10/2026) nunca foi gravada, e linha que aparecer nela não vale."""
    return livros.ler(visao._base(), visao._sessao(), LIVRO, ABA)


def _da_linha(d: dict, numero: str, codigo) -> bool:
    """A decisão `d` é desta PT (pelo número) e, com `codigo`, desta linha (pelo código do ativo; "" = a linha sem
    ativo). Sem `codigo`, de qualquer linha da PT."""
    return D._txt(d.get("pt")) == numero and (codigo is None or D._txt(d.get("codigo_ativo")) == D._txt(codigo))


def da_pt(numero, codigo=None) -> dict | None:
    """A decisão mais recente do Nexus sobre a linha da PT (`codigo`: o código do ativo da linha) ou, sem ele, sobre
    qualquer linha dela."""
    n = D._txt(numero)
    return next((d for d in reversed(decisoes()) if _da_linha(d, n, codigo)), None)


def _linha(numero, codigo) -> tuple[dict, int]:
    """(a linha da PT que se decide, quantas linhas a PT tem), do livro do App lido agora. `codigo` = o que o
    formulário mandou (o código do ativo da linha; None = o formulário não disse). Sem a linha, só a PT de uma linha
    se decide: numa de mais, pegar a 1ª seria chutar a qual ativo a decisão vale (regra 4 da governança, GR-4)."""
    linhas = visao.pt_linhas(numero)
    if not linhas:
        raise Recusada(f"{numero} não está no livro do App.")
    if codigo is None:
        if len(linhas) > 1:
            raise Recusada(f"{numero} tem {len(linhas)} equipamentos, e cada um tem a sua decisão: decida pela linha "
                           "do equipamento.")
        return linhas[0], 1
    p = next((x for x in linhas if D._txt(x.get("codigo")) == D._txt(codigo)), None)
    if not p:
        raise Recusada(f"{numero} não tem o equipamento {D._txt(codigo) or '(sem equipamento)'} no livro do App.")
    return p, len(linhas)


def decidir(numero, decisao: str, motivo: str, email: str, nome: str = "", admin: bool = False,
            codigo=None) -> dict:
    """Grava a decisão sobre UMA linha da PT (`codigo`: o código do ativo dela; ver `_linha`) e confere no banco.
    Recusa: decisão inválida, negar sem motivo, quem não pode decidir esta PT (`pode_decidir`, quem a pediu inclusive),
    PT ou linha que não existe, que já não está aguardando no livro do App ou que já tem decisão do Nexus (o primeiro que
    decide vale, como no App). O que o App descartaria e já se sabe na hora (a linha, quem pediu, a 1ª decisão) é
    recusado aqui, antes de gravar; os 7 dias e o painel que decide no meio, só o App vê (ver o topo)."""
    cfg = current_app.config
    if decisao not in DECISOES:
        raise Recusada("A decisão precisa ser De acordo ou Não autorizo.")
    motivo = mascarar(motivo)
    if decisao == "negada" and len(motivo) < 3:
        raise Recusada("Escreva o motivo: é o que o técnico lê quando a PT não é autorizada.")
    quem = codigo_da_pessoa(cfg.get("NEXUS_PESSOA_HMAC"), email)
    if not quem:
        raise Recusada("Não sei quem está assinando: entre com o seu login do Fracttal.")
    if not cfg.get("GRIDCO_SQL_TOKEN"):
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN).")
    with _TRAVA:
        # decide sobre o livro do App lido agora, não a cópia de 5 min: saem da memória só a conta das PT e os livros
        # dela (até 19/10/2026 era o `visao.limpar()`, que zerava TODAS as telas do Campo a cada decisão e as fazia
        # voltar do zero juntas: o Nexus travou às 15:04 com duas Visões do responsável lendo o banco ao mesmo tempo)
        visao.esquecer_pt()
        p, n_linhas = _linha(numero, codigo)
        cod = D._txt(p.get("codigo"))
        # na PT de mais de um equipamento, a recusa diz de qual linha se fala
        qual = f"{numero} ({cod or 'sem equipamento'})" if n_linhas > 1 else str(numero)
        if p["situacao"] != "aguardando":
            raise Recusada(f"{qual} já foi decidida no App ({p['situacao']}).")
        pode, porque = pode_decidir(p, email, nome, admin)
        if not pode:
            raise Recusada(porque)
        linhas = decisoes()
        ja = [d for d in linhas if _da_linha(d, p["numero"], cod)]
        if ja and not recusada_pelo_app(p, ja):
            raise Recusada(f"{qual} já tem decisão gravada pelo Nexus.")
        agora = datetime.now(timezone.utc)
        nova = {"decidida_em": agora.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "data_id": int(agora.astimezone(_BRT).strftime("%Y%m%d")), "pt": p["numero"], "os": str(p["os"] or ""),
                "usina_id": p["usina_id"], "decisao": decisao, "motivo": motivo, "decidida_por_hmac": quem,
                "login": "Fracttal (OS Creator)", "origem": "Nexus", "codigo_ativo": cod or None}
        nova["assinatura"] = assinatura(nova, cfg.get("NEXUS_PESSOA_HMAC"))
        linhas = [[d.get(c) for c in CAB] for d in linhas] + [[nova[c] for c in CAB]]
        livros.publicar(LIVRO, NOME_LIVRO, {ABA: (list(CAB), linhas)}, base=visao._base(),
                        token=cfg["GRIDCO_SQL_TOKEN"], sessao=visao._sessao())
    return nova
