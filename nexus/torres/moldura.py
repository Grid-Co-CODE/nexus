"""As telas da plataforma de Performance dentro do Nexus: uma moldura (iframe) por tela do mapa (spec 5.5 e 5.6).

Levi, 09/10/2026: "a partir de segunda quero o Nexus como link principal; o Nexus será o centro de tudo, precisamos
trazer o tempo real de performance painel para o Nexus". Desenho "uma porta, dois motores"
(`docs/superpowers/specs/2026-10-09-performance-no-nexus-design.md`): a página do Nexus tem o menu e o login; dentro
dela, a tela da plataforma, que continua o motor.

Como uma tela abre:
1. a view do item (`registrar_molduras`) monta o passe (`nexus/performance/porta.py`) para o destino da tela;
2. a página tem um formulário escondido que faz POST do passe para `<plataforma>/painel/nexus/entrar`, com alvo na
   moldura (o `porta.js` o envia ao carregar; sem JavaScript, o botão "Abrir");
3. a plataforma confere o passe, abre a sessão DELA e responde 303 para a tela, já no modo Nexus (sem a navegação
   própria) e avisando a moldura de cada troca de caminho (`postMessage` `{tipo: "nexus:rota", caminho}`);
4. o `porta.js` troca o endereço (`?p=<caminho>`, para F5 e favorito) e acende o item do menu pela tabela do mapa.

Nada passa pelo processo do Nexus (a ponte de 04/10 passava): o navegador fala com cada sistema. Sem a
`NEXUS_SSO_CHAVE` (ou com a `NEXUS_PLATAFORMA_URL` inválida) a tela diz "Performance ainda não ligada neste servidor" e
o resto do Nexus segue igual; a plataforma, sem a mesma chave, responde 404 em `/painel/nexus/*`.

Mora em `nexus/torres/` (e não numa torre) porque três torres a usam: Performance, COS (Acompanhamento COS) e Base
(Chaves das fontes). Um módulo solto aqui não vira torre: a descoberta só olha os pacotes.
"""
from urllib.parse import urlencode, urlsplit

from flask import (current_app, has_request_context, jsonify, make_response, redirect, render_template, request, session,
                   url_for)

from ..performance import porta
from ..prefixo import na_raiz

# Tempo real com duas visões (spec 5.7): "Ao vivo" (a moldura da plataforma, o padrão) e "Pelo banco" (a Operação em
# tempo real de código próprio, lendo `operacao_tempo_real`). A segunda entra DEPOIS que a Ao vivo estiver no servidor
# (o Tempo real nunca fica sem a leitura ao vivo): até lá ela fica aqui com pronta=False e a alternância não aparece.
# Quando a branch da Operação em tempo real entrar: pronta=True, e a view do Tempo real responde `?ver=banco`.
VISOES_DO_TEMPO_REAL = (
    {"id": "ao-vivo", "nome": "Ao vivo", "pronta": True},
    {"id": "banco", "nome": "Pelo banco", "pronta": False},
)


def estado_da_porta(config=None) -> dict:
    """{"ligada": bool, "motivo": texto (desligada), "plataforma": base ('' = a própria origem)}. Nunca o valor da
    chave: o motivo vai para a tela.

    Sem `config` (uma tela, o Sair), confere também a base contra o endereço DESTE pedido (`porta.motivo_da_origem`,
    revisão de 10/10/2026): a NEXUS_PLATAFORMA_URL interna do servidor com o Nexus aberto por fora desliga a porta, e o
    Tempo real segue pela ponte. Com `config` (o menu, calculado uma vez), só a configuração."""
    cfg = current_app.config if config is None else config
    motivo = porta.motivo_da_chave(cfg.get("NEXUS_SSO_CHAVE"))
    if motivo:
        return {"ligada": False, "motivo": motivo, "plataforma": ""}
    try:
        base = porta.base_da_plataforma(cfg.get("NEXUS_PLATAFORMA_URL"))
    except ValueError as e:
        return {"ligada": False, "motivo": str(e), "plataforma": ""}
    if config is None and has_request_context():
        motivo = porta.motivo_da_origem(base, request.host)
        if motivo:
            return {"ligada": False, "motivo": motivo, "plataforma": ""}
    return {"ligada": True, "motivo": "", "plataforma": base}


def url_da_tela(t) -> str:
    """O endereço do item no Nexus, como o navegador o pede (com o prefixo em que o Nexus roda)."""
    return na_raiz(f"/t/{t.torre}/{t.tela}")


def _quem() -> tuple[str, str, bool]:
    """E-mail, nome e se é admin, para o passe. Quem entrou pela senha de administrador não é uma pessoa: vai com o
    e-mail da reserva (`porta.EMAIL_DA_SENHA_DE_ADMIN`)."""
    usuario = session.get("usuario") or {}
    email = (usuario.get("email") or "").strip()
    if not email:
        return porta.EMAIL_DA_SENHA_DE_ADMIN, porta.NOME_DA_SENHA_DE_ADMIN, bool(session.get("admin"))
    return email, usuario.get("nome") or "", bool(session.get("admin"))


def _passe(destino: str) -> str:
    email, nome, admin = _quem()
    return porta.montar_passe(current_app.config["NEXUS_SSO_CHAVE"], email, nome, admin, destino)


def _dados_do_navegador(t, estado: dict, destino: str | None, passe_lista: str | None) -> dict:
    """O que o `porta.js` precisa: a base da plataforma, o item aberto, o destino e a tabela do mapa (o endereço de cada
    item no Nexus e as expressões dos caminhos dele, para acender o item certo quando a moldura avisa)."""
    return {
        "plataforma": estado["plataforma"],
        "url": url_da_tela(t),
        # onde pedir um passe novo quando a sessão da plataforma vence ou vai vencer (`_passe_novo`)
        "renovar": url_for(f"{request.blueprint}.{_endpoint(t)}_passe"),
        "destino": destino or "",
        "telas": [{"url": url_da_tela(x), "nome": x.nome, "caminho": x.caminho if porta.concreto(x) else "",
                   "padroes": porta.padroes_do_navegador(x)} for x in porta.MAPA],
        # Diagnóstico: o passe que abre a sessão da plataforma para ler a lista de usinas (o mesmo /api/macro do Painel
        # NOC, por isso o destino é o /painel; o 303 não é seguido). Só vai à rede se a lista voltar 401.
        "passe_lista": passe_lista or "",
    }


def _pagina(torre, t, reserva=None):
    tela = torre.tela(t.tela)
    estado = estado_da_porta()
    # `?p=` (favorito, F5, o endereço que a moldura acompanhou): só caminho do mapa. De outro item, vai ao item dono (o
    # menu acende o certo); fora do mapa, a tela padrão do item (spec 7: "sem seguir o caminho").
    destino = t.caminho if porta.concreto(t) else None      # o Diagnóstico espera a usina do seletor
    pedido = porta.destino_permitido(request.args.get("p"))
    if pedido:
        dono = porta.tela_do_caminho(pedido)
        if (dono.torre, dono.tela) != (t.torre, t.tela):
            return redirect(url_da_tela(dono) + "?" + urlencode({"p": pedido}))
        destino = pedido
    contexto = {"torre": torre, "tela": tela, "estado": estado, "ligada": estado["ligada"], "motivo": estado["motivo"],
                "plataforma": estado["plataforma"], "destino": destino, "passe": None, "recusa": None,
                "seletor": t.tela == "diagnostico", "ver": "ao-vivo",
                "visoes": [v for v in VISOES_DO_TEMPO_REAL if v["pronta"]] if t.tela == "tempo-real" else []}
    if t.so_admin and not session.get("admin"):
        # spec 5.3: as chaves das fontes são administração. A plataforma recusa de novo (o passe diz quem é admin).
        contexto.update(recusa="As chaves das fontes (SunOp, Axis e Plataforma) são administração: abrem só para "
                               "quem é administrador do Nexus (NEXUS_ADMINS, ou a senha de administrador).")
        return render_template("performance/moldura.html", **contexto), 403
    if not estado["ligada"] and reserva:
        # o Tempo real que já funcionava pela ponte de 04/10 continua até a T.I. pôr a chave (nada afeta o que
        # funciona hoje, spec 10); com a porta ligada a ponte sai do menu e fica só no código
        resp = reserva(estado["motivo"])
        if resp is not None:
            return resp
    if estado["ligada"]:
        if destino:
            contexto["passe"] = _passe(destino)
        contexto["dados"] = _dados_do_navegador(t, estado, destino,
                                                _passe("/painel") if contexto["seletor"] else None)
    resp = make_response(render_template("performance/moldura.html", **contexto))
    # O passe vale 60 s e uma vez só: a página não fica em cache nenhum (voltar pelo navegador gera outro) e não é
    # guardada em disco com o e-mail dentro.
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _json_sem_cache(corpo: dict, status: int):
    resp = jsonify(corpo)
    resp.status_code = status
    resp.headers["Cache-Control"] = "no-store"       # o passe leva o e-mail e vale uma vez: nada de cache
    return resp


def _de_outro_site() -> bool:
    """O pedido NÃO veio de uma página deste mesmo endereço. A mesma regra do `_de_outra_origem` da plataforma: pelo
    Sec-Fetch-Site, só 'same-origin' (o fetch do porta.js; 'same-site' não, porque todo subdomínio de gridco.com.br é
    'same-site'); sem ele, o Origin tem de ser deste host ('null' não); sem os dois não é navegador, e não há cookie de
    vítima para usar. A resposta é JSON que outro site não lê (sem CORS); isto fecha também o pedido às cegas."""
    sfs = (request.headers.get("Sec-Fetch-Site") or "").strip().lower()
    if sfs:
        return sfs != "same-origin"
    origem = request.headers.get("Origin")
    if origem is None:
        return False
    try:
        de = urlsplit(origem.strip()).netloc.lower()
    except ValueError:
        return True
    return not de or de != (request.host or "").lower()


def _passe_novo(t):
    """`POST /t/<torre>/<tela>/passe` (`p` = o caminho da plataforma): um passe novo, em JSON, para a moldura renovar a
    sessão da plataforma (auditoria A5 da porta única, 10/10/2026).

    O caso: a sessão que o passe abre na plataforma vale 12 h fixas; depois, o `/api/macro` do Painel NOC dava 401 e o
    painel desenhava "Energia perdida 0,0 MWh", número falso numa tela de NOC ou de TV. Agora a página da plataforma avisa
    a moldura (`nexus:sessao-vencida`) e o porta.js pede aqui um passe novo para reabrir a mesma tela, e renova sozinho a
    cada 11 h. O passe é o da abertura da tela (60 s, uso único, quem está logado), para qualquer caminho do MAPA (a
    moldura pode ter ido do Painel NOC ao diagnóstico de uma usina); as chaves das fontes, só para admin. Sessão do Nexus
    encerrada: o portão já respondeu antes (401 em JSON, ou o salto ao Entrar), e o porta.js leva a janela ao login."""
    if not estado_da_porta()["ligada"]:
        return _json_sem_cache({"ok": False, "erro": "Performance ainda não ligada neste servidor."}, 404)
    if _de_outro_site():
        return _json_sem_cache({"ok": False, "erro": "Pedido de outro site."}, 403)
    caminho = porta.destino_permitido(request.form.get("p"))
    if not caminho:
        return _json_sem_cache({"ok": False, "erro": "Caminho fora das telas da Performance."}, 400)
    if (t.so_admin or porta.tela_do_caminho(caminho).so_admin) and not session.get("admin"):
        return _json_sem_cache({"ok": False, "erro": "Só administradores do Nexus."}, 403)
    return _json_sem_cache({"ok": True, "passe": _passe(caminho), "destino": caminho}, 200)


def _endpoint(t) -> str:
    return "moldura_" + t.tela.replace("-", "_")


def registrar_molduras(bp, torre, reserva: dict | None = None) -> None:
    """Uma view para cada tela do mapa que mora nesta torre (`/t/<torre>/<tela>`), vencendo o placeholder, e a rota do
    passe novo dela (`/t/<torre>/<tela>/passe`, só POST: `_passe_novo`). A tela tem de estar declarada na `TORRE` (é o
    que entra no menu): sem ela, o erro sai ao subir, não na mão de quem clica.
    `reserva` = {tela: função(motivo) -> resposta ou None}, chamada com a porta desligada (o Tempo real pela ponte)."""
    reserva = reserva or {}
    for t in porta.da_torre(torre.id):
        if torre.tela(t.tela) is None:
            raise RuntimeError(f"a tela {t.tela!r} do mapa da Performance não está declarada na torre {torre.id!r}")

        def view(_t=t):
            return _pagina(torre, _t, reserva.get(_t.tela))

        def passe_novo(_t=t):
            return _passe_novo(_t)
        endpoint = _endpoint(t)
        bp.add_url_rule("/" + t.tela, endpoint=endpoint, view_func=view)
        bp.add_url_rule("/" + t.tela + "/passe", endpoint=endpoint + "_passe", view_func=passe_novo, methods=["POST"])
        if t.tela not in reserva:
            SO_COM_A_PORTA.add(f"{bp.name}.{endpoint}")


# As views de moldura sem reserva: só têm conteúdo com a porta ligada. O verde do menu (`telas_com_conteudo`) as conta só
# então (revisão de 10/10/2026: sem a chave, 12 itens ficavam verdes e abriam o aviso, e o verde, "uma marca esquecida
# não mente", passava a mentir até a T.I. pôr a chave). O Tempo real tem a ponte de 04/10 como reserva: segue verde,
# como antes da porta.
SO_COM_A_PORTA: set[str] = set()
