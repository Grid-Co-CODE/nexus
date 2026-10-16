"""Os motivos das tarefas do PCM e a lista do backoffice (16/10/2026).

Levi, 16/10/2026, com a lista de 11 motivos (de "Engenharia - Tarefas originadas com cunho que envolve a engenharia" a
"Pendente recurso - Quando estiver pendente sobressalente, peça ou outro item, detalhes em observação") e, sobre o
backoffice, "Quando a OS estiver atrelada como responsável para alguém do time de backoffice, desconsiderar para a
programação da semana". As decisões dele, uma a uma:
- o motivo não vai ao Fracttal: mora no Nexus;
- vale por TAREFA, e é UM por tarefa ("Um só por tarefa": marcar outro troca o anterior);
- marcam e tiram o PCM, os supervisores (setor Responsáveis UFV) e o administrador, no Nexus, e o técnico pelo App de
  Campo, com qualquer motivo, valendo na hora ("Sim, e já vale"; `motivos_app.py`); o cadastro dos motivos é do
  administrador e do setor PCM;
- os motivos de espera (os quatro "Aguardando", Condições Climáticas Adversas e Pendente recurso) TIRAM a tarefa da
  programação: a geração não a programa e, na semana em curso, o robô do PCM apaga as linhas dela e não a reinclui;
- o painel "Fora da programação" mostra só esses, com o filtro Motivo, e a tarefa finalizada no Fracttal sai dele
  sozinha (a marca fica no histórico);
- marca-se no Quadro da semana (a janela da OS) e no painel, pelo número da OS;
- a OS do backoffice fica fora da geração e o robô não a inclui como OS nova; não aparece no painel nem no App. A lista
  é fixa no Nexus, editável no Gerar a semana, e vai ao robô em claro ("precisa disso não, faz o simples").

O dado (livro `nexus_pcm_motivos`, registrado em `nexus/dados/catalogo.py`; regras em `nexus/dados/CLAUDE.md`):
- `dim_motivo`: 1 linha = 1 motivo do cadastro (`motivo_id` 1, 2, 3...). Excluir marca `excluido = sim` e o ID nunca
  volta: as marcas antigas continuam apontando para ele, e deixam de valer. Antes da 1ª gravação vale o
  CADASTRO_INICIAL (os 11 do pedido, na ordem dele), que entra no banco junto com a 1ª gravação.
- `fato_decisao_motivo`: 1 linha = 1 decisão sobre o motivo de 1 tarefa: marcar (`motivo_id`) ou tirar (vazio). Só
  acrescenta; vale a última de cada tarefa (`item_id`).
- `fato_decisao_backoffice`: 1 linha = 1 decisão de pôr ou tirar 1 nome da lista do backoffice; vale a última de cada
  nome (`nome_hmac`).
A tarefa, o nome, a usina, a observação e quem decidiu vão só CIFRADOS (o Cofre, a chave do cadastro): a API do banco
tem leitura aberta (regra 8). Em claro: a OS, o código do ativo e o `equipamento_id`, o `tarefa_chave` (a mesma conta
da programação e do fechamento) e o código de quem decidiu (no Nexus, o do e-mail do login; pelo App, o do técnico:
`motivos_app.py`). Gravar troca o livro inteiro, sempre com as TRÊS abas
(gravar sem uma a apagaria), relido do banco antes (leitura que falha não grava), uma gravação por vez neste processo.

A tarefa = OS + código do ativo + nome (`item_id`). A marca pelo número da OS (painel) vem da Gestão PCM, que não traz o
código do ativo: vale para a tarefa daquele nome em TODOS os ativos da OS (código vazio). Na conta, a marca do ativo vence
a da OS (`motivo_de`).

O que vai ao motor e ao robô: o `Fora_da_programacao.json` (`arquivo`), na pasta de cada rodada (o motor) e na raiz do
repositório do PCM (o robô e o App de Campo, `publicar_arquivo`): o cadastro, as tarefas com motivo (sem a observação e
sem quem marcou: o repositório é público) e os nomes do backoffice.
"""
import hashlib
import hmac
import json
import logging
import threading
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..dados import fatos as D
from ..dados import livros
from ..dados.equipamento import canon, equipamento_id

log = logging.getLogger(__name__)

LIVRO, NOME_LIVRO = "nexus_pcm_motivos", "Nexus · motivos das tarefas do PCM e o backoffice"
ABA_MOTIVO, ABA_MARCA, ABA_BACKOFFICE = "dim_motivo", "fato_decisao_motivo", "fato_decisao_backoffice"
ABAS = (ABA_MOTIVO, ABA_MARCA, ABA_BACKOFFICE)
CAB_MOTIVO = ("motivo_id", "nome", "descricao", "tira_da_programacao", "criado_em", "alterado_em", "excluido",
              "alterado_por_hmac")
CAB_MARCA = ("decidida_em", "data_id", "item_id", "os", "codigo_ativo", "equipamento_id", "tarefa_chave", "motivo_id",
             "semana", "origem", "decidida_por_hmac", "dados_cifrados")
CAB_BACKOFFICE = ("decidida_em", "data_id", "nome_hmac", "na_lista", "decidida_por_hmac", "dados_cifrados")
CABS = {ABA_MOTIVO: CAB_MOTIVO, ABA_MARCA: CAB_MARCA, ABA_BACKOFFICE: CAB_BACKOFFICE}
ARQUIVO = "Fora_da_programacao.json"
VERSAO_ARQUIVO = 1
NOME_MIN, NOME_MAX, DESCRICAO_MAX, OBS_MAX, PESSOA_MAX = 2, 60, 300, 500, 80
TTL_S = 60
ORIGENS = ("quadro", "painel", "app")       # app: o técnico pelo App de Campo (motivos_app.py)
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()
_CACHE: dict = {}

# Os 11 do pedido (Levi, 16/10/2026), na ordem e com o texto dele: (nome, descrição, tira da programação). Os que tiram
# são os que ele escolheu ("Aguardando e clima tiram da semana": os quatro Aguardando, Condições Climáticas e Pendente
# recurso); Prioridade não muda a geração.
CADASTRO_INICIAL = (
    ("Engenharia", "Tarefas originadas com cunho que envolve a engenharia, para o time backoffice ou para o time de "
                   "campo com auxílio da engenharia backoffice.", False),
    ("Chamados (garantia)", "Tarefas originadas com cunho de garantia, para o time de backoffice (controle) ou para o "
                            "time de campo.", False),
    ("Performance", "Tarefas originadas com cunho que envolve a performance, para o time de backoffice ou para o time "
                    "de campo.", False),
    ("Aguardando Cliente", "", True),
    ("Aguardando Concessionária", "", True),
    ("Aguardando Material", "", True),
    ("Aguardando Fabricante/Terceiro", "", True),
    ("Condições Climáticas Adversas", "", True),
    ("Prioridade", "Prioridades a pedido do cliente.", False),
    ("Sinistro", "Casos de furto, incêndio, raios, vendaval ou outros casos anormais.", False),
    ("Pendente recurso", "Quando estiver pendente sobressalente, peça ou outro item, detalhes em observação.", True),
)


class Recusada(ValueError):
    """Nada foi gravado: o texto diz por quê, para a tela mostrar."""


# ── a tarefa e o nome ─────────────────────────────────────────────────────────────────────────────────────────
def norm(s) -> str:
    """Sem acento, sem caixa, espaço único: a mesma conta do `tarefa_chave` (e a do robô do PCM no arquivo)."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def os_de(v) -> str:
    try:
        return str(int(float(v)))
    except (TypeError, ValueError):
        return str(v or "").strip()


def item_id(os_, codigo, tarefa) -> str:
    """A tarefa em qualquer máquina: OS + código do ativo (canônico: maiúsculo, sem espaço) + nome normalizado. Código
    vazio = a marca da tarefa em todos os ativos da OS (a do painel, pela Gestão PCM)."""
    chave = f"{os_de(os_)}|{canon(codigo)}|{norm(tarefa)}"
    return hashlib.sha1(chave.encode("utf-8")).hexdigest()[:16]


def nome_hmac(chave: str | None, nome) -> str | None:
    """O código do nome do backoffice (HMAC com a NEXUS_PESSOA_HMAC): o nome não vai em claro ao banco, e o código
    junta as decisões do mesmo nome escrito com ou sem acento."""
    n = norm(nome)
    if not chave or not n:
        return None
    return hmac.new(chave.encode("utf-8"), f"backoffice|{n}".encode("utf-8"), hashlib.sha256).hexdigest()[:24]


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def _data_id(d: datetime) -> int:
    return int(d.astimezone(_BRT).strftime("%Y%m%d"))


def _brt(iso) -> datetime | None:
    try:
        return datetime.fromisoformat(str(iso or "").replace("Z", "+00:00")).astimezone(_BRT)
    except ValueError:
        return None


def _sim(v) -> bool:
    return D._txt(v).lower() in ("sim", "1", "true", "s")


# ── o livro: o banco, ou um arquivo na cópia de prova ─────────────────────────────────────────────────────────
def _arquivo_local(cfg) -> Path | None:
    p = cfg.get("NEXUS_PCM_MOTIVOS_ARQUIVO")
    return Path(p) if p else None


def _banco(cfg):
    from ..cadastro.ligacoes import BASE_API
    base = str(cfg.get("GRIDCO_DB_API") or BASE_API).rstrip("/")
    sessao = None
    try:
        from flask import current_app
        sessao = current_app.extensions.get("nexus_dados_sessao")
    except RuntimeError:            # fora de um pedido (a ferramenta da foto): sessão própria
        pass
    if sessao is None:
        import requests
        sessao = requests.Session()
    return base, sessao


def _ler_cru(cfg) -> dict:
    """{aba: [linhas]} das três abas, lidas agora. Livro que ainda não existe = vazio; erro de leitura sobe. Teste sem o
    arquivo nunca vai à rede (vale vazio)."""
    loc = _arquivo_local(cfg)
    if loc is not None:
        try:
            d = json.loads(loc.read_text(encoding="utf-8"))
        except FileNotFoundError:
            d = {}
        return {a: [dict(x) for x in d.get(a) or []] for a in ABAS}
    if cfg.get("TESTING"):
        return {a: [] for a in ABAS}
    base, sessao = _banco(cfg)
    a = livros.abas(base, sessao, LIVRO)
    return {aba: (list(livros._linhas(base, sessao, a[aba])) if aba in a else []) for aba in ABAS}


def _gravar_cru(cfg, tabelas: dict) -> None:
    """Troca o livro inteiro (as três abas) e confere. Na cópia de prova, o arquivo."""
    vazio = (lambda v: None if v in ("", None) else v)      # noqa: E731
    linhas = {aba: [[vazio(x.get(c)) for c in CABS[aba]] for x in tabelas[aba]] for aba in ABAS}
    loc = _arquivo_local(cfg)
    if loc is not None:
        loc.parent.mkdir(parents=True, exist_ok=True)
        tmp = loc.with_suffix(".tmp")
        tmp.write_text(json.dumps({aba: [dict(zip(CABS[aba], l)) for l in linhas[aba]] for aba in ABAS},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(loc)
        return
    token = cfg.get("GRIDCO_SQL_TOKEN")
    if not token:
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN): nada foi gravado.")
    base, sessao = _banco(cfg)
    livros.publicar(LIVRO, NOME_LIVRO, {aba: (list(CABS[aba]), linhas[aba]) for aba in ABAS},
                    base=base, token=token, sessao=sessao)


# ── a leitura ─────────────────────────────────────────────────────────────────────────────────────────────────
def _motivo(x: dict) -> dict | None:
    mid = D._id(x.get("motivo_id"))
    if not mid:
        return None
    return {"id": mid, "nome": " ".join(D._txt(x.get("nome")).split()), "descricao": D._txt(x.get("descricao")),
            "tira": _sim(x.get("tira_da_programacao")), "criado_em": D._txt(x.get("criado_em")),
            "alterado_em": D._txt(x.get("alterado_em")), "excluido": _sim(x.get("excluido")),
            "alterado_por_hmac": D._txt(x.get("alterado_por_hmac"))}


def cadastro_inicial() -> list[dict]:
    return [{"id": i, "nome": n, "descricao": d, "tira": t, "criado_em": "", "alterado_em": "", "excluido": False,
             "alterado_por_hmac": ""} for i, (n, d, t) in enumerate(CADASTRO_INICIAL, start=1)]


def _estado(cru: dict) -> dict:
    motivos = [m for m in (_motivo(x) for x in cru[ABA_MOTIVO]) if m]
    return {"motivos": motivos or cadastro_inicial(), "inicial": not motivos,
            "marcas": [dict(x) for x in cru[ABA_MARCA] if D._txt(x.get("item_id"))],
            "backoffice": [dict(x) for x in cru[ABA_BACKOFFICE] if D._txt(x.get("nome_hmac"))]}


def ler(cfg, forcar: bool = False) -> dict:
    """{"motivos", "inicial", "marcas", "backoffice", "erro", "lido_em"}: o livro, guardado por 1 minuto. Leitura que
    falha devolve a última boa com `velha` e o erro; sem nenhuma, o cadastro inicial e nenhuma marca, com o erro (a tela
    não deixa gravar sem saber o que há no banco)."""
    chave = str(_arquivo_local(cfg) or "banco")
    g = _CACHE.get(chave)
    if g and not forcar and time.time() - g["lido_em"] < TTL_S:
        return g
    try:
        e = _estado(_ler_cru(cfg))
    except Exception as ex:      # noqa: BLE001 — banco fora, rede: a tela diz e não deixa gravar
        erro = f"{type(ex).__name__}: {str(ex)[:160]}"
        if g:
            return dict(g, erro=erro, velha=True)
        return dict(_estado({a: [] for a in ABAS}), erro=erro, lido_em=None)
    g = dict(e, erro="", lido_em=time.time())
    _CACHE[chave] = g
    return g


def limpar() -> None:
    _CACHE.clear()


def ativos(est: dict) -> list[dict]:
    """Os motivos que valem (sem os excluídos), na ordem do cadastro."""
    return [m for m in est["motivos"] if not m["excluido"]]


def _cofre(cfg):
    chave = cfg.get("NEXUS_CHAVE_CADASTRO")
    if not chave:
        raise Recusada("Este Nexus não tem a chave do cadastro (NEXUS_CHAVE_CADASTRO): a tarefa e a observação vão "
                       "cifradas, e sem ela nada é gravado.")
    from ..cadastro.cifra import Cofre
    return Cofre(chave)


def _cofre_ou_nada(cfg):
    try:
        return _cofre(cfg)
    except Exception:        # noqa: BLE001 — sem a chave, as marcas saem sem o texto (contadas como ilegíveis)
        return None


def _ctx_marca(iid: str, quando: str) -> str:
    return f"pcm/motivos/{iid}/{quando}"


def _ctx_backoffice(nh: str, quando: str) -> str:
    return f"pcm/backoffice/{nh}/{quando}"


def vigentes(cfg, est: dict) -> dict:
    """{item_id: marca}: a última decisão de cada tarefa, quando ela marca um motivo que vale (não excluído). A marca
    traz a OS, o código, a tarefa e o resto do que foi cifrado (usina, cliente, tipo, observação, quem), o motivo, desde
    quando a tarefa está com ele (a 1ª decisão da sequência com o mesmo motivo: trocar só a observação não reinicia) e a
    hora da última decisão. Linha que não abre com a chave conta em `_ilegiveis` e não entra."""
    validos = {m["id"]: m for m in ativos(est)}
    por_item: dict[str, list[dict]] = {}
    for x in sorted(est["marcas"], key=lambda x: D._txt(x.get("decidida_em"))):
        por_item.setdefault(D._txt(x.get("item_id")), []).append(x)
    cofre = _cofre_ou_nada(cfg)
    out, ilegiveis = {}, 0
    for iid, lst in por_item.items():
        ult = lst[-1]
        mid = D._id(ult.get("motivo_id"))
        if not mid or mid not in validos:
            continue
        inicio = ult
        for x in reversed(lst[:-1]):
            if D._id(x.get("motivo_id")) != mid:
                break
            inicio = x
        quando = D._txt(ult.get("decidida_em"))
        try:
            corpo = json.loads(cofre.decifrar(D._txt(ult.get("dados_cifrados")), _ctx_marca(iid, quando)))
        except Exception:        # noqa: BLE001 — sem a chave, cifra de outra chave ou linha mexida
            ilegiveis += 1
            continue
        m = validos[mid]
        out[iid] = {"item_id": iid, "os": os_de(ult.get("os")), "codigo": D._txt(corpo.get("codigo")),
                    "tarefa": D._txt(corpo.get("tarefa")), "usina": D._txt(corpo.get("usina")),
                    "cliente": D._txt(corpo.get("cliente")), "tipo": D._txt(corpo.get("tipo")),
                    "cluster": D._txt(corpo.get("cluster")), "data_prog": D._txt(corpo.get("data_prog")),
                    "obs": D._txt(corpo.get("obs")), "quem": D._txt(corpo.get("quem")),
                    "motivo_id": mid, "motivo": m["nome"], "tira": m["tira"],
                    "desde": D._txt(inicio.get("decidida_em")), "quando": quando,
                    "semana": D._txt(ult.get("semana")), "origem": D._txt(ult.get("origem")),
                    "quem_hmac": D._txt(ult.get("decidida_por_hmac"))}
    if ilegiveis:
        out["_ilegiveis"] = ilegiveis       # type: ignore[assignment]
    return out


def indice(vig: dict) -> dict:
    """{(os, código canônico, nome normalizado): marca} para achar a marca de uma linha da semana."""
    return {(m["os"], canon(m["codigo"]), norm(m["tarefa"])): m for k, m in vig.items() if not k.startswith("_")}


def motivo_de(idx: dict, os_, codigo, tarefa) -> dict | None:
    """A marca que vale para a linha: a do ativo; sem ela, a da tarefa em todos os ativos da OS (a do painel)."""
    o, t = os_de(os_), norm(tarefa)
    return idx.get((o, canon(codigo), t)) or idx.get((o, "", t))


def backoffice(cfg, est: dict) -> list[dict]:
    """[{"nome", "desde", "nome_hmac"}]: os nomes na lista agora (a última decisão de cada nome), pelo nome."""
    ult: dict[str, dict] = {}
    for x in sorted(est["backoffice"], key=lambda x: D._txt(x.get("decidida_em"))):
        ult[D._txt(x.get("nome_hmac"))] = x
    cofre = _cofre_ou_nada(cfg)
    out = []
    for nh, x in ult.items():
        if not _sim(x.get("na_lista")):
            continue
        quando = D._txt(x.get("decidida_em"))
        try:
            corpo = json.loads(cofre.decifrar(D._txt(x.get("dados_cifrados")), _ctx_backoffice(nh, quando)))
        except Exception:        # noqa: BLE001
            continue
        out.append({"nome": D._txt(corpo.get("nome")), "desde": quando, "nome_hmac": nh})
    return sorted(out, key=lambda b: norm(b["nome"]))


# ── gravar ────────────────────────────────────────────────────────────────────────────────────────────────────
def _quem(cfg, usuario: dict | None) -> tuple[str, str]:
    """(o código de quem decide, o nome que a tela mostra). A senha de administrador não diz quem é: vai sem código."""
    from ..campo.ligacao_cadastro import codigo_da_pessoa
    email = str((usuario or {}).get("email") or "").strip().lower()
    nome = " ".join(str((usuario or {}).get("nome") or "").split()) or email or "administrador (senha)"
    return (codigo_da_pessoa(cfg.get("NEXUS_PESSOA_HMAC"), email) or "") if email else "", nome


def _gravar(cfg, mudar):
    """Relê o livro, aplica `mudar(tabelas) -> (resultado, mudou)` e, se mudou, grava as três abas. A 1ª gravação leva
    o cadastro inicial junto (antes dela ele só existe no código)."""
    with _TRAVA:
        try:
            cru = _ler_cru(cfg)
        except Exception as ex:  # noqa: BLE001
            raise Recusada(f"Não consegui ler os motivos no banco ({type(ex).__name__}): nada foi gravado, para não "
                           "apagar o que já está lá.") from ex
        if not [m for m in (_motivo(x) for x in cru[ABA_MOTIVO]) if m]:
            cru[ABA_MOTIVO] = [{"motivo_id": m["id"], "nome": m["nome"], "descricao": m["descricao"],
                                "tira_da_programacao": "sim" if m["tira"] else "não", "criado_em": _iso(_agora()),
                                "alterado_em": "", "excluido": "", "alterado_por_hmac": ""}
                               for m in cadastro_inicial()]
        resultado, mudou = mudar(cru)
        if mudou:
            _gravar_cru(cfg, cru)
        _CACHE.pop(str(_arquivo_local(cfg) or "banco"), None)
        return resultado


def marcar(cfg, tarefa: dict, motivo_id, obs: str, usuario: dict | None, semana: str = "",
           origem: str = "quadro", quem_hmac: str | None = None) -> dict:
    """Marca o motivo de uma tarefa (ou o tira: `motivo_id` None). `tarefa` = {os, codigo, tarefa, usina, cliente, tipo}
    tirada da SEMANA ou da Gestão PCM pelo servidor, nunca da página. Um motivo por tarefa: marcar outro troca. Marcar o
    mesmo motivo com a mesma observação não grava. `quem_hmac`: o código de quem marcou quando ele chega pronto (o
    técnico pelo App, que não tem e-mail no pedido). {"gravou", "marca"}."""
    os_s = os_de(tarefa.get("os"))
    # o texto EXATO da linha da programação (o App de Campo casa OS|ativo|nome como estão no banco_dados.json); a
    # identidade da tarefa (`item_id`) e a comparação do motor e do robô seguem normalizadas
    nome_t = str(tarefa.get("tarefa") or "").strip()
    codigo = str(tarefa.get("codigo") or "").strip()
    if not os_s.isdigit() or not nome_t:
        raise Recusada("A tarefa não foi achada: atualize a página.")
    if origem not in ORIGENS:
        raise Recusada("origem desconhecida")
    obs = "\n".join(" ".join(l.split()) for l in str(obs or "").strip().splitlines()).strip()
    if len(obs) > OBS_MAX:
        raise Recusada(f"A observação passou de {OBS_MAX} caracteres.")
    mid = D._id(motivo_id) if motivo_id not in (None, "", 0, "0") else None
    cofre = _cofre(cfg)
    cod_quem, nome_quem = _quem(cfg, usuario)
    if quem_hmac:
        cod_quem = quem_hmac
    iid = item_id(os_s, codigo, nome_t)

    def mudar(cru):
        est = _estado(cru)
        if mid and mid not in {m["id"] for m in ativos(est)}:
            raise Recusada("Esse motivo não existe mais (alguém mudou o cadastro): atualize a página.")
        atual = vigentes(cfg, est).get(iid)
        if not mid and not atual:
            return {"gravou": False, "marca": None}, False
        if mid and atual and atual["motivo_id"] == mid and atual["obs"] == obs:
            return {"gravou": False, "marca": atual}, False
        agora = _agora()
        quando = _iso(agora)
        corpo = {"tarefa": nome_t, "codigo": codigo, "usina": str(tarefa.get("usina") or "").strip(),
                 "cluster": str(tarefa.get("cluster") or "").strip(),
                 "data_prog": str(tarefa.get("data_prog") or "").strip(),
                 "cliente": str(tarefa.get("cliente") or "").strip(), "tipo": str(tarefa.get("tipo") or "").strip(),
                 "obs": obs if mid else "", "quem": nome_quem}
        cru[ABA_MARCA].append({
            "decidida_em": quando, "data_id": _data_id(agora), "item_id": iid, "os": int(os_s),
            "codigo_ativo": canon(codigo) or "", "equipamento_id": equipamento_id(codigo) if codigo else None,
            "tarefa_chave": D.tarefa_chave(nome_t), "motivo_id": mid, "semana": semana or "", "origem": origem,
            "decidida_por_hmac": cod_quem,
            "dados_cifrados": cofre.cifrar(json.dumps(corpo, ensure_ascii=False), _ctx_marca(iid, quando))})
        return {"gravou": True, "marca": vigentes(cfg, _estado(cru)).get(iid)}, True

    r = _gravar(cfg, mudar)
    log.info("Motivos do PCM: OS %s, %s %s, por %s.", os_s, "motivo" if mid else "tirou o motivo", mid or "",
             nome_quem if not cod_quem else cod_quem[:6])
    return r


def _nome_motivo(nome) -> str:
    n = " ".join(str(nome or "").split())
    if len(n) < NOME_MIN:
        raise Recusada("Escreva o nome do motivo.")
    if len(n) > NOME_MAX:
        raise Recusada(f"O nome do motivo tem no máximo {NOME_MAX} letras.")
    if "@" in n:
        raise Recusada("O nome do motivo não pode ter e-mail: o banco tem leitura aberta.")
    return n


def _descricao(d) -> str:
    d = " ".join(str(d or "").split())
    if len(d) > DESCRICAO_MAX:
        raise Recusada(f"A descrição tem no máximo {DESCRICAO_MAX} letras.")
    if "@" in d:
        raise Recusada("A descrição não pode ter e-mail: o banco tem leitura aberta.")
    return d


def cadastro(cfg, acao: str, usuario: dict | None, motivo_id=None, nome=None, descricao=None,
             tira=None) -> dict:
    """O cadastro dos motivos (administrador e setor PCM): `acao` criar | editar | excluir. Excluir não apaga: marca
    `excluido = sim` e o ID não volta; as tarefas com ele perdem o motivo (a confirmação da tela diz quantas)."""
    cod_quem, _ = _quem(cfg, usuario)
    mid = D._id(motivo_id) if motivo_id not in (None, "") else None

    def mudar(cru):
        motivos = [m for m in (_motivo(x) for x in cru[ABA_MOTIVO]) if m]
        agora = _iso(_agora())
        if acao == "criar":
            n, d = _nome_motivo(nome), _descricao(descricao)
            if any(not m["excluido"] and norm(m["nome"]) == norm(n) for m in motivos):
                raise Recusada(f"Já existe o motivo {n}.")
            novo = {"motivo_id": max((m["id"] for m in motivos), default=0) + 1, "nome": n, "descricao": d,
                    "tira_da_programacao": "sim" if tira else "não", "criado_em": agora, "alterado_em": "",
                    "excluido": "", "alterado_por_hmac": cod_quem}
            cru[ABA_MOTIVO].append(novo)
            return {"acao": acao, "motivo_id": novo["motivo_id"], "nome": n}, True
        linha = next((x for x in cru[ABA_MOTIVO] if D._id(x.get("motivo_id")) == mid and not _sim(x.get("excluido"))),
                     None)
        if linha is None:
            raise Recusada("Esse motivo não existe mais (alguém mudou o cadastro): atualize a página.")
        if acao == "editar":
            n, d = _nome_motivo(nome), _descricao(descricao)
            if any(not m["excluido"] and m["id"] != mid and norm(m["nome"]) == norm(n) for m in motivos):
                raise Recusada(f"Já existe o motivo {n}.")
            t = "sim" if tira else "não"
            if (" ".join(D._txt(linha.get("nome")).split()) == n and D._txt(linha.get("descricao")) == d
                    and ("sim" if _sim(linha.get("tira_da_programacao")) else "não") == t):
                return {"acao": acao, "motivo_id": mid, "nome": n, "mudou": False}, False
            linha.update(nome=n, descricao=d, tira_da_programacao=t, alterado_em=agora, alterado_por_hmac=cod_quem)
            return {"acao": acao, "motivo_id": mid, "nome": n, "mudou": True}, True
        if acao == "excluir":
            linha.update(excluido="sim", alterado_em=agora, alterado_por_hmac=cod_quem)
            return {"acao": acao, "motivo_id": mid, "nome": D._txt(linha.get("nome"))}, True
        raise Recusada("ação desconhecida")

    r = _gravar(cfg, mudar)
    log.info("Motivos do PCM: cadastro %s %s.", acao, r.get("motivo_id"))
    return r


def backoffice_definir(cfg, nome: str, na_lista: bool, usuario: dict | None) -> dict:
    """Põe (`na_lista`) ou tira um nome da lista do backoffice. O nome é o do responsável da OS no Fracttal; casa sem
    acento e sem caixa. Pôr quem já está, ou tirar quem não está, não grava."""
    n = " ".join(str(nome or "").split())
    if len(n) < 3:
        raise Recusada("Escreva o nome como ele aparece no Fracttal (responsável da OS).")
    if len(n) > PESSOA_MAX or "@" in n:
        raise Recusada("Escreva só o nome da pessoa, sem e-mail.")
    chave = cfg.get("NEXUS_PESSOA_HMAC")
    nh = nome_hmac(chave, n)
    if not nh:
        raise Recusada("Este Nexus não tem a chave do código da pessoa (NEXUS_PESSOA_HMAC): nada foi gravado.")
    cofre = _cofre(cfg)
    cod_quem, _ = _quem(cfg, usuario)

    def mudar(cru):
        est = _estado(cru)
        esta = any(b["nome_hmac"] == nh for b in backoffice(cfg, est))
        if esta == bool(na_lista):
            return {"gravou": False, "nome": n}, False
        agora = _agora()
        quando = _iso(agora)
        cru[ABA_BACKOFFICE].append({
            "decidida_em": quando, "data_id": _data_id(agora), "nome_hmac": nh, "na_lista": "sim" if na_lista else "não",
            "decidida_por_hmac": cod_quem,
            "dados_cifrados": cofre.cifrar(json.dumps({"nome": n}, ensure_ascii=False), _ctx_backoffice(nh, quando))})
        return {"gravou": True, "nome": n}, True

    r = _gravar(cfg, mudar)
    log.info("Motivos do PCM: backoffice, %s um nome.", "pôs" if na_lista else "tirou")
    return r


# ── o arquivo do motor, do robô e do App ──────────────────────────────────────────────────────────────────────
def arquivo(cfg, est: dict | None = None) -> dict:
    """O `Fora_da_programacao.json`: o cadastro (os motivos que valem), as tarefas com motivo e os nomes do
    backoffice. Sem observação e sem quem marcou (o repositório do PCM é público). `hash` = o sha256 do conteúdo sem a
    hora, para saber se o arquivo do repositório está em dia.

    O contrato com o App de Campo (16/10/2026, o chat do App): o arquivo é o estado de AGORA (a tarefa desmarcada sai);
    os, codigo e tarefa como nas linhas do banco_dados.json (os em texto; código vazio = a tarefa em todos os ativos da
    OS); usina e cluster (já públicos no banco_dados.json) para o App agrupar; data_prog = o dia em que a tarefa estava na
    agenda quando foi marcada (vazio na pendente e na marca pela OS); motivo = o id; desde e gerado_em em ISO. Motivo
    tirado do cadastro tira as marcas dele: todo motivo das tarefas está em `motivos`."""
    est = est or ler(cfg)
    vig = vigentes(cfg, est)
    motivos = [{"id": m["id"], "nome": m["nome"], "descricao": m["descricao"], "tira_da_programacao": m["tira"],
                "ativo": True}
               for m in ativos(est)]
    tarefas = sorted(({"os": m["os"], "codigo": m["codigo"], "tarefa": m["tarefa"], "usina": m["usina"],
                       "cluster": m["cluster"], "data_prog": m["data_prog"], "motivo": m["motivo_id"],
                       "tira_da_programacao": m["tira"], "desde": (_brt(m["desde"]) or _agora()).strftime("%Y-%m-%d")}
                      for k, m in vig.items() if not k.startswith("_")),
                     key=lambda t: (int(t["os"]) if t["os"].isdigit() else 0, norm(t["tarefa"]), canon(t["codigo"])))
    conteudo = {"motivos": motivos, "tarefas": tarefas, "backoffice": [b["nome"] for b in backoffice(cfg, est)]}
    h = hashlib.sha256(json.dumps(conteudo, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return dict({"versao": VERSAO_ARQUIVO, "gerado_em": datetime.now(_BRT).isoformat(timespec="seconds"), "hash": h},
                **conteudo)


def bytes_do_arquivo(dados: dict) -> bytes:
    return (json.dumps(dados, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


def materializar(cfg, pasta: Path, trabalho: Path) -> dict:
    """Escreve o arquivo na pasta da rodada (o motor lê) e devolve o carimbo do insumo. Lê o banco na hora; se ele não
    responder, vale a última cópia boa desta máquina (`trabalho`), com aviso; sem nenhuma, a rodada não sai: gerar sem
    as exclusões programaria a tarefa que o PCM tirou e a OS do backoffice."""
    copia = Path(trabalho) / ("ultimo_" + ARQUIVO)
    est = ler(cfg, forcar=True)
    aviso = ""
    if est.get("erro"):
        try:
            dados = json.loads(copia.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise Recusada(f"motivos e backoffice: o banco não respondeu ({est['erro']}) e não há cópia") from None
        aviso = f"o banco não respondeu ({est['erro']}): vale a cópia de {str(dados.get('gerado_em'))[:16]}"
    else:
        dados = arquivo(cfg, est)
        try:
            copia.parent.mkdir(parents=True, exist_ok=True)
            copia.write_bytes(bytes_do_arquivo(dados))
        except OSError:
            pass
    destino = Path(pasta) / ARQUIVO
    destino.write_bytes(bytes_do_arquivo(dados))
    fora = sum(1 for t in dados.get("tarefas") or [] if t.get("tira_da_programacao"))
    return {"nome": "Motivos e backoffice (Fora da programação)", "sha": hashlib.sha256(destino.read_bytes()).hexdigest()[:12],
            "atualizado": str(dados.get("gerado_em") or "")[:16],
            "detalhe": (f"{fora} {'tarefa' if fora == 1 else 'tarefas'} fora por motivo, "
                        f"{len(dados.get('backoffice') or [])} {'nome' if len(dados.get('backoffice') or []) == 1 else 'nomes'}"
                        " do backoffice" + (f"; {aviso}" if aviso else "")),
            "aviso": bool(aviso)}


def publicar_arquivo(cfg, est: dict | None = None) -> dict:
    """Grava o arquivo na raiz do repositório do PCM (o PUT do `publicar.py`), relê e confere. Igual ao que está lá
    (mesmo `hash`): não grava. {"commit", "hash", "igual"}; erro sobe (a marca já está no banco: a tela avisa)."""
    from . import publicar as PB
    dados = arquivo(cfg, est)
    with PB._trava:
        tok, _de_onde = PB.token(cfg)
        if not tok:
            raise Recusada("sem token do GitHub (NEXUS_PCM_GITHUB_TOKEN): o robô do PCM não recebe o arquivo")
        repo, ramo = PB.repositorio(cfg)
        s = PB._sessao(cfg)
        atual = PB._ler(s, tok, repo, ramo, ARQUIVO)
        if atual:
            try:
                if json.loads(atual["bytes"].decode("utf-8")).get("hash") == dados["hash"]:
                    return {"commit": "", "hash": dados["hash"], "igual": True}
            except ValueError:
                pass
        corpo = bytes_do_arquivo(dados)
        n = sum(1 for t in dados["tarefas"] if t["tira_da_programacao"])
        commit = PB._gravar(s, tok, repo, ramo, ARQUIVO, corpo,
                            f"chore: Nexus atualiza o que fica fora da programação ({n} "
                            f"{'tarefa' if n == 1 else 'tarefas'} por motivo, {len(dados['backoffice'])} do backoffice)")
        lido = PB._ler(s, tok, repo, ramo, ARQUIVO)
        if not lido or PB._sha256(lido["bytes"]) != PB._sha256(corpo):
            raise Recusada(f"o repositório não tem o arquivo enviado (commit {commit}); confira no GitHub")
    return {"commit": commit, "hash": dados["hash"], "igual": False}


_ESTADO_REPO: dict = {}
REPO_TTL_S = 120


def estado_no_repositorio(cfg, est: dict | None = None) -> dict:
    """O arquivo do repositório está em dia com o banco? {"em_dia", "existe", "gerado_em", "erro"}; lido no máximo a
    cada 2 minutos (é a API do GitHub)."""
    from . import publicar as PB
    dados = arquivo(cfg, est)
    g = _ESTADO_REPO.get("x")
    if not g or time.time() - g["t"] > REPO_TTL_S:
        g = {"t": time.time(), "hash": None, "gerado_em": "", "existe": False, "erro": ""}
        tok, _ = PB.token(cfg)
        if not tok:
            g["erro"] = "sem token do GitHub (NEXUS_PCM_GITHUB_TOKEN)"
        else:
            try:
                repo, ramo = PB.repositorio(cfg)
                lido = PB._ler(PB._sessao(cfg), tok, repo, ramo, ARQUIVO)
                if lido:
                    j = json.loads(lido["bytes"].decode("utf-8"))
                    g.update(existe=True, hash=j.get("hash"), gerado_em=str(j.get("gerado_em") or ""))
            except Exception as ex:      # noqa: BLE001 — rede, GitHub fora: a tela diz
                g["erro"] = f"não consegui ler o repositório do PCM ({type(ex).__name__})"
        _ESTADO_REPO["x"] = g
    return {"em_dia": bool(g["existe"]) and g["hash"] == dados["hash"], "existe": g["existe"],
            "gerado_em": g["gerado_em"], "erro": g["erro"], "vazio": not dados["tarefas"] and not dados["backoffice"]}


def esquecer_estado_no_repositorio() -> None:
    _ESTADO_REPO.clear()
