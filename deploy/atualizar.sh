#!/usr/bin/env bash
# Atualiza o Nexus no servidor: puxa do GitHub, instala as dependências, confere que o Nexus novo sobe, reinicia o
# serviço e confere no /saude que o commit novo está no ar. É o passo 8 do DEPLOY.md num comando só (Levi, 06/10/2026:
# "é linux, não consegue implementar no git para eu rodar pelo server?").
#
#   sudo /opt/nexus/deploy/atualizar.sh            puxa; se o commit do clone ainda não foi instalado, instala e reinicia
#   sudo /opt/nexus/deploy/atualizar.sh --forcar   instala e reinicia mesmo sem nada novo
#
# O restart é obrigatório: o Nexus não relê as telas com o processo rodando. Só o "git pull" deixou o servidor com a
# tela velha do PCM em 06/10. O git não toca nos .env nem na dados/. Qualquer erro para o script antes do restart, e o
# Nexus de antes segue no ar.
#
# Auditoria A6 da porta única (10/10/2026): o pip só rodava quando o requirements.txt mudava entre o commit de antes e o
# de depois do pull. Se ele falhasse na 1ª rodada (o reportlab, novo e importado no boot, sem saída para o pypi), a 2ª
# via o mesmo commit e dizia "nada a fazer", e com --forcar pulava o pip e reiniciava: o Nexus novo não subia, e o
# Restart=always do systemd o deixava caindo em laço. Agora:
#   - o pip roda SEMPRE antes do restart (idempotente: sem nada novo, só confere e sai em segundos);
#   - o boot é conferido antes do restart (deploy/conferir_boot.py, com o Python do .venv): falhou, para aqui;
#   - "nada a fazer" é quando o commit do clone é o último INSTALADO (a marca em .git/nexus-instalado, gravada depois do
#     restart), e não o de antes do pull: a rodada que parou no meio é completada pela seguinte (o timer, 2 min depois).
set -euo pipefail

SERVICO="${NEXUS_SERVICO:-nexus}"
PORTA="${NEXUS_PORTA:-5070}"
TENTATIVAS="${NEXUS_TENTATIVAS:-30}"          # 30 x 2 s: o boot leva poucos segundos
RAIZ="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"

if [ "$(id -u)" -ne 0 ]; then
  echo "Rode com sudo: sudo $0 $*" >&2
  exit 1
fi
cd "$RAIZ"
DONO="$(stat -c %U "$RAIZ")"                   # o clone é do usuário do serviço (DEPLOY.md, passo 3): o git roda como ele
como() { sudo -u "$DONO" "$@"; }
DONO_VENV="$(stat -c %U .venv)"
no_venv() { sudo -u "$DONO_VENV" "$@"; }
# o último commit instalado aqui (dependências, boot conferido e restart pedido): dentro do .git, fora da árvore, onde o
# pull não mexe e o git status não mostra
MARCA="$(como git rev-parse --git-dir)/nexus-instalado"

antes="$(como git rev-parse --short HEAD)"
echo "Nexus em $RAIZ, no commit $antes. Buscando no GitHub..."
como git pull --ff-only
depois="$(como git rev-parse --short HEAD)"
instalado="$(cat "$MARCA" 2>/dev/null || true)"

if [ "$depois" = "$instalado" ] && [ "${1:-}" != "--forcar" ]; then
  echo "Já estava no último commit ($depois), instalado: nada a fazer."
  exit 0
fi
if [ "$antes" != "$depois" ]; then
  echo "Commits novos:"
  como git log --oneline "$antes..$depois"
elif [ "$depois" != "$instalado" ]; then
  echo "O commit $depois já estava no clone, mas não chegou a ser instalado (${instalado:-nenhum registro}): instalando agora."
fi

# Sempre, antes de todo restart: sem isto, a dependência que faltou numa rodada nunca mais era instalada
echo "Instalando as dependências do requirements.txt..."
if ! no_venv .venv/bin/pip install -q -r requirements.txt; then
  echo "ERRO: o pip falhou (o servidor alcança o pypi.org?). O serviço NÃO foi reiniciado: o Nexus de antes segue no ar." >&2
  echo "A próxima rodada tenta de novo." >&2
  exit 1
fi
echo "Conferindo se o Nexus novo sobe..."
if ! no_venv .venv/bin/python -B deploy/conferir_boot.py; then
  echo "ERRO: o Nexus novo não subiria. O serviço NÃO foi reiniciado: o Nexus de antes segue no ar." >&2
  exit 1
fi

echo "Reiniciando o serviço $SERVICO..."
systemctl restart "$SERVICO"
# gravada depois do restart, venha o /saude ou não: um commit que não sobe por outro motivo (o .env, por exemplo) não fica
# reiniciando a cada 2 min (cada boot relê a Aprovação no Fracttal, na cota dividida com o App); o próximo commit conserta
printf '%s\n' "$depois" | como tee "$MARCA" >/dev/null
resp=""
for _ in $(seq 1 "$TENTATIVAS"); do
  sleep 2
  resp="$(curl -s --max-time 3 "http://127.0.0.1:$PORTA/saude" || true)"
  case "$resp" in
    *"\"$depois\""*) echo "No ar: $resp"; exit 0 ;;
  esac
done
echo "ERRO: o /saude não respondeu com o commit $depois (última resposta: ${resp:-nenhuma})." >&2
echo "Veja o log: sudo journalctl -u $SERVICO -n 50" >&2
exit 1
