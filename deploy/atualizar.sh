#!/usr/bin/env bash
# Atualiza o Nexus no servidor: busca no GitHub, confere o commit novo FORA da pasta do serviço (dependências e boot),
# só então anda com a pasta, reinicia o serviço e confere no /saude que o commit novo está no ar. É o passo 8 do
# DEPLOY.md num comando só (Levi, 06/10/2026: "é linux, não consegue implementar no git para eu rodar pelo server?").
#
#   sudo /opt/nexus/deploy/atualizar.sh            busca; se o commit do GitHub ainda não foi instalado, instala e reinicia
#   sudo /opt/nexus/deploy/atualizar.sh --forcar   instala e reinicia mesmo sem nada novo
#
# O restart é obrigatório: o Nexus não relê as telas com o processo rodando. Só o "git pull" deixou o servidor com a
# tela velha do PCM em 06/10. O git não toca nos .env nem na dados/.
#
# Auditoria A6 da porta única (10/10/2026): o pip só rodava quando o requirements.txt mudava entre o commit de antes e o
# de depois do pull. Se ele falhasse na 1ª rodada (o reportlab, novo e importado no boot, sem saída para o pypi), a 2ª
# via o mesmo commit e dizia "nada a fazer", e com --forcar pulava o pip e reiniciava: o Nexus novo não subia, e o
# Restart=always do systemd o deixava caindo em laço. Daí o pip e a conferência do boot antes de todo restart.
#
# Revisão adversarial (10/10/2026): o "git pull" continuava ANTES do pip e da conferência. Com um dos dois falhando, o
# script saía sem reiniciar, mas a pasta do serviço já estava no commit que não sobe: o processo velho seguia no ar lendo
# templates e o clone do OS Creator do disco novo, e qualquer restart fora do script (reboot, queda com Restart=always,
# o "systemctl restart nexus" do DESFAZER) subia o código que não monta, com a raiz de app.gridco.com.br em 502. Agora:
#   1. git fetch (a pasta do serviço não muda) e o commit do GitHub vai para uma pasta temporária (git archive);
#   2. o pip instala o requirements.txt DELE, e o deploy/conferir_boot.py DELE importa o Nexus DELE (o .venv é o do
#      serviço; o pip só acrescenta ou atualiza pacotes, como antes);
#   3. só com os dois aprovados a pasta do serviço anda (git merge --ff-only) e o serviço reinicia;
#   4. falhou o pip ou a conferência: a pasta fica no commit em que estava e, se ela já estava fora do último instalado
#      (um "git pull" à mão, ou o script antigo que parou no meio), volta a ele (git reset --keep), que é o que está no
#      ar. Um reboot, então, sobe o mesmo Nexus que estava rodando;
#   5. "nada a fazer" é quando o commit do GitHub é o último INSTALADO (a marca em .git/nexus-instalado, gravada depois
#      do restart) e a pasta está nele: a rodada que parou no meio é completada pela seguinte (o timer, 2 min depois).
#
# A pasta do serviço é a de cima deste script, ou NEXUS_RAIZ: na 1ª vez, o servidor ainda tem o script antigo (que puxa
# antes de conferir), e este pode rodar direto do commit novo, sem puxar à mão (DEPLOY.md, passo 8):
#   sudo -u nexus git -C /opt/nexus fetch && sudo -u nexus git -C /opt/nexus show origin/main:deploy/atualizar.sh > /tmp/atualizar.sh
#   sudo env NEXUS_RAIZ=/opt/nexus bash /tmp/atualizar.sh
set -euo pipefail

SERVICO="${NEXUS_SERVICO:-nexus}"
PORTA="${NEXUS_PORTA:-5070}"
TENTATIVAS="${NEXUS_TENTATIVAS:-30}"          # 30 x 2 s: o boot leva poucos segundos
RAIZ="${NEXUS_RAIZ:-$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)}"

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
# git não mexe e o git status não mostra
MARCA="$(como git rev-parse --git-dir)/nexus-instalado"

antes="$(como git rev-parse --short HEAD)"
instalado="$(cat "$MARCA" 2>/dev/null || true)"
echo "Nexus em $RAIZ, no commit $antes. Buscando no GitHub..."
como git fetch --quiet
github="$(como git rev-parse '@{u}')"
# o alvo é o commit do GitHub; se a pasta tem commits à frente dele (feitos no servidor), é ela, como o pull fazia
if como git merge-base --is-ancestor HEAD "$github"; then
  alvo_completo="$github"
elif como git merge-base --is-ancestor "$github" HEAD; then
  alvo_completo="$(como git rev-parse HEAD)"
else
  echo "ERRO: a pasta do serviço e o GitHub divergiram (commits dos dois lados). Nada foi mudado; resolva à mão." >&2
  exit 1
fi
alvo="$(como git rev-parse --short "$alvo_completo")"

if [ "$alvo" = "$instalado" ] && [ "$antes" = "$alvo" ] && [ "${1:-}" != "--forcar" ]; then
  echo "Já estava no último commit ($alvo), instalado: nada a fazer."
  exit 0
fi
if [ "$antes" != "$alvo" ]; then
  echo "Commits novos:"
  como git log --oneline "$antes..$alvo_completo"
elif [ "$alvo" != "$instalado" ]; then
  echo "O commit $alvo já estava na pasta, mas não chegou a ser instalado (${instalado:-nenhum registro}): instalando agora."
fi

# O commit que está no ar: a marca; sem ela (a 1ª rodada depois do script antigo, que não a gravava), o que o /saude do
# processo rodando diz. Vazio quando não dá para saber.
no_ar() {
  if [ -n "$instalado" ]; then
    printf '%s\n' "$instalado"
    return 0
  fi
  curl -s --max-time 3 "http://127.0.0.1:$PORTA/saude" 2>/dev/null \
    | sed -n 's/.*"commit" *: *"\([0-9a-f]\{4,40\}\)".*/\1/p' || true
}

# Falhou antes do restart: a pasta do serviço tem de ficar no que está no ar. Ela só sai dele quando alguém puxou à mão,
# ou pelo script antigo, que puxava antes de conferir. O --keep não apaga arquivo mexido à mão: se houver conflito, ele
# recusa e o aviso diz o que fazer. Sem saber o que está no ar, a pasta fica como está.
voltar_ao_instalado() {
  local volta
  volta="$(no_ar)"
  if [ -z "$volta" ] || ! como git rev-parse --verify --quiet "${volta}^{commit}" >/dev/null; then
    return 0
  fi
  if [ "$(como git rev-parse HEAD)" != "$(como git rev-parse "${volta}^{commit}")" ]; then
    if como git reset --quiet --keep "$volta"; then
      echo "A pasta do serviço voltou ao commit que está no ar ($volta): um reboot sobe o mesmo Nexus." >&2
    else
      echo "AVISO: não deu para voltar a pasta ao commit que está no ar ($volta); ela segue em $(como git rev-parse --short HEAD), que não passou na conferência. Não reinicie o serviço até resolver." >&2
    fi
  fi
}

# 1. o commit novo numa pasta temporária, fora da do serviço (do dono do clone; legível pelo dono do .venv)
CONFERIDA="$(como mktemp -d)"
trap 'rm -rf "$CONFERIDA"' EXIT
como git archive --format=tar -o "$CONFERIDA/arvore.tar" "$alvo_completo"
como tar -xf "$CONFERIDA/arvore.tar" -C "$CONFERIDA"
rm -f "$CONFERIDA/arvore.tar"
chmod 755 "$CONFERIDA"

# 2. sempre, antes de todo restart: sem isto, a dependência que faltou numa rodada nunca mais era instalada
echo "Instalando as dependências do requirements.txt do commit $alvo..."
if ! no_venv .venv/bin/pip install -q -r "$CONFERIDA/requirements.txt"; then
  echo "ERRO: o pip falhou (o servidor alcança o pypi.org?). O serviço NÃO foi reiniciado e a pasta do serviço não andou: o Nexus de antes segue no ar." >&2
  voltar_ao_instalado
  echo "A próxima rodada tenta de novo." >&2
  exit 1
fi
echo "Conferindo se o Nexus do commit $alvo sobe..."
if ! no_venv .venv/bin/python -B "$CONFERIDA/deploy/conferir_boot.py"; then
  echo "ERRO: o Nexus do commit $alvo não subiria. O serviço NÃO foi reiniciado e a pasta do serviço não andou: o Nexus de antes segue no ar." >&2
  voltar_ao_instalado
  exit 1
fi

# 3. aprovado: só agora a pasta do serviço anda (até o commit conferido, nem um a mais), e o serviço reinicia
como git merge --ff-only --quiet "$alvo_completo"
echo "Reiniciando o serviço $SERVICO..."
systemctl restart "$SERVICO"
# gravada depois do restart, venha o /saude ou não: um commit que não sobe por outro motivo (o .env, por exemplo) não fica
# reiniciando a cada 2 min (cada boot relê a Aprovação no Fracttal, na cota dividida com o App); o próximo commit conserta
printf '%s\n' "$alvo" | como tee "$MARCA" >/dev/null
resp=""
for _ in $(seq 1 "$TENTATIVAS"); do
  sleep 2
  resp="$(curl -s --max-time 3 "http://127.0.0.1:$PORTA/saude" || true)"
  case "$resp" in
    *"\"$alvo\""*) echo "No ar: $resp"; exit 0 ;;
  esac
done
echo "ERRO: o /saude não respondeu com o commit $alvo (última resposta: ${resp:-nenhuma})." >&2
echo "Veja o log: sudo journalctl -u $SERVICO -n 50" >&2
exit 1
