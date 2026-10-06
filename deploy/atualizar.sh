#!/usr/bin/env bash
# Atualiza o Nexus no servidor: puxa do GitHub, instala o que o requirements.txt pedir, reinicia o serviço e confere
# no /saude que o commit novo está no ar. É o passo 8 do DEPLOY.md num comando só (Levi, 06/10/2026: "é linux, não
# consegue implementar no git para eu rodar pelo server?").
#
#   sudo /opt/nexus/deploy/atualizar.sh            puxa; se veio commit novo, reinicia e confere
#   sudo /opt/nexus/deploy/atualizar.sh --forcar   reinicia e confere mesmo sem commit novo
#
# O restart é obrigatório: o Nexus não relê as telas com o processo rodando. Só o "git pull" deixou o servidor com a
# tela velha do PCM em 06/10. O git não toca nos .env nem na dados/. Qualquer erro para o script antes do restart.
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

antes="$(como git rev-parse --short HEAD)"
echo "Nexus em $RAIZ, no commit $antes. Buscando no GitHub..."
como git pull --ff-only
depois="$(como git rev-parse --short HEAD)"

if [ "$antes" = "$depois" ] && [ "${1:-}" != "--forcar" ]; then
  echo "Já estava no último commit ($depois): nada a fazer."
  exit 0
fi
if [ "$antes" != "$depois" ]; then
  echo "Commits novos:"
  como git log --oneline "$antes..$depois"
  if ! como git diff --quiet "$antes" "$depois" -- requirements.txt; then
    echo "O requirements.txt mudou: instalando as dependências..."
    sudo -u "$(stat -c %U .venv)" .venv/bin/pip install -q -r requirements.txt
  fi
fi

echo "Reiniciando o serviço $SERVICO..."
systemctl restart "$SERVICO"
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
