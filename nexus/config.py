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
             # o histórico do almoxarifado (25/10/2026): "1" liga a gravação; sem ela a carga só mede (Levi: o Nexus sobe
             # antes do App, em ensaio, e a gravação liga depois do ensaio com o 1º ciclo real)
             "NEXUS_ALMOX_GRAVAR",
             # o almoxarifado de TESTE do inventário (26/10/2026): IDs do Fracttal, separados por vírgula; ficam fora das
             # telas do PCM e do histórico (a prova das gravações é nele, nunca num almoxarifado de usina)
             "NEXUS_ALMOX_TESTE_IDS",
             # o livro do inventário num arquivo (só na cópia de prova e nos testes; no servidor ele vem do banco,
             # `nexus_almoxarifado_inventario`, nexus/dados/fato_inventario.py)
             "NEXUS_ALMOX_INVENTARIO_ARQUIVO",
             # a gravação do inventário no Fracttal (27/10/2026, nexus/pcm/inventario/gravacao.py): só onde vale "1", o
             # servidor (a vez do almoxarifado e a espera do deploy moram na máquina que grava); vazia, o PC não grava
             "NEXUS_INVENTARIO_GRAVAR",
             # os chamados de garantia no banco (12/10/2026, nexus/campo/chamados_acompanhamento.py): "0" desliga numa máquina
             "NEXUS_CHAMADOS_PUBLICAR",
             # as tarefas das OS do Fracttal no banco (18/10/2026, nexus/campo/tarefas_os.py): "0" desliga numa máquina
             "NEXUS_OS_PUBLICAR",
             # a Zeladoria no banco para o dashboard do cliente (26/10/2026, nexus/campo/zeladoria_banco.py): "0" desliga;
             # onde NEXUS_CAMPO_AQUECER=0 (o PC) ela nem liga
             "NEXUS_ZELADORIA_PUBLICAR",
             # as normalizações da Ronda COS no banco (29/10/2026, nexus/cos/normalizacoes_banco.py): "0" desliga; onde
             # a fonte do Andamento não está ligada (o PC) cada volta só pula
             "NEXUS_NORMALIZACOES_PUBLICAR",
             # login pelo Fracttal (06/10/2026): e-mails (separados por vírgula) que entram como admin (o Cadastro)
             "NEXUS_ADMINS",
             # Entrar com a Microsoft da Grid Co. (14/10/2026, nexus/auth/microsoft.py): as QUATRO primeiras ligam a porta
             # da Microsoft, e o Fracttal sai da porta; sem qualquer uma delas, a porta segue a do Fracttal. O diretório é
             # o ID (GUID) do Entra; a volta é o /entrar EXATO que a T.I. registrou. Domínios: padrão gridco.com.br
             "NEXUS_MS_CLIENT_ID", "NEXUS_MS_TENANT_ID", "NEXUS_MS_CLIENT_SECRET", "NEXUS_MS_VOLTA", "NEXUS_MS_DOMINIOS",
             # Performance -> Clima e risco (06/10/2026): endereços das fontes públicas (INMET, focos e risco de fogo do INPE, e
             # a irradiação diária da NASA POWER, de 07/10); vazios valem os padrões de nexus/performance/clima/fontes.py. O do
             # risco leva {d} (o dia, de 0 a 3); o da NASA leva {lat}, {lon}, {inicio} e {fim}. O do FIRMS (10/10/2026) é a base dos
             # arquivos públicos de focos da NASA (fontes.FIRMS_ARQUIVOS vão depois dela).
             "NEXUS_CLIMA_INMET_URL", "NEXUS_CLIMA_FOCOS_URL", "NEXUS_CLIMA_RISCO_URL", "NEXUS_CLIMA_POWER_URL",
             "NEXUS_CLIMA_FIRMS_URL",
             # PCM -> Gestão PCM (07/10/2026): a senha que abre o mpas.json da Gerencial (o mesmo do painel do PCM);
             # sem ela a Fila mostra só o lado do Fracttal. As fontes trocam o endereço padrão (repositório do PCM).
             "NEXUS_PCM_MPAS_SENHA", "NEXUS_PCM_GESTAO_FONTE", "NEXUS_PCM_MPAS_FONTE",
             # os relatórios do PCM na Central (14/10/2026, nexus/pcm/relatorios): "0" desliga a emissão automática numa
             # máquina; as fontes trocam o endereço padrão (repositório do PCM) da Gerencial, da Confiabilidade, do BD de
             # Operações e dos feriados
             "NEXUS_PCM_RELATORIOS_AUTO", "NEXUS_PCM_GERENCIAL_FONTE", "NEXUS_PCM_ENGENHARIA_FONTE",
             "NEXUS_PCM_OPERACOES_FONTE", "NEXUS_PCM_FERIADOS_FONTE", "NEXUS_PCM_CONFIABILIDADE_FONTE",
             # o e-mail semanal das pendências da Segurança (24/10/2026, nexus/hseq/email_semanal.py): "1" liga a
             # publicação de segunda, que o App de Campo manda; sem ela, desligado
             "NEXUS_HSEQ_EMAIL_AUTO",
             # a curadoria do Acompanhamento do PCM num arquivo (só na cópia de prova; no servidor ela vem do banco)
             "NEXUS_PCM_CURADORIA_ARQUIVO",
             # o caminho em que o Nexus é servido (09/10/2026, "a partir de segunda quero o Nexus como link principal"):
             # /nexus no servidor (app.gridco.com.br/nexus); vazio = a raiz, o PC e a fase 4. Ver nexus/prefixo.py
             "NEXUS_PREFIXO",
             # o que cada setor vê (12/10/2026, Base → Acessos): padrão ligado; "0" desliga numa máquina (todos veem
             # tudo, como antes). Sem a NEXUS_PESSOA_HMAC fica desligado de qualquer jeito (nexus/auth/setor_telas.py)
             "NEXUS_ACESSO_POR_SETOR",
             # a pré-carga das telas de quem tem setor (12/10/2026, nexus/auth/pre_carga.py): padrão ligada; "0" desliga
             "NEXUS_PRE_CARGA",
             # Contratos e clientes → Contestações (13/10/2026): a chave PRIVADA (X25519, base64) que abre o nome, o
             # contato e a mensagem do cliente que o Dashboard Thopen grava cifrados com a pública. Sem ela, a tela lista
             # as contestações sem esses dados (nexus/contratos/contestacoes.py)
             "NEXUS_CONTESTACAO_CHAVE_PRIVADA",
             # Contratos e clientes → Acessos dos clientes (14/10/2026, nexus/contratos/acessos_clientes.py): a chave
             # PÚBLICA do Dashboard Thopen (as contas vão seladas para ela; também pela tela Base → Chaves do Nexus) e o
             # endereço do painel nos links de definir senha (padrão https://app.gridco.com.br/performance)
             "NEXUS_ACESSOS_5080_PUBLICA", "NEXUS_THOPEN_URL",
             # Engenharia → ETMs (26/10/2026, nexus/engenharia/etm_historico.py): o histórico do app de ETM, trazido uma
             # vez — um token que leia as Issues do repositório privado do app e o repositório (dono/nome; o nome traz
             # o de uma pessoa, por isso não fica no código)
             "NEXUS_ETM_GITHUB_TOKEN", "NEXUS_ETM_GITHUB_REPO")


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
