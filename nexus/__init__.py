"""Nexus: casca única da operação O&M da Grid Co."""
from datetime import timedelta

from flask import Flask

from .config import OPCIONAIS, carregar_config


def create_app(config: dict | None = None) -> Flask:
    cfg = carregar_config(config)
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=cfg["NEXUS_SECRET_KEY"],
        NEXUS_SENHA_ADMIN=cfg["NEXUS_SENHA_ADMIN"],
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

    from .auth import bp as auth_bp, instalar_portao
    from .casca import bp as casca_bp, instalar_contexto
    from .torres import registrar_torres

    app.register_blueprint(auth_bp)
    app.register_blueprint(casca_bp)
    registrar_torres(app)
    instalar_portao(app)
    instalar_contexto(app)
    return app
