"""O Responsável UFV de cada usina no livro de técnicos por usina (30/10/2026, a fase 3 do `atribuicoes`).

Levi, 30/10/2026: "PT aguardando assinatura você manda para os responsáveis das UFVs do Nexus" e, perguntado, o
Responsável UFV do Nexus também passa a ser quem pode assinar a PT da usina. O App de Campo lê o livro
`nexus_pcm_atribuicoes` (o papel `executa`, desde a v283) e não tinha como saber o responsável: a ficha da usina
(`responsavel_om_id`, o mesmo da Visão do responsável e do e-mail semanal da Segurança) não sai do Nexus com o nome da
usina no Fracttal nem com o código da pessoa. Aqui o Nexus põe no livro, no papel `responsavel`, o Responsável O&M da
ficha de cada usina, pelo mesmo caminho das decisões do PCM (assinado, só acrescenta), com a origem `cadastro`:

- **quem:** o `responsavel_om_id` da ficha das usinas não excluídas que têm nome no Fracttal (o 1º do de-para, o que o
  App lê), com o código do e-mail da pessoa (`codigo_da_pessoa`): o da pessoa ligada ao usuário do Fracttal (Base →
  Acessos → Pessoas e setores) e, sem ele, o do e-mail da ficha. É a mesma conta do e-mail semanal da Segurança
  (`hseq/email_semanal.destinatarios`), que casou os 6 códigos da W44 no App;
- **o que muda no livro:** o responsável que vale hoje e não é mais o da ficha sai (a ficha trocou de responsável ou
  ficou sem); o da ficha entra. O `_linha` não grava a decisão que não mudou, então a volta sem mudança não grava nada,
  e a usina que mudou de nome no Fracttal (ou a pessoa com o e-mail corrigido) vai de novo. Não precisa tirar a linha
  velha: o App conta a última de cada usina × pessoa × papel, como o `atuais` daqui;
- **o que não se faz no escuro:** sem o código do e-mail, ou sem o nome no Fracttal, o responsável da ficha não entra;
  se é a mesma pessoa que já está no livro, ela FICA (sair seria tirar a assinatura da PT por uma leitura ruim), e
  quem a ficha trocou sai mesmo assim (a ficha manda; nessa usina o App volta à regra de antes). O cadastro que não
  se leu, ou lido sem nenhum responsável, não grava nada (tiraria todos);
- **quando:** a cada hora, a 1ª volta 3 min depois de subir, num minuto sorteado por máquina; NEXUS_RESPONSAVEIS=0
  desliga numa máquina. Duas máquinas não gravam diferente: a que chega depois relê o livro antes de gravar e não acha o
  que mudar.

Os leitores do livro dentro do Nexus (a tela Técnicos por usina, a Visão do responsável, os Extintores) contam só o
`executa` (`atribuicoes.atuais` filtra pelo papel desde esta fase); o App conta o `responsavel` à parte desde a v314.
"""
import logging
import random
import threading
from datetime import datetime, timedelta, timezone

from ..dados import fatos as D
from . import atribuicoes as A

log = logging.getLogger(__name__)

PAPEL, ORIGEM = "responsavel", "cadastro"
PRIMEIRA_S = 180
INTERVALO_S = 3600
_BRT = timezone(timedelta(hours=-3))
_LACO = {"thread": None, "parar": threading.Event(), "ultimo": None, "quando": None}


def codigos(cfg, base) -> dict:
    """{pessoa_id: o código do e-mail} pela conta do e-mail semanal da Segurança: o do e-mail da ficha (único no
    cadastro) e, por cima, o da pessoa ligada ao usuário do Fracttal (Pessoas e setores)."""
    from ..campo import visao
    from ..campo.ligacao_cadastro import mapas_de
    out = {}
    for c, pid in mapas_de(cfg, [], base.pessoas)["hmac"].items():
        out.setdefault(pid, c)
    try:
        from ..cadastro import setores as S
        st = S.ler(visao._base(), visao._sessao())
        for d in sorted(st.get("decisoes") or [], key=lambda x: x["decidida_em"]):
            if d.get("pessoa_id") and d.get("pessoa_hmac"):
                out[d["pessoa_id"]] = d["pessoa_hmac"]
    except Exception as e:      # noqa: BLE001 — sem os setores, vale o código do e-mail da ficha
        log.info("responsáveis: sem os setores (%s); vale o código do e-mail da ficha", type(e).__name__)
    return out


def pedidos(base, codigo_da: dict, est: dict, hoje: int) -> tuple[list[dict], dict]:
    """(os pedidos para o `decidir_varias`, a conta). Tirar só o responsável que vale hoje e não é mais o da ficha."""
    from . import tecnicos_usina as TU
    fr = TU._fracttal(base)
    conta = {"usinas": 0, "com_responsavel": 0, "sem_fracttal": 0, "sem_codigo": 0, "por": 0, "tirar": 0}
    da_ficha, quer = {}, {}
    for uid, u in sorted(TU._usinas(base, todas=True).items()):
        conta["usinas"] += 1
        pid = D._id(u.get("responsavel_om_id"))
        if not pid:
            continue
        conta["com_responsavel"] += 1
        da_ficha[uid] = pid
        nome = (fr.get(uid) or [""])[0]
        cod = D._txt(codigo_da.get(pid))
        if not nome:
            conta["sem_fracttal"] += 1
        elif not cod:
            conta["sem_codigo"] += 1
        else:
            quer[uid] = (pid, nome, cod)
    out = []
    for (uid, pid, _papel), x in sorted(A.atuais(est, hoje, papel=PAPEL).items()):
        if da_ficha.get(uid) != pid:
            out.append({"usina_id": uid, "usina_fracttal": D._txt(x.get("usina_fracttal")), "pessoa_id": pid,
                        "pessoa_hmac": D._txt(x.get("pessoa_hmac")), "na_usina": False, "papel": PAPEL})
            conta["tirar"] += 1
    for uid, (pid, nome, cod) in sorted(quer.items()):
        out.append({"usina_id": uid, "usina_fracttal": nome, "pessoa_id": pid, "pessoa_hmac": cod, "na_usina": True,
                    "papel": PAPEL})
        conta["por"] += 1
    return out, conta


def sincronizar(cfg, *, base=None, codigo_da: dict | None = None) -> dict:
    """Uma volta: põe no livro o responsável da ficha de cada usina. Devolve a conta (`gravadas` = linhas novas)."""
    if not str(cfg.get("NEXUS_PESSOA_HMAC") or "").strip():
        return {"recusou": "sem a NEXUS_PESSOA_HMAC a linha iria sem assinatura e o App não a usaria"}
    if base is None:
        from . import tecnicos_usina as TU
        try:
            base = TU.ler_base()
        except TU.SemCadastro as e:
            return {"recusou": f"não li o cadastro ({e}): nada gravado"}
    if codigo_da is None:
        if not cfg.get("NEXUS_CHAVE_CADASTRO"):
            return {"recusou": "sem a NEXUS_CHAVE_CADASTRO não há como ler o e-mail da ficha (o código da pessoa)"}
        codigo_da = codigos(cfg, base)
    est = A.ler(cfg, forcar=True)
    if est.get("erro"):
        return {"recusou": f"não li os técnicos por usina ({est['erro']}): nada gravado"}
    ped, conta = pedidos(base, codigo_da, est, A.hoje_id())
    if not conta["com_responsavel"]:
        return dict(conta, recusou="o cadastro veio sem nenhum responsável: gravar tiraria todos; nada gravado")
    conta["gravadas"] = A.decidir_varias(cfg, ped, None, ORIGEM) if ped else 0
    return conta


def ligar(app):
    """O laço de hora em hora. Quem chama é o `campo.instalar` (app.py e servir.py), nunca o create_app: teste não fala
    com a rede."""
    if _LACO["thread"] is not None or str(app.config.get("NEXUS_RESPONSAVEIS", "1")).strip() == "0":
        return
    desencontro = random.randint(0, 600)

    def laco():
        espera = PRIMEIRA_S + desencontro // 10
        while not _LACO["parar"].wait(espera):
            espera = INTERVALO_S + random.randint(-120, 120)
            with app.app_context():
                try:
                    _LACO["ultimo"] = sincronizar(app.config)
                    log.info("responsáveis das usinas no livro: %s", _LACO["ultimo"])
                except Exception as e:      # noqa: BLE001 — o laço não morre por uma volta
                    _LACO["ultimo"] = {"erro": f"{type(e).__name__}: {e}"[:300]}
                    log.exception("responsáveis das usinas no livro")
                _LACO["quando"] = datetime.now(_BRT).isoformat(timespec="minutes")

    _LACO["thread"] = threading.Thread(target=laco, name="nexus-responsaveis-usina", daemon=True)
    _LACO["thread"].start()
