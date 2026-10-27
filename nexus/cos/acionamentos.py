"""Acionamentos e distribuidoras (26/10/2026): quem aciono e qual o canal da distribuidora desta UF?

Duas metades, duas fontes, nenhuma cópia:
- **Quem aciono** é do cadastro do Nexus (BD_Operações): o Supervisor de Campo da região da usina, o Responsável O&M, e o
  técnico, o eletricista e o mantenedor dela, com o contato que o cadastro guarda CIFRADO. Decifra-se só para a tela; o
  nome e o telefone não vão a log, a livro nem ao Andamento (regra da torre: nome e telefone de pessoa vêm do cadastro).
- **A distribuidora** é do Andamento da Ronda COS (`andamento.ler_distribuidoras`): a UC de cada usina (da planilha do
  cliente, uma por sub-usina), o canal de cada concessionária (o SMS de registro e o canal para abrir à mão, que a Ronda
  COS declara) e os chamados de 30 dias com o protocolo. Usina sem UC lá usa a concessionária do cadastro, sem UC.

A usina do Andamento liga ao cadastro pelo código (o `Ligador` dos fatos: código de duas usinas não liga, regra 4 da
camada de dados). A concessionária liga ao canal pela mesma chave da Ronda COS (`chave_da_concessionaria`); nome que não
casa fica "canal não levantado", sem chute.
"""
import json
import re
import unicodedata
from datetime import datetime

from ..campo import visao
from ..dados import fatos as D
from . import andamento as AND

# O estado do chamado à concessionária como a Ronda COS o grava (`chamados.regra.ts`), em palavras e no tom da casa.
ESTADOS_DO_CHAMADO = {
    "PENDENTE": ("pendente", "alerta"),
    "ENVIANDO": ("saindo", "info"),
    "ENVIADO": ("enviado, aguardando resposta", "info"),
    "PROTOCOLO": ("com protocolo", "ok"),
    "SEM_PROTOCOLO": ("sem protocolo", "alerta"),
    "FALHOU": ("falhou", "critico"),
    "DISPENSADO": ("dispensado", "neutro"),
}
# O que pede a mão do operador: os `ESTADOS_QUE_PEDEM_ACAO` da Ronda COS.
PEDEM_ACAO = ("PENDENTE", "SEM_PROTOCOLO", "FALHOU")
# O celular que manda o SMS sem sinal há 30 min: a mesma régua da faixa da Ronda COS ("sem sinal há 30 min, avisa").
SINAL_VELHO_MIN = 30
CONFIANCA = {"alta": "formato confirmado", "media": "formato de nota oficial", "baixa": "formato a confirmar"}

SUPERVISOR_DE_CAMPO = "Supervisor de Campo"
# (coluna do cadastro da usina, papel, o contato que a usina guarda para ele)
PAPEIS_DA_USINA = (("responsavel_om", "Responsável O&M", None),
                   ("tecnico_om", "Técnico", "contato_tecnico"),
                   ("eletricista_om", "Eletricista", "contato_eletricista"),
                   ("mantenedor_om", "Mantenedor", "contato_mantenedor"))


def chave_da_concessionaria(nome) -> str:
    """"CPFL PAULISTA" -> "CPFL_PAULISTA"; "Energisa MT" -> "ENERGISA_MT". A MESMA conta de `chaveDaConcessionaria` da
    Ronda COS (`chamados.regra.ts`): é por ela que o canal de lá casa com a concessionária do cadastro daqui."""
    s = unicodedata.normalize("NFD", str(nome or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).upper()
    return re.sub(r"[^A-Z0-9]+", "_", s).strip("_")


def _abrir(cofre, texto, contexto) -> dict:
    if not cofre or not texto:
        return {}
    try:
        return json.loads(cofre.decifrar(texto, contexto)) or {}
    except Exception:       # noqa: BLE001 — cifra de outra chave ou adulterada: sem contato
        return {}


def _tel(v) -> str:
    return " ".join(str(v or "").split())


def numero_para_discar(tel: str) -> str:
    """O número do link `tel:` (o celular disca com um toque): só os dígitos, com o 55 do Brasil quando vem sem ele. O
    template escreve o `tel:` literal: um href que começa por {{ }} seria lido como endereço do Nexus (test_prefixo)."""
    d = re.sub(r"\D", "", tel or "")
    if not d:
        return ""
    return f"+{d}" if d.startswith("55") and len(d) > 11 else f"+55{d}"


class Contatos:
    """Quem aciono em cada usina, decifrado do cadastro uma vez por pessoa."""

    def __init__(self, b, cofre):
        self.b, self.cofre = b, cofre
        self.pessoa = {D._id(p.get("pessoa_id")): p for p in b.pessoas if D._id(p.get("pessoa_id"))}
        self._tel_pessoa: dict = {}

    def telefone_da_pessoa(self, pid) -> str:
        """O corporativo, ou o pessoal (a regra do cadastro, `calculos.contato`)."""
        if pid not in self._tel_pessoa:
            s = _abrir(self.cofre, (self.pessoa.get(pid) or {}).get("sensivel_cifrado"), f"banco/pessoas/{pid}")
            self._tel_pessoa[pid] = _tel(s.get("telefone_corporativo")) or _tel(s.get("telefone_pessoal"))
        return self._tel_pessoa[pid]

    def da_usina(self, uid) -> list[dict]:
        """[{papel, nome, contato, link}]: o Supervisor de Campo da região (ou "vaga"), o Responsável O&M e o técnico, o
        eletricista e o mantenedor da usina. Sem a chave do cadastro, o papel com o número da pessoa e sem contato."""
        b = self.b
        u = b.por_id.get(uid) or {}
        sens = _abrir(self.cofre, u.get("sensivel_cifrado"), f"banco/usinas/{uid}")
        out = []
        r = b.info_regiao(b.regiao_da_usina(uid))
        sid = r.get("supervisor_id")
        if r.get("nome") and r["nome"] != visao.SEM_REGIAO:
            tel = self.telefone_da_pessoa(sid) if sid else ""
            out.append({"papel": SUPERVISOR_DE_CAMPO, "nome": r.get("supervisor") or "vaga", "contato": tel,
                        "discar": numero_para_discar(tel), "detalhe": r.get("nome", "")})
        for campo, papel, contato_campo in PAPEIS_DA_USINA:
            pid = D._id(u.get(f"{campo}_id"))
            if not pid:
                continue
            tel = (_tel(sens.get(contato_campo)) if contato_campo else "") or self.telefone_da_pessoa(pid)
            out.append({"papel": papel, "nome": b.nome_da_pessoa(pid, papel), "contato": tel,
                        "discar": numero_para_discar(tel), "detalhe": ""})
        return out


def _ativa(u: dict) -> bool:
    return (D._txt(u.get("excluido")).lower() != "sim"
            and D._txt(u.get("status")).upper() == visao.STATUS_OPERACAO)


def _sinal(g: dict | None, agora: datetime) -> dict:
    """O celular do SMS: com sinal, sem sinal há mais de 30 min, ou nunca deu sinal (o chamado é aberto à mão)."""
    visto = AND.instante((g or {}).get("visto_em"))
    if not visto:
        return {"tom": "neutro", "rotulo": "nunca deu sinal", "detalhe": "o chamado é aberto à mão", "visto": None}
    minutos = int((agora - visto).total_seconds() // 60)
    if minutos > SINAL_VELHO_MIN:
        return {"tom": "alerta", "rotulo": "sem sinal", "detalhe": f"desde {visto.strftime('%d/%m %H:%M')}", "visto": visto}
    return {"tom": "ok", "rotulo": "com sinal", "detalhe": f"visto às {visto.strftime('%H:%M')}", "visto": visto}


def painel(b, cofre, leituras: list, agora: datetime, cliente: str = "", uf: str = "", busca: str = "") -> dict:
    """O que a tela mostra. `b` é o cadastro (`visao._Base`), `leituras` as do Andamento (uma por cliente). As usinas
    em operação do cadastro, filtradas por cliente, UF e busca (nome, cidade ou código), com a distribuidora e quem
    acionar; os chamados de 30 dias; os canais das distribuidoras das usinas listadas."""
    canais: dict[str, dict] = {}
    ucs_do: dict[int, list] = {}
    sem_ligacao, chamados, gateways, erros = [], [], [], []
    for lt in leituras:
        if lt.erro:
            erros.append((lt.cliente, lt.erro, lt.velha))
        d = lt.dados
        if not d:
            continue
        for c in d.get("canais") or []:
            canais.setdefault(str(c.get("chave") or ""), c)
        uid_do_codigo = {}
        for u in d.get("usinas") or []:
            uid, _como = b.lig.usina(u.get("nome"), u.get("codigo"))
            uid_do_codigo[u.get("codigo")] = uid
            if not uid:
                if u.get("ucs"):
                    sem_ligacao.append({"cliente": lt.cliente, "usina": u.get("nome"), "codigo": u.get("codigo")})
                continue
            ucs_do.setdefault(uid, []).extend(u.get("ucs") or [])
        for c in d.get("chamados") or []:
            est = str(c.get("estado") or "")
            rot, tom = ESTADOS_DO_CHAMADO.get(est, (est.lower(), "neutro"))
            chamados.append({**c, "cliente": lt.cliente, "uid": uid_do_codigo.get(c.get("usina_codigo")),
                             "estado_rotulo": rot, "tom": tom, "pede_acao": est in PEDEM_ACAO,
                             "criado": AND.instante(c.get("criado_em")), "enviado": AND.instante(c.get("enviado_em")),
                             "protocolo_quando": AND.instante(c.get("protocolo_em"))})
        if d.get("gateway"):
            gateways.append(d["gateway"])

    alvo = " ".join(busca.lower().split())
    linhas, ufs, clientes = [], set(), {}
    for uid, u in b.por_id.items():
        if not _ativa(u):
            continue
        onde = b.onde(uid)
        ufs.add(onde["uf"])
        clientes[onde["cliente"]] = clientes.get(onde["cliente"], 0) + 1
        if (cliente and onde["cliente"] != cliente) or (uf and onde["uf"] != uf):
            continue
        if alvo and not all(p in " ".join((onde["usina"], onde["cidade"], D._txt(u.get("codigo")))).lower()
                            for p in alvo.split()):
            continue
        distribuidoras = []
        for x in ucs_do.get(uid, []):
            distribuidoras.append({"nome": x.get("concessionaria") or "", "chave": x.get("chave") or "",
                                   "uc": x.get("uc") or "", "parte": x.get("parte") or "", "de": "andamento"})
        conc = D._txt(u.get("concessionaria"))
        if not distribuidoras and conc:
            distribuidoras.append({"nome": conc, "chave": chave_da_concessionaria(conc), "uc": "", "parte": "",
                                   "de": "cadastro"})
        for x in distribuidoras:
            x["canal"] = canais.get(x["chave"])
        abertos = [c for c in chamados if c["uid"] == uid and c["pede_acao"]]
        linhas.append({"uid": uid, **onde, "codigo": D._txt(u.get("codigo")), "distribuidoras": distribuidoras,
                       "chamados_pedem_acao": len(abertos)})
    linhas.sort(key=lambda x: (x["cliente"], x["usina"]))
    quem = Contatos(b, cofre)
    for x in linhas:
        x["contatos"] = quem.da_usina(x["uid"])

    uids = {x["uid"] for x in linhas}
    filtrado = bool(cliente or uf or alvo)
    chamados_da_tela = sorted((c for c in chamados if not filtrado or c["uid"] in uids),
                              key=lambda c: c["criado"] or datetime.min.replace(tzinfo=AND._BRT), reverse=True)
    usadas = {}
    for x in linhas:
        for dd in x["distribuidoras"]:
            usadas.setdefault(dd["chave"], {"nome": dd["nome"], "canal": dd["canal"], "usinas": 0})["usinas"] += 1
    gateway = max(gateways, key=lambda g: str(g.get("visto_em") or ""), default=None)
    return {
        "linhas": linhas, "clientes": sorted((c, n) for c, n in clientes.items() if c), "ufs": sorted(u for u in ufs if u),
        "chamados": chamados_da_tela, "sem_ligacao": sem_ligacao, "erros": erros,
        "distribuidoras": sorted(usadas.items(), key=lambda kv: (-kv[1]["usinas"], kv[1]["nome"])),
        "resumo": {"usinas": len(linhas),
                   "com_canal": sum(1 for x in linhas if any(dd["canal"] for dd in x["distribuidoras"])),
                   "sem_distribuidora": sum(1 for x in linhas if not x["distribuidoras"]),
                   "chamados": len(chamados_da_tela),
                   "com_protocolo": sum(1 for c in chamados_da_tela if c.get("protocolo")),
                   "pedem_acao": sum(1 for c in chamados_da_tela if c["pede_acao"])},
        "sinal": _sinal(gateway, agora) if any(lt.dados for lt in leituras) else None,
        # o canal, a UC e os chamados de TODOS os clientes do Andamento foram lidos? Sem isso, as contas que dependem
        # deles (com canal, chamados, pedem ação) não vão à faixa: número pela metade não vai para a tela
        "andamento_completo": bool(leituras) and all(lt.dados for lt in leituras),
        "dias": 30, "agora": agora,
    }
