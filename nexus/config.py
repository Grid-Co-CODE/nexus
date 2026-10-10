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
             # tela Base → Ligações (04/10/2026): onde moram as decisões e o token para publicar no banco
             "NEXUS_DADOS", "NEXUS_DE_PARA_REGRAS", "GRIDCO_SQL_TOKEN", "GRIDCO_DB_API",
             # torre Campo · App (04/10/2026): o coletor do Fracttal roda só onde NEXUS_CAMPO_COLETOR=1, a cada N minutos
             "NEXUS_CAMPO_COLETOR", "NEXUS_CAMPO_COLETOR_MIN",
             # as leituras do Fracttal ao subir: a fila da Aprovação de OS, as rondas aprovadas, as OS de falha e o Quadro
             # da equipe da Engenharia (NEXUS_CAMPO_AQUECER=0 desliga numa máquina; a pré-carga das telas pelo banco
             # fica sempre ligada)
             "NEXUS_CAMPO_AQUECER",
             # a pessoa nos workbooks que o App de Campo manda (v226): HMAC do e-mail, a mesma chave do App Setting
             "NEXUS_PESSOA_HMAC",
             # aba Tempo real (04/10/2026): onde está a plataforma de Performance e a chave só de leitura dela (a ponte).
             # Desde a porta única (09/10/2026) a NEXUS_PLATAFORMA_URL é também a base que o NAVEGADOR usa para abrir as
             # telas da plataforma na moldura: no servidor, o próprio endereço (app.gridco.com.br), que também traz a ponte
             # de volta se a chave sair (revisão de 10/10/2026); vazia = a própria origem do Nexus
             "NEXUS_PLATAFORMA_URL", "NEXUS_PLATAFORMA_TOKEN",
             # porta única (09/10/2026, Levi: "a partir de segunda quero o Nexus como link principal"): a chave do passe que
             # abre as telas da Performance dentro do Nexus (a MESMA no .env da plataforma; 32 caracteres ou mais). Sem
             # ela as telas dizem "Performance ainda não ligada neste servidor" e o resto do Nexus segue igual
             "NEXUS_SSO_CHAVE",
             # camada de dados (05/10/2026): a carga de hora em hora liga onde há o token de escrita; "0" desliga
             "NEXUS_CARGA_DADOS",
             # login pelo Fracttal (06/10/2026): e-mails (separados por vírgula) que entram como admin (o Cadastro)
             "NEXUS_ADMINS",
             # Performance -> Clima e risco (06/10/2026): endereços das fontes públicas (INMET, focos e risco de fogo do INPE, e
             # a irradiação diária da NASA POWER, de 07/10); vazios valem os padrões de nexus/performance/clima/fontes.py. O do
             # risco leva {d} (o dia, de 0 a 3); o da NASA leva {lat}, {lon}, {inicio} e {fim}. O do FIRMS (10/10/2026) é a base dos
             # arquivos públicos de focos da NASA (fontes.FIRMS_ARQUIVOS vão depois dela).
             "NEXUS_CLIMA_INMET_URL", "NEXUS_CLIMA_FOCOS_URL", "NEXUS_CLIMA_RISCO_URL", "NEXUS_CLIMA_POWER_URL",
             "NEXUS_CLIMA_FIRMS_URL",
             # PCM -> Gestão PCM (07/10/2026): a senha que abre o mpas.json da Gerencial (o mesmo do painel do PCM);
             # sem ela a Fila mostra só o lado do Fracttal. As fontes trocam o endereço padrão (repositório do PCM).
             "NEXUS_PCM_MPAS_SENHA", "NEXUS_PCM_GESTAO_FONTE", "NEXUS_PCM_MPAS_FONTE",
             # o caminho em que o Nexus é servido (09/10/2026, "a partir de segunda quero o Nexus como link principal"):
             # /nexus no servidor (app.gridco.com.br/nexus); vazio = a raiz, o PC e a fase 4. Ver nexus/prefixo.py
             "NEXUS_PREFIXO")


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
