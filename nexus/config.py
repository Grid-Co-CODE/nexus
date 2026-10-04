"""Configuração do Nexus: lê o .env e se recusa a subir se faltar variável.

Por que abortar no boot: na plataforma de Performance o coletor já ficou sem credencial em silêncio
depois de uma mudança de pasta (o .env era procurado relativo ao diretório de trabalho), e ninguém
percebeu até a coleta falhar. Aqui o .env é achado pelo caminho do próprio projeto e a falta de uma
variável derruba o processo com o nome dela na mensagem.
"""
import os
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values

RAIZ = Path(__file__).resolve().parent.parent
OBRIGATORIAS = ("NEXUS_SECRET_KEY", "NEXUS_SENHA_ADMIN")
# Opcionais: sem elas o Nexus sobe, e só a tela que depende delas avisa. O cadastro (29/09/2026) é a primeira:
# sem NEXUS_CHAVE_CADASTRO ele não abre, e o resto da casca segue igual (a torre COS não precisa dela).
OPCIONAIS = ("NEXUS_CHAVE_CADASTRO", "NEXUS_ARMAZEM_LOCAL",
             # aba Tempo real (04/10/2026): onde está a plataforma de Performance e a chave só de leitura dela
             "NEXUS_PLATAFORMA_URL", "NEXUS_PLATAFORMA_TOKEN")


class ConfigErro(RuntimeError):
    pass


def ler_ambiente() -> dict:
    """O .env do projeto, com as variáveis de ambiente do processo por cima (é assim no servidor)."""
    valores = {k: v for k, v in dotenv_values(RAIZ / ".env").items() if v is not None}
    valores.update({k: v for k, v in os.environ.items() if k.startswith("NEXUS_")})
    return valores


def carregar_config(env: Mapping[str, str] | None = None) -> dict:
    env = ler_ambiente() if env is None else env
    faltando = [nome for nome in OBRIGATORIAS if not (env.get(nome) or "").strip()]
    if faltando:
        # Só o nome da variável, nunca o valor: a mensagem vai para log e terminal.
        raise ConfigErro(
            "Variável obrigatória ausente no .env: " + ", ".join(faltando)
            + f". Copie o .env.example para {RAIZ / '.env'} e preencha."
        )
    cfg = {nome: env[nome] for nome in OBRIGATORIAS}
    cfg.update({nome: env[nome] for nome in OPCIONAIS if (env.get(nome) or "").strip()})
    return cfg
