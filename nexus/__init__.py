"""Nexus: casca única da operação O&M da Grid Co."""
from datetime import timedelta

from flask import Flask

from .config import OPCIONAIS, carregar_config
from .prefixo import Prefixo, SessaoNoPrefixo, na_raiz, normalizar


def create_app(config: dict | None = None) -> Flask:
    cfg = carregar_config(config)
    prefixo = normalizar(cfg.get("NEXUS_PREFIXO"))
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=cfg["NEXUS_SECRET_KEY"],
        NEXUS_SENHA_ADMIN=cfg["NEXUS_SENHA_ADMIN"],
        # Passo 0 da porta única (spec 2026-10-09, seção 5.1): o Nexus e a plataforma estão no mesmo endereço e os dois
        # usavam o `session` do Flask em `/`; o navegador guardava um só, e entrar num apagava a sessão do outro. Nome
        # próprio aqui, e o caminho é o do prefixo em que o Nexus roda (`SessaoNoPrefixo`). Efeito único: quem estava
        # logado entra de novo uma vez.
        SESSION_COOKIE_NAME="nexus_sessao",
        NEXUS_PREFIXO=prefixo,
        APPLICATION_ROOT=prefixo or "/",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # Secure por padrão (servidor atrás de HTTPS). O app.py desliga só para rodar em
        # http://localhost, onde o navegador descartaria um cookie Secure.
        SESSION_COOKIE_SECURE=True,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        # Cadastro (o BD_Operações fora da planilha): a chave da cifra e onde fica o ensaio local. Sem a chave,
        # as telas do cadastro avisam e o resto do Nexus não percebe.
        NEXUS_CHAVE_CADASTRO=cfg.get("NEXUS_CHAVE_CADASTRO"),
        NEXUS_ARMAZEM_LOCAL=cfg.get("NEXUS_ARMAZEM_LOCAL"),
        # O BD_Operações tem 350 KB: 25 MB é folga para a planilha crescer sem abrir a porta a upload gigante.
        MAX_CONTENT_LENGTH=25 * 1024 * 1024,
    )
    # As outras opcionais (tela Ligações: pasta de dados, regras, token do banco). Sem isto o teste que passava
    # NEXUS_DADOS gravava no arquivo de regras de verdade (04/10/2026).
    app.config.update({k: v for k, v in cfg.items() if k in OPCIONAIS and k not in app.config})
    app.session_interface = SessaoNoPrefixo()
    if prefixo:
        # o servidor (app.gridco.com.br/nexus): o app se vê debaixo do prefixo, venha ele no caminho ou não (nexus/prefixo.py)
        app.wsgi_app = Prefixo(app.wsgi_app, prefixo)
    # o endereço do Nexus nos templates: {{ raiz }}/t/... e o filtro |na_raiz para o que vem montado do Python
    app.jinja_env.filters["na_raiz"] = na_raiz

    from .auth import bp as auth_bp, instalar_portao
    from .casca import bp as casca_bp, instalar_contexto
    from .torres import registrar_torres

    app.register_blueprint(auth_bp)
    app.register_blueprint(casca_bp)
    registrar_torres(app)
    instalar_portao(app)
    instalar_contexto(app)
    _instalar_cache_estatico(app)
    return app


def _instalar_cache_estatico(app) -> None:
    """O CSS, o JS e as imagens com a versão no endereço (`?v=<commit>`) e guardados 1 ano pelo navegador (13/10/2026,
    Levi: "o link do servidor demorou muito para carregar"): antes, cada página reconfirmava cada arquivo com o servidor
    (no-cache, um vaivém por arquivo). Commit novo = endereço novo, então nada fica velho depois de um deploy. Pasta sem
    git (o commit "local"): fica como antes. O que não sai do `url_for` (sem o `v`) também fica como antes. Chave
    `NEXUS_ESTATICO_VERSAO` (0 desliga); sem ela, ligado fora dos testes, como a pré-carga (os testes conferem o
    endereço exato do arquivo)."""
    from flask import current_app, request

    from .casca import _commit

    def _e_estatico(endpoint) -> bool:
        return bool(endpoint) and (endpoint == "static" or endpoint.endswith(".static"))

    def _ligada() -> bool:
        v = current_app.config.get("NEXUS_ESTATICO_VERSAO")
        if v is None:
            return not current_app.config.get("TESTING")
        return str(v).strip().lower() not in ("", "0", "false", "nao", "não", "desligado")

    @app.url_defaults
    def _versao_do_estatico(endpoint, values):
        if _e_estatico(endpoint) and "v" not in values and _ligada():
            v = _commit()
            if v and v != "local":
                values["v"] = v

    @app.after_request
    def _guardar_o_estatico(resp):
        if _e_estatico(request.endpoint) and request.args.get("v") and resp.status_code == 200:
            resp.cache_control.no_cache = None
            resp.cache_control.public = True
            resp.cache_control.max_age = 31536000
            resp.cache_control.immutable = True
        return resp
