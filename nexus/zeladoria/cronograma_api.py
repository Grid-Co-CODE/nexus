"""O link do cronograma de zeladoria (etapa 5, 06/11/2026): a função `cronograma-api` do Radar, servida pelo Nexus.

Para que serve: o app central da Grid Co. lê, por usina, o histórico de roçagem, limpeza de módulos e poda química e
os próximos serviços previstos (com as remarcações e o motivo). Não mostra quem executa (decisão do Radar: o cliente vê
só "GridCo"), nem valor, fornecedor ou documento.

De onde vem: do retrato que o próprio app publica na tabela `cronograma_publico` (id "cronograma") a cada salvamento,
porque as regras do cronograma vivem no app (`snapshotCronograma` do clone). Até a troca, o retrato é o da cópia do
Radar; depois, o que o Nexus grava (o gravador só regrava quando o cronograma muda: `gravacao.RETRATO`).

O acesso: GET com o header `x-api-key` igual à `NEXUS_ZELADORIA_CRONOGRAMA_CHAVE` (Base → Chaves das fontes → aba Nexus,
ou o .env). Sem a chave, 503 "ainda não configurada", como no Radar. A rota é pública (`auth.ROTAS_PUBLICAS`): quem chama
é outro sistema, sem login do Nexus. A mesma resposta da função do Radar, campo a campo, para quem já lia lá só trocar o
endereço. Em 06/11/2026 a chave nunca tinha sido posta no Supabase: ninguém lia o link ainda."""
from __future__ import annotations

import hmac
import unicodedata
from datetime import datetime, timedelta, timezone

CHAVE = "NEXUS_ZELADORIA_CRONOGRAMA_CHAVE"
FONTE = "Radar de Fornecedores — GridCo Zeladoria"
SERVICOS = ["Roçagem", "Limpeza de módulos", "Poda química"]
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "x-api-key, content-type",
        "Access-Control-Allow-Methods": "GET, OPTIONS"}
_BRT = timezone(timedelta(hours=-3))


def _sem(s) -> str:
    """Sem acento, minúscula e sem espaço nas pontas: a régua dos filtros do Radar."""
    t = unicodedata.normalize("NFD", str(s if s is not None else ""))
    return "".join(c for c in t if not unicodedata.combining(c)).lower().strip()


def _data(s) -> str | None:
    s = str(s or "")
    try:
        datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        return None
    return s if len(s) == 10 else None


def chave_confere(esperada: str | None, enviada: str | None) -> bool:
    return bool(esperada and enviada) and hmac.compare_digest(enviada.encode(), esperada.encode())


def responder(est: dict, args, agora: datetime | None = None) -> tuple[int, dict]:
    """(status, corpo) do link, com a chave já conferida. `args` = os parâmetros do GET (usina, cliente, uf,
    historico_desde)."""
    agora = agora or datetime.now(timezone.utc)
    linha = next((l for l in est["abas"].get("cronograma_publico", []) if str(l.get("id")) == "cronograma"), None)
    snap = (linha or {}).get("dados")
    if not isinstance(snap, dict):
        return 503, {"erro": "Cronograma ainda não publicado. Abra a Zeladoria no Nexus uma vez para publicar."}
    f_usina, f_cliente, f_uf = _sem(args.get("usina")), _sem(args.get("cliente")), _sem(args.get("uf"))
    desde = _data(args.get("historico_desde"))
    hoje = agora.astimezone(_BRT).date().isoformat()
    usinas = []
    for u in snap.get("usinas") if isinstance(snap.get("usinas"), list) else []:
        if not isinstance(u, dict):
            continue
        if (f_usina and f_usina not in _sem(u.get("usina"))) or (f_cliente and _sem(u.get("cliente")) != f_cliente) \
                or (f_uf and _sem(u.get("uf")) != f_uf):
            continue
        proximos = []
        for p in u.get("proximos") or []:
            situacao = "em_execucao" if p.get("iniciado") else ("confirmado" if p.get("confirmado") else "previsto")
            resto = {k: v for k, v in p.items() if k not in ("iniciado", "confirmado")}
            proximos.append({**resto, "situacao": situacao, "atrasado": bool(p.get("fim") and p["fim"] < hoje)})
        usinas.append({**u, "historico": [h for h in u.get("historico") or [] if not desde or (h.get("data") and
                                                                                              h["data"] >= desde)],
                       "proximos": proximos})
    return 200, {"fonte": FONTE, "atualizado_em": linha.get("atualizado_em"),
                 "consultado_em": agora.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                 "servicos": SERVICOS, "total_usinas": len(usinas), "usinas": usinas}
