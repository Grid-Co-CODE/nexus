"""CÓPIA da lógica de regras do App de Campo (function_app.py). NÃO EDITE: rode ferramentas/extrair_regras_campo.py.

Origem: function_app.py do App, codigo 92772066214dff23 (o número que o /api/health do App mostra quando é esta a
versão no ar). Copiado em 09/10/2026 17:40. Sem comentários nem docstrings (o repositório é
público); o porquê de cada regra está no código do App. Só o acesso a dado foi trocado (fim do arquivo).
"""
# ruff: noqa
CODIGO_APP = "92772066214dff23"
COPIADAS = ('ApiError', 'CADASTRO_TTL_S', 'ESTOURO_EXEC_MIN', 'ESTOURO_EXEC_X', 'ESTOURO_PREV_TETO', 'ESTOURO_PREV_X', 'FILA_TTL_S', 'FxLimite', 'LIMIARES_PADRAO', 'STATUS_IN_REVIEW', 'SUP_CAP_BACKLOG', 'TRIAGEM_ESTOURO', 'TRIAGEM_NOTA_OK', 'V2_PESOS', 'V2_PISO', 'VARREDURA_ESPERA_S', '_CAD', '_CANON', '_CATOV', '_CL_USINA', '_FILA_CACHE', '_SUPCAN', '_VARR', '_agora_iso', '_area_ok', '_cadastro_tab', '_canon_cluster', '_casa_nome', '_catalogo_ov', '_cluster_da_usina', '_clusters_por_email', '_concentracao', '_contar_fotos', '_dias_entre', '_duracao_ronda', '_estouro', '_estouro_causa', '_fila_bruta', '_fila_do_app', '_fila_supervisao', '_filtro_pessoas', '_fora', '_fx_wo_paralelo', '_gestao_prioridades', '_hoje', '_int0', '_janela', '_janela_str', '_lim_cache', '_limiares', '_link_fracttal_os', '_no_escopo', '_norm', '_obs_do_fechamento', '_parse_iso', '_pessoa_por_nome', '_preenchido_item', '_qlog_por_os', '_qualidade_os', '_qualidade_v2', '_ronda_resumo', '_rondas_os_pares', '_rondas_os_por_folio', '_sup_canon', '_sup_canon_mapa', '_sup_norm', '_triagem', '_txt_tarefa', '_usinas_do_cluster', '_v2_achou_falha', '_v2_e_na', '_v2_pede_foto', '_veredito_os', '_veredito_ronda', '_veredito_usina', 'tabela_limiares', 'tabela_ronda', 'tabela_ronda_ativos', 'tabela_ronda_os')
ASSINATURAS_TROCADAS = {'_tabela': '583740a7d68b3a65', '_varredura_carregar': '377c494f9c294aaf', 'fx': 'df3a6bba0b68da47', 'ident': 'a47f156debb43b7c', 'tabela': '666a04282aab3cbf', 'tabela_qlog': '95a72f1f98b561d4'}

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


class FxLimite(ApiError):
    pass


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


def _qualidade_v2(ev, gps_inicio=False, gps_ronda=False):
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
    gps_fim = isinstance(geo, dict) and geo.get('lat') is not None
    tem_gps = gps_fim or bool(gps_inicio) or bool(gps_ronda)
    return {'q': q, 'gps': tem_gps, 'base': base, 'gps_fonte': 'fechamento' if gps_fim else 'inicio' if gps_inicio else 'ronda' if gps_ronda else '', 'pontos': max(0, q - 60) if q >= V2_PISO and tem_gps else 0, 'itens': [{'rot': k, 'peso': p, 'pts': round(p * f, 1), 'det': dd} for k, p, f, dd in partes]}


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


SUP_CAP_BACKLOG = 20000


def _dias_entre(a, b):
    try:
        return round((_parse_iso(b) - _parse_iso(a)).total_seconds() / 86400.0, 1)
    except Exception:
        return None


STATUS_IN_REVIEW = 2


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


_FILA_CACHE = {'ts': None, 'linhas': None, 't': 0.0}


def _fx_wo_paralelo(status, sort, cap, paciente=False, prazo=None, esperas=None, recusas=None):
    from concurrent.futures import ThreadPoolExecutor
    if prazo is not None and time.time() > prazo:
        raise ApiError(504, 'o prazo do relógio acabou antes de ler o status %d' % status)

    def _ler(url):
        return fx(url, _tentativa=1) if paciente else fx(url)
    res = _ler('work_orders?id_status_work_order=%d&limit=1' % status)
    if not isinstance(res, dict) or res.get('total') is None:
        raise ApiError(502, 'o Fracttal não informou o total do status %d — fila não lida' % status)
    total_fx = int(res.get('total') or 0)
    total = min(total_fx, int(cap))
    if total_fx > int(cap):
        logging.error('varredura: TRUNCADA status %d — o Fracttal tem %d linhas e o teto é %d: as %d do fim da ordem (sort=%s, as mais recentes) ficam fora da fila do técnico, do painel e da zeladoria', status, total_fx, int(cap), total_fx - int(cap), sort)

    def _marca(lidas):
        _VARR.setdefault('teto', {})[str(status)] = {'total': total_fx, 'lidas': int(lidas), 'truncada': total_fx > int(cap), 't': round(time.time())}
    if total <= 0:
        _marca(0)
        return []
    offsets = list(range(0, total, 100))
    falhas = []
    parou = [False]

    def _pag(start):
        if prazo is not None and time.time() > prazo:
            falhas.append((start, 'prazo do relógio', 0))
            return []
        if parou[0]:
            falhas.append((start, 'esperando a cota do Fracttal', 0))
            return []
        try:
            res = _ler('work_orders?id_status_work_order=%d&limit=100&start=%d&sort=%s' % (status, start, sort))
            return (res.get('data') if isinstance(res, dict) else res) or []
        except Exception as e:
            falhas.append((start, str(e)[:90], int(getattr(e, 'espera', 0) or 0)))
            if recusas is not None and isinstance(e, FxLimite):
                recusas.append(start)
            if paciente and isinstance(e, FxLimite):
                parou[0] = True
            logging.warning('wo pagina %s@%d: %s', status, start, e)
            return []
    with ThreadPoolExecutor(max_workers=2 if paciente else 6) as ex:
        partes = dict(zip(offsets, ex.map(_pag, offsets)))
    for _rodada in range(4 if paciente else 2):
        if not falhas:
            break
        _pend = [x[0] for x in falhas]
        w = VARREDURA_ESPERA_S if paciente else min(max(max((x[2] for x in falhas)), 5), 30)
        if prazo is not None and time.time() + w > prazo:
            break
        del falhas[:]
        parou[0] = False
        if esperas is not None:
            esperas.append(w)
        time.sleep(w)
        for start in _pend:
            partes[start] = _pag(start)
    linhas = [x for s in offsets for x in partes.get(s) or []]
    if falhas:
        logging.error('fila status %s INCOMPLETA: %d de %d pagina(s) falharam (%s) — vieram %d de %d linhas', status, len(falhas), len(offsets), falhas[0][1], len(linhas), total)
        raise ApiError(502, 'fila do Fracttal veio incompleta (%d pagina(s) falharam)' % len(falhas))
    if len(linhas) < total:
        logging.warning('fila status %s: vieram %d de %d esperadas', status, len(linhas), total)
    _marca(min(len(linhas), int(cap)))
    return linhas[:int(cap)]


def _fila_bruta(forcar=False):
    agora = time.time()
    if not forcar and _FILA_CACHE.get('linhas') is not None and (agora - (_FILA_CACHE.get('t') or 0) < FILA_TTL_S):
        return _FILA_CACHE['linhas']
    if not forcar and _varredura_carregar():
        return _FILA_CACHE['linhas']
    try:
        linhas = _fx_wo_paralelo(2, 'final_date', SUP_CAP_BACKLOG)
    except Exception as e:
        if _FILA_CACHE.get('linhas') is not None:
            logging.error('fila incompleta (%s) — servindo o cache de %.0f s atrás', str(e)[:100], agora - (_FILA_CACHE.get('t') or agora))
            return _FILA_CACHE['linhas']
        raise
    _FILA_CACHE['t'] = _FILA_CACHE['ts'] = agora
    _FILA_CACHE['linhas'] = linhas
    return linhas


VARREDURA_ESPERA_S = int(os.environ.get('VARREDURA_ESPERA_S', '60') or '60')


_VARR = {'cli': None, 'etag': None, 'checado': 0.0, 'teto': {}}


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


def _rondas_os_pares(piso=None, respostas=False):
    oss = [dict(e) for e in tabela_ronda_os().query_entities("PartitionKey eq 'os'", select=['RowKey', 'folio', 'id_work_order', 'usina', 'data', 'tipo', 'email', 'ativo', 'em_revisao', 'erro', 'criada_em', 'reservado_em'])]
    if piso:
        oss = [o for o in oss if str(o.get('data') or '') >= piso]
    if not oss:
        return []
    p = min((str(o.get('data') or '9999-12-31') for o in oss))
    ron = {}
    for r in tabela_ronda().query_entities("PartitionKey ge '%s'" % p, select=['PartitionKey', 'RowKey', 'email', 'nome', 'usina', 'cluster', 'qualidade', 'falhas', 'trk_total', 'trk_resp', 'inicio', 'fim', 'tipo', 'geo'] + (['respostas', 'multiItens'] if respostas else [])):
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


# ── Trocados pelo Nexus ────────────────────────────────────────────────────────────────────────────────────────────
# O resto deste arquivo é a lógica do App, intocada. Estes é que mudam: de onde o dado vem, nunca a conta.
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


def _varredura_carregar():
    return False
