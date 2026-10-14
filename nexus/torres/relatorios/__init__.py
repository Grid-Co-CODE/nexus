"""Torre Relatórios: Emissão dos relatórios diários, semanais e mensais.

A Central de emissão (13/10/2026). Levi: "Criador de relatório e relatório semanal vai para a central de emissão no Nexus >
Relatórios. Ficará filtrado no setor da pessoa, caso a pessoa seja administradora aparece todos os relatórios. Aí a pessoa
escolhe que tipo de relatório ela quer! Sai da parte de Performance!"

- Cada relatório é uma tela desta torre que se abre POR DENTRO da Central (`Tela.dentro_de`): sem item próprio no menu,
  ele acende a Central quando está aberto. Os da Plataforma de Performance abrem na moldura, pelo mapa da porta única
  (`nexus/performance/porta.py`, torre "relatorios"; as views saem de `registrar_molduras`).
- O filtro do setor: cada relatório é DO setor dono (`Tela.do_setor`; os três de hoje são da Performance, Levi,
  13/10/2026: "Potência ativa faz parte da performance!" e "Esses dois são do setor performance"), e quem é do setor o
  vê sem marcar; outro setor vê o que for marcado para ele em Base → Acessos (`auth/setor_telas.py`); o administrador vê
  todos. Quem tem um relatório vê a Central (a tela de fora) sem marcá-la. As marcas de antes, quando os relatórios eram
  da Performance (`performance/relatorio`...), valem para os daqui (`setor_telas.RENOMEADAS`).
- Relatório novo: uma `Tela(..., dentro_de="central", do_setor="<setor dono>")` aqui e o ícone em RELATORIOS.
- O Relatório executivo do PCM (14/10/2026: Interno Grid, Cliente, Abertura da Semana) é a CÓPIA do JavaScript do painel
  do PCM numa moldura (`nexus/pcm/relatorio_exec`), também do setor PCM.
- O setor dono escolhido na tela (14/10/2026, Levi: "adicione a opção de eu escolher de qual setor é o relatório! Apenas
  administradores podem editar!"): a seção "Setor de cada relatório", embaixo das colunas, só para administrador. A
  escolha vale por cima do `do_setor` do código (`auth/dono_relatorio.py`, `setor_telas.das_do_setor`).
- Os quatro do PCM (14/10/2026, Levi: "Quero trazer esses quatro relatórios para a plataforma, com as mesmas métricas e
  parâmetros e estilos"): Relatório diário de manutenção, Recuperação da tarde, Fechamento da semana e Alerta da
  programação, do setor PCM, NATIVOS do Nexus (não da plataforma): as telas e a folha em `nexus/pcm/relatorios`
  (`telas.registrar`), com a emissão automática nos horários do PCM (`agenda.py`).
- UMA estrutura para todas as telas da Central (14/10/2026, Levi: "Use a mesma estrutura do print 1 para todos os
  relatórios de todos os setores e aí vai ficar filtrado por setor"; o print 1 era a tela do Relatório diário): à
  esquerda, os BLOCOS (`BLOCOS`, montados por `lado`), só com o que a pessoa pode ver, e embaixo deles o período e o
  recorte do relatório aberto; à direita, a folha ou a tela. Para o PCM, "Relatórios Padrão PCM" (os quatro) e, abaixo,
  "Relatório Gerencial PCM" (os três tipos do Relatório executivo). Relatório novo entra num bloco (o teste reprova
  relatório da Central fora de bloco). Os da plataforma vêm na moldura dentro da coluna da direita
  (`relatorios/moldura.html`), com o período e o recorte dentro da própria tela da plataforma.
"""
import hmac

from flask import current_app, redirect, render_template, request, session, url_for

from ...auth import dono_relatorio as DR
from ...auth import setor_telas
from ...cadastro import setores as S
from ...pcm import relatorio_exec
from ...pcm.relatorios import TIPOS as TIPOS_PCM
from ...pcm.relatorios import telas as telas_pcm
from ...performance import porta
from ..modelo import Tela, Torre
from ..moldura import estado_da_porta, registrar_molduras

TORRE = Torre(
    id="relatorios",
    nome="Relatórios",
    ordem=70,
    icone="file-text",
    descricao="Emissão dos relatórios diários, semanais e mensais.",
    telas=[
        Tela("central", "Central de emissão",
             "Que relatório eu preciso emitir, e onde ele está?",
             "os relatórios liberados para o setor de quem entrou (todos, para o administrador)"),
        Tela("relatorio", "Criador de relatório",
             "Como monto o relatório do cliente com os números certos?",
             "Plataforma de Performance", dentro_de="central", do_setor="Performance"),
        Tela("relatorio-semanal", "Relatório semanal",
             "Como foi a semana de cada usina no relatório do cliente?",
             "Plataforma de Performance", dentro_de="central", do_setor="Performance"),
        Tela("potencia-ativa", "Potência Ativa dos Inversores",
             "Como a potência ativa de cada inversor se comportou, dia a dia?",
             "Plataforma de Performance (as leituras das curvas do Tempo real)", dentro_de="central",
             do_setor="Performance"),
        *[Tela(t.tela_id, t.nome, t.pergunta,
               "o robô do PCM: Programação Semanal, Gestão PCM, Gerencial e Confiabilidade", dentro_de="central",
               do_setor="PCM") for t in TIPOS_PCM.values()],
        # o Relatório executivo do painel do PCM, com o nome do bloco que o Levi deu (14/10/2026): "Relatório Gerencial PCM"
        Tela(relatorio_exec.TELA_ID, "Relatório Gerencial PCM",
             "O que rodou, o que travou e onde agir: Interno Grid, Cliente ou Abertura da Semana?",
             "o painel do PCM: Gestão PCM, programação semanal, Confiabilidade e Gerencial", dentro_de="central",
             do_setor="PCM"),
    ],
)

# O ícone (Phosphor) do cartão de cada relatório na Central; a área do cartão é o setor dono (`Tela.do_setor`)
RELATORIOS = {
    "relatorio": "file-text",
    "relatorio-semanal": "calendar-check",
    "potencia-ativa": "chart-line",
    "pcm-diario": "sun-horizon",
    "pcm-tarde": "clock-afternoon",
    "pcm-semanal": "calendar-check",
    "pcm-alerta": "warning",
    "pcm-executivo": "presentation-chart",
}

# Os blocos da coluna da esquerda, na ordem (14/10/2026; Levi, para o PCM: "um bloco lateral ... com o título 'Relatórios
# Padrão PCM' e abaixo terá um bloco 'Relatório Gerencial PCM' onde terá os três tipos de relatório"). Item: a tela, o
# `sub` (o `?tipo=` das telas com mais de um tipo), o nome, a linha de baixo e a marca (a letra do PCM ou um ícone).
# `setor` = o setor do bloco: o item que o administrador passou para outro setor mostra o nome do setor novo.
BLOCOS = (
    {"id": "pcm-padrao", "titulo": "Relatórios Padrão PCM", "setor": "PCM",
     "itens": [{"tela": t.tela_id, "nome": t.nome, "descricao": t.descricao, "letra": t.letra}
               for t in TIPOS_PCM.values()]},
    {"id": "pcm-gerencial", "titulo": "Relatório Gerencial PCM", "setor": "PCM",
     "itens": [{"tela": relatorio_exec.TELA_ID, "sub": k, "nome": v["nome"], "descricao": v["descricao"],
                "icone": v["icone"]} for k, v in relatorio_exec.TIPOS.items()]},
    {"id": "performance", "titulo": "Relatórios Performance", "setor": "Performance",
     "itens": [{"tela": "relatorio", "nome": "Criador de relatório", "icone": RELATORIOS["relatorio"],
                "descricao": "o relatório do cliente, montado com os números da plataforma"},
               {"tela": "relatorio-semanal", "nome": "Relatório semanal", "icone": RELATORIOS["relatorio-semanal"],
                "descricao": "a semana de cada usina, no relatório do cliente"},
               {"tela": "potencia-ativa", "nome": "Potência Ativa dos Inversores", "icone": RELATORIOS["potencia-ativa"],
                "descricao": "a potência ativa de cada inversor, dia a dia"}]},
)

bp = TORRE.criar_blueprint(__name__)


_CHAVE_AVISO = "central_aviso"


def _setores_ativos(forcar: bool = False) -> tuple[list[dict], str]:
    """([{setor_id, nome}] dos setores ativos, erro): para o nome no cartão e a escolha do administrador."""
    try:
        base, sessao = setor_telas._banco()
        st = S.ler(base, sessao, forcar=forcar)
        return S.ativos(st.get("setores") or []), st.get("erro") or ""
    except Exception as ex:      # noqa: BLE001 — sem o endereço do banco, por exemplo
        return [], type(ex).__name__


def _relatorios():
    return [t for t in TORRE.telas if t.dentro_de == "central"]


def lado(atual: str = "", sub: str = "") -> list[dict]:
    """Os blocos da coluna da esquerda com o que quem entrou pode ver (todos, para o administrador), na ordem de
    BLOCOS; bloco sem nada liberado não aparece. `atual` e `sub`: o relatório aberto, que acende. A mesma régua do menu
    (`setor_telas.liberadas_do_menu`): a lista e a porta do setor nunca discordam."""
    liberadas = setor_telas.liberadas_do_menu()
    escolhas = setor_telas.escolhas_de_dono()
    setores, _erro = _setores_ativos()
    blocos = []
    for b in BLOCOS:
        itens = []
        for it in b["itens"]:
            t = TORRE.tela(it["tela"])
            if liberadas is not None and setor_telas.chave(TORRE.id, t.id) not in liberadas:
                continue
            dono = setor_telas.dono_de(TORRE.id, t, escolhas, setores)
            # o setor só aparece no item quando o administrador o tirou do setor do bloco (a escolha da Central)
            fora = dono["escolhido"] and (dono["setor_id"] is None or
                                          setor_telas._sem_acento(dono["nome"]) != setor_telas._sem_acento(b["setor"]))
            itens.append(dict(it, url=f"/t/{TORRE.id}/{t.id}" + (f"?tipo={it['sub']}" if it.get("sub") else ""),
                              on=t.id == atual and it.get("sub", "") == sub,
                              tag=(dono["nome"] or "Nenhum setor") if fora else ""))
        if itens:
            blocos.append(dict(b, itens=itens))
    return blocos


def _moldura_extra(t) -> dict:
    """O que a tela da plataforma na Central leva além da moldura: os blocos da esquerda, com ela acesa."""
    return {"lado": lado(t.tela)}


@bp.route("/central", methods=["GET", "POST"])
def central():
    """Os relatórios que a pessoa pode emitir: os do setor dela (todos, para o administrador), na ordem da torre. O
    administrador vê embaixo a escolha do setor de cada relatório (o POST grava)."""
    if request.method == "POST":
        return _gravar_donos()
    liberadas = setor_telas.liberadas_do_menu()
    molduras = {t.tela for t in porta.da_torre(TORRE.id)}
    escolhas = setor_telas.escolhas_de_dono()
    setores, erro_setores = _setores_ativos()
    cartoes = []
    for t in _relatorios():
        if liberadas is not None and setor_telas.chave(TORRE.id, t.id) not in liberadas:
            continue
        dono = setor_telas.dono_de(TORRE.id, t, escolhas, setores)
        cartoes.append({"tela": t, "url": f"/t/{TORRE.id}/{t.id}", "area": dono["nome"], "dono": dono,
                        "icone": RELATORIOS.get(t.id, "file-text"), "moldura": t.id in molduras})
    estado = estado_da_porta()
    admin = bool(session.get("admin"))
    codigo = ""
    if admin:
        from ...auth.telas_acessos import _codigo
        codigo = _codigo()
    # o aviso da plataforma desligada é só dos relatórios dela (os do PCM são do Nexus e abrem sempre)
    return render_template("relatorios/central.html", torre=TORRE, tela=TORRE.tela("central"), cartoes=cartoes,
                           lado=lado(), todos=liberadas is None, ligada=estado["ligada"], motivo=estado["motivo"],
                           com_moldura=any(c["moldura"] for c in cartoes), admin=admin, setores=setores,
                           erro_setores=erro_setores, codigo=codigo, aviso=session.pop(_CHAVE_AVISO, None),
                           pode_gravar=bool(current_app.config.get("GRIDCO_SQL_TOKEN")) and not erro_setores)


def _voltar(aviso: str, status_erro: bool = False):
    session[_CHAVE_AVISO] = aviso
    return redirect(url_for(".central", _anchor="setor-dos-relatorios"), code=303)


def _gravar_donos():
    """O Salvar da seção "Setor de cada relatório": só administrador, só desta origem e com o código do formulário da
    sessão (o mesmo da tela Acessos). Só o relatório cujo dono mudou ganha linha no banco."""
    if not session.get("admin"):
        return render_template("cadastro/sem_permissao.html", titulo="Central de emissão", eyebrow="Relatórios",
                               area="A escolha do setor de cada relatório", email=""), 403
    from ...auth.telas_acessos import _CHAVE_CODIGO, _de_outro_site, _meu_email
    if _de_outro_site():
        return _voltar("Pedido de outro site: nada foi gravado.")
    certo, enviado = session.get(_CHAVE_CODIGO) or "", request.form.get("codigo") or ""
    if not certo or not hmac.compare_digest(enviado.encode(), certo.encode()):
        return _voltar("O formulário venceu (a sessão mudou desde que a tela abriu): abra a tela de novo. Nada foi "
                       "gravado.")
    setores, erro = _setores_ativos(forcar=True)
    if erro:
        return _voltar(f"Não consegui ler os setores no banco ({erro[:80]}): nada foi gravado.")
    ids = {s["setor_id"] for s in setores}
    try:
        base, sessao = setor_telas._banco()
        lido = DR.ler(base, sessao, forcar=True)
        if lido.get("erro"):
            raise DR.Recusada(f"Não consegui ler os donos dos relatórios no banco ({lido['erro'][:80]}): nada foi "
                              "gravado.")
        vigentes = DR.vigentes(lido["decisoes"])
        atuais, escolhas = {}, {}
        for t in _relatorios():
            k = setor_telas.chave(TORRE.id, t.id)
            atuais[k] = setor_telas.dono_de(TORRE.id, t, vigentes, setores)["setor_id"]
            v = request.form.get(f"dono:{t.id}")
            if v is None:
                continue                         # não veio no formulário: fica como está
            if v == "":
                escolhas[k] = None
            elif v.isdigit() and int(v) in ids:
                escolhas[k] = int(v)
            else:
                raise DR.Recusada("Setor desconhecido ou excluído (a lista mudou desde que a tela abriu): nada foi "
                                  "gravado.")
        r = DR.gravar(escolhas, atuais, current_app.config, base, sessao, _meu_email())
    except DR.Recusada as ex:
        return _voltar(str(ex))
    except Exception as ex:      # noqa: BLE001 — a publicação no banco falhou: nada mudou (o livro é trocado inteiro)
        current_app.logger.error("Setor dos relatórios: a gravação falhou (%s: %s).", type(ex).__name__, ex)
        return _voltar(f"Não consegui gravar no banco ({type(ex).__name__}): nada mudou. Tente de novo; se continuar, "
                       "avise a T.I.")
    n = r["gravadas"]
    return _voltar("Nada mudou: os relatórios já estavam nesses setores." if not n else
                   f"{n} relatório{'s' if n != 1 else ''} mudou de setor. Vale no próximo clique de quem é do setor "
                   "(até 1 minuto).")


# Os relatórios da Plataforma de Performance, cada um na moldura (porta única), na coluna da direita da Central
registrar_molduras(bp, TORRE, modelo="relatorios/moldura.html", extra=_moldura_extra)
# Os quatro do PCM, nativos (nexus/pcm/relatorios)
telas_pcm.registrar(bp, TORRE, lado)
# O Relatório executivo do PCM, a cópia do painel numa moldura (nexus/pcm/relatorio_exec)
relatorio_exec.registrar(bp, TORRE, lado)
