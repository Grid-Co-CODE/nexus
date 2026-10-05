"""CÓPIA da lógica de regras do App de Campo (function_app.py). NÃO EDITE: rode ferramentas/extrair_regras_campo.py.

Origem: function_app.py do App, codigo 9662733fd7381fa1 (o número que o /api/health do App mostra quando é esta a
versão no ar). Copiado em 04/10/2026 20:42. Sem comentários nem docstrings (o repositório é
público); o porquê de cada regra está no código do App. Só o acesso a dado foi trocado (fim do arquivo).
"""
# ruff: noqa
CODIGO_APP = "9662733fd7381fa1"
COPIADAS = ('ACESSOS_TTL', 'ATN_DIAS_SEM_RONDA', 'ATN_PESO', 'ATN_SEG', 'ATN_TIPOS', 'ApiError', 'CADASTRO_TTL_S', 'CHECKLIST_RONDA', 'ESTOURO_EXEC_MIN', 'ESTOURO_EXEC_X', 'ESTOURO_PREV_TETO', 'ESTOURO_PREV_X', 'EXTENSAO_ALERTA', 'EXTENSAO_NENHUMA', 'FILA_TTL_S', 'GESTAO_OS_MAX', 'GESTAO_TODAS_MAX', 'LIMIARES_PADRAO', 'PT_CAMPOS_RESUMO', 'PT_CHECKLISTS', 'PT_DESTAQUE_MIN', 'PT_HIST_DIAS_MAX', 'PT_HIST_MAX', 'PT_POR_ID', 'PT_RESP_TTL_S', 'PT_VALIDADE_DIAS', 'STATUS_IN_REVIEW', 'SUP_CAP_BACKLOG', 'TRIAGEM_ESTOURO', 'TRIAGEM_NOTA_OK', 'V2_PESOS', 'V2_PISO', '_ATRIB', '_CAD', '_CANON', '_CATOV', '_CL_USINA', '_FILA_CACHE', '_PT_RESP', '_SUPCAN', '_acessos', '_acessos_cache', '_agora_iso', '_aplicar_tratamentos', '_area_ok', '_atencao_os_guardada', '_atribuicoes', '_bloqueados', '_cadastro_tab', '_canon_cluster', '_casa_nome', '_catalogo_ov', '_central_atencao', '_chave_atencao', '_cluster_da_usina', '_clusters_por_email', '_concentracao', '_contar_fotos', '_dias_entre', '_duracao_ronda', '_enc_resumo', '_estouro', '_estouro_causa', '_fila_bruta', '_fila_do_app', '_fila_supervisao', '_filtro_pessoas', '_fora', '_fx_wo_paralelo', '_gestao_os', '_gestao_prioridades', '_hist_ler', '_hoje', '_int0', '_invariantes_guardados', '_janela', '_janela_str', '_lim_cache', '_limiares', '_link_fracttal_os', '_niveis_vazios', '_no_escopo', '_norm', '_obs_do_fechamento', '_parse_iso', '_pessoa_por_nome', '_pontos_atencao_ronda', '_preenchido_item', '_pt_agora_brt', '_pt_br', '_pt_chave_tarefa', '_pt_cos_operadores', '_pt_destinos', '_pt_dt', '_pt_emails_cos', '_pt_esc_usina', '_pt_forcados', '_pt_forcados_lista', '_pt_lista', '_pt_lista_aprovadores', '_pt_meio_usina', '_pt_numero', '_pt_pode_assinar', '_pt_publico', '_pt_quem_assina', '_pt_quem_txt', '_pt_resp_bd', '_pt_resp_da_pt', '_pt_sup_email', '_pt_supervisores', '_pt_tok_cod', '_pt_usina_norm', '_pt_ve', '_qlog_por_os', '_qualidade_os', '_qualidade_v2', '_ronda_resumo', '_rondas_os_pares', '_rondas_os_por_folio', '_sem_bloqueados', '_sup_canon', '_sup_canon_mapa', '_sup_norm', '_tratamentos', '_triagem', '_trk_respondido', '_txt_tarefa', '_usinas_do_cluster', '_v2_achou_falha', '_v2_e_na', '_v2_pede_foto', '_veredito_os', '_veredito_ronda', '_veredito_usina', 'tabela_acessos', 'tabela_atencao_os', 'tabela_atribuicoes', 'tabela_decisoes', 'tabela_limiares', 'tabela_ronda', 'tabela_ronda_ativos', 'tabela_ronda_os')
ASSINATURAS_TROCADAS = {'_tabela': '583740a7d68b3a65', 'fx': 'df3a6bba0b68da47', 'ident': 'a47f156debb43b7c', 'tabela': '666a04282aab3cbf', 'tabela_qlog': '95a72f1f98b561d4'}

import base64
import gzip
import hashlib
import io
import json
import logging
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import uuid
import secrets as _secrets
from datetime import datetime, timedelta as _timedelta, timezone


class ApiError(Exception):

    def __init__(self, status, msg):
        self.status = status
        self.msg = msg


def _norm(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub('\\s+', ' ', s).strip()


def _agora_iso():
    n = datetime.now(timezone.utc)
    return n.strftime('%Y-%m-%dT%H:%M:%S.') + f'{n.microsecond // 1000:03d}Z'


CADASTRO_TTL_S = int(os.environ.get('CADASTRO_TTL_S', '600') or '600')


_CAD = {'t': 0.0, 'v': None}


def _cadastro_tab():
    import time as _t
    if _CAD['v'] is not None and _t.time() - _CAD['t'] < CADASTRO_TTL_S:
        return _CAD['v']
    v = {}
    try:
        e = tabela().get_entity('cadastro', 'bd_operacoes')
        v = json.loads(e.get('json') or '{}')
        if not isinstance(v, dict):
            v = {}
    except Exception as e:
        logging.info('cadastro da tabela: %s', e)
        v = {}
    _CAD['v'], _CAD['t'] = (v, _t.time())
    return v


_acessos_cache = {'t': 0.0, 'admins': set(), 'sups': {}, 'bloq': {}}


ACESSOS_TTL = int(os.environ.get('ACESSOS_TTL_SEG', '60') or '60')


def tabela_acessos():
    return _tabela('acessos', '_table_acessos')


def _acessos(forcar=False):
    if not forcar and time.time() - _acessos_cache['t'] < ACESSOS_TTL:
        return _acessos_cache
    admins, sups, bloq = (set(), {}, {})
    try:
        tb = tabela_acessos()
        for e in tb.query_entities("PartitionKey eq 'admin'"):
            if e.get('email'):
                admins.add(str(e['email']).strip().lower())
        for e in tb.query_entities("PartitionKey eq 'sup'"):
            if not e.get('email'):
                continue

            def _jl(campo):
                try:
                    v = json.loads(e.get(campo) or '[]')
                    return [str(x) for x in v] if isinstance(v, list) else []
                except Exception:
                    return []
            sups[str(e['email']).strip().lower()] = {'nome': e.get('nome') or '', 'clusters': _jl('clusters'), 'usinas': _jl('usinas'), 'colabs': _jl('colabs')}
        for e in tb.query_entities("PartitionKey eq 'bloq'"):
            if e.get('email'):
                bloq[str(e['email']).strip().lower()] = {'nome': e.get('nome') or '', 'motivo': e.get('motivo') or '', 'por': e.get('por') or '', 'quando': e.get('quando') or ''}
    except Exception as ex:
        logging.warning('acessos: %s', ex)
        return _acessos_cache
    _acessos_cache.update({'t': time.time(), 'admins': admins, 'sups': sups, 'bloq': bloq})
    return _acessos_cache


_ATRIB = {'t': 0.0, 'd': None, 'n': None}


def tabela_atribuicoes():
    return _tabela('atribuicoes', '_table_atrib')


def _bloqueados():
    try:
        return set(_acessos().get('bloq') or {})
    except Exception as e:
        logging.warning('bloqueados: %s', e)
        return set()


def _atribuicoes(com_bloqueados=False):
    if _ATRIB['d'] is not None and time.time() - _ATRIB['t'] < 120:
        d, n = (_ATRIB['d'], _ATRIB['n'])
        return (d if com_bloqueados else _sem_bloqueados(d), n)
    d, nomes = ({}, {})
    try:
        for e in tabela_atribuicoes().query_entities("PartitionKey eq 'atr'"):
            if str(e.get('ate') or '').strip():
                continue
            em = str(e.get('email') or '').strip().lower()
            u = str(e.get('usina') or '').strip()
            if not em or not u:
                continue
            k = _norm(u)
            nomes[k] = u
            d.setdefault(em, []).append({'usina': k, 'papel': str(e.get('papel') or '')})
    except Exception as ex:
        logging.warning('atribuicoes: %s', ex)
        return (_ATRIB['d'] or {}, _ATRIB['n'] or {})
    _ATRIB['t'], _ATRIB['d'], _ATRIB['n'] = (time.time(), d, nomes)
    return (d if com_bloqueados else _sem_bloqueados(d), nomes)


def _sem_bloqueados(d):
    b = _bloqueados()
    return {em: v for em, v in d.items() if em not in b} if b else d


def _clusters_por_email():
    out = {}
    for em, p in (ident().get('porEmail') or {}).items():
        cl = p.get('clusters') or ([p['cluster']] if p.get('cluster') else [])
        out[str(em).strip().lower()] = [c for c in cl if c]
    return out


def _no_escopo(email, permitidos, mapa):
    if permitidos is None:
        return True
    for c in mapa.get(str(email or '').strip().lower(), []):
        if _norm(c) in permitidos:
            return True
    return False


def _filtro_pessoas(clusters):
    if clusters is None:
        return (None, {})
    pes = getattr(clusters, 'pessoas', None)
    if pes is not None:
        pes = set((_norm(x) for x in pes if x))
        return (pes, {x: [x] for x in pes})
    return (set((_norm(c) for c in clusters or [])), _clusters_por_email())


def _area_ok(linha, clusters, permitidos, campo='usina'):
    if permitidos is None:
        return True
    us = getattr(clusters, 'usinas', None)
    if us is None:
        return _norm(linha.get('cluster') or '') in permitidos
    u = _norm(linha.get(campo) or '')
    if u:
        return u in us
    reg = getattr(clusters, 'regioes', None)
    if reg is None:
        reg = set((_norm(_cluster_da_usina(x)) for x in us)) - {''}
        try:
            clusters.regioes = reg
        except Exception:
            pass
    return _norm(linha.get('cluster') or '') in reg


def _contar_fotos(d):
    fotos = d.get('fotos')
    if not isinstance(fotos, list) or (not fotos and (d.get('fotosResumo') or d.get('fotoItens'))):
        r = d.get('fotosResumo') or {}
        itens = [x for x in d.get('fotoItens') or [] if isinstance(x, dict)]
        n = _int0(r.get('total')) + len(itens)
        nd = _int0(r.get('comDesc')) + sum((1 for x in itens if '—' in str(x.get('desc') or '')))
        return (n, nd)
    n = len(fotos)
    nd = 0
    for f in fotos:
        if not isinstance(f, dict):
            continue
        desc = str(f.get('desc') or '').strip()
        if not desc:
            continue
        if f.get('campo'):
            if '—' in desc:
                nd += 1
        else:
            nd += 1
    return (n, nd)


def _int0(v):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _preenchido_item(i, v):
    t = i.get('tipo')
    if t == 'check':
        return v is True
    if t == 'verif':
        return v is not None
    if t in ('texto', 'num', 'dropdown', 'date'):
        return str('' if v is None else v).strip() != ''
    return v is not None and str(v).strip() != ''


V2_PISO = int(os.environ.get('PLACAR_PISO', '70') or '70')


V2_PESOS = {'sub': 30, 'foto': 25, 'obs': 20, 'desc': 15, 'assin': 10}


def _v2_pede_foto(c):
    return bool(c.get('anexo')) or bool(c.get('anexoApp'))


def _v2_e_na(c, na):
    fid = c.get('fid')
    if fid is not None and str(fid) in na:
        return True
    return fid is None and str(c.get('id')) in na


def _obs_do_fechamento(d):
    app = str(d.get('obs') or '').strip()
    intoc = set((str(x) for x in d.get('intocados') or []))
    items = d.get('items') or {}
    chk = []
    for c in d.get('checklist') or []:
        if not isinstance(c, dict) or str(c.get('tipo') or '').strip().lower() != 'texto':
            continue
        if not re.search('observ|coment', _norm(c.get('desc') or '')):
            continue
        if c.get('fid') is not None and str(c.get('fid')) in intoc:
            continue
        v = items.get(c.get('id'))
        t = v.strip() if isinstance(v, str) else ''
        if t and t != app and (t not in chk):
            chk.append(t)
    onde = '+'.join((x for x, tem in (('app', bool(app)), ('checklist', bool(chk))) if tem))
    return ('\n'.join(([app] if app else []) + chk), onde)


def _v2_achou_falha(checklist, items):
    for c in checklist or []:
        if _int0(c.get('ftype')) != 4 and str(c.get('tipo') or '').strip().lower() != 'verif':
            continue
        v = items.get(c.get('id'))
        if v is None:
            continue
        t = str(v).strip().lower()
        if t in ('3', '2', 'falha', 'falhou', 'falho', 'alerta', 'alert', 'fallo'):
            return True
    return False


def _qualidade_v2(ev):
    d = ev.get('dados') or {}
    checklist = d.get('checklist') or []
    items = d.get('items') or {}
    na = set((str(x) for x in d.get('naoAplica') or []))
    n_fotos, n_desc = _contar_fotos(d)
    partes = []
    req = [c for c in checklist if c.get('req')]
    if req:
        ok = sum((1 for c in req if not _v2_e_na(c, na) and _preenchido_item(c, items.get(c.get('id')))))
        n_na = sum((1 for c in req if _v2_e_na(c, na)))
        partes.append(('sub', V2_PESOS['sub'], ok / float(len(req)), '%d de %d respondidas%s' % (ok, len(req), ', %d NA' % n_na if n_na else '')))
    pedidas = sum((1 for c in checklist if _v2_pede_foto(c)))
    if pedidas:
        partes.append(('foto', V2_PESOS['foto'], min(1.0, n_fotos / float(pedidas)), '%d de %d pedidas' % (n_fotos, pedidas)))
    elif n_fotos:
        partes.append(('foto', V2_PESOS['foto'], 1.0, '%d foto(s), nenhuma exigida' % n_fotos))
    if _v2_achou_falha(checklist, items):
        obs, _onde = _obs_do_fechamento(d)
        partes.append(('obs', V2_PESOS['obs'], 1.0 if len(obs) >= 20 else 0.0, 'houve achado; %s' % ('descreveu' if len(obs) >= 20 else 'NAO descreveu')))
    if n_fotos:
        partes.append(('desc', V2_PESOS['desc'], n_desc / float(n_fotos), '%d de %d com descricao' % (n_desc, n_fotos)))
    assinou = str(d.get('assinatura') or '').startswith('data:image')
    partes.append(('assin', V2_PESOS['assin'], 1.0 if assinou else 0.0, 'assinou' if assinou else 'nao assinou'))
    base = sum((p for _k, p, _f, _d in partes)) or 1
    q = int(round(100.0 * sum((p * f for _k, p, f, _d in partes)) / base))
    geo = ev.get('geo') or {}
    tem_gps = isinstance(geo, dict) and geo.get('lat') is not None
    return {'q': q, 'gps': tem_gps, 'base': base, 'pontos': max(0, q - 60) if q >= V2_PISO and tem_gps else 0, 'itens': [{'rot': k, 'peso': p, 'pts': round(p * f, 1), 'det': dd} for k, p, f, dd in partes]}


def _qualidade_os(ev):
    d = ev.get('dados') or {}
    checklist = d.get('checklist') or []
    items = d.get('items') or {}
    req = [c for c in checklist if c.get('req')]
    sub = sum((1 for c in req if _preenchido_item(c, items.get(c.get('id'))))) / float(len(req)) if req else 1.0
    todas = bool(checklist) and all((_preenchido_item(c, items.get(c.get('id'))) for c in checklist))
    n_fotos, n_desc = _contar_fotos(d)
    foto = min(1.0, n_fotos / 3.0)
    desc = n_desc / float(n_fotos) if n_fotos else 0.0
    assin = 1.0 if str(d.get('assinatura') or '').startswith('data:image') else 0.0
    obs, obs_onde = _obs_do_fechamento(d)
    obs_s = 1.0 if len(obs) >= 20 else len(obs) / 20.0
    geo = ev.get('geo') or {}
    geo_fim = 1.0 if isinstance(geo, dict) and geo.get('lat') is not None else 0.0
    q = 25 * sub + 20 * foto + 10 * desc + 10 * assin + 15 * obs_s + 20 * geo_fim
    itens = [{'rot': 'Subtarefas obrigatórias', 'peso': 25, 'pts': round(25 * sub, 1), 'det': '%d de %d respondidas' % (sum((1 for c in req if _preenchido_item(c, items.get(c.get('id'))))), len(req)) if req else 'sem obrigatórias'}, {'rot': 'Fotos', 'peso': 20, 'pts': round(20 * foto, 1), 'det': '%d foto%s (3 dá o total)' % (n_fotos, '' if n_fotos == 1 else 's')}, {'rot': 'Fotos com descrição', 'peso': 10, 'pts': round(10 * desc, 1), 'det': '%d de %d' % (n_desc, n_fotos) if n_fotos else 'sem foto'}, {'rot': 'Assinatura', 'peso': 10, 'pts': round(10 * assin, 1), 'det': 'assinou' if assin else 'não assinou'}, {'rot': 'Observações', 'peso': 15, 'pts': round(15 * obs_s, 1), 'det': '%d caractere%s (20 dá o total)%s' % (len(obs), '' if len(obs) == 1 else 's', {'checklist': ' · escritos no checklist', 'app+checklist': ' · no App e no checklist'}.get(obs_onde, ''))}, {'rot': 'GPS no fechamento', 'peso': 20, 'pts': round(20 * geo_fim, 1), 'det': 'com posição' if geo_fim else 'sem posição'}]
    return {'q': int(round(q)), 'todas': bool(todas), 'n_fotos': n_fotos, 'n_desc': n_desc, 'obs_ok': len(obs) >= 20, 'geo_fim': geo_fim >= 1, 'assinou': assin >= 1, 'sub_ok': sub >= 0.999, 'itens': itens}


def _parse_iso(s):
    from datetime import datetime
    t = str(s).replace('Z', '').strip()
    return datetime.fromisoformat(t[:19])


_CL_USINA = {'t': 0.0, 'm': {}}


def _cluster_da_usina(usina):
    import time as _t
    if not usina:
        return ''
    if _t.time() - _CL_USINA['t'] > 300:
        m = {}
        try:
            for e in tabela_ronda_ativos().query_entities("PartitionKey eq 'usina'"):
                m[_norm(e.get('usina') or '')] = str(e.get('cluster') or '')
        except Exception as ex:
            logging.warning('cluster_da_usina: %s', ex)
            return ''
        _CL_USINA['t'], _CL_USINA['m'] = (_t.time(), m)
    return _CL_USINA['m'].get(_norm(usina), '')


def _link_fracttal_os(folio):
    base = os.environ.get('FRACTTAL_OS_LINK', 'https://one.fracttal.com/')
    return base.replace('{folio}', str(folio)) if '{folio}' in base else base


def _janela_str(req):
    de, ate = _janela(req)
    return (de.strftime('%Y-%m-%dT%H:%M:%S'), ate.strftime('%Y-%m-%dT%H:%M:%S'))


def _fora(ts, corte, teto):
    if not ts:
        return True
    if ts < corte:
        return True
    return bool(teto) and ts > teto


def tabela_decisoes():
    return _tabela('decisoes', '_table_decis')


SUP_CAP_BACKLOG = 6000


def _dias_entre(a, b):
    try:
        return round((_parse_iso(b) - _parse_iso(a)).total_seconds() / 86400.0, 1)
    except Exception:
        return None


STATUS_IN_REVIEW = 2


PT_VALIDADE_DIAS = int(os.environ.get('PT_VALIDADE_DIAS', '7') or '7')


PT_DESTAQUE_MIN = int(os.environ.get('PT_DESTAQUE_MIN', '30') or '30')


PT_CHECKLISTS = [{'id': 'altura', 'titulo': 'Trabalho em altura (acima de 2,00 m)', 'campo': '^trabalho em altura$', 'perguntas': ['Os executantes possuem ASO válido e com aptidão para trabalho em altura?', 'Os executantes possuem treinamento para trabalhos em altura (evidenciado Certificado de treinamento)?', 'Os EPIs atendem conforme disposto na NR 06 e NR 35?', 'Foi realizada a inspeção nos EPIs e EPCs? (ferrugem, trincos, desgaste, costuras soltas, cordas em mau estado, etc.)', 'Os EPCs estão adequados? (guarda-corpo, pontos de ancoragem, linha de vida, etc.)', 'Foram implantados dois sistemas fixos em pontos de ancoragem independentes? (um como forma de acesso e outro como corda de segurança)', 'Foram adotados procedimentos de segurança para atividades próximas ao local do trabalho em altura?', 'As condições climáticas estão favoráveis para a realização do trabalho? (intempéries)', 'Existe procedimento de emergências em caso de acidentes envolvendo altura?']}, {'id': 'escada', 'titulo': 'Trabalho com escada', 'campo': '^atividades? com escada$', 'perguntas': ['A escada possui base antiderrapante? (sapatas de borracha)', 'A escada está isenta de trincas nos degraus e/ou montantes?', 'A escada para reparos elétricos é constituída por material não condutor?', 'A escada está presa/ancorada impossibilitando a queda da mesma?', 'Degraus estão devidamente fixados nos montantes?', 'A escada está longe de redes energizadas?', 'Existe limitador de abertura ou de curso na escada?', 'No uso de escada marinheiro, o checklist de segurança foi preenchido e assinado?']}, {'id': 'telhado', 'titulo': 'Trabalho em telhados', 'campo': '^atividades? em telhados?$', 'perguntas': ['A estrutura do telhado foi avaliada para suportar as cargas durante o trabalho?', 'Foram avaliados o tipo de telha, seu estado e resistência? (rachaduras, trincas, etc.)', 'O telhado está longe das redes energizadas?', 'O equipamento encontra-se desligado para realização do trabalho sobre fornos ou equipamentos com emanações de gases?', 'Existem pranchões para andar sobre o telhado e estão presos?', 'Os trabalhadores estão utilizando EPIs?', 'Foi realizada a instalação de cabo-guia ou cabo de segurança para fixação do mecanismo de ligação por talabarte?', 'As condições climáticas estão favoráveis para a realização do trabalho? (trabalho externo)']}, {'id': 'cargas', 'titulo': 'Guindar e movimentação de cargas pesadas', 'campo': '^atividades? de movimentacao de (materiais|cargas)$', 'perguntas': ['Existe um plano das operações de elevação de cargas (Plano de Rigging)?', 'Quem procedeu com o Plano de Rigging tem qualificação?', 'O valor exato da carga é conhecido?', 'Está indicado no equipamento, em lugar visível, a carga máxima de trabalho permitida?', 'Foi realizada a inspeção visual nos equipamentos de içamento?', 'Estão definidas as competências e responsabilidades de todos os envolvidos nas movimentações mecânicas das cargas?', 'O local onde o equipamento está instalado garante estabilidade durante sua utilização?', 'Os ganchos possuem dispositivo eficiente que evite o desprendimento da carga?', 'Caso necessário depositar carga em telhado, todos os itens de altura foram considerados? (linha de vida, cinto, etc.)', 'Existe um colaborador responsável por guiar o processo de içamento?', 'Existem itens que possam oferecer risco no local aproximado? (rede viva)', 'As condições climáticas foram levadas em consideração?', 'Existem pontos de içamento definidos pelo fabricante do material/equipamento?']}, {'id': 'quimicos', 'titulo': 'Manuseio de produtos químicos', 'campo': '^atividades? com produtos quimicos$', 'perguntas': ['Todos os produtos possuem rótulo de segurança em boas condições de leitura?', 'A FDS (Ficha de Segurança, antiga FISPQ) foi analisada antes da execução do serviço?', 'Colaborador tem treinamento de recomendações das FDS dos produtos que irá manusear?', 'As fichas de segurança estão em locais de armazenagem e em condições de fácil acesso à leitura?', 'Foi feito o aterramento para a transferência de produtos inflamáveis?', 'A armazenagem dos produtos é feita de modo seguro?', 'Líquidos ou combustíveis inflamáveis estão armazenados em recipientes adequados?', 'Os recipientes de líquidos inflamáveis encontram-se em locais afastados de possíveis fontes de calor?', 'Existe sinalização de emergência de produtos inflamáveis?', 'O local onde os produtos inflamáveis estão armazenados possui ventilação?', 'Os colaboradores utilizam os EPIs para manusear os produtos?', 'Existe equipamento de proteção contra incêndio disponível no local?', 'As ferramentas utilizadas são antifaíscas ou intrinsecamente seguras nas áreas classificadas?', 'O local de trabalho é caracterizado como área classificada?']}, {'id': 'eletrica', 'titulo': 'Proteção para trabalhos com eletricidade', 'campo': '^atividades? com eletrica energizada$', 'perguntas': ['Todos os trabalhadores executantes são capacitados e autorizados?', 'Os trabalhadores estão com o treinamento de NR 10 vigente?', 'O trabalho está sendo executado por no mínimo dois profissionais habilitados, qualificados e/ou capacitados?', 'Existe um profissional habilitado acompanhando os trabalhadores capacitados?', 'Possui técnico responsável pela instalação?', 'Colaborador não está utilizando adornos (pulseira, brincos, anéis, colares, relógios, etc.) para realizar a atividade em eletricidade?', 'O local de trabalho está limpo, organizado e seco?', 'As condições climáticas estão favoráveis para a realização do trabalho? (trabalho externo)', 'Há necessidade do seccionamento da energia da concessionária?', 'Foi isolado/desenergizado as redes elétricas onde será a execução do trabalho?', 'Foi isolado/desenergizado as redes elétricas próximas à execução do trabalho?', 'Existe a impossibilidade de realizar a desenergização e isolamento da rede elétrica onde será realizado o trabalho?', 'Os trabalhadores estão utilizando os EPIs adequados para o trabalho em rede energizada?', 'Está prevista a utilização de tensão reduzida?', 'Foi realizado o aterramento temporário? (Quando necessário)', 'Foi realizado o travamento, bloqueio e sinalização para impedir a reenergização?', 'Foi realizado teste de ausência de tensão?', 'As ferramentas de desbloqueio e destravamento estão em poder dos executantes?', 'Cada executante está com a ferramenta de desbloqueio e destravamento da rede na qual executa o serviço, impossibilitando que outro colaborador religue a rede?', 'As ferramentas a serem utilizadas são isoladas e adequadas ao trabalho?', 'As escadas são de material não condutor?', 'Os equipamentos elétricos e extensões possuem conexões adequadas para ligamento na rede energizada do local?', 'Os cabos ou extensões estão isentos de emendas?', 'As ferramentas elétricas estão em ótimo estado de conservação?', 'Foi retirada todas as pessoas não autorizadas da zona controlada?', 'Existe equipamento de proteção contra incêndio adequado disponível no local?']}]


PT_POR_ID = {c['id']: c for c in PT_CHECKLISTS}


def _pt_chave_tarefa(os_, codigo, tarefa):
    return '%s|%s|%s' % (str(os_ or '').strip(), str(codigo or '').strip(), _norm(tarefa))


def _pt_dt(iso):
    from datetime import datetime as _dt, timezone as _tz
    try:
        return _dt.fromisoformat(str(iso).replace('Z', '+00:00')[:32]).astimezone(_tz.utc)
    except Exception:
        return None


def _pt_br(iso, fmt='%d/%m %H:%M'):
    from datetime import timedelta as _td
    d = _pt_dt(iso)
    return (d - _td(hours=3)).strftime(fmt) if d else ''


def _pt_numero(e):
    return 'PT-%s-%s' % (str(e.get('os') or ''), _pt_br(e.get('criado_em'), '%d%m-%H%M') or '0000')


PT_CAMPOS_RESUMO = ('PartitionKey', 'RowKey', 'os', 'tarefa', 'codigo', 'chave', 'chave_t', 'usina', 'cluster', 'ativo', 'email', 'nome', 'status', 'criado_em', 'decidido_em', 'decidido_nome', 'decidido_papel', 'motivo', 'efeito', 'naos', 'faltam', 'atividades', 'aviso1_em', 'aviso1_quem', 'aviso1_motivo', 'forcado')


PT_HIST_DIAS_MAX = 400


PT_HIST_MAX = 2000


def _pt_lista(dias=30, campos=None, status=None):
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
    ref = _pt_dt(_agora_iso()) or _dt.now(_tz.utc)
    desde = (ref - _td(days=max(1, int(dias)))).strftime('%Y-%m-%dT%H:%M:%S')
    flt = "PartitionKey eq 'pt' and criado_em ge '%s'" % desde
    if status == 'aguardando':
        flt += " and status eq 'aguardando'"
    if campos:
        try:
            return list(tabela().query_entities(flt, select=list(campos)))
        except TypeError:
            logging.warning('pt lista: query_entities sem select; lendo as colunas todas')
    return list(tabela().query_entities(flt))


def _pt_publico(e, completo=False, esc=None, email=None):
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz

    def js(k, fb):
        try:
            v = json.loads(e.get(k) or '')
            return v if isinstance(v, type(fb)) else fb
        except Exception:
            return fb
    agora = _pt_dt(_agora_iso()) or _dt.now(_tz.utc)
    st = str(e.get('status') or 'aguardando')
    cri, dec = (_pt_dt(e.get('criado_em')), _pt_dt(e.get('decidido_em')))
    ate = dec + _td(days=PT_VALIDADE_DIAS) if st == 'de_acordo' and dec else None
    ativs = []
    for a in js('atividades', []):
        c = PT_POR_ID.get(str((a or {}).get('id') or ''))
        if not c:
            continue
        r = list((a or {}).get('r') or [])
        item = {'id': c['id'], 'titulo': c['titulo'], 'n': len(c['perguntas']), 'sim': r.count('SIM'), 'nao': r.count('NAO'), 'na': r.count('NA'), 'naos': [i + 1 for i, x in enumerate(r) if x == 'NAO']}
        if completo:
            item['itens'] = [{'n': i + 1, 'q': q, 'r': r[i] if i < len(r) else ''} for i, q in enumerate(c['perguntas'])]
        ativs.append(item)
    out = {'id': e.get('RowKey'), 'numero': _pt_numero(e), 'os': e.get('os') or '', 'tarefa': e.get('tarefa') or '', 'codigo': e.get('codigo') or '', 'chave': e.get('chave') or '', 'chave_t': e.get('chave_t') or _pt_chave_tarefa(e.get('os'), e.get('codigo'), e.get('tarefa')), 'usina': e.get('usina') or '', 'cluster': e.get('cluster') or '', 'ativo': e.get('ativo') or '', 'email': e.get('email') or '', 'nome': e.get('nome') or '', 'status': st, 'criado_em': e.get('criado_em') or '', 'criado_br': _pt_br(e.get('criado_em')), 'decidido_em': e.get('decidido_em') or '', 'decidido_br': _pt_br(e.get('decidido_em')), 'decidido_nome': e.get('decidido_nome') or '', 'decidido_papel': e.get('decidido_papel') or '', 'motivo': e.get('motivo') or '', 'efeito': e.get('efeito') or '', 'idade_min': int((agora - cri).total_seconds() // 60) if cri else None, 'validade_ate': ate.strftime('%Y-%m-%dT%H:%M:%SZ') if ate else '', 'validade_br': _pt_br(ate.strftime('%Y-%m-%dT%H:%M:%SZ')) if ate else '', 'vencida': bool(ate and agora > ate), 'naos': int(e.get('naos') or 0), 'faltam': int(e.get('faltam') or 0), 'atividades': ativs}
    if st == 'aguardando':
        quem, _dest = _pt_destinos(e)
        out['assina_agora'] = quem
        out['assina_agora_txt'] = _pt_quem_txt(quem)
    else:
        out['assina_agora'], out['assina_agora_txt'] = ('', '')
    if esc is not None:
        pode, porque = _pt_pode_assinar(esc, email, e)
        out['pode_assinar'], out['motivo_nao'] = (bool(pode and st == 'aguardando'), '' if pode else porque)
    out['aviso_br'] = _pt_br(e.get('aviso1_em')) if e.get('aviso1_em') else ''
    out['aviso_quem'] = e.get('aviso1_quem') or ''
    out['aviso_motivo'] = e.get('aviso1_motivo') or ''
    out['forcado'] = [{'nome': x.get('nome') or x.get('email'), 'quando_br': _pt_br(x.get('quando'))} for x in _pt_forcados_lista(e)]
    if completo:
        out['apr'] = js('apr', {})
        out['foto'] = bool(e.get('foto'))
        out['comentarios'] = js('comentarios', [])
        out['ass_tec'] = e.get('ass_tec') or ''
        out['ass_aprov'] = e.get('ass_aprov') or ''
    return out


def _pt_lista_aprovadores():
    return [x.strip().lower() for x in (os.environ.get('PT_APROVADORES') or '').split(',') if x.strip()]


def _pt_emails_cos():
    return [x.strip().lower() for x in (os.environ.get('PT_EMAIL_COS') or '').split(',') if x.strip()]


def _pt_cos_operadores():
    return [x.strip().lower() for x in (os.environ.get('PT_COS_OPERADORES') or '').split(',') if x.strip()]


_PT_RESP = {'t': 0.0, 'v': None}


PT_RESP_TTL_S = int(os.environ.get('PT_RESP_TTL_S', '600') or '600')


def _pt_tok_cod(c):
    return [t for t in re.split('[-\\s_/]+', _norm(c)) if t]


def _pt_meio_usina(u):
    p = [x.strip() for x in re.split('\\s+-\\s*|\\s*-\\s+', str(u or '')) if x.strip()]
    return _norm(' - '.join(p[1:-1]) if len(p) >= 3 else ' '.join(p))


def _pt_resp_bd():
    import time as _t
    if _PT_RESP['v'] is not None and _t.time() - _PT_RESP['t'] < PT_RESP_TTL_S:
        return _PT_RESP['v']
    rows, quando = ([], '')
    try:
        e = tabela().get_entity('cadastro', 'bd_responsaveis')
        rows = json.loads(e.get('json') or '[]') or []
        quando = e.get('quando') or ''
    except Exception as ex:
        logging.info('pt dono das usinas: %s', str(ex)[:120])
    por_cod, por_nome = ({}, {})
    for r in rows:
        if not isinstance(r, dict) or not r.get('r'):
            continue
        t = tuple(_pt_tok_cod(r.get('c')))
        if t:
            por_cod.setdefault(t, []).append(r)
        por_nome.setdefault(_norm(r.get('u')), []).append(r)
    v = {'rows': rows, 'por_cod': por_cod, 'por_nome': por_nome, 'quando': quando}
    _PT_RESP['v'], _PT_RESP['t'] = (v, _t.time())
    return v


def _pt_resp_da_pt(p):
    idx = _pt_resp_bd()
    if not idx['rows']:
        return None
    toks = _pt_tok_cod(p.get('ativo') or p.get('codigo') or '')
    achou = []
    for i in range(len(toks)):
        for j in range(i + 1, len(toks) + 1):
            for r in idx['por_cod'].get(tuple(toks[i:j]), []):
                achou.append((j - i, r))
    if achou:
        tam = max((a for a, _r in achou))
        donos = {_norm(r['r']): r for a, r in achou if a == tam}
        como = 'codigo'
    else:
        donos = {_norm(r['r']): r for r in idx['por_nome'].get(_pt_meio_usina(p.get('usina')), [])}
        como = 'nome'
    if len(donos) != 1:
        return None
    r = next(iter(donos.values()))
    return {'responsavel': r['r'], 'email': _pt_sup_email(r['r']), 'como': como, 'usina_bd': r.get('u') or ''}


def _pt_sup_email(nome):
    n = _norm(nome)
    if not n:
        return ''
    for par in (os.environ.get('PT_SUP_EMAILS') or '').split(';'):
        k, _s, v = par.partition('=')
        if not _s or _norm(k) != n:
            continue
        v = v.strip().lower()
        if '@' in v:
            return v
        if v in ('', '-'):
            return ''
    toks = [t for t in n.split() if len(t) > 2]
    if not toks:
        return ''
    alvo = {toks[0], toks[-1]}
    cand = []
    for em, s in (_acessos().get('sups') or {}).items():
        nm = set(_norm((s or {}).get('nome') or '').split()) | set(_norm(str(em).split('@')[0].replace('.', ' ')).split())
        if alvo <= nm:
            cand.append(str(em).lower())
    return cand[0] if len(cand) == 1 else ''


def _pt_forcados_lista(p):
    try:
        L = json.loads(p.get('forcado') or '[]')
    except Exception:
        L = []
    return [x for x in L if isinstance(x, dict) and x.get('email')] if isinstance(L, list) else []


def _pt_forcados(p):
    return {str(x.get('email')).strip().lower() for x in _pt_forcados_lista(p)}


def _pt_agora_brt():
    from datetime import timedelta as _td
    d = _pt_dt(_agora_iso())
    return d - _td(hours=3) if d else None


def _pt_quem_assina(agora_brt=None):
    a = agora_brt or _pt_agora_brt()
    if a is None:
        return 'supervisor'
    fer = {x.strip() for x in (os.environ.get('PT_FERIADOS') or '').split(',') if x.strip()}
    return 'cos' if a.weekday() >= 5 or a.strftime('%Y-%m-%d') in fer else 'supervisor'


def _pt_quem_txt(quem, dia=None):
    if quem == 'supervisor':
        return 'o supervisor da usina (segunda a sexta)'
    if (dia or _pt_quem_assina()) == 'cos':
        return 'o COS (fim de semana ou feriado)'
    return 'o COS (a usina não tem supervisor cadastrado)'


def _pt_usina_norm(u):
    s = str(u or '')
    if ' · ' in s:
        s = s.split(' · ', 1)[1]
    return _norm(s)


def _pt_supervisores(p):
    try:
        bd = _pt_resp_da_pt(p)
    except Exception as ex:
        logging.warning('pt supervisores (BD_Operacoes): %s', ex)
        bd = None
    if bd and bd.get('email'):
        return [bd['email']]
    u = _pt_usina_norm(p.get('usina'))
    if not u:
        return []
    out = set()
    try:
        atr, _ = _atribuicoes()
        for em, lst in atr.items():
            if any((a.get('usina') == u and a.get('papel') == 'responsavel' for a in lst)):
                out.add(str(em).lower())
    except Exception as ex:
        logging.warning('pt supervisores (atribuicoes): %s', ex)
    try:
        for em, s_ in (_acessos().get('sups') or {}).items():
            if u in {_norm(x) for x in s_.get('usinas') or []}:
                out.add(str(em).lower())
    except Exception as ex:
        logging.warning('pt supervisores (acessos): %s', ex)
    return sorted(out)


def _pt_esc_usina(esc, p):
    cls = (esc or {}).get('clusters')
    if cls is None:
        return True
    us = getattr(cls, 'usinas', None)
    if us is not None:
        return bool(p.get('usina')) and _pt_usina_norm(p.get('usina')) in us
    return bool(p.get('cluster')) and _norm(p.get('cluster')) in {_norm(c) for c in cls}


def _pt_ve(esc, email, p):
    em = str(email or '').strip().lower()
    papel = str((esc or {}).get('papel') or '')
    if papel == 'Admin' or papel.upper() == 'COS' or (em and (em in _pt_lista_aprovadores() or em in _pt_cos_operadores())):
        return True
    if em and (em in _pt_supervisores(p) or em in _pt_forcados(p)):
        return True
    return papel == 'Supervisor' and _pt_esc_usina(esc, p)


def _pt_pode_assinar(esc, email, p, quem=None):
    em = str(email or '').strip().lower()
    if em and em == str(p.get('email') or '').strip().lower():
        return (False, 'Quem pediu a PT não pode assiná-la.')
    papel = str((esc or {}).get('papel') or '')
    if papel == 'Admin' or (em and em in _pt_lista_aprovadores()):
        return (True, '')
    quem = quem or _pt_quem_assina()
    cos = papel.upper() == 'COS' or bool(em and em in _pt_cos_operadores())
    if quem == 'cos':
        return (True, '') if cos else (False, 'No fim de semana e no feriado quem assina a PT é o COS.')
    if papel == 'Supervisor' and _pt_esc_usina(esc, p) or (em and (em in _pt_supervisores(p) or em in _pt_forcados(p))):
        return (True, '')
    if cos:
        if not _pt_supervisores(p):
            return (True, '')
        return (False, 'De segunda a sexta quem assina a PT é o supervisor da usina.')
    return (False, 'Esta PT é de uma usina fora do seu escopo.')


def _pt_destinos(p, quem=None):
    quem = quem or _pt_quem_assina()
    if quem == 'supervisor':
        sups = _pt_supervisores(p)
        if sups:
            return ('supervisor', sups)
    return ('cos', _pt_emails_cos())


LIMIARES_PADRAO = {'os_critico_q': 50, 'os_atencao_q': 70, 'os_exemplar_q': 95, 'os_tempo_min_pct': 20, 'ronda_critico_q': 60, 'ronda_atencao_q': 85, 'ronda_exemplar_q': 95, 'ronda_dur_min': 10, 'sup_latencia_critica': 7, 'sup_latencia_atencao': 3, 'sup_divergencia': 30, 'usina_dias_critico': 14, 'usina_dias_atencao': 7, 'img_escura': 42, 'img_estourada': 226, 'img_borrada': 6, 'img_margem': 8, 'img_min_ref': 2, 'traj_raio_m': 30, 'traj_min_fotos': 8, 'traj_janela_min': 5, 'traj_janela_fotos': 15, 'traj_cobertura_gps': 60, 'img_margem_afer': 25}


_lim_cache = {'t': 0.0, 'v': None}


def tabela_limiares():
    return _tabela('limiares', '_table_limiares')


def _limiares(forcar=False):
    if not forcar and _lim_cache['v'] is not None and (time.time() - _lim_cache['t'] < 60):
        return _lim_cache['v']
    v = dict(LIMIARES_PADRAO)
    try:
        e = tabela_limiares().get_entity('lim', 'atual')
        for k in LIMIARES_PADRAO:
            if e.get(k) is not None:
                try:
                    v[k] = int(e[k])
                except Exception:
                    pass
    except Exception:
        pass
    _lim_cache.update({'t': time.time(), 'v': v})
    return v


def _duracao_ronda(r):
    ini, fim = (str(r.get('inicio') or ''), str(r.get('fim') or ''))
    if not ini or not fim:
        return None
    try:
        d = (_parse_iso(fim) - _parse_iso(ini)).total_seconds() / 60.0
    except Exception:
        return None
    try:
        pausado = max(0, int(r.get('pausado_min') or 0))
    except Exception:
        pausado = 0
    if r.get('retomada_outro_dia'):
        d -= pausado
        return int(round(d)) if 0 <= d <= 480 else None
    if not 0 <= d <= 480:
        return None
    d -= pausado
    return int(round(max(0, d)))


def _veredito_os(r, lim):
    q = int(r.get('qualidade') or 0)
    sem_foto = int(r.get('n_fotos') or 0) == 0
    sem_gps = not r.get('geo_ok')
    prev = int(r.get('fx_dur_prev_min') or 0)
    real = int(r.get('fx_dur_real_min') or 0)
    rapido = bool(prev and real and (100.0 * real / prev < lim['os_tempo_min_pct']))
    faltas = []
    if sem_gps:
        faltas.append('sem GPS')
    if sem_foto:
        faltas.append('sem foto')
    if not r.get('assinou', True):
        faltas.append('sem assinatura')
    if sem_gps and sem_foto:
        m = 'Não dá para comprovar que foi executada: <b>sem GPS, sem foto</b>'
        if rapido:
            m += ' e fechada em <b>%d min de %d previstos</b>' % (real, prev)
        return {'nivel': 'critico', 'titulo': 'NÃO ESTÁ BOM', 'motivo': m + '.'}
    if q < lim['os_critico_q']:
        return {'nivel': 'critico', 'titulo': 'NÃO ESTÁ BOM', 'motivo': 'Registro incompleto — qualidade <b>%d%%</b>%s.' % (q, ' · ' + ', '.join(faltas) if faltas else '')}
    if rapido:
        return {'nivel': 'critico', 'titulo': 'TEMPO INCOMPATÍVEL', 'motivo': 'Executada em <b>%d min</b> de <b>%d previstos</b> — tempo insuficiente para a tarefa.' % (real, prev)}
    if q >= lim['os_exemplar_q'] and (not faltas):
        return {'nivel': 'exemplar', 'titulo': 'MUITO BOM', 'motivo': 'Registro completo: %d foto%s, GPS, assinatura e observações.' % (int(r.get('n_fotos') or 0), 's' if int(r.get('n_fotos') or 0) != 1 else '')}
    if q < lim['os_atencao_q'] or faltas:
        return {'nivel': 'atencao', 'titulo': 'ATENÇÃO', 'motivo': 'Qualidade <b>%d%%</b>%s.' % (q, ' · falta ' + ', '.join(faltas) if faltas else '')}
    return None


def _veredito_ronda(r, lim):
    q = int(r.get('qualidade') or 0)
    dur = r.get('duracao_min')
    tt, tr = (int(r.get('trk_total') or 0), int(r.get('trk_resp') or 0))
    try:
        falhas = json.loads(r.get('falhas') or '[]')
    except Exception:
        falhas = []
    try:
        tem_gps = (json.loads(r.get('geo') or '{}') or {}).get('lat') is not None
    except Exception:
        tem_gps = False
    curta = dur is not None and dur < lim['ronda_dur_min']
    if curta and (not tem_gps or (tt and tr == 0)):
        det = []
        if not tem_gps:
            det.append('sem GPS')
        if tt:
            det.append('%d de %d trackers' % (tr, tt))
        return {'nivel': 'critico', 'titulo': 'NÃO ESTÁ BOM', 'motivo': 'Ronda de <b>%d min</b> — %s. Não houve visita.' % (dur, ' · '.join(det))}
    if not tem_gps:
        return {'nivel': 'critico', 'titulo': 'NÃO ESTÁ BOM', 'motivo': '<b>Sem GPS</b> — não há prova de que a ronda foi feita em campo.'}
    if tt and tr == 0:
        return {'nivel': 'critico', 'titulo': 'SEM DEVOLUTIVA', 'motivo': 'A performance apontou <b>%d trackers</b> e <b>nenhum</b> foi respondido.' % tt}
    if curta:
        return {'nivel': 'atencao', 'titulo': 'ATENÇÃO', 'motivo': 'Ronda de <b>%d min</b> — abaixo do tempo mínimo do checklist.' % dur}
    if q < lim['ronda_critico_q']:
        return {'nivel': 'critico', 'titulo': 'NÃO ESTÁ BOM', 'motivo': 'Qualidade <b>%d%%</b>%s.' % (q, ' · ' + ', '.join(falhas) if falhas else '')}
    if q >= lim['ronda_exemplar_q'] and (not falhas) and (not tt or tr == tt):
        return {'nivel': 'exemplar', 'titulo': 'MUITO BOM', 'motivo': 'GPS na usina%s · checklist completo%s.' % (' · %d de %d trackers' % (tr, tt) if tt else '', ' · %d min' % dur if dur else '')}
    if q < lim['ronda_atencao_q'] or falhas:
        return {'nivel': 'atencao', 'titulo': 'ATENÇÃO', 'motivo': 'Qualidade <b>%d%%</b>%s%s.' % (q, ' · ' + ', '.join(falhas) if falhas else '', ' · %d de %d trackers' % (tr, tt) if tt and tr < tt else '')}
    return None


def _veredito_usina(u, dias, lim):
    if dias is None or dias >= 999:
        return {'nivel': 'critico', 'titulo': 'NUNCA RONDADA', 'motivo': 'Nenhuma ronda registrada nesta usina.'}
    if dias >= lim['usina_dias_critico']:
        return {'nivel': 'critico', 'titulo': 'SEM RONDA', 'motivo': '<b>%d dias</b> sem ronda.' % round(dias)}
    if dias >= lim['usina_dias_atencao']:
        return {'nivel': 'atencao', 'titulo': 'SEM RONDA', 'motivo': '<b>%d dias</b> sem ronda.' % round(dias)}
    return None


GESTAO_OS_MAX = 200


GESTAO_TODAS_MAX = int(os.environ.get('GESTAO_TODAS_MAX', '5000') or '5000')


def _concentracao(itens, chave_fn, rotulo, sufixo):
    cont = {}
    for i in itens:
        k = (chave_fn(i) or '').strip()
        if k:
            cont[k] = cont.get(k, 0) + 1
    total = sum(cont.values())
    if not total:
        return None
    ordenado = sorted(cont.items(), key=lambda x: -x[1])
    acum = n = 0
    for _k, v in ordenado:
        acum += v
        n += 1
        if acum >= total * 0.8:
            break
    return {'rotulo': rotulo, 'sufixo': sufixo, 'n': n, 'pct': int(round(100.0 * acum / total)), 'total': total, 'top': [{'nome': k, 'n': v} for k, v in ordenado[:5]]}


def _gestao_prioridades(dias=30, clusters=None, janela=None):
    from datetime import datetime, timedelta
    lim = _limiares()
    corte = (datetime.utcnow() - timedelta(days=int(dias))).strftime('%Y-%m-%dT%H:%M:%S')
    corte_d = (datetime.utcnow() - timedelta(days=int(dias))).strftime('%Y-%m-%d')
    teto = None
    if janela:
        corte, teto = (janela[0], janela[1])
    teto_d = None
    if janela:
        corte_d, teto_d = (corte[:10], teto[:10])
    hoje = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')
    permitidos, mapa = _filtro_pessoas(clusters)
    I = ident()
    sup_de = {str(em).lower(): _sup_canon((p or {}).get('supervisor')) for em, p in (I.get('porEmail') or {}).items()}
    itens, exemplares = ([], [])
    n_os = n_ronda = 0
    sup_lat, sup_div = ({}, {})
    try:
        for e in tabela_qlog().query_entities("PartitionKey eq 'q'"):
            if _fora(str(e.get('server_ts') or ''), corte, teto):
                continue
            em = str(e.get('email') or '').lower()
            if not _no_escopo(em, permitidos, mapa):
                continue
            n_os += 1
            r = dict(e)
            sup = sup_de.get(em) or '(sem supervisor)'
            v = _veredito_os(r, lim)
            base = {'tipo': 'os', 'id': r.get('os'), 'quem': r.get('nome') or em, 'email': em, 'onde': r.get('usina') or r.get('fx_ativo') or '', 'supervisor': sup, 'cluster': r.get('cluster') or r.get('fx_area') or '', 'quando': r.get('server_ts'), 'qualidade': int(r.get('qualidade') or 0), 'link': _link_fracttal_os(r.get('os'))}
            if v and v['nivel'] == 'exemplar':
                exemplares.append(dict(base, **v))
            elif v:
                itens.append(dict(base, **v))
            fim = str(r.get('fx_final') or r.get('dev_ts') or '')[:19]
            aprov = str(r.get('fx_aprov') or '')[:19]
            st = int(r.get('fx_status') or 0)
            if fim and st == STATUS_IN_REVIEW:
                d = _dias_entre(fim, hoje)
                if d is not None:
                    a = sup_lat.setdefault(sup, {'n': 0, 'max': 0, 'os': []})
                    a['n'] += 1
                    a['max'] = max(a['max'], d)
                    if r.get('os'):
                        a['os'].append(r.get('os'))
            rating = int(r.get('fx_rating') or 0)
            q = int(r.get('qualidade') or 0)
            if rating and q and (rating * 20 - q >= lim['sup_divergencia']):
                b = sup_div.setdefault(sup, {'n': 0, 'os': []})
                b['n'] += 1
                b['os'].append(r.get('os'))
    except Exception as ex:
        logging.warning('prioridades qlog: %s', ex)
    ultima_usina = {}
    try:
        for e in tabela_ronda().query_entities("PartitionKey ge '%s'" % corte_d):
            if not e.get('finalizada'):
                continue
            if not _area_ok(e, clusters, permitidos):
                continue
            n_ronda += 1
            r = dict(e)
            r['duracao_min'] = _duracao_ronda(r)
            u, d = (r.get('usina') or '', str(r.get('PartitionKey') or ''))
            if u and (u not in ultima_usina or d > ultima_usina[u]):
                ultima_usina[u] = d
            v = _veredito_ronda(r, lim)
            base = {'tipo': 'ronda', 'id': r.get('PartitionKey'), 'quem': r.get('nome') or r.get('email'), 'email': r.get('email'), 'onde': u, 'cluster': r.get('cluster') or '', 'quando': r.get('PartitionKey'), 'qualidade': int(r.get('qualidade') or 0), 'duracao': r['duracao_min'], 'data': r.get('PartitionKey')}
            if v and v['nivel'] == 'exemplar':
                exemplares.append(dict(base, **v))
            elif v:
                itens.append(dict(base, **v))
    except Exception as ex:
        logging.warning('prioridades rondas: %s', ex)
    hoje_d = _hoje()
    nunca = []
    for x in _usinas_do_cluster(clusters):
        u = x['usina']
        ult = ultima_usina.get(u)
        if not ult:
            nunca.append(u)
            continue
        dd = _dias_entre(ult, hoje_d)
        v = _veredito_usina(u, dd, lim)
        if v:
            itens.append(dict({'tipo': 'usina', 'id': u, 'quem': '', 'onde': u, 'cluster': x.get('cluster') or '', 'quando': ult, 'dias': dd if dd is not None else 999}, **v))
    if nunca:
        itens.append({'tipo': 'usina_nunca', 'id': 'nunca', 'quem': '', 'onde': '', 'cluster': '', 'nivel': 'atencao', 'titulo': 'SEM COBERTURA', 'motivo': '<b>%d usinas</b> ainda não receberam nenhuma ronda pelo app.' % len(nunca), 'quando': None, 'dias': 0, 'usinas': sorted(nunca)[:60]})
    for sup, a in sup_lat.items():
        if a['max'] >= lim['sup_latencia_critica']:
            itens.append({'tipo': 'supervisor', 'id': sup, 'quem': sup, 'onde': '', 'cluster': '', 'nivel': 'atencao', 'titulo': 'FILA PARADA', 'motivo': '<b>%d OS</b> em verificação, a mais antiga há <b>%d dias</b>.' % (a['n'], round(a['max'])), 'quando': None, 'os': [x for x in a.get('os') or [] if x][:8]})
    for sup, b in sup_div.items():
        itens.append({'tipo': 'supervisor', 'id': sup, 'quem': sup, 'onde': '', 'cluster': '', 'nivel': 'critico', 'titulo': 'AVALIAÇÃO ERRADA', 'motivo': 'Deu nota alta em <b>%d OS</b> cujo registro ficou abaixo do aceitável — sem verificação real.' % b['n'], 'quando': None, 'os': b['os'][:8]})
    ordem = {'critico': 0, 'atencao': 1}
    itens.sort(key=lambda x: (ordem.get(x['nivel'], 2), -(x.get('dias') or 0), x.get('qualidade') or 0))
    exemplares.sort(key=lambda x: -(x.get('qualidade') or 0))
    criticos = [i for i in itens if i['nivel'] == 'critico']
    conc = [c for c in [_concentracao([i for i in itens if i['tipo'] in ('os', 'ronda')], lambda i: i.get('quem'), 'pessoas', 'dos desvios'), _concentracao([i for i in itens if i['tipo'] == 'usina'], lambda i: i.get('onde'), 'usinas', 'do atraso de ronda'), _concentracao([i for i in itens if i['tipo'] == 'supervisor'], lambda i: i.get('quem'), 'supervisores', 'dos problemas de verificação')] if c]
    return {'gerado_em': _agora_iso(), 'periodo_dias': int(dias), 'limiares': lim, 'resumo': {'total': len(itens), 'criticos': len(criticos), 'atencao': len(itens) - len(criticos), 'exemplares': len(exemplares), 'os_periodo': n_os, 'rondas_periodo': n_ronda, 'por_tipo': {t: len([i for i in itens if i['tipo'] == t]) for t in ('os', 'ronda', 'usina', 'supervisor')}}, 'concentracao': conc, 'itens': itens[:120], 'exemplares': exemplares[:12], 'totais': {'itens': len(itens), 'exemplares': len(exemplares)}}


def _gestao_os(dias=30, filtros=None, clusters=None, janela=None, inteira=False):
    from datetime import datetime, timedelta
    f = filtros or {}
    corte = (datetime.utcnow() - timedelta(days=int(dias))).strftime('%Y-%m-%dT%H:%M:%S')
    teto = None
    if janela:
        corte, teto = (janela[0], janela[1])
    permitidos, mapa = _filtro_pessoas(clusters)
    I = ident()
    sup_de = {str(em).lower(): _sup_canon((p or {}).get('supervisor')) for em, p in (I.get('porEmail') or {}).items()}
    todas, linhas = ([], [])
    try:
        for e in tabela_qlog().query_entities("PartitionKey eq 'q'"):
            if _fora(str(e.get('server_ts') or ''), corte, teto):
                continue
            em = str(e.get('email') or '').lower()
            if not _no_escopo(em, permitidos, mapa):
                continue
            r = dict(e)
            r['_sup'] = sup_de.get(em) or '(sem supervisor)'
            r['_reg'] = str(r.get('cluster') or r.get('fx_area') or '').strip()
            todas.append(r)
    except Exception as ex:
        logging.warning('gestao os: %s', ex)

    def passa(r):
        if f.get('email') and str(r.get('email') or '').lower() != str(f['email']).lower():
            return False
        if f.get('sup') and _norm(r['_sup']) != _norm(f['sup']):
            return False
        if f.get('cluster') and _norm(r.get('_reg') or '') != _norm(f['cluster']):
            return False
        if f.get('tipo') and _norm(r.get('fx_tipo') or '') != _norm(f['tipo']):
            return False
        if f.get('crit') and _norm(r.get('fx_crit') or '') != _norm(f['crit']):
            return False
        return True
    linhas = [r for r in todas if passa(r)]

    def opcoes(chave, rot=None):
        vs = {}
        for r in todas:
            v = (rot(r) if rot else str(r.get(chave) or '')).strip()
            if v:
                vs[v] = vs.get(v, 0) + 1
        return sorted([{'v': k, 'n': n} for k, n in vs.items()], key=lambda x: -x['n'])
    n = len(linhas)
    aprovadas = [r for r in linhas if str(r.get('rev') or '') == 'aprovada']
    devolvidas = [r for r in linhas if r.get('foi_devolvida')]
    primeira_ok = [r for r in aprovadas if not r.get('foi_devolvida')]
    pontuais = [r for r in linhas if r.get('pontual')]
    com_tempo = [r for r in linhas if int(r.get('fx_dur_real_min') or 0) > 0 and int(r.get('fx_dur_prev_min') or 0) > 0]
    desvio_tempo = None
    if com_tempo:
        desvio_tempo = int(round(100.0 * sum((int(r['fx_dur_real_min']) / float(int(r['fx_dur_prev_min'])) for r in com_tempo)) / len(com_tempo)))

    def _opcoes_pessoa(rows):
        m = {}
        for r in rows:
            em = str(r.get('email') or '').lower()
            if not em:
                continue
            a = m.setdefault(em, {'v': em, 'rot': r.get('nome') or em, 'n': 0})
            a['n'] += 1
        return sorted(m.values(), key=lambda x: -x['n'])

    def agrupa(chave_fn, rotulo):
        g = {}
        for r in linhas:
            k = chave_fn(r) or '—'
            a = g.setdefault(k, {'nome': k, 'os': 0, 'q': 0, 'dev': 0, 'pont': 0})
            a['os'] += 1
            a['q'] += int(r.get('qualidade') or 0)
            if r.get('foi_devolvida'):
                a['dev'] += 1
            if r.get('pontual'):
                a['pont'] += 1
        out = [{'nome': a['nome'], 'os': a['os'], 'qualidade': int(round(a['q'] / a['os'])) if a['os'] else 0, 'devolvidas': a['dev'], 'pontualidade': int(round(100.0 * a['pont'] / a['os'])) if a['os'] else 0} for a in g.values()]
        out.sort(key=lambda x: (x['qualidade'], -x['devolvidas']))
        return {'rotulo': rotulo, 'itens': out}
    return {'gerado_em': _agora_iso(), 'periodo_dias': int(dias), 'filtros': f, 'opcoes': {'colaborador': _opcoes_pessoa(todas), 'supervisor': opcoes(None, lambda r: r['_sup']), 'regiao': opcoes(None, lambda r: r['_reg']), 'tipo': opcoes('fx_tipo'), 'criticidade': opcoes('fx_crit')}, 'resumo': {'os': n, 'qualidade_media': int(round(sum((int(r.get('qualidade') or 0) for r in linhas)) / n)) if n else 0, 'devolvidas': len(devolvidas), 'retrabalho_pct': int(round(100.0 * len(devolvidas) / n)) if n else 0, 'primeira_aprovacao_pct': int(round(100.0 * len(primeira_ok) / len(aprovadas))) if aprovadas else None, 'pontualidade_pct': int(round(100.0 * len(pontuais) / n)) if n else 0, 'tempo_vs_previsto_pct': desvio_tempo, 'em_verificacao': len([r for r in linhas if int(r.get('fx_status') or 0) == STATUS_IN_REVIEW])}, 'por_colaborador': agrupa(lambda r: r.get('nome') or r.get('email') or '', 'Colaborador'), 'por_supervisor': agrupa(lambda r: r['_sup'], 'Supervisor'), 'por_regiao': agrupa(lambda r: r['_reg'], 'Região'), 'por_tipo': agrupa(lambda r: r.get('fx_tipo') or '', 'Tipo de OS'), 'totais': {'linhas': len(linhas)}, 'linhas': [{'os': r.get('os'), 'tarefa': r.get('tarefa'), 'tecnico': r.get('nome') or r.get('email'), 'email': r.get('email'), 'supervisor': r['_sup'], 'cluster': r['_reg'], 'usina': r.get('usina') or r.get('fx_ativo') or '', 'tipo': r.get('fx_tipo') or '', 'crit': r.get('fx_crit') or '', 'qualidade': int(r.get('qualidade') or 0), 'pontual': bool(r.get('pontual')), 'devolvida': bool(r.get('foi_devolvida')), 'rev': r.get('rev') or '', 'dur_prev': int(r.get('fx_dur_prev_min') or 0), 'dur_real': int(r.get('fx_dur_real_min') or 0), 'quando': r.get('server_ts'), 'link': _link_fracttal_os(r.get('os'))} for r in sorted(linhas, key=lambda r: str(r.get('server_ts') or ''), reverse=True)[:GESTAO_TODAS_MAX if inteira else GESTAO_OS_MAX]]}


def _sup_norm(nome):
    return ' '.join(str(nome or '').split()).strip()


_SUPCAN = {'v': None, 't': 0.0}


def _sup_canon_mapa():
    import time as _t
    if _SUPCAN['v'] is not None and _t.time() - _SUPCAN['t'] < 300:
        return _SUPCAN['v']
    por = ident().get('porEmail') or {}
    oficial = {}
    chefes = {}
    for _em, p in por.items():
        of = _sup_norm((p or {}).get('nomePadrao') or (p or {}).get('nome') or '')
        if not of:
            continue
        oficial.setdefault(_norm(of), of)
        if 'supervisor' in _norm((p or {}).get('cargo')):
            chefes.setdefault(_norm(of), of)
    mapa, orfas = ({}, [])
    for _em, p in por.items():
        g = _sup_norm((p or {}).get('supervisor'))
        if not g:
            continue
        n = _norm(g)
        if n in mapa:
            continue
        alvo = oficial.get(n)
        if not alvo:
            t = n.split()
            cand = {v for k, v in oficial.items() if k.split() and t and (k.split()[0] == t[0]) and (k.split()[-1] == t[-1])}
            if len(cand) != 1:
                cand = {v for k, v in oficial.items() if k.startswith(n + ' ') or n.startswith(k + ' ')}
            if len(cand) != 1 and t:
                cand = {v for k, v in chefes.items() if k.split()[:1] == t[:1]}
                if len(cand) == 1:
                    logging.info("supervisor '%s' resolvido por primeiro nome -> '%s' (unico supervisor assim no cadastro)", g, next(iter(cand)))
            alvo = next(iter(cand)) if len(cand) == 1 else None
        mapa[n] = alvo or g
        if not alvo:
            orfas.append(g)
    if orfas:
        logging.info('supervisor sem correspondencia no cadastro (%d): %s — corrigir a grafia no BD_Operacoes', len(set(orfas)), '; '.join(sorted(set(orfas))))
    _SUPCAN['v'] = mapa
    _SUPCAN['t'] = _t.time()
    return mapa


def _sup_canon(nome):
    g = _sup_norm(nome)
    if not g:
        return ''
    try:
        return _sup_canon_mapa().get(_norm(g), g)
    except Exception as e:
        logging.warning('sup canon: %s', e)
        return g


FILA_TTL_S = 600


_FILA_CACHE = {'ts': None, 'linhas': None}


def _fx_wo_paralelo(status, sort, cap):
    from concurrent.futures import ThreadPoolExecutor
    res = fx('work_orders?id_status_work_order=%d&limit=1' % status)
    if not isinstance(res, dict) or res.get('total') is None:
        raise ApiError(502, 'o Fracttal não informou o total do status %d — fila não lida' % status)
    total = min(int(res.get('total') or 0), int(cap))
    if total <= 0:
        return []
    offsets = list(range(0, total, 100))
    falhas = []

    def _pag(start):
        try:
            res = fx('work_orders?id_status_work_order=%d&limit=100&start=%d&sort=%s' % (status, start, sort))
            return (res.get('data') if isinstance(res, dict) else res) or []
        except Exception as e:
            falhas.append((start, str(e)[:90]))
            logging.warning('wo pagina %s@%d: %s', status, start, e)
            return []
    with ThreadPoolExecutor(max_workers=6) as ex:
        partes = list(ex.map(_pag, offsets))
    linhas = [x for p in partes for x in p]
    if falhas:
        logging.error('fila status %s INCOMPLETA: %d de %d pagina(s) falharam (%s) — vieram %d de %d linhas', status, len(falhas), len(offsets), falhas[0][1], len(linhas), total)
        raise ApiError(502, 'fila do Fracttal veio incompleta (%d pagina(s) falharam)' % len(falhas))
    if len(linhas) < total:
        logging.warning('fila status %s: vieram %d de %d esperadas', status, len(linhas), total)
    return linhas[:int(cap)]


def _fila_bruta(forcar=False):
    from datetime import datetime
    agora = datetime.utcnow()
    ts = _FILA_CACHE.get('ts')
    if not forcar and ts and (_FILA_CACHE.get('linhas') is not None) and ((agora - ts).total_seconds() < FILA_TTL_S):
        return _FILA_CACHE['linhas']
    try:
        linhas = _fx_wo_paralelo(2, 'final_date', SUP_CAP_BACKLOG)
    except Exception as e:
        if _FILA_CACHE.get('linhas') is not None:
            logging.error('fila incompleta (%s) — servindo o cache de %s', str(e)[:100], _FILA_CACHE.get('ts'))
            return _FILA_CACHE['linhas']
        raise
    _FILA_CACHE['ts'] = agora
    _FILA_CACHE['linhas'] = linhas
    return linhas


def _pessoa_por_nome():
    out = {}
    for em, p in (ident().get('porEmail') or {}).items():
        reg = dict(p or {})
        reg['email'] = str(em).strip().lower()
        for campo in ('nome', 'nomePadrao'):
            n = _norm(reg.get(campo))
            if n:
                out.setdefault(n, reg)
    return out


def _txt_tarefa(w):
    for k in ('tasks_description', 'task_description', 'tasks_descriptions', 'group_task_description', 'description'):
        v = w.get(k)
        if isinstance(v, (list, tuple)):
            v = next((str(x) for x in v if x), '')
        v = str(v or '').strip()
        if v and v.lower() != 'none':
            return v
    return ''


def _janela(req):
    from datetime import datetime, timedelta

    def _dia(v, fim=False):
        try:
            d = datetime.strptime(str(v)[:10], '%Y-%m-%d')
            return d.replace(hour=23, minute=59, second=59) if fim else d
        except Exception:
            return None
    de = _dia(req.params.get('de'))
    ate = _dia(req.params.get('ate'), fim=True)
    if not de:
        try:
            dias = max(1, min(int(req.params.get('dias') or 30), 3650))
        except Exception:
            dias = 30
        de = (datetime.utcnow() - timedelta(days=dias)).replace(hour=0, minute=0, second=0)
    if not ate:
        ate = datetime.utcnow()
    if ate < de:
        de, ate = (ate, de)
    return (de, ate)


def _qlog_por_os(de, ate):
    out = {}
    corte = de.strftime('%Y-%m-%dT%H:%M:%S')
    try:
        for e in tabela_qlog().query_entities("PartitionKey eq 'q'"):
            if _fora(str(e.get('server_ts') or ''), corte, None):
                continue
            folio = str(e.get('os') or e.get('fx_folio') or '').strip()
            if folio:
                out[folio] = e
    except Exception as ex:
        logging.warning('qlog p/ fila: %s', ex)
    return out


TRIAGEM_NOTA_OK = 80


ESTOURO_EXEC_MIN = int(os.environ.get('ESTOURO_EXEC_MIN', '480') or '480')


ESTOURO_EXEC_X = float(os.environ.get('ESTOURO_EXEC_X', '20') or '20')


ESTOURO_PREV_TETO = int(os.environ.get('ESTOURO_PREV_TETO', '15') or '15')


ESTOURO_PREV_X = float(os.environ.get('ESTOURO_PREV_X', '5') or '5')


TRIAGEM_ESTOURO = 1.75


def _estouro(q):
    if not q:
        return None
    try:
        real = float(q.get('fx_dur_real_min') or 0)
        prev = float(q.get('fx_dur_prev_min') or 0)
    except Exception:
        return None
    if real <= 0 or prev <= 0:
        return None
    return round(real / prev, 2)


def _estouro_causa(prev, real):
    try:
        prev, real = (float(prev or 0), float(real or 0))
    except (TypeError, ValueError):
        return None
    if prev <= 0 or real <= 0:
        return None
    x = real / prev
    if x < TRIAGEM_ESTOURO:
        return None
    if real >= ESTOURO_EXEC_MIN and x >= ESTOURO_EXEC_X:
        return 'execucao'
    if prev <= ESTOURO_PREV_TETO and x >= ESTOURO_PREV_X:
        return 'previsto'
    return 'tecnico'


def _fila_do_app(q, rr):
    q = q or {}
    if q:
        return {'pelo_app': True, 'ronda': False, 'qualidade': int(q.get('qualidade') or 0), 'foi_devolvida': bool(q.get('foi_devolvida')), 'foto_divergente': bool(q.get('foto_divergente')), 'falhas': None}
    if rr:
        return {'pelo_app': True, 'ronda': True, 'qualidade': rr.get('qualidade'), 'foi_devolvida': None, 'foto_divergente': None, 'falhas': list(rr.get('falhas') or [])}
    return {'pelo_app': False, 'ronda': False, 'qualidade': None, 'foi_devolvida': None, 'foto_divergente': None, 'falhas': None}


def _triagem(x):
    if not x.get('pelo_app'):
        return 'fora_do_app'
    q = x.get('qualidade')
    if q is None or int(q) < TRIAGEM_NOTA_OK:
        return 'olho'
    if x.get('ronda') and x.get('falhas'):
        return 'olho'
    if x.get('foi_devolvida'):
        return 'olho'
    if x.get('estouro_causa') == 'tecnico':
        return 'olho'
    if x.get('foto_divergente'):
        return 'olho'
    return 'completa'


def _casa_nome(texto, termos):
    t = _norm(texto)
    return all((x in t for x in termos or []))


def _fila_supervisao(req, esc):
    from datetime import datetime
    de, ate = _janela(req)
    f_sup = _norm(req.params.get('sup') or '')
    f_fun = _norm(req.params.get('funcao') or '')
    f_col = _norm(req.params.get('colab') or '')
    f_reg = _norm(req.params.get('regiao') or '')
    f_os = str(req.params.get('os') or '').strip()
    f_bal = (req.params.get('balde') or '').strip()
    f_nome = _norm(req.params.get('nome') or '').split()
    try:
        pag = max(1, int(req.params.get('pag') or 1))
        tam = max(1, min(int(req.params.get('tam') or 50), 200))
    except Exception:
        pag, tam = (1, 50)
    permitidos = None
    if esc.get('clusters') is not None:
        permitidos = set((_norm(c) for c in esc.get('clusters') or []))
    porNome = _pessoa_por_nome()
    qlog = _qlog_por_os(de, ate)
    try:
        ron_os = _rondas_os_por_folio((de - _timedelta(days=7)).strftime('%Y-%m-%d'))
    except Exception as ex:
        logging.warning('rondas p/ fila: %s', str(ex)[:120])
        ron_os = {}
    agora = datetime.utcnow()
    linhas, vistos, sem_cadastro = ([], set(), 0)
    for w in _fila_bruta(req.params.get('refresh') == '1'):
        k = w.get('id_work_orders_tasks') or w.get('id_work_order')
        if k in vistos:
            continue
        vistos.add(k)
        fim = str(w.get('final_date') or '')[:19]
        try:
            dt = _parse_iso(fim) if fim else None
        except Exception:
            dt = None
        if dt is None or dt < de or dt > ate:
            continue
        tec = ' '.join(str(w.get('personnel_description') or '').split())
        p = porNome.get(_norm(tec)) or {}
        if not p and tec:
            sem_cadastro += 1
        area = (w.get('groups_2_description') or '').strip() or '(sem área)'
        if not _area_ok(w, esc.get('clusters'), permitidos, 'groups_1_description'):
            continue
        if f_os:
            _fo = str(w.get('wo_folio') or '')
            if not (_fo == f_os or _fo.startswith(f_os)):
                continue
        if f_nome and (not _casa_nome(_txt_tarefa(w), f_nome)):
            continue
        if f_sup and _norm(p.get('supervisor')) != f_sup:
            continue
        if f_fun and _norm(p.get('cargo')) != f_fun:
            continue
        if f_col and f_col not in (_norm(p.get('email')), _norm(tec)):
            continue
        if f_reg and _norm(area) != f_reg:
            continue
        folio = str(w.get('wo_folio') or '')
        q = qlog.get(folio) or {}
        espera = int((agora - dt).total_seconds() // 86400) if dt else None
        linhas.append({'os': folio, 'id_wt': k, 'tarefa': _txt_tarefa(w), 'ativo': w.get('items_log_description') or '', 'area': area, 'tecnico': tec or '—', 'funcao': p.get('cargo') or '', 'supervisor': _sup_canon(p.get('supervisor')) or '(sem supervisor)', 'email': p.get('email') or '', 'fim': fim, 'espera_d': espera, 'rating': int(w.get('rating') or 0) or None, **_fila_do_app(q, None if q else ron_os.get(folio)), 'estouro': _estouro(q), 'estouro_causa': _estouro_causa((q or {}).get('fx_dur_prev_min'), (q or {}).get('fx_dur_real_min'))})
        linhas[-1]['balde'] = _triagem(linhas[-1])
    linhas.sort(key=lambda x: (x['espera_d'] is None, -(x['espera_d'] or 0)))
    baldes = {b: sum((1 for x in linhas if x['balde'] == b)) for b in ('completa', 'olho', 'fora_do_app')}
    if f_bal:
        linhas = [x for x in linhas if x['balde'] == f_bal]
    total = len(linhas)
    ini = (pag - 1) * tam
    return {'janela': {'de': de.strftime('%Y-%m-%d'), 'ate': ate.strftime('%Y-%m-%d')}, 'resumo': {'tarefas': total, 'ordens': len(set((x['os'] for x in linhas if x['os']))), 'aged7d': sum((1 for x in linhas if (x['espera_d'] or 0) >= 7)), 'aged30d': sum((1 for x in linhas if (x['espera_d'] or 0) >= 30)), 'espera_max': max([x['espera_d'] or 0 for x in linhas] or [0]), 'pelo_app': sum((1 for x in linhas if x['pelo_app']))}, 'baldes': baldes, 'balde': f_bal, 'sem_cadastro': sem_cadastro, 'pagina': {'n': pag, 'tam': tam, 'total': total, 'paginas': (total + tam - 1) // tam if tam else 1}, 'linhas': linhas[ini:ini + tam], 'ts': _agora_iso()}


def _hoje():
    from datetime import datetime
    return datetime.utcnow().strftime('%Y-%m-%d')


def tabela_ronda():
    return _tabela('rondas', '_table_ronda')


def tabela_ronda_ativos():
    return _tabela('rondaativos', '_table_rativos')


def _niveis_vazios():
    return [{'n': i + 1, 'premissa': '', 'fotos': []} for i in range(5)]


CHECKLIST_RONDA = [{'id': 'computador', 'label': 'Computador', 'foto_guia': 'A TELA ligada, legível. Se estiver desligado, mostre o gabinete e a tela apagada.', 'tipo': 'estado', 'opcoes': ['Ligado', 'Desligado'], 'alerta': ['Desligado'], 'na': True, 'foto': True, 'ajuda': 'Foto obrigatória para evidenciar o computador.'}, {'id': 'cftv', 'label': 'CFTV', 'foto_guia': 'O MONITOR com as câmeras aparecendo. Só o rack não comprova que o sistema está funcionando.', 'tipo': 'estado', 'opcoes': ['Ligado', 'Desligado'], 'alerta': ['Desligado'], 'na': True, 'foto': True, 'ajuda': 'Foto obrigatória para evidenciar o CFTV.'}, {'id': 'vala', 'label': 'Sujidade da vala de drenagem', 'foto_guia': 'Um TRECHO da vala com o fundo visível. De cima e de perto — a foto tem de mostrar se há entulho.', 'tipo': 'estado', 'opcoes': ['Limpa', 'Parcial', 'Obstruída'], 'alerta': ['Obstruída'], 'na': True, 'foto': True, 'ajuda': 'Foto obrigatória — a não ser que a usina não tenha vala.'}, {'id': 'pir_ghi', 'label': 'Piranômetro GHI (estação solarimétrica)', 'foto_guia': 'A CÚPULA DE VIDRO de perto, preenchendo boa parte da foto. Plano geral da estação não serve: de longe não dá para ver sujeira.', 'tipo': 'estado', 'opcoes': ['Limpo', 'Sujo'], 'alerta': ['Sujo'], 'na': True, 'foto': True, 'acao_se': ['Sujo'], 'acao': 'Limpeza com álcool isopropílico', 'ajuda': 'Foto sempre. Se estiver sujo, passar pano com álcool isopropílico e registrar.'}, {'id': 'pir_ipoa', 'label': 'Piranômetro IPOA (mesa tracker, plano dos módulos)', 'foto_guia': 'A CÚPULA DE VIDRO de perto, preenchendo boa parte da foto. Aproxime até o vidro ocupar o centro do enquadramento.', 'tipo': 'estado', 'opcoes': ['Limpo', 'Sujo'], 'alerta': ['Sujo'], 'na': True, 'foto': True, 'acao_se': ['Sujo'], 'acao': 'Limpeza com álcool isopropílico', 'ajuda': 'Foto sempre. Se estiver sujo, passar pano com álcool isopropílico e registrar.'}, {'id': 'pir_albedo', 'label': 'Albedômetro (mesa tracker, voltado ao solo)', 'foto_guia': 'O sensor fica SOB a mesa, virado para o solo. Agache e enquadre a cúpula de baixo — se o sensor não aparece, a foto não responde nada.', 'tipo': 'estado', 'opcoes': ['Limpo', 'Sujo'], 'alerta': ['Sujo'], 'na': True, 'foto': True, 'acao_se': ['Sujo'], 'acao': 'Limpeza com álcool isopropílico', 'ajuda': 'Fica na mesma mesa do IPOA, virado para baixo. Foto sempre; se sujo, limpar.'}, {'id': 'sujidade', 'label': 'Sujidade dos módulos', 'foto_guia': 'A SUPERFÍCIE do módulo de perto, preenchendo a foto. Uma das duas pode ser mais aberta, mas pelo menos uma tem de mostrar a célula.', 'tipo': 'escala5', 'ajuda': 'Compare com a referência antes de escolher o nível. Tire ao menos 2 fotos.', 'foto': True, 'fotos_min': 2, 'alerta_acima': 3, 'niveis': _niveis_vazios(), 'multi': {'label': 'Tipos de sujidade presentes', 'opcoes': ['Poeira / areia', 'Fezes de pássaros', 'Matéria orgânica / pólen', 'Vegetação impregnada'], 'acima_de': 1, 'ajuda': 'Marque todos os que aparecem. É o que define o método de limpeza.'}}, {'id': 'vegetacao', 'label': 'Altura da vegetação', 'foto_guia': 'A vegetação COM OS MÓDULOS ao fundo — é a estrutura que dá a escala da altura. Só o chão não permite julgar o nível.', 'tipo': 'escala5', 'ajuda': 'Compare com a referência antes de escolher o nível. Tire ao menos 2 fotos.', 'foto': True, 'fotos_min': 2, 'alerta_acima': 3, 'niveis': _niveis_vazios()}, {'id': 'praga', 'label': 'Pragas', 'tipo': 'disperso', 'tipos': ['Formiga', 'Cupim', 'Abelha', 'Marimbondo', 'Outro'], 'multi': True, 'mesas': 'obrigatorio', 'acao': None, 'abre_ss': True, 'ss_se': ['Generalizado'], 'ajuda': 'Marque todas as pragas encontradas. Generalizado (acima de 5 focos) vai para a Central de atenção da gestão, que decide a dedetização.'}, {'id': 'dejeto', 'label': 'Dejeto de pássaro nos módulos', 'tipo': 'disperso', 'mesas': 'opcional', 'acao': 'Limpeza realizada', 'abre_ss': False, 'ajuda': 'Aqui importa o tamanho, não o endereço de cada ponto.'}, {'id': 'sombreamento', 'label': 'Sombreamento por vegetação', 'tipo': 'disperso', 'mesas': 'obrigatorio', 'acao': 'Poda realizada', 'abre_ss': False, 'ajuda': 'A poda é dirigida — informe as mesas afetadas (ex.: 12-18, 22).'}, {'id': 'trincado', 'label': 'Módulo trincado', 'tipo': 'ocorrencia', 'campos': ['mesa', 'termografia'], 'acao': None, 'abre_ss': True, 'ajuda': 'Registre cada módulo individualmente. Faça a termografia se houver condição.'}, {'id': 'infra_entrada', 'label': 'Entrada da usina / portaria', 'foto_guia': 'O portão e o entorno imediato, de fora para dentro.', 'tipo': 'estado', 'opcoes': ['OK', 'Atenção', 'Irregular'], 'alerta': ['Irregular'], 'na': True, 'foto': True}, {'id': 'infra_placas', 'label': 'Placas de sinalização', 'foto_guia': 'A placa LEGÍVEL. Se houver problema em várias, fotografe a pior e informe os locais no campo de texto.', 'tipo': 'estado', 'opcoes': ['OK', 'Pontual', 'Generalizado'], 'alerta': ['Generalizado'], 'na': True, 'foto': True, 'texto_se': {'Pontual': 'Locais com problema', 'Generalizado': 'Descreva a situação'}, 'ajuda': 'Se houver problema, indique os locais. Generalizado: descreva melhor.'}, {'id': 'infra_sala', 'label': 'Sala de O&M', 'foto_guia': 'O ambiente INTEIRO, de um canto, mostrando piso e bancada.', 'tipo': 'estado', 'opcoes': ['OK', 'Atenção', 'Irregular'], 'alerta': ['Irregular'], 'na': True, 'foto': True}, {'id': 'infra_almox', 'label': 'Almoxarifado', 'foto_guia': 'As PRATELEIRAS, mostrando organização e o que está no chão.', 'tipo': 'estado', 'opcoes': ['OK', 'Atenção', 'Irregular'], 'alerta': ['Irregular'], 'na': True, 'foto': True}, {'id': 'infra_luvas', 'label': 'As luvas isolantes estão disponíveis?', 'foto_guia': 'As LUVAS ISOLANTES no lugar onde ficam guardadas, com o par inteiro no enquadramento. Se não houver, fotografe o lugar vazio.', 'tipo': 'estado', 'opcoes': ['Sim', 'Não'], 'alerta': ['Não'], 'foto': True, 'ajuda': 'Confira o par de luvas isolantes no local de guarda. Foto sempre, com ou sem as luvas.'}, {'id': 'infra_banheiro', 'label': 'Banheiro', 'foto_guia': 'O ambiente inteiro, com pia e vaso no enquadramento.', 'tipo': 'estado', 'opcoes': ['OK', 'Atenção', 'Irregular'], 'alerta': ['Irregular'], 'na': True, 'foto': True}]


EXTENSAO_NENHUMA = 'Nenhuma'


EXTENSAO_ALERTA = 'Generalizado'


def _trk_respondido(t):
    return isinstance(t, dict) and bool(str(t.get('veredito') or '').strip() or str(t.get('acao') or '').strip())


_CANON = {'t': 0.0, 'm': None}


def _canon_cluster(nome=None, forcar=False):
    import time as _t
    if forcar or _CANON['m'] is None or _t.time() - _CANON['t'] > 300:
        freq = {}
        try:
            for e in tabela_ronda_ativos().query_entities("PartitionKey eq 'usina'"):
                c = str(e.get('cluster') or '').strip()
                if c:
                    formas = freq.setdefault(_norm(c), {})
                    formas[c] = formas.get(c, 0) + 1
        except Exception as ex:
            logging.warning('grafia canônica: %s', ex)
        m = {}
        for k, formas in freq.items():
            m[k] = sorted(formas, key=lambda f: (-formas[f], f.isupper(), f))[0]
        _CANON['t'], _CANON['m'] = (_t.time(), m)
    if nome is None:
        return _CANON['m']
    n = str(nome or '').strip()
    return _CANON['m'].get(_norm(n), n) if n else n


_CATOV = {'t': 0.0, 'usina': None, 'cluster': None}


def _catalogo_ov(forcar=False):
    if not forcar and _CATOV['usina'] is not None and (time.time() - _CATOV['t'] < 60):
        return (_CATOV['usina'], _CATOV['cluster'])
    us, cl = ({}, [])
    try:
        tb = tabela_ronda_ativos()
        for e in tb.query_entities("PartitionKey eq 'usina_ov'"):
            us[str(e.get('RowKey'))] = str(e.get('cluster') or '')
        for e in tb.query_entities("PartitionKey eq 'cluster_ov'"):
            n = str(e.get('cluster') or '').strip()
            if n:
                cl.append(n)
    except Exception as ex:
        logging.warning('catalogo override: %s', ex)
        return (_CATOV['usina'] or {}, _CATOV['cluster'] or [])
    _CATOV['t'], _CATOV['usina'], _CATOV['cluster'] = (time.time(), us, sorted(set(cl)))
    return (us, _CATOV['cluster'])


def _usinas_do_cluster(clusters, extras=None, fora=None):
    alvo = None if clusters is None else set((_norm(c) for c in clusters or []))
    av = set((_norm(u) for u in extras or []))
    nao = set((_norm(u) for u in fora or []))
    ov, _ = _catalogo_ov()
    out = []
    try:
        for e in tabela_ronda_ativos().query_entities("PartitionKey eq 'usina'"):
            cl = str(e.get('cluster') or '')
            rk = str(e.get('RowKey') or '')
            if rk in ov:
                cl = ov[rk]
            cl = _canon_cluster(cl)
            if _norm(e.get('usina') or '') in nao:
                continue
            if alvo is not None and _norm(cl) not in alvo and (_norm(e.get('usina') or '') not in av):
                continue
            nt, ni = (int(e.get('trk_n') or 0), int(e.get('inv_n') or 0))
            if not nt and (not ni):
                continue
            out.append({'usina': e.get('usina'), 'cluster': cl, 'trackers': nt, 'inversores': ni, 'lat': e.get('lat'), 'lon': e.get('lon')})
    except Exception as ex:
        logging.warning('usinas: %s', ex)
    out.sort(key=lambda x: x['usina'])
    return out


def tabela_ronda_os():
    return _tabela('rondaos', '_table_ronda_os')


ATN_TIPOS = {'os_exec_presa': 'Execução presa (>24 h)', 'ronda_sem_os': 'Ronda sem OS no Fracttal', 'ronda_os_fora_revisao': 'OS de ronda fora de Em Verificação', 'os_parcial': 'OS parcial na fila de verificação', 'os_duracao': 'Duração atípica (>12 h)', 'cadastro': 'Cadastro em divergência', 'os_sem_dono': 'OS aberta sem responsável', 'os_rolagem': 'Rolagem crônica', 'os_exec_cancelada': 'Execução presa em OS cancelada', 'urgente_nao_entregue': 'Religamento que o App não ofereceu', 'sem_sessao': 'Sessão do Fracttal caiu', 'desvio': 'Fora do padrão', 'nao_fez': 'Ação não feita', 'praga': 'Praga/vegetação generalizada', 'ocorrencia': 'Ocorrência pendente', 'tracker': 'Tracker sem devolutiva', 'tracker_nao': 'Tracker não normalizado', 'obs': 'Observação do técnico', 'os_falha': 'OS · falha na verificação', 'os_alerta': 'OS · alerta na verificação', 'os_branco': 'OS · obrigatória em branco', 'os_sem_foto': 'OS · sem o anexo exigido', 'sem_ronda': 'Usina sem ronda', 'os_nao_chegou': 'Fechamento não chegou ao Fracttal', 'ronda_item': 'Item da ronda'}


ATN_PESO = {'ronda_sem_os': 5, 'ronda_os_fora_revisao': 5, 'os_falha': 6, 'praga': 5, 'sem_ronda': 5, 'nao_fez': 4, 'os_alerta': 4, 'ocorrencia': 3, 'os_sem_foto': 3, 'desvio': 2, 'obs': 2, 'os_branco': 2, 'tracker': 1, 'tracker_nao': 2, 'os_exec_presa': 6, 'os_parcial': 3, 'os_duracao': 2, 'cadastro': 4, 'os_sem_dono': 5, 'os_rolagem': 3, 'os_exec_cancelada': 2, 'urgente_nao_entregue': 7, 'sem_sessao': 6, 'os_nao_chegou': 7, 'ronda_item': 3}


ATN_DIAS_SEM_RONDA = 14


def _pontos_atencao_ronda(r):

    def _js(v, padrao='{}'):
        if isinstance(v, (dict, list)):
            return v
        try:
            return json.loads(v or padrao)
        except Exception:
            return json.loads(padrao)
    resp = _js(r.get('respostas'))
    oc = _js(r.get('ocorrencias'))
    disp = _js(r.get('dispersos'))
    ai = _js(r.get('acoesItem'))
    mi = _js(r.get('multiItens'))
    ti = _js(r.get('textosItem'))
    fi = _js(r.get('fotosItem'))
    base = {'data': str(r.get('PartitionKey') or ''), 'usina': r.get('usina') or '', 'cluster': r.get('cluster') or '', 'email': r.get('RowKey') or r.get('email') or '', 'nome': r.get('nome') or r.get('email') or '', 'origem': 'ronda'}
    out = []

    def _add(tipo, oque, detalhe='', fotos=0):
        p = dict(base)
        p.update({'tipo': tipo, 'rotulo': ATN_TIPOS.get(tipo, tipo), 'oque': oque, 'detalhe': detalhe, 'fotos': int(fotos or 0), 'peso': ATN_PESO.get(tipo, 1)})
        out.append(p)
    for c in CHECKLIST_RONDA:
        cid, rot = (c['id'], c.get('label') or c['id'])
        tipo_c = c.get('tipo')
        if tipo_c == 'ocorrencia':
            for i, p in enumerate(oc.get(cid) or []):
                if not isinstance(p, dict):
                    continue
                if c.get('acao'):
                    if p.get('resolvido'):
                        continue
                    nota = 'pendente'
                else:
                    nota = 'sem ação em campo — decisão da gestão'
                onde = ' · '.join((str(x) for x in (p.get('tipo'), p.get('tracker'), p.get('inversor'), p.get('mesa'), p.get('local')) if x))
                _add('ocorrencia', '%s %d' % (rot, i + 1), ' — '.join((x for x in (onde, nota) if x)), len(p.get('fotos') or []) + len(p.get('fotosDepois') or []))
            continue
        if tipo_c == 'disperso':
            d = disp.get(cid) or {}
            ext = str(d.get('extensao') or '').strip()
            if not ext or ext == EXTENSAO_NENHUMA:
                continue
            tipos = ' · '.join((str(x) for x in d.get('tipos') or []))
            onde = str(d.get('mesasTxt') or '').strip() or ' · '.join(d.get('mesas') or [])
            det = ' — '.join((x for x in (tipos, onde) if x))
            nf = len(d.get('fotos') or [])
            if ext == EXTENSAO_ALERTA:
                _add('praga', '%s — %s' % (rot, ext), det, nf)
            elif c.get('acao') and d.get('resolvido') in (False, 'parcial'):
                _add('nao_fez', '%s — %s' % (rot, ext), ('não fez' if d.get('resolvido') is False else 'só parcial') + (' — ' + str(d.get('motivo')) if d.get('motivo') else '') + (' · ' + det if det else ''), nf)
            continue
        v = resp.get(cid)
        if v is None or v == '':
            continue
        alerta = v in (c.get('alerta') or []) or (c.get('tipo') == 'escala5' and c.get('alerta_acima') is not None and (_int0(v) > _int0(c.get('alerta_acima'))))
        a = ai.get(cid) or {}
        nf = len(fi.get(cid) or [])
        det = ' — '.join((x for x in (' · '.join(mi.get(cid) or []), str(ti.get(cid) or '').strip()) if x))
        if c.get('acao') and a.get('resolvido') is False:
            _add('nao_fez', '%s — %s' % (rot, v), det, nf)
        elif alerta:
            _add('desvio', '%s — %s' % (rot, v), det, nf)
    for t in _js(r.get('trackers'), '[]') or []:
        if not isinstance(t, dict):
            continue
        if str(t.get('veredito') or '').strip() == 'nao':
            _add('tracker_nao', 'Tracker %s' % t.get('n'), ' · '.join((str(x) for x in ('não normalizado', t.get('ativo'), t.get('causa'), 'chamado OS #%s' % t.get('chamado') if t.get('chamado') else '') if x)))
        elif not _trk_respondido(t):
            _add('tracker', 'Tracker %s' % t.get('n'), ' · '.join((str(x) for x in (t.get('ativo'), t.get('causa')) if x)))
    obs = str(r.get('atividades') or '').strip()
    if obs:
        _add('obs', 'Observação escrita', obs[:400])
    return out


def tabela_atencao_os():
    return _tabela('atencaoos', '_table_atn_os')


def _invariantes_guardados(clusters):
    try:
        e = tabela_atencao_os().get_entity('inv', 'pontos')
    except Exception:
        return ([], '')
    try:
        pts = json.loads(e.get('pontos') or '[]')
    except Exception:
        return ([], str(e.get('quando') or ''))
    if clusters is not None:
        permitidos = set((_norm(c) for c in clusters or []))
        pts = [p for p in pts if _area_ok(p, clusters, permitidos)]
    return (pts, str(e.get('quando') or ''))


def _atencao_os_guardada(clusters):
    permitidos = None if clusters is None else set((_norm(c) for c in clusters or []))
    out, ts = ([], '')
    try:
        for e in tabela_atencao_os().query_entities("PartitionKey eq 'os'"):
            if not _area_ok(e, clusters, permitidos):
                continue
            q = str(e.get('quando') or '')
            if q > ts:
                ts = q
            try:
                out += json.loads(e.get('pontos') or '[]')
            except Exception:
                continue
    except Exception as ex:
        logging.warning('atenção OS leitura: %s', ex)
    return (out, ts)


def _central_atencao(clusters, dias, janela=None):
    from datetime import datetime, timedelta
    corte = (datetime.utcnow() - timedelta(days=int(dias))).strftime('%Y-%m-%d')
    teto = None
    if janela:
        corte, teto = (janela[0][:10], janela[1][:10])
    permitidos = None if clusters is None else set((_norm(c) for c in clusters or []))
    pontos = []
    try:
        for e in tabela_ronda().query_entities("PartitionKey ge '%s'" % corte):
            if not e.get('finalizada'):
                continue
            if not _area_ok(e, clusters, permitidos):
                continue
            if _fora(str(e.get('PartitionKey') or ''), corte, teto):
                continue
            try:
                pontos += _pontos_atencao_ronda(dict(e))
            except Exception as ex:
                logging.warning('pontos de atenção %s/%s: %s', e.get('PartitionKey'), e.get('RowKey'), ex)
    except Exception as ex:
        logging.warning('central de atenção: %s', ex)
    os_pontos, os_ts = _atencao_os_guardada(clusters)
    for p in os_pontos:
        if not _fora(str(p.get('data') or ''), corte, teto):
            pontos.append(p)
    inv_pontos, inv_ts = _invariantes_guardados(clusters)
    pontos.extend(inv_pontos)
    hoje = _hoje()
    try:
        ultima = {}
        largo = (datetime.utcnow() - timedelta(days=180)).strftime('%Y-%m-%d')
        for e in tabela_ronda().query_entities("PartitionKey ge '%s'" % largo):
            if not e.get('finalizada'):
                continue
            u, d = (e.get('usina') or '', str(e.get('PartitionKey') or ''))
            if u and d > ultima.get(u, ''):
                ultima[u] = d
        nunca = []
        for x in _usinas_do_cluster(clusters):
            u = x['usina']
            d = ultima.get(u)
            dd = _dias_entre(d, hoje) if d else None
            if not d:
                nunca.append(x)
                continue
            if dd is None or dd < ATN_DIAS_SEM_RONDA:
                continue
            pontos.append({'origem': 'usina', 'tipo': 'sem_ronda', 'rotulo': ATN_TIPOS['sem_ronda'], 'usina': u, 'cluster': x['cluster'], 'email': '', 'nome': '', 'data': d, 'fotos': 0, 'peso': ATN_PESO['sem_ronda'], 'oque': 'Sem ronda há %d dias' % int(dd), 'detalhe': 'última em ' + '/'.join(reversed(d.split('-'))), 'dias': int(dd)})
        if nunca:
            pontos.append({'origem': 'usina', 'tipo': 'sem_ronda', 'rotulo': ATN_TIPOS['sem_ronda'], 'usina': '%d usinas' % len(nunca), 'cluster': '', 'email': '', 'nome': '', 'data': '', 'fotos': 0, 'peso': ATN_PESO['sem_ronda'], 'dias': 999, 'oque': '%d usinas nunca receberam ronda' % len(nunca), 'detalhe': 'de %d no cadastro · abre a cobertura para ver quais' % (len(nunca) + len(ultima))})
    except Exception as ex:
        logging.warning('usinas sem ronda: %s', ex)
    for p in pontos:
        if p.get('dias') is None or p.get('origem') != 'usina':
            p['dias'] = _dias_entre(p['data'], hoje) or 0
    pontos.sort(key=lambda p: (-int(p.get('dias') or 0), -int(p.get('peso') or 0), p.get('usina') or ''))
    por_tipo, por_usina = ({}, {})
    for p in pontos:
        por_tipo[p['tipo']] = por_tipo.get(p['tipo'], 0) + 1
        por_usina[p['usina']] = por_usina.get(p['usina'], 0) + 1
    velhos = [p for p in pontos if int(p.get('dias') or 0) >= 7]
    return {'pontos': pontos[:600], 'total': len(pontos), 'por_tipo': por_tipo, 'tipos': ATN_TIPOS, 'usinas_afetadas': len(por_usina), 'mais_de_7d': len(velhos), 'top_usinas': sorted(({'usina': u, 'n': n} for u, n in por_usina.items()), key=lambda x: -x['n'])[:12], 'os_ts': os_ts, 'os_no_periodo': sum((1 for p in pontos if p.get('origem') == 'os')), 'inv_ts': inv_ts, 'ts': _agora_iso()}


def _rondas_os_pares(piso=None):
    oss = [dict(e) for e in tabela_ronda_os().query_entities("PartitionKey eq 'os'", select=['RowKey', 'folio', 'id_work_order', 'usina', 'data', 'tipo', 'email', 'ativo', 'em_revisao', 'erro', 'criada_em', 'reservado_em'])]
    if piso:
        oss = [o for o in oss if str(o.get('data') or '') >= piso]
    if not oss:
        return []
    p = min((str(o.get('data') or '9999-12-31') for o in oss))
    ron = {}
    for r in tabela_ronda().query_entities("PartitionKey ge '%s'" % p, select=['PartitionKey', 'RowKey', 'email', 'nome', 'usina', 'cluster', 'qualidade', 'falhas', 'trk_total', 'trk_resp', 'inicio', 'fim', 'tipo', 'geo']):
        ron[str(r.get('PartitionKey') or ''), str(r.get('email') or '').lower(), _norm(r.get('usina'))] = r
    return [(o, ron.get((str(o.get('data') or ''), str(o.get('email') or '').lower(), _norm(o.get('usina')))) or {}) for o in oss]


def _ronda_resumo(o, r):
    r = r or {}

    def lst(x):
        if isinstance(x, list):
            return [str(y) for y in x]
        try:
            return [str(y) for y in json.loads(x or '[]') or []]
        except Exception:
            return []

    def geo(x):
        if isinstance(x, dict):
            return x
        try:
            return json.loads(x or '{}') or {}
        except Exception:
            return {}

    def i(x):
        try:
            return None if x in (None, '') else int(x)
        except (TypeError, ValueError):
            return None
    return {'ronda': True, 'folio': str(o.get('folio') or ''), 'data': str(o.get('data') or ''), 'email': str(o.get('email') or '').lower(), 'usina': o.get('usina') or '', 'tipo': o.get('tipo') or r.get('tipo') or '', 'tecnico': r.get('nome') or r.get('email') or '', 'qualidade': i(r.get('qualidade')), 'falhas': lst(r.get('falhas')), 'geo_ok': geo(r.get('geo')).get('lat') is not None if r else None, 'trk_total': i(r.get('trk_total')) or 0, 'trk_resp': i(r.get('trk_resp')) or 0, 'inicio': r.get('inicio') or '', 'fim': r.get('fim') or ''}


def _rondas_os_por_folio(piso):
    out = {}
    for o, r in _rondas_os_pares(piso):
        f = str(o.get('folio') or '').strip()
        if f:
            out[f] = _ronda_resumo(o, r)
    return out


ATN_SEG = {'ocorrencia', 'praga'}


def _chave_atencao(p, item=None):
    base = '|'.join((str(p.get(k) or '') for k in ('tipo', 'usina', 'os', 'data', 'email')))
    if item:
        base += '|' + _norm(item)[:160]
    import hashlib
    return hashlib.sha1(base.encode('utf-8')).hexdigest()[:12]


def _tratamentos():
    try:
        return {str(e.get('RowKey')): dict(e) for e in tabela_decisoes().query_entities("PartitionKey eq 'atn'")}
    except Exception as e:
        logging.warning('tratamentos: %s', e)
        return {}


def _aplicar_tratamentos(pontos):
    import time as _t
    tr = _tratamentos()
    hoje = _t.time()
    out = []
    for p in pontos:
        ch = _chave_atencao(p, p.get('oque'))
        ch_legado = _chave_atencao(p)
        p['chave'] = ch
        p['chave_legado'] = ch_legado
        t = tr.get(ch) or tr.get(ch_legado)
        if not t:
            out.append(p)
            continue
        estado = str(t.get('estado') or '')
        prazo = str(t.get('prazo') or '')
        venc = prazo and prazo < _agora_iso()[:10]
        if estado in ('resolvida', 'confirmada'):
            continue
        if estado == 'feita':
            if str(p.get('tipo')) in ATN_SEG:
                p['estado'] = 'aguarda_confirmacao'
                p['resp_nome'] = t.get('resp_nome') or ''
                out.append(p)
            continue
        if estado == 'silenciada':
            if not venc:
                continue
            p['estado'] = 'silencio_vencido'
            p['motivo_silencio'] = t.get('motivo') or ''
            out.append(p)
            continue
        if estado == 'encaminhada':
            p['estado'] = 'encaminhada'
            p['resp_nome'] = t.get('resp_nome') or ''
            p['resp_email'] = t.get('resp_email') or ''
            p['prazo'] = prazo
            p['escalada'] = bool(venc)
            out.append(p)
            continue
        out.append(p)
    return out


def _enc_resumo(itens, hoje):
    import collections as _c
    FECHADO = ('feita', 'confirmada', 'resolvida')
    abertos = [i for i in itens if i['estado'] == 'encaminhada']
    fechados = [i for i in itens if i['estado'] in FECHADO]
    vencidos = [i for i in abertos if i['vencida']]

    def _dias(i):
        try:
            from datetime import datetime as _d
            a = _d.fromisoformat(str(i.get('quando') or '')[:19])
            return max(0, (_d.fromisoformat(hoje + 'T00:00:00') - a).days)
        except Exception:
            return None
    idades = [d for d in (_dias(i) for i in abertos) if d is not None]

    def _top(chave, fonte):
        c = _c.Counter()
        for i in fonte:
            v = str(i.get(chave) or '').strip() or '—'
            c[v[:40]] += 1
        return [{'nome': k, 'n': v} for k, v in c.most_common(8)]
    return {'abertos': len(abertos), 'vencidos': len(vencidos), 'fechados': len(fechados), 'total': len(itens), 'idadeMedia': round(sum(idades) / len(idades), 1) if idades else None, 'idadeMax': max(idades) if idades else None, 'porDestino': _top('resp_nome', abertos), 'porRemetente': _top('por_nome', itens), 'viraramOS': sum((1 for i in itens if str(i.get('os_gerada') or '').strip())), 'comConversa': sum((1 for i in itens if int(i.get('conversas') or 0) > 0))}


def _hist_ler(ent):
    try:
        v = json.loads(str((ent or {}).get('historico') or '[]'))
        return v if isinstance(v, list) else []
    except Exception:
        return []


# ── Trocados pelo Nexus ────────────────────────────────────────────────────────────────────────────────────────────
# O resto deste arquivo é a lógica do App, intocada. Estes quatro é que mudam: de onde o dado vem, nunca a conta.
from . import fracttal as _fracttal_do_nexus  # noqa: E402
from . import pessoas as _pessoas_do_nexus  # noqa: E402
from .tabelas import tabela as _tabela_do_nexus  # noqa: E402


def _tabela(nome, cache_attr=None):
    return _tabela_do_nexus(nome)


def tabela():
    return _pessoas_do_nexus.tabela_dos_tokens()


def tabela_qlog():
    return _tabela_do_nexus("qualidadelog")


def fx(path, method="GET", body=None, _tentativa=0):
    return _fracttal_do_nexus.ler(path, method, body)


def ident():
    return _pessoas_do_nexus.ident(_cadastro_tab)
