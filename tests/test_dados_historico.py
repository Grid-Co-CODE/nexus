"""O histórico SCD tipo 2 da camada de dados (passo 5 da auditoria Kimball de 08/10/2026).

Cada teste é uma regra de `nexus/dados/historico.py` com o caso que a criou: a 1ª versão "desde sempre" (antes, 3 de
cada 4 fechamentos não achavam versão), a migração das linhas já gravadas, o dia de Brasília, duas trocas no mesmo dia,
a reentrada que sobrepunha, o cadastro vazio que fechava todo mundo, a conferência antes de publicar e a medida "fatos
que acham exatamente 1 versão". IDs e valores inventados.
"""
from datetime import date

from pg_falso import ApiPGFalsa

from nexus.dados import historico, livros

BASE = "http://pg.falso"
CAB_P = historico.cabecalho("pessoas")
CAB_U = historico.cabecalho("usinas")


def _p(pid, equipe=10, sup=100, alterado="2026-09-30T02:15:00Z", **kw):
    d = {"pessoa_id": pid, "equipe_id": equipe, "supervisor_id": sup, "cargo": "Técnico", "vinculo": "CLT",
         "status": "Ativo", "alterado_em": alterado, "excluido": "não", "versao": 3}
    d.update(kw)
    return d


def _u(uid, resp=500, alterado="2026-09-30T02:15:00Z", **kw):
    d = {"usina_id": uid, "cliente_id": 9, "equipe_id": 10, "status": "Operação", "responsavel_om_id": resp,
         "tecnico_om_id": 600, "cluster": "Cluster A", "regiao": "Sul", "alterado_em": alterado, "excluido": "não"}
    d.update(kw)
    return d


def _dic(linhas, cab=CAB_P):
    return [dict(zip(cab, l)) for l in linhas]


def _carga(atuais, anteriores, hoje, entidade="pessoas"):
    """Uma carga como a de hora em hora: o histórico gravado volta do banco como dict."""
    linhas, rel = historico.atualizar(entidade, atuais, anteriores, hoje)
    return _dic(linhas, historico.cabecalho(entidade)), rel


def _resumo(h, campo="supervisor_id"):
    return [(x[campo], x["valido_de"], x["valido_ate"], x["vigente"], x["inicio_presumido"]) for x in h]


# ── o formato ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_cabecalho_novo_tem_versao_ids_de_data_e_presumido():
    fim = ["versao", "valido_de", "valido_ate", "valido_de_id", "valido_ate_id", "vigente", "inicio_presumido"]
    assert CAB_P == ["pessoa_id", "equipe_id", "supervisor_id", "cargo", "vinculo", "status", *fim]
    assert CAB_U == ["usina_id", "cliente_id", "equipe_id", "status", "responsavel_om_id", "tecnico_om_id", "cluster",
                     "regiao", *fim]


def test_dia_de_brasilia_do_carimbo_utc():
    """133 de 134 pessoas tinham alterado_em 30/09 02:xxZ, que é 29/09 em Brasília."""
    assert historico.dia_brt("2026-09-30T02:15:00Z") == date(2026, 9, 29)
    assert historico.dia_brt("2026-10-01T02:30:00.000Z") == date(2026, 9, 30)
    assert historico.dia_brt("2026-09-30T10:00:00") == date(2026, 9, 30)        # sem fuso = UTC
    assert historico.dia_brt("2026-09-30") == date(2026, 9, 30)                 # só a data: o próprio dia
    assert historico.dia_brt("") is None and historico.dia_brt(None) is None and historico.dia_brt("ontem") is None


# ── regra 1: desde sempre, presumido ──────────────────────────────────────────────────────────────────────────────
def test_primeira_carga_vale_desde_sempre_e_o_fechamento_de_12_08_acha_a_versao():
    """O exemplo do docstring: o fechamento de 12/08 acha a versão da pessoa. Antes a 1ª versão começava em 30/09 e
    74,9% dos fechamentos com pessoa não achavam nenhuma."""
    linhas, rel = historico.atualizar("pessoas", [_p(1), _p(2, sup=200)], [], date(2026, 10, 5))
    h = _dic(linhas)
    assert [(x["pessoa_id"], x["versao"], x["valido_de"], x["valido_de_id"], x["valido_ate"], x["valido_ate_id"],
             x["vigente"], x["inicio_presumido"]) for x in h] == [
        (1, 1, "1900-01-01", 19000101, None, 99991231, "sim", 1),
        (2, 1, "1900-01-01", 19000101, None, 99991231, "sim", 1)]
    assert historico.da_epoca(h, 1, 20260812)["supervisor_id"] == 100
    assert historico.da_epoca(linhas, 2, 20260812)[2] == 200                    # também nas listas da carga
    assert (rel["novos"], rel["membros"], rel["versoes"], rel["presumidas"]) == (2, 2, 2, 2)


def test_membro_novo_depois_da_primeira_carga_tambem_nasce_desde_sempre():
    """Dimensão que chega atrasada: a pessoa cadastrada em 07/10 já tinha fechamento em agosto."""
    h, _ = _carga([_p(1)], [], date(2026, 10, 5))
    h, rel = _carga([_p(1), _p(3, alterado="2026-10-07T13:00:00Z")], h, date(2026, 10, 7))
    tres = [x for x in h if x["pessoa_id"] == 3]
    assert _resumo(tres) == [(100, "1900-01-01", None, "sim", 1)] and rel["novos"] == 1
    assert historico.da_epoca(h, 3, 20260820) is not None


def test_migrar_as_linhas_gravadas_antes_de_08_10_e_idempotente():
    """O banco de 08/10 tem 134 pessoas com valido_de 30/09 (o dia UTC da importação) e uma troca em 07/10."""
    antigo = [
        {"pessoa_id": 1, "equipe_id": 10, "supervisor_id": 100, "cargo": "Técnico", "vinculo": "CLT", "status": "Ativo",
         "valido_de": "2026-09-30", "valido_ate": "2026-10-07", "vigente": "não"},
        {"pessoa_id": 1, "equipe_id": 11, "supervisor_id": 101, "cargo": "Técnico", "vinculo": "CLT", "status": "Ativo",
         "valido_de": "2026-10-07", "valido_ate": None, "vigente": "sim"},
        {"pessoa_id": 2, "equipe_id": 10, "supervisor_id": 100, "cargo": "Técnico", "vinculo": "CLT", "status": "Ativo",
         "valido_de": "2026-09-30", "valido_ate": None, "vigente": "sim"},
        # duas trocas no mesmo dia com o código de antes: a versão do meio tem duração zero e some
        {"pessoa_id": 3, "supervisor_id": 299, "valido_de": "2026-09-30", "valido_ate": "2026-10-06", "vigente": "não"},
        {"pessoa_id": 3, "supervisor_id": 300, "valido_de": "2026-10-06", "valido_ate": "2026-10-06", "vigente": "não"},
        {"pessoa_id": 3, "supervisor_id": 301, "valido_de": "2026-10-06", "valido_ate": None, "vigente": "sim"},
    ]
    m = historico.migrar(antigo, "pessoas")
    assert [(x["pessoa_id"], x["versao"], x["supervisor_id"], x["valido_de"], x["valido_ate"], x["valido_de_id"],
             x["valido_ate_id"], x["vigente"], x["inicio_presumido"]) for x in m] == [
        (1, 1, 100, "1900-01-01", "2026-10-07", 19000101, 20261007, "não", 1),
        (1, 2, 101, "2026-10-07", None, 20261007, 99991231, "sim", 0),
        (2, 1, 100, "1900-01-01", None, 19000101, 99991231, "sim", 1),
        (3, 1, 299, "1900-01-01", "2026-10-06", 19000101, 20261006, "não", 1),
        (3, 2, 301, "2026-10-06", None, 20261006, 99991231, "sim", 0)]
    assert historico.migrar(m, "pessoas") == m
    assert historico.conferir(m, "pessoas") == {"sobreposicoes": 0, "buracos": 0, "sem_vigente": 0}


def test_a_carga_seguinte_migra_o_formato_antigo_sem_abrir_versao():
    antigo = [{"pessoa_id": 1, "equipe_id": 10, "supervisor_id": 100, "cargo": "Técnico", "vinculo": "CLT",
               "status": "Ativo", "valido_de": "2026-09-30", "valido_ate": None, "vigente": "sim"}]
    h, rel = _carga([_p(1)], antigo, date(2026, 10, 8))
    assert _resumo(h) == [(100, "1900-01-01", None, "sim", 1)]
    assert (rel["trocas"], rel["novos"], rel["trocas_no_mesmo_dia"]) == (0, 0, 0)


def test_o_mesmo_valor_com_outro_tipo_nao_e_mudanca():
    h1, _ = _carga([_p(1, 10, 100)], [], date(2026, 10, 5))
    h2, rel = _carga([_p(1, 10.0, "100")], h1, date(2026, 10, 6))
    assert h2 == h1 and rel["trocas"] == 0


# ── regras 2 e 3: a troca no dia de Brasília do alterado_em ───────────────────────────────────────────────────────
def test_troca_vale_no_dia_de_brasilia_do_alterado_em():
    """Troca editada 06/10 às 23h30 em Brasília (07/10 02:30Z) e vista pela carga de 08/10: vale 06/10, não 08/10."""
    h, _ = _carga([_p(1)], [], date(2026, 10, 5))
    h, rel = _carga([_p(1, sup=101, alterado="2026-10-07T02:30:00Z")], h, date(2026, 10, 8))
    assert _resumo(h) == [(100, "1900-01-01", "2026-10-06", "não", 1), (101, "2026-10-06", None, "sim", 0)]
    assert historico.da_epoca(h, 1, 20261005)["supervisor_id"] == 100
    assert historico.da_epoca(h, 1, 20261006)["supervisor_id"] == 101
    assert rel["trocas"] == 1


def test_troca_limitada_entre_o_inicio_da_vigente_e_hoje():
    base, _ = _carga([_p(1)], [], date(2026, 10, 5))
    futuro, _ = _carga([_p(1, sup=101, alterado="2026-10-20T12:00:00Z")], base, date(2026, 10, 8))
    assert futuro[1]["valido_de"] == "2026-10-08"                              # nunca depois de hoje
    sem_data, _ = _carga([_p(1, sup=101, alterado=None)], base, date(2026, 10, 8))
    assert sem_data[1]["valido_de"] == "2026-10-08"                            # sem alterado_em: o dia da carga


def test_publicacao_antiga_de_outro_dono_nao_deixa_lixo():
    """Herda do passo 1 (dois donos do cadastro): a publicação antiga volta com alterado_em anterior à vigente. A troca
    cai no início da vigente e a sobrescreve; voltar ao estado anterior reabre a versão. O vai e vem não empilha."""
    h, _ = _carga([_p(1)], [], date(2026, 10, 5))
    novo, _ = _carga([_p(1, sup=101, alterado="2026-10-07T13:00:00Z")], h, date(2026, 10, 7))
    velho, rel = _carga([_p(1, sup=100, alterado="2026-09-30T02:15:00Z")], novo, date(2026, 10, 8))
    assert _resumo(velho) == [(100, "1900-01-01", None, "sim", 1)] and rel["trocas_no_mesmo_dia"] == 1
    de_novo, _ = _carga([_p(1, sup=101, alterado="2026-10-07T13:00:00Z")], velho, date(2026, 10, 8))
    assert _resumo(de_novo) == _resumo(novo)


# ── regra 4: duas trocas no mesmo dia ─────────────────────────────────────────────────────────────────────────────
def test_duas_trocas_no_mesmo_dia_viram_uma_versao():
    """Antes: [06/10, 06/10) com o 101, que nunca casa com fato e repete a chave (id, valido_de)."""
    h, _ = _carga([_p(1)], [], date(2026, 10, 5))
    h, _ = _carga([_p(1, sup=101, alterado="2026-10-06T13:00:00Z")], h, date(2026, 10, 6))
    h, rel = _carga([_p(1, sup=102, alterado="2026-10-06T14:00:00Z")], h, date(2026, 10, 6))
    assert _resumo(h) == [(100, "1900-01-01", "2026-10-06", "não", 1), (102, "2026-10-06", None, "sim", 0)]
    assert rel["trocas_no_mesmo_dia"] == 1
    assert len({(x["pessoa_id"], x["valido_de"]) for x in h}) == len(h)
    # e a terceira desfaz no mesmo dia: a versão de antes reabre, sem versão nova
    h, _ = _carga([_p(1, sup=100, alterado="2026-10-06T15:00:00Z")], h, date(2026, 10, 6))
    assert _resumo(h) == [(100, "1900-01-01", None, "sim", 1)]


# ── regra 5: reentrada ────────────────────────────────────────────────────────────────────────────────────────────
def test_reentrada_abre_hoje_sem_sobrepor():
    """Antes a reentrada reabria no alterado_em antigo, por cima da versão fechada: o fato de 01/10 casava 2."""
    h, _ = _carga([_p(1)], [], date(2026, 10, 1))
    h, rel = _carga([_p(1, excluido="sim", alterado="2026-10-03T12:00:00Z")], h, date(2026, 10, 3))
    assert _resumo(h) == [(100, "1900-01-01", "2026-10-03", "não", 1)] and rel["exclusoes"] == 1
    h, rel = _carga([_p(1, sup=101, alterado="2026-09-30T02:15:00Z")], h, date(2026, 10, 8))
    assert _resumo(h) == [(100, "1900-01-01", "2026-10-03", "não", 1), (101, "2026-10-08", None, "sim", 0)]
    assert rel["reentradas"] == 1
    assert historico.conferir(h, "pessoas") == {"sobreposicoes": 0, "buracos": 1, "sem_vigente": 0}
    assert historico.da_epoca(h, 1, 20261001)["supervisor_id"] == 100
    assert historico.da_epoca(h, 1, 20261005) is None                          # excluída nesse intervalo: de fato
    assert historico.da_epoca(h, 1, 20261008)["supervisor_id"] == 101


def test_saiu_e_voltou_igual_no_mesmo_dia_segue_a_mesma_versao():
    h, _ = _carga([_p(1)], [], date(2026, 10, 1))
    h, _ = _carga([_p(1, excluido="sim", alterado="2026-10-08T12:00:00Z")], h, date(2026, 10, 8))
    h, _ = _carga([_p(1, alterado="2026-10-08T13:00:00Z")], h, date(2026, 10, 8))
    assert _resumo(h) == [(100, "1900-01-01", None, "sim", 1)]


# ── regra 6: só a exclusão fecha; leitura vazia não anda ──────────────────────────────────────────────────────────
def test_ausente_sem_excluido_continua_vigente():
    """O cadastro não apaga linha: quem some da leitura continua vigente, e a qualidade conta."""
    h, _ = _carga([_p(1), _p(2)], [], date(2026, 10, 5))
    h, rel = _carga([_p(1)], h, date(2026, 10, 6))
    assert [(x["pessoa_id"], x["vigente"], x["valido_ate"]) for x in h] == [(1, "sim", None), (2, "sim", None)]
    assert rel["ausentes_na_leitura"] == 1


def test_excluido_sim_fecha_no_dia_do_alterado_em():
    h, _ = _carga([_p(1), _p(2)], [], date(2026, 10, 5))
    h, rel = _carga([_p(1), _p(2, excluido="sim", alterado="2026-10-06T02:00:00Z")], h, date(2026, 10, 7))
    assert [(x["pessoa_id"], x["valido_ate"], x["valido_ate_id"], x["vigente"]) for x in h] == [
        (1, None, 99991231, "sim"), (2, "2026-10-05", 20261005, "não")]
    assert rel["exclusoes"] == 1
    # excluída de novo (já fechada): nada muda; nunca vista e excluída: não nasce
    h2, _ = _carga([_p(1), _p(2, excluido="sim"), _p(9, excluido="sim")], h, date(2026, 10, 8))
    assert h2 == h


def test_excluida_no_dia_em_que_a_versao_comecou_nao_deixa_versao_de_duracao_zero():
    h, _ = _carga([_p(1)], [], date(2026, 10, 5))
    h, _ = _carga([_p(1, sup=101, alterado="2026-10-07T13:00:00Z")], h, date(2026, 10, 7))
    h, _ = _carga([_p(1, sup=101, excluido="sim", alterado="2026-10-07T18:00:00Z")], h, date(2026, 10, 7))
    assert _resumo(h) == [(100, "1900-01-01", "2026-10-07", "não", 1)]
    assert historico.conferir(h, "pessoas") == {"sobreposicoes": 0, "buracos": 0, "sem_vigente": 1}


def test_cadastro_lido_vazio_nao_fecha_ninguem():
    """Antes, uma leitura vazia do cadastro fechava todas as versões vigentes."""
    h, _ = _carga([_p(1), _p(2)], [], date(2026, 10, 5))
    linhas, rel = historico.atualizar("pessoas", [], h, date(2026, 10, 6))
    assert _dic(linhas) == h and all(x["vigente"] == "sim" for x in _dic(linhas))
    assert "cadastro lido vazio" in rel["pulou_motivo"] and rel["publicar"] and not rel["segurar"]


def test_historico_anterior_lido_vazio_com_o_livro_gravado_nao_publica():
    """Antes, um histórico anterior lido vazio fazia a versão fechada sumir e o fato passava a casar 0 versões."""
    linhas, rel = historico.atualizar("pessoas", [_p(1)], [], date(2026, 10, 6), livro_existe=True)
    assert linhas == [] and not rel["publicar"] and rel["segurar"] and "lido vazio" in rel["pulou_motivo"]
    h_u, _ = _carga([_u(7)], [], date(2026, 10, 5), "usinas")
    tab, r = historico.tabelas({"pessoas": [_p(1)], "usinas": [_u(7)]}, {"pessoas": [], "usinas": h_u},
                               date(2026, 10, 6), "2026-10-06T10:40:00-03:00", {"atualizacao", "dim_data"})
    assert r["segurar"] and "pessoas_historico" not in tab and "usinas_historico" in tab
    # 1ª carga de todas (o livro não existe): anda normalmente
    tab, r = historico.tabelas({"pessoas": [_p(1)], "usinas": [_u(7)]}, {}, date(2026, 10, 6), "t", set())
    assert not r["segurar"] and len(tab["pessoas_historico"][1]) == 1


def test_ja_gravado_decide_pelo_livro_e_pela_aba_da_entidade_nova():
    assert not historico.ja_gravado(set(), "pessoas")
    assert not historico.ja_gravado({"pessoas_historico"}, "pessoas")           # sem atualizacao: livro não existe
    assert historico.ja_gravado({"atualizacao"}, "pessoas")                    # a listagem perdeu a aba: segura
    assert historico.ja_gravado({"atualizacao"}, "usinas")
    assert not historico.ja_gravado({"atualizacao"}, "clientes")               # entidade nova: 1ª carga anda
    assert historico.ja_gravado({"atualizacao", "clientes_historico"}, "clientes")


# ── a usina ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_usina_troca_de_responsavel():
    h, _ = _carga([_u(7), _u(8)], [], date(2026, 10, 5), "usinas")
    h, rel = _carga([_u(7, resp=501, alterado="2026-10-06T15:00:00Z"), _u(8)], h, date(2026, 10, 6), "usinas")
    sete = [x for x in h if x["usina_id"] == 7]
    assert _resumo(sete, "responsavel_om_id") == [(500, "1900-01-01", "2026-10-06", "não", 1),
                                                   (501, "2026-10-06", None, "sim", 0)]
    assert historico.da_epoca(h, 7, 20260901)["responsavel_om_id"] == 500
    assert rel["trocas"] == 1 and rel["membros"] == 2 and rel["versoes"] == 3
    # campo não rastreado (a potência) mudar não abre versão
    h2, rel = _carga([_u(7, resp=501, potencia_real=900), _u(8)], h, date(2026, 10, 7), "usinas")
    assert h2 == h and rel["trocas"] == 0


# ── regra 7: conferir antes de publicar ───────────────────────────────────────────────────────────────────────────
def _linha(pid, sup, de, ate):
    return {"pessoa_id": pid, "supervisor_id": sup, "valido_de": de, "valido_ate": ate}


def test_conferir_conta_sobreposicao_buraco_e_membro_sem_vigente():
    h = [_linha(1, 100, "1900-01-01", "2026-10-07"), _linha(1, 101, "2026-10-05", None),     # sobrepõe
         _linha(2, 100, "1900-01-01", "2026-10-01"), _linha(2, 101, "2026-10-03", None),     # buraco
         _linha(3, 100, "1900-01-01", "2026-10-01"),                                          # sem vigente
         _linha(4, 100, "1900-01-01", None), _linha(4, 101, "2026-10-01", None)]             # 2 vigentes
    assert historico.conferir(h, "pessoas") == {"sobreposicoes": 2, "buracos": 1, "sem_vigente": 1}
    assert historico.da_epoca(h, 1, 20261006) is None                           # 2 versões: não escolhe ao acaso
    assert historico.da_epoca(h, 2, 20261002) is None                           # no buraco: nenhuma
    assert historico.da_epoca(h, 1, 20261004)["supervisor_id"] == 100


def test_conferencia_que_acha_sobreposicao_publica_o_historico_anterior(monkeypatch):
    anterior, _ = _carga([_p(1), _p(2)], [], date(2026, 10, 5))
    anterior_u, _ = _carga([_u(7)], [], date(2026, 10, 5), "usinas")
    real = historico.atualizar

    def com_defeito(entidade, atuais, anteriores, hoje, **kw):
        linhas, rel = real(entidade, atuais, anteriores, hoje, **kw)
        if entidade == "pessoas":       # um defeito qualquer que abra uma 2ª vigente por cima
            linhas = linhas + [[1, 10, 999, "Técnico", "CLT", "Ativo", 2, "2026-10-06", None, 20261006, 99991231,
                                "sim", 0]]
        return linhas, rel
    monkeypatch.setattr(historico, "atualizar", com_defeito)
    tab, rel = historico.tabelas({"pessoas": [_p(1), _p(2)], "usinas": [_u(7)]},
                                 {"pessoas": anterior, "usinas": anterior_u},
                                 date(2026, 10, 6), "2026-10-06T10:40:00-03:00", {"atualizacao"})
    assert _dic(tab["pessoas_historico"][1]) == anterior
    q = {l[0]: dict(zip(historico.CAB_QUALIDADE, l)) for l in tab[historico.ABA_QUALIDADE][1]}
    assert q["pessoas"]["pulou_motivo"].startswith("conferência falhou (1 sobreposições")
    assert (q["pessoas"]["sobreposicoes"], q["pessoas"]["versoes"]) == (0, 2)
    assert rel["pessoas"]["conferencia_recusada"]["sobreposicoes"] == 1
    assert q["usinas"]["pulou_motivo"] is None and not rel["segurar"]


def test_buraco_da_reentrada_e_membro_excluido_nao_barram_a_publicacao():
    h, _ = _carga([_p(1), _p(2)], [], date(2026, 10, 1))
    h, _ = _carga([_p(1, excluido="sim", alterado="2026-10-03T12:00:00Z"), _p(2)], h, date(2026, 10, 3))
    tab, rel = historico.tabelas({"pessoas": [_p(1), _p(2, excluido="sim", alterado="2026-10-08T12:00:00Z")]},
                                 {"pessoas": h}, date(2026, 10, 8), "t", {"atualizacao"})
    q = dict(zip(historico.CAB_QUALIDADE, tab[historico.ABA_QUALIDADE][1][0]))
    assert q["pulou_motivo"] is None and (q["buracos"], q["sem_vigente"]) == (1, 1)
    assert rel["pessoas"]["reentradas"] == 1 and rel["pessoas"]["exclusoes"] == 1


def test_qualidade_historico_uma_linha_por_entidade():
    tab, rel = historico.tabelas({"pessoas": [_p(1), _p(2)], "usinas": [_u(7)]},
                                 {"pessoas": [{"pessoa_id": 1, "supervisor_id": 100, "valido_de": "2026-09-30",
                                               "valido_ate": None, "vigente": "sim"}]},
                                 date(2026, 10, 8), "2026-10-08T10:40:00-03:00", set())
    cab, linhas = tab[historico.ABA_QUALIDADE]
    assert cab == ["entidade", "membros", "versoes", "presumidas", "sobreposicoes", "buracos", "sem_vigente",
                   "ausentes_na_leitura", "pulou_motivo", "gerado_em"]
    q = {l[0]: dict(zip(cab, l)) for l in linhas}
    assert (q["pessoas"]["membros"], q["pessoas"]["versoes"], q["pessoas"]["presumidas"]) == (2, 3, 2)
    assert (q["usinas"]["membros"], q["usinas"]["gerado_em"]) == (1, "2026-10-08T10:40:00-03:00")
    assert tab["pessoas_historico"][0] == CAB_P and tab["usinas_historico"][0] == CAB_U


# ── a medida: fatos que acham exatamente 1 versão ─────────────────────────────────────────────────────────────────
def test_todo_fato_acha_exatamente_uma_versao():
    """A meta do passo 5: 100% (era 25,4% na pessoa e 26,4% na usina, nos fechamentos de 08/10)."""
    hp, _ = _carga([_p(1), _p(2)], [], date(2026, 10, 5))
    hp, _ = _carga([_p(1, sup=101, alterado="2026-10-07T13:00:00Z"), _p(2)], hp, date(2026, 10, 7))
    hp, _ = _carga([_p(1, sup=101), _p(2), _p(3, alterado="2026-10-09T13:00:00Z")], hp, date(2026, 10, 9))
    hu, _ = _carga([_u(7)], [], date(2026, 10, 5), "usinas")
    hu, _ = _carga([_u(7, resp=501, alterado="2026-10-06T15:00:00Z"), _u(8)], hu, date(2026, 10, 6), "usinas")
    cab = ["fechamento_id", "data_id", "usina_id", "pessoa_id"]
    fatos = [["a", 20260811, 7, 1], ["b", 20260930, 8, 2], ["c", 20261006, 7, 1], ["d", 20261007, 7, 1],
             ["e", 20261008, 8, 3], ["f", 20260813, None, None], ["g", None, 7, 1]]
    assert historico.cobertura(fatos, cab, "pessoa_id", "data_id", hp) == (5, 5)
    assert historico.cobertura(fatos, cab, "usina_id", "data_id", hu) == (5, 5)
    assert historico.cobertura([dict(zip(cab, l)) for l in fatos], cab, "pessoa_id", "data_id", hp) == (5, 5)
    # o histórico de antes (1ª versão em 30/09): só os fatos a partir de 30/09 achavam versão
    antes = [{"pessoa_id": p, "supervisor_id": 100, "valido_de": "2026-09-30", "valido_ate": None, "vigente": "sim"}
             for p in (1, 2, 3)]
    assert historico.cobertura(fatos, cab, "pessoa_id", "data_id", antes) == (5, 4)


# ── ida e volta pelo banco ────────────────────────────────────────────────────────────────────────────────────────
def test_ida_e_volta_pelo_banco_com_tudo_em_texto_nao_abre_versao():
    """A API pode devolver 19000101 como "19000101" e o 1 do presumido como "1": a carga seguinte não vê mudança."""
    api = ApiPGFalsa(como_texto=True)
    cad = {"pessoas": [_p(1), _p(2, sup=200)], "usinas": [_u(7)]}
    tab, _ = historico.tabelas(cad, {}, date(2026, 10, 5), "2026-10-05T15:40:00-03:00", set())
    livros.publicar("nexus_dimensoes", "teste", tab, base=BASE, token="t", sessao=api)
    lidos = {e: livros.ler(BASE, api, "nexus_dimensoes", f"{e}_historico") for e in historico.RASTREADOS}
    assert lidos["pessoas"][0]["valido_de_id"] == "19000101"                   # veio texto mesmo
    assert historico.da_epoca(lidos["pessoas"], 2, 20260812)["supervisor_id"] == "200"
    tab2, rel = historico.tabelas(cad, lidos, date(2026, 10, 6), "2026-10-06T10:40:00-03:00",
                                  livros.abas(BASE, api, "nexus_dimensoes"))
    assert tab2["pessoas_historico"] == tab["pessoas_historico"]
    assert tab2["usinas_historico"] == tab["usinas_historico"]
    assert rel["pessoas"]["trocas"] == 0 and rel["pessoas"]["pulou_motivo"] is None
