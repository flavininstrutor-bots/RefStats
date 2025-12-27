"""
REFSTATS - JOGOS DO DIA - VERSÃO 1.5 ⚽
========================================

🆕 NOVIDADES v1.5:
✅ Navbar idêntica ao Home (INÍCIO, JOGOS DO DIA, HISTÓRICO, CONTATO)
✅ Título atualizado para "Jogos do Dia" com a data consultada
✅ Logo e identidade visual do RefStats
✅ Integração visual com a página inicial

🔄 MANTIDO DA v1.4:
✅ Data informada funciona como "hoje" para todo o sistema
✅ Histórico do árbitro: jogos ANTES da data informada
✅ Histórico dos times: jogos ANTES da data informada  
✅ Próximos jogos: jogos APÓS a data informada
✅ Scroll horizontal nas tabelas do árbitro (mobile-friendly)
✅ Gráfico de linha comparativo de amarelos (Árbitro x Times - últimos 5j)
✅ Filtro por perfil do árbitro (Rigoroso/Médio/Permissivo) na barra de pesquisa

🔄 MANTIDO DA v1.3:
✅ Correção do bug de margens acumulativas com muitos jogos
✅ Correção do bug de tags <a> não fechadas nos resumos de notícias
✅ Adicionado width: 100% e box-sizing: border-box em elementos chave

🔄 MANTIDO DA v1.2:
✅ Barra de pesquisa estilo Ctrl+F (busca na página com highlights)
✅ Navegação entre ocorrências (próximo/anterior)
✅ Contador de resultados encontrados
✅ Atalho Ctrl+F / Cmd+F para abrir a barra

🔄 MANTIDO DA v1.1:
✅ Próximos jogos com colocação do adversário + competição
✅ Busca notícias do árbitro em PT e EN (para árbitros estrangeiros)
✅ Busca info do estádio via API do evento (como no Consultor)
✅ Tooltips (ℹ️) explicando cada métrica e conceito
✅ Design melhorado da seção de perfil do árbitro
✅ Explicações para Faltas Pró/Contra, Amarelos

📌 ESTRUTURA DA PÁGINA:
1) Navbar (INÍCIO, JOGOS DO DIA, HISTÓRICO, CONTATO)
2) Barra de Pesquisa + Filtros de Perfil
3) Cabeçalho "Jogos do Dia" com data consultada
4) Cards dos Jogos (Árbitro, Times, Gráfico)
5) Footer com aviso de responsabilidade

Autor: RefStats v1.5
Data: 2025-12-24
"""

import requests
import feedparser
import json
from datetime import datetime, timedelta
from urllib.parse import quote
import time
import sys
import re
import os
import traceback
from functools import wraps, lru_cache
import unicodedata

# ============================================================================
# CONFIGURAÇÕES
# ============================================================================

BASE_URL = 'https://api.sofascore.com/api/v1'
SOFASCORE_WEB = 'https://www.sofascore.com'
OUTPUT_DIR = 'relatorios_unificados'

# Headers para simular navegador
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
    'Referer': 'https://www.sofascore.com/'
}

# Configurações de retry e timeout
MAX_RETRIES = 3
RETRY_DELAY = 2
TIMEOUT_PADRAO = 10

# IDs das principais ligas
LIGAS_PRINCIPAIS = {
    # Brasil
    325: 'Brasileirão Série A',
    390: 'Brasileirão Série B',
    384: 'Copa do Brasil',
    
    # Europa - Top 5
    17: 'Premier League',
    8: 'La Liga',
    23: 'Bundesliga',
    34: 'Serie A',
    53: 'Ligue 1',
    
    # Sul-Americana
    13: 'Copa Libertadores',
    11: 'Copa Sudamericana',
    
    # Outras importantes
    679: 'Série C Brasil',
    373: 'Série D Brasil',
    16: 'Championship',
    87: 'Liga Portugal',
    35: 'Serie B Italia',
    155: 'La Liga 2',
}

# Médias por liga (baseline)
MEDIA_LIGAS = {
    2:   {"liga": "UEFA Europa League",     "amarelos_total_jogo": 4.9, "faltas_total_jogo": 25.2},
    8:   {"liga": "La Liga",               "amarelos_total_jogo": 5.2, "faltas_total_jogo": 25.6},
    11:  {"liga": "Copa Sudamericana",     "amarelos_total_jogo": 5.8, "faltas_total_jogo": 27.8},
    13:  {"liga": "Copa Libertadores",     "amarelos_total_jogo": 6.0, "faltas_total_jogo": 28.6},
    16:  {"liga": "Championship",          "amarelos_total_jogo": 4.4, "faltas_total_jogo": 24.2},
    17:  {"liga": "Premier League",        "amarelos_total_jogo": 5.0, "faltas_total_jogo": 23.0},
    23:  {"liga": "Bundesliga",            "amarelos_total_jogo": 4.2, "faltas_total_jogo": 20.4},
    34:  {"liga": "Serie A",               "amarelos_total_jogo": 4.6, "faltas_total_jogo": 24.0},
    35:  {"liga": "Serie B",               "amarelos_total_jogo": 5.6, "faltas_total_jogo": 28.0},
    53:  {"liga": "Ligue 1",               "amarelos_total_jogo": 4.0, "faltas_total_jogo": 22.0},
    87:  {"liga": "Liga Portugal",         "amarelos_total_jogo": 5.8, "faltas_total_jogo": 28.8},
    155: {"liga": "La Liga 2",             "amarelos_total_jogo": 5.4, "faltas_total_jogo": 27.6},
    325: {"liga": "Brasileirão Série A",   "amarelos_total_jogo": 5.4, "faltas_total_jogo": 28.4},
    373: {"liga": "Série D Brasil",        "amarelos_total_jogo": 6.2, "faltas_total_jogo": 32.0},
    384: {"liga": "Copa do Brasil",        "amarelos_total_jogo": 5.8, "faltas_total_jogo": 28.4},
    390: {"liga": "Brasileirão Série B",   "amarelos_total_jogo": 5.6, "faltas_total_jogo": 27.1},
    679: {"liga": "Série C Brasil",        "amarelos_total_jogo": 6.0, "faltas_total_jogo": 31.0},
}

# ============================================================================
# DECORATOR DE RETRY
# ============================================================================

def retry_on_failure(max_attempts=MAX_RETRIES, delay=RETRY_DELAY, exceptions=(Exception,)):
    """Decorator que tenta executar uma função até max_attempts vezes"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        time.sleep(delay)
            if last_exception:
                raise last_exception
        return wrapper
    return decorator

# ============================================================================
# FUNÇÕES AUXILIARES
# ============================================================================

def fazer_requisicao(url, headers=None, timeout=TIMEOUT_PADRAO):
    """Faz uma requisição HTTP com tratamento de erros"""
    try:
        if headers is None:
            headers = HEADERS
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        return None
    except requests.exceptions.RequestException:
        return None
    except json.JSONDecodeError:
        return None

@retry_on_failure(max_attempts=3)
def fazer_requisicao_com_retry(url, headers=None, timeout=TIMEOUT_PADRAO):
    """Faz uma requisição HTTP com retry automático"""
    if headers is None:
        headers = HEADERS
    response = requests.get(url, headers=headers, timeout=timeout)
    if response.status_code != 200:
        raise Exception(f"HTTP {response.status_code}")
    return response.json()

def _extrair_valor_estatistica(valor):
    """Extrai valor numérico de uma estatística"""
    if valor is None:
        return 0
    if isinstance(valor, (int, float)):
        return int(valor)
    if isinstance(valor, str):
        try:
            return int(float(valor.strip()))
        except:
            return 0
    return 0

def obter_media_liga(liga_id):
    """Obtém médias baseline da liga"""
    if liga_id is None:
        return None
    try:
        return MEDIA_LIGAS.get(int(liga_id))
    except:
        return None

# ============================================================================
# v1.1: BUSCA INFO DO ESTÁDIO VIA API DO EVENTO
# ============================================================================

@retry_on_failure(max_attempts=2)
def buscar_info_estadio_evento(event_id):
    """
    v1.1: Busca informações completas do estádio onde o jogo será realizado
    """
    try:
        url = f"{BASE_URL}/event/{event_id}"
        data = fazer_requisicao_com_retry(url, timeout=TIMEOUT_PADRAO)
        
        event_info = data.get('event', {})
        venue = event_info.get('venue', {})
        
        if not venue:
            return None
        
        estadio_info = {
            'nome': venue.get('stadium', {}).get('name', 'Estádio não informado'),
            'cidade': venue.get('city', {}).get('name', 'Cidade não informada'),
            'pais': venue.get('country', {}).get('name', ''),
            'latitude': venue.get('latitude'),
            'longitude': venue.get('longitude')
        }
        
        return estadio_info
        
    except Exception:
        return None

# ============================================================================
# BUSCA DE PARTIDAS DO DIA
# ============================================================================

def buscar_partidas_do_dia(data_str):
    """
    Busca todas as partidas do dia escolhido (00:00 às 23:59 horário de Brasília)
    """
    try:
        data_obj = datetime.strptime(data_str, '%d/%m/%Y')
        data_api = data_obj.strftime('%Y-%m-%d')
        
        inicio_dia = data_obj.replace(hour=0, minute=0, second=0)
        fim_dia = data_obj.replace(hour=23, minute=59, second=59)
        
        timestamp_inicio = int(inicio_dia.timestamp())
        timestamp_fim = int(fim_dia.timestamp())
        
        print(f"\n🔍 Buscando partidas de {data_str}...")
        print(f"   📅 Horário: 00:00 às 23:59 (Brasília)")
        
        partidas = []
        
        for liga_id, liga_nome in LIGAS_PRINCIPAIS.items():
            print(f"\n   🏆 {liga_nome}...")
            
            url = f"{BASE_URL}/sport/football/scheduled-events/{data_api}"
            data = fazer_requisicao(url)
            
            if not data or 'events' not in data:
                continue
            
            eventos_liga = [
                e for e in data['events'] 
                if e.get('tournament', {}).get('uniqueTournament', {}).get('id') == liga_id
            ]
            
            if not eventos_liga:
                print(f"      ℹ️ Nenhuma partida encontrada")
                continue
            
            eventos_do_dia = []
            for evento in eventos_liga:
                start_timestamp = evento.get('startTimestamp', 0)
                if timestamp_inicio <= start_timestamp <= timestamp_fim:
                    eventos_do_dia.append(evento)
            
            if not eventos_do_dia:
                print(f"      ℹ️ Nenhuma partida neste horário")
                continue
            
            print(f"      ✅ {len(eventos_do_dia)} partida(s) encontrada(s)")
            
            for evento in eventos_do_dia:
                try:
                    torneio = evento.get('tournament', {})
                    torneio_nome = torneio.get('name', liga_nome)
                    
                    # Round/Fase
                    round_info = evento.get('roundInfo', {})
                    round_name = round_info.get('name', '')
                    round_round = round_info.get('round', '')
                    
                    # Determina a fase/rodada
                    fase = ''
                    if round_name:
                        round_lower = round_name.lower()
                        if 'final' in round_lower and 'semi' not in round_lower and 'quarter' not in round_lower:
                            fase = 'FINAL'
                        elif 'semi' in round_lower:
                            fase = 'SEMIFINAL'
                        elif 'quarter' in round_lower or 'quartas' in round_lower:
                            fase = 'QUARTAS'
                        elif 'oitavas' in round_lower or 'round of 16' in round_lower:
                            fase = 'OITAVAS'
                        elif round_round:
                            fase = f'{round_round}ª Rodada'
                    elif round_round:
                        fase = f'{round_round}ª Rodada'
                    
                    partida = {
                        'id': evento['id'],
                        'liga_id': liga_id,
                        'liga_nome': torneio_nome,
                        'time_casa': evento['homeTeam']['name'],
                        'time_casa_id': evento['homeTeam']['id'],
                        'time_fora': evento['awayTeam']['name'],
                        'time_fora_id': evento['awayTeam']['id'],
                        'horario': datetime.fromtimestamp(evento['startTimestamp']).strftime('%H:%M'),
                        'data': data_str,
                        'data_formatada': datetime.fromtimestamp(evento['startTimestamp']).strftime('%d/%m/%Y - %H:%M'),
                        'status': evento.get('status', {}).get('description', 'Não iniciado'),
                        'fase': fase,
                    }
                    
                    partidas.append(partida)
                    print(f"         • {partida['time_casa']} vs {partida['time_fora']} - {partida['horario']}")
                    
                except Exception as e:
                    continue
        
        print(f"\n✅ Total de partidas encontradas: {len(partidas)}")
        return partidas
        
    except Exception as e:
        print(f"\n❌ Erro ao buscar partidas: {str(e)}")
        traceback.print_exc()
        return []

# ============================================================================
# BUSCA DE INFORMAÇÕES DO ÁRBITRO
# ============================================================================

def buscar_arbitro_partida(partida_id):
    """Busca informações do árbitro de uma partida específica"""
    try:
        url = f"{BASE_URL}/event/{partida_id}"
        data = fazer_requisicao(url)
        
        if not data or 'event' not in data:
            return None
        
        evento = data['event']
        
        if 'referee' not in evento:
            return None
        
        arbitro = evento['referee']
        
        arbitro_info = {
            'id': arbitro['id'],
            'nome': arbitro['name'],
            'pais': arbitro.get('country', {}).get('name', 'N/A'),
            'pais_codigo': arbitro.get('country', {}).get('alpha2', 'N/A')
        }
        
        print(f"         ⚖️ Árbitro: {arbitro_info['nome']} ({arbitro_info['pais']})")
        return arbitro_info
        
    except Exception as e:
        return None

def _buscar_stats_evento_por_periodo(event_id, nome_keywords):
    """Função genérica para ler estatísticas por período"""
    periodos = {
        "1ST": {"home": 0, "away": 0},
        "2ND": {"home": 0, "away": 0},
        "ALL": {"home": 0, "away": 0},
    }
    
    try:
        if not event_id:
            return periodos
        
        url = f"{BASE_URL}/event/{event_id}/statistics"
        data = fazer_requisicao(url)
        
        if not data:
            return periodos
        
        statistics = data.get("statistics", [])
        nome_keywords = [k.lower() for k in nome_keywords]
        
        for bloco in statistics:
            period = bloco.get("period", "ALL")
            if period not in periodos:
                period = "ALL"
            
            grupos = bloco.get("groups", [])
            
            for grupo in grupos:
                items = grupo.get("statisticsItems", [])
                for item in items:
                    nome_stat = (item.get("name", "") or "").lower()
                    
                    if any(kw in nome_stat for kw in nome_keywords):
                        periodos[period]["home"] = _extrair_valor_estatistica(item.get("home", 0))
                        periodos[period]["away"] = _extrair_valor_estatistica(item.get("away", 0))
                        break
        
        return periodos
        
    except Exception:
        return periodos

def buscar_estatisticas_partida(partida_id):
    """Busca estatísticas detalhadas de uma partida"""
    try:
        # Busca faltas
        keywords_faltas = ["fouls", "fouls committed", "faltas", "faltas cometidas"]
        flt = _buscar_stats_evento_por_periodo(partida_id, keywords_faltas)
        
        # Qualidade do dado
        faltas_tempos_missing = False
        if (flt["1ST"]["home"] == 0 and flt["1ST"]["away"] == 0 and
            flt["2ND"]["home"] == 0 and flt["2ND"]["away"] == 0 and
            (flt["ALL"]["home"] > 0 or flt["ALL"]["away"] > 0)):
            faltas_tempos_missing = True
            flt["1ST"]["home"] = None
            flt["1ST"]["away"] = None
            flt["2ND"]["home"] = None
            flt["2ND"]["away"] = None
        
        # Busca cartões amarelos
        amarelos = _buscar_stats_evento_por_periodo(partida_id, ["yellow card", "yellow cards"])
        
        # Busca cartões vermelhos
        vermelhos = _buscar_stats_evento_por_periodo(partida_id, ["red card", "red cards"])
        
        stats = {
            # Faltas
            'faltas_1t_casa': flt["1ST"]["home"],
            'faltas_1t_fora': flt["1ST"]["away"],
            'faltas_2t_casa': flt["2ND"]["home"],
            'faltas_2t_fora': flt["2ND"]["away"],
            'faltas_total_casa': flt["ALL"]["home"] if flt["ALL"]["home"] > 0 else (
                (flt["1ST"]["home"] + flt["2ND"]["home"]) if flt["1ST"]["home"] is not None else None),
            'faltas_total_fora': flt["ALL"]["away"] if flt["ALL"]["away"] > 0 else (
                (flt["1ST"]["away"] + flt["2ND"]["away"]) if flt["1ST"]["away"] is not None else None),
            'faltas_tempos_missing': faltas_tempos_missing,
            
            # Cartões Amarelos
            'amarelos_1t_casa': amarelos["1ST"]["home"],
            'amarelos_1t_fora': amarelos["1ST"]["away"],
            'amarelos_2t_casa': amarelos["2ND"]["home"],
            'amarelos_2t_fora': amarelos["2ND"]["away"],
            'amarelos_total_casa': amarelos["ALL"]["home"] if amarelos["ALL"]["home"] > 0 else amarelos["1ST"]["home"] + amarelos["2ND"]["home"],
            'amarelos_total_fora': amarelos["ALL"]["away"] if amarelos["ALL"]["away"] > 0 else amarelos["1ST"]["away"] + amarelos["2ND"]["away"],
            
            # Cartões Vermelhos
            'vermelhos_total_casa': vermelhos["ALL"]["home"] if vermelhos["ALL"]["home"] > 0 else vermelhos["1ST"]["home"] + vermelhos["2ND"]["home"],
            'vermelhos_total_fora': vermelhos["ALL"]["away"] if vermelhos["ALL"]["away"] > 0 else vermelhos["1ST"]["away"] + vermelhos["2ND"]["away"],
        }
        
        return stats
        
    except Exception:
        return None

def identificar_fase_partida(evento):
    """Identifica a fase da partida"""
    try:
        round_info = evento.get('roundInfo', {})
        round_name = round_info.get('name', '')
        
        if not round_name:
            return ''
        
        round_lower = round_name.lower()
        
        if 'final' in round_lower and 'semi' not in round_lower and 'quarter' not in round_lower:
            return 'FINAL'
        elif 'semi' in round_lower:
            return 'SEMIFINAL'
        elif 'quarter' in round_lower or 'quartas' in round_lower:
            return 'QUARTAS'
        elif 'oitavas' in round_lower or 'round of 16' in round_lower:
            return 'OITAVAS'
        elif 'round' in round_lower and any(char.isdigit() for char in round_name):
            return ''
        elif 'rodada' in round_lower:
            return ''
        
        return round_name
        
    except Exception:
        return ''

def buscar_ultimas_partidas_arbitro(arbitro_id, quantidade=10, data_alvo=None):
    """
    Busca as últimas partidas que o árbitro apitou ANTES da data_alvo.
    Se data_alvo não for informada, usa a data atual.
    """
    try:
        print(f"         🔍 Buscando últimas {quantidade} partidas...")
        
        url = f"{BASE_URL}/referee/{arbitro_id}/events/last/0"
        data = fazer_requisicao(url)
        
        if not data or 'events' not in data:
            return []
        
        todos_eventos = data['events']
        
        # Define a data limite (meia-noite do dia alvo)
        if data_alvo:
            if isinstance(data_alvo, str):
                data_limite = datetime.strptime(data_alvo, '%d/%m/%Y')
            else:
                data_limite = data_alvo
            # Usa o início do dia como limite
            data_limite = data_limite.replace(hour=0, minute=0, second=0, microsecond=0)
            timestamp_limite = data_limite.timestamp()
        else:
            timestamp_limite = datetime.now().timestamp()
        
        # Filtra apenas partidas finalizadas E anteriores à data_alvo
        eventos_finalizados = []
        for evento in todos_eventos:
            status_code = evento.get('status', {}).get('code')
            status_type = evento.get('status', {}).get('type')
            evento_timestamp = evento.get('startTimestamp', 0)
            
            # Só inclui se finalizado E antes da data limite
            if (status_code == 100 or status_type == 'finished') and evento_timestamp < timestamp_limite:
                eventos_finalizados.append(evento)
        
        # Ordena por timestamp DECRESCENTE
        eventos_finalizados.sort(key=lambda x: x.get('startTimestamp', 0), reverse=True)
        
        # Pega as 10 mais recentes
        eventos = eventos_finalizados[:quantidade]
        partidas = []
        
        print(f"         ✅ {len(eventos)} partida(s) finalizada(s) encontrada(s)")
        
        # Processa cada partida
        for idx, evento in enumerate(eventos, 1):
            try:
                torneio_nome = evento.get('tournament', {}).get('name', 'N/A')
                
                partida_info = {
                    'id': evento['id'],
                    'campeonato': torneio_nome,
                    'liga_id': evento.get('tournament', {}).get('uniqueTournament', {}).get('id'),
                    'time_casa': evento['homeTeam']['name'],
                    'time_fora': evento['awayTeam']['name'],
                    'placar_casa': evento.get('homeScore', {}).get('current', 0),
                    'placar_fora': evento.get('awayScore', {}).get('current', 0),
                    'data': datetime.fromtimestamp(evento['startTimestamp']).strftime('%d/%m/%Y'),
                }
                
                # Busca estatísticas detalhadas da partida
                stats = buscar_estatisticas_partida(evento['id'])
                if stats:
                    partida_info.update(stats)
                
                # Busca fase
                partida_info['fase'] = identificar_fase_partida(evento)
                
                partidas.append(partida_info)
                time.sleep(0.3)
                
            except Exception:
                continue
        
        return partidas
        
    except Exception:
        return []

# ============================================================================
# v1.1: BUSCA DE NOTÍCIAS DO ÁRBITRO (PT + EN)
# ============================================================================

def buscar_noticias_arbitro(nome_arbitro, pais_arbitro='', dias=90):
    """
    v1.1: Busca notícias recentes sobre o árbitro via Google News RSS
    Busca em PORTUGUÊS e INGLÊS para cobrir árbitros estrangeiros
    """
    noticias = []
    
    try:
        # Termos de busca em PORTUGUÊS
        termos_pt = [
            f'"{nome_arbitro}" árbitro futebol',
            f'{nome_arbitro} árbitro',
        ]
        
        # Termos de busca em INGLÊS (para árbitros estrangeiros)
        termos_en = [
            f'"{nome_arbitro}" referee football',
            f'"{nome_arbitro}" referee soccer',
            f'{nome_arbitro} referee',
        ]
        
        data_limite = datetime.now() - timedelta(days=dias)
        links_vistos = set()
        titulos_vistos = set()
        
        # Busca em Português (Brasil)
        for termo in termos_pt:
            try:
                url = f"https://news.google.com/rss/search?q={quote(termo)}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
                feed = feedparser.parse(url)
                
                for entry in feed.entries[:8]:
                    noticia = _processar_noticia_entry(entry, nome_arbitro, data_limite, links_vistos, titulos_vistos)
                    if noticia:
                        noticias.append(noticia)
                        
            except Exception:
                continue
        
        # Busca em Inglês (Internacional)
        for termo in termos_en:
            try:
                url = f"https://news.google.com/rss/search?q={quote(termo)}&hl=en-US&gl=US&ceid=US:en"
                feed = feedparser.parse(url)
                
                for entry in feed.entries[:8]:
                    noticia = _processar_noticia_entry(entry, nome_arbitro, data_limite, links_vistos, titulos_vistos)
                    if noticia:
                        noticias.append(noticia)
                        
            except Exception:
                continue
        
        # Ordena por data (mais recentes primeiro)
        noticias.sort(key=lambda x: x['data'], reverse=True)
        
        # Retorna top 3
        return noticias[:3]
        
    except Exception:
        return []

def _processar_noticia_entry(entry, nome_arbitro, data_limite, links_vistos, titulos_vistos):
    """Processa uma entrada do feed RSS e retorna notícia se válida"""
    try:
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            data_noticia = datetime(*entry.published_parsed[:6])
        else:
            data_noticia = datetime.now()
        
        if data_noticia < data_limite:
            return None
        
        titulo = entry.title if hasattr(entry, 'title') else ''
        link = entry.link if hasattr(entry, 'link') else ''
        
        # Evita duplicatas por link
        if link in links_vistos:
            return None
        
        # Evita duplicatas por título similar
        titulo_normalizado = titulo.lower()[:50]
        if titulo_normalizado in titulos_vistos:
            return None
        
        links_vistos.add(link)
        titulos_vistos.add(titulo_normalizado)
        
        # Verifica se é relevante (menciona o nome do árbitro)
        nome_partes = nome_arbitro.lower().split()
        nome_encontrado = False
        for parte in nome_partes:
            if len(parte) > 3 and parte in titulo.lower():
                nome_encontrado = True
                break
        
        if not nome_encontrado:
            return None
        
        fonte = ''
        if hasattr(entry, 'source') and hasattr(entry.source, 'title'):
            fonte = entry.source.title
        
        # Resumo curto
        resumo = ''
        if hasattr(entry, 'summary'):
            # PRIMEIRO remove tags HTML completas
            resumo = re.sub(r'<[^>]+>', '', entry.summary)
            # Remove tags incompletas (ex: "<a href=..." sem fechar)
            resumo = re.sub(r'<[^>]*$', '', resumo)
            # Remove fechamentos órfãos (ex: "...>texto")
            resumo = re.sub(r'^[^<]*>', '', resumo)
            # Remove qualquer < ou > restante
            resumo = resumo.replace('<', '').replace('>', '')
            # Limpa espaços extras
            resumo = ' '.join(resumo.split())
            # DEPOIS trunca o texto limpo
            if len(resumo) > 150:
                resumo = resumo[:150] + '...'
        
        return {
            'titulo': titulo,
            'link': link,
            'data': data_noticia,
            'data_formatada': data_noticia.strftime('%d/%m/%Y'),
            'fonte': fonte,
            'resumo': resumo,
        }
        
    except Exception:
        return None

# ============================================================================
# CÁLCULOS E MÉTRICAS DO ÁRBITRO
# ============================================================================

def calcular_metricas_arbitro(historico, liga_id_jogo):
    """Calcula todas as métricas do árbitro baseado no histórico"""
    if not historico:
        return None
    
    # Separa jogos da mesma liga e outras ligas
    jogos_mesma_liga = [j for j in historico if j.get('liga_id') == liga_id_jogo]
    jogos_outras_ligas = [j for j in historico if j.get('liga_id') != liga_id_jogo]
    
    # Lista de amarelos dos últimos 5 jogos NA MESMA LIGA (para o gráfico)
    amarelos_5j_liga = []
    for jogo in jogos_mesma_liga[:5]:
        am_casa = jogo.get('amarelos_total_casa', 0) or 0
        am_fora = jogo.get('amarelos_total_fora', 0) or 0
        amarelos_5j_liga.append(am_casa + am_fora)
    
    # Médias gerais (10 jogos)
    amarelos_10j = []
    amarelos_5j = []
    amarelos_1t_10j = []
    amarelos_2t_10j = []
    faltas_10j = []
    faltas_5j = []
    faltas_1t_10j = []
    faltas_2t_10j = []
    vermelhos_10j = []
    
    jogos_missing_faltas_1t = 0
    
    for i, jogo in enumerate(historico[:10]):
        # Amarelos
        am_casa = jogo.get('amarelos_total_casa', 0) or 0
        am_fora = jogo.get('amarelos_total_fora', 0) or 0
        amarelos_total = am_casa + am_fora
        amarelos_10j.append(amarelos_total)
        if i < 5:
            amarelos_5j.append(amarelos_total)
        
        # Amarelos 1T
        am_1t = (jogo.get('amarelos_1t_casa', 0) or 0) + (jogo.get('amarelos_1t_fora', 0) or 0)
        amarelos_1t_10j.append(am_1t)
        
        # Amarelos 2T
        am_2t = (jogo.get('amarelos_2t_casa', 0) or 0) + (jogo.get('amarelos_2t_fora', 0) or 0)
        amarelos_2t_10j.append(am_2t)
        
        # Faltas
        ft_casa = jogo.get('faltas_total_casa')
        ft_fora = jogo.get('faltas_total_fora')
        if ft_casa is not None and ft_fora is not None:
            faltas_total = ft_casa + ft_fora
            faltas_10j.append(faltas_total)
            if i < 5:
                faltas_5j.append(faltas_total)
        
        # Faltas 1T
        f1t_casa = jogo.get('faltas_1t_casa')
        f1t_fora = jogo.get('faltas_1t_fora')
        if f1t_casa is not None and f1t_fora is not None:
            faltas_1t_10j.append(f1t_casa + f1t_fora)
        else:
            jogos_missing_faltas_1t += 1
        
        # Faltas 2T
        f2t_casa = jogo.get('faltas_2t_casa')
        f2t_fora = jogo.get('faltas_2t_fora')
        if f2t_casa is not None and f2t_fora is not None:
            faltas_2t_10j.append(f2t_casa + f2t_fora)
        
        # Vermelhos
        verm = (jogo.get('vermelhos_total_casa', 0) or 0) + (jogo.get('vermelhos_total_fora', 0) or 0)
        vermelhos_10j.append(verm)
    
    # Calcula médias
    media_amarelos_10j = round(sum(amarelos_10j) / len(amarelos_10j), 2) if amarelos_10j else 0
    media_amarelos_5j = round(sum(amarelos_5j) / len(amarelos_5j), 2) if amarelos_5j else 0
    media_amarelos_1t = round(sum(amarelos_1t_10j) / len(amarelos_1t_10j), 2) if amarelos_1t_10j else 0
    media_amarelos_2t = round(sum(amarelos_2t_10j) / len(amarelos_2t_10j), 2) if amarelos_2t_10j else 0
    media_faltas_10j = round(sum(faltas_10j) / len(faltas_10j), 2) if faltas_10j else 0
    media_faltas_5j = round(sum(faltas_5j) / len(faltas_5j), 2) if faltas_5j else 0
    media_faltas_1t = round(sum(faltas_1t_10j) / len(faltas_1t_10j), 2) if faltas_1t_10j else 0
    media_faltas_2t = round(sum(faltas_2t_10j) / len(faltas_2t_10j), 2) if faltas_2t_10j else 0
    media_vermelhos = round(sum(vermelhos_10j) / len(vermelhos_10j), 2) if vermelhos_10j else 0
    
    # Percentuais
    jogos_5mais_amarelos = sum(1 for a in amarelos_10j if a >= 5)
    pct_5mais_amarelos = round((jogos_5mais_amarelos / len(amarelos_10j)) * 100, 1) if amarelos_10j else 0
    
    jogos_3mais_amarelos_1t = sum(1 for a in amarelos_1t_10j if a >= 3)
    pct_3mais_amarelos_1t = round((jogos_3mais_amarelos_1t / len(amarelos_1t_10j)) * 100, 1) if amarelos_1t_10j else 0
    
    # Perfil
    baseline = obter_media_liga(liga_id_jogo)
    baseline_amarelos = baseline.get('amarelos_total_jogo', 5.0) if baseline else 5.0
    
    if media_amarelos_10j >= baseline_amarelos * 1.15:
        perfil = 'Rigoroso'
    elif media_amarelos_10j <= baseline_amarelos * 0.85:
        perfil = 'Permissivo'
    else:
        perfil = 'Médio'
    
    # Pipoqueiro 1T (se média 1T é muito alta em relação à média total)
    pipoqueiro_1t = False
    if media_amarelos_10j > 0 and (media_amarelos_1t / media_amarelos_10j) > 0.5:
        pipoqueiro_1t = True
    
    # Qualidade dos dados
    qualidade_faltas_1t = round((1 - jogos_missing_faltas_1t / 10) * 100, 1) if len(historico) >= 10 else 0
    
    metricas = {
        'media_amarelos_10j': media_amarelos_10j,
        'media_amarelos_5j': media_amarelos_5j,
        'media_amarelos_1t': media_amarelos_1t,
        'media_amarelos_2t': media_amarelos_2t,
        'media_faltas_10j': media_faltas_10j,
        'media_faltas_5j': media_faltas_5j,
        'media_faltas_1t': media_faltas_1t,
        'media_faltas_2t': media_faltas_2t,
        'media_vermelhos': media_vermelhos,
        'pct_5mais_amarelos': pct_5mais_amarelos,
        'pct_3mais_amarelos_1t': pct_3mais_amarelos_1t,
        'perfil': perfil,
        'pipoqueiro_1t': pipoqueiro_1t,
        'qualidade_faltas_1t': qualidade_faltas_1t,
        'jogos_mesma_liga': jogos_mesma_liga,
        'jogos_outras_ligas': jogos_outras_ligas,
        'baseline': baseline,
        # Dados para o gráfico de amarelos
        'amarelos_5j_liga': amarelos_5j_liga,  # últimos 5 jogos na mesma liga
        'amarelos_5j_geral': amarelos_5j,       # últimos 5 jogos gerais
    }
    
    return metricas

# ============================================================================
# BUSCA DE INFORMAÇÕES DOS TIMES
# ============================================================================

@retry_on_failure(max_attempts=2)
def buscar_colocacao_time(team_id, liga_id):
    """Busca colocação atual do time no campeonato"""
    try:
        # Busca temporada atual
        url_tournament = f"{BASE_URL}/unique-tournament/{liga_id}/seasons"
        seasons_data = fazer_requisicao_com_retry(url_tournament, timeout=TIMEOUT_PADRAO)
        
        seasons = seasons_data.get('seasons', [])
        if not seasons:
            return None
        
        season_id = seasons[0].get('id')
        
        # Busca tabela de classificação
        url_standings = f"{BASE_URL}/unique-tournament/{liga_id}/season/{season_id}/standings/total"
        standings_data = fazer_requisicao_com_retry(url_standings, timeout=TIMEOUT_PADRAO)
        
        standings = standings_data.get('standings', [])
        if not standings:
            return None
        
        # Procura o time na tabela
        for standing_group in standings:
            rows = standing_group.get('rows', [])
            for row in rows:
                team = row.get('team', {})
                if team.get('id') == team_id:
                    return {
                        'posicao': row.get('position', 0),
                        'pontos': row.get('points', 0),
                        'jogos': row.get('matches', 0),
                        'vitorias': row.get('wins', 0),
                        'empates': row.get('draws', 0),
                        'derrotas': row.get('losses', 0),
                        'gols_pro': row.get('scoresFor', 0),
                        'gols_contra': row.get('scoresAgainst', 0),
                        'saldo_gols': row.get('scoresFor', 0) - row.get('scoresAgainst', 0),
                    }
        
        return None
        
    except Exception:
        return None

# ============================================================================
# v1.1: PRÓXIMOS JOGOS COM COLOCAÇÃO + COMPETIÇÃO
# ============================================================================

@retry_on_failure(max_attempts=2)
def buscar_proximos_jogos(team_id, quantidade=3, data_alvo=None):
    """
    v1.4: Busca os próximos jogos do time APÓS a data_alvo.
    Se data_alvo for no passado, busca jogos que aconteceram após essa data
    (podem ser jogos já finalizados ou futuros).
    """
    try:
        # Define a data limite (fim do dia alvo)
        if data_alvo:
            if isinstance(data_alvo, str):
                data_limite = datetime.strptime(data_alvo, '%d/%m/%Y')
            else:
                data_limite = data_alvo
            # Usa o fim do dia como limite
            data_limite = data_limite.replace(hour=23, minute=59, second=59, microsecond=999999)
            timestamp_limite = data_limite.timestamp()
        else:
            timestamp_limite = datetime.now().timestamp()
        
        todos_eventos = []
        
        # Busca eventos futuros
        try:
            url_next = f"{BASE_URL}/team/{team_id}/events/next/0"
            data_next = fazer_requisicao_com_retry(url_next, timeout=TIMEOUT_PADRAO)
            if data_next and 'events' in data_next:
                todos_eventos.extend(data_next['events'])
        except:
            pass
        
        # Se data_alvo é no passado, também busca eventos passados
        # (pois os "próximos" jogos em relação a data_alvo podem já ter acontecido)
        data_hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        if timestamp_limite < data_hoje.timestamp():
            try:
                url_last = f"{BASE_URL}/team/{team_id}/events/last/0"
                data_last = fazer_requisicao_com_retry(url_last, timeout=TIMEOUT_PADRAO)
                if data_last and 'events' in data_last:
                    todos_eventos.extend(data_last['events'])
            except:
                pass
        
        if not todos_eventos:
            return []
        
        # Filtra apenas jogos APÓS a data_alvo
        eventos_futuros = [
            e for e in todos_eventos 
            if e.get('startTimestamp', 0) > timestamp_limite
        ]
        
        # Remove duplicados (mesmo evento pode aparecer em next e last)
        eventos_unicos = {}
        for e in eventos_futuros:
            event_id = e.get('id')
            if event_id and event_id not in eventos_unicos:
                eventos_unicos[event_id] = e
        
        # Ordena por data (mais próximos primeiro)
        eventos_ordenados = sorted(
            eventos_unicos.values(),
            key=lambda x: x.get('startTimestamp', 0)
        )
        
        proximos_jogos = []
        
        for evento in eventos_ordenados[:quantidade]:
            try:
                home_team = evento.get('homeTeam', {})
                away_team = evento.get('awayTeam', {})
                tournament = evento.get('tournament', {})
                unique_tournament = tournament.get('uniqueTournament', {})
                
                eh_casa = (home_team.get('id') == team_id)
                adversario = away_team.get('name') if eh_casa else home_team.get('name')
                adversario_id = away_team.get('id') if eh_casa else home_team.get('id')
                local = '🏠' if eh_casa else '✈️'
                
                timestamp = evento.get('startTimestamp', 0)
                data_formatada = datetime.fromtimestamp(timestamp).strftime('%d/%m - %H:%M')
                
                # Nome do campeonato
                campeonato = unique_tournament.get('name', tournament.get('name', ''))
                liga_id = unique_tournament.get('id')
                
                # Fase do campeonato
                round_info = evento.get('roundInfo', {})
                fase = round_info.get('name', '')
                round_num = round_info.get('round', '')
                
                # Simplifica fases
                if fase:
                    fase_lower = fase.lower()
                    if 'grupo' in fase_lower or 'group' in fase_lower:
                        fase = 'Grupos'
                    elif 'final' in fase_lower and 'semi' not in fase_lower and 'quarter' not in fase_lower:
                        fase = 'Final'
                    elif 'semi' in fase_lower:
                        fase = 'Semi'
                    elif 'quarter' in fase_lower or 'quartas' in fase_lower:
                        fase = 'Quartas'
                elif round_num:
                    fase = f'R{round_num}'
                
                # Busca colocação do adversário
                colocacao_adversario = None
                if liga_id and adversario_id:
                    try:
                        colocacao_adversario = buscar_colocacao_time(adversario_id, liga_id)
                    except:
                        pass
                
                proximos_jogos.append({
                    'adversario': adversario,
                    'data': data_formatada,
                    'campeonato': campeonato,
                    'local': local,
                    'fase': fase,
                    'colocacao_adversario': colocacao_adversario,
                })
                
            except Exception:
                continue
        
        return proximos_jogos
        
    except Exception:
        return []

@retry_on_failure(max_attempts=2)
def buscar_ultimos_jogos_time(team_id, quantidade=5, data_alvo=None):
    """
    Busca últimos jogos do time ANTES da data_alvo com estatísticas de faltas e amarelos.
    Se data_alvo não for informada, usa a data atual.
    """
    try:
        url = f"{BASE_URL}/team/{team_id}/events/last/0"
        data = fazer_requisicao_com_retry(url, timeout=TIMEOUT_PADRAO)
        
        eventos = data.get('events', [])
        if not eventos:
            return None
        
        # Define a data limite (meia-noite do dia alvo)
        if data_alvo:
            if isinstance(data_alvo, str):
                data_limite = datetime.strptime(data_alvo, '%d/%m/%Y')
            else:
                data_limite = data_alvo
            # Usa o início do dia como limite
            data_limite = data_limite.replace(hour=0, minute=0, second=0, microsecond=0)
            timestamp_limite = data_limite.timestamp()
        else:
            timestamp_limite = datetime.now().timestamp()
        
        # Filtra apenas jogos ANTERIORES à data_alvo
        eventos_filtrados = [
            e for e in eventos 
            if e.get('startTimestamp', 0) < timestamp_limite
        ]
        
        # Ordena por data (mais recentes primeiro)
        eventos_ordenados = sorted(
            eventos_filtrados,
            key=lambda x: x.get('startTimestamp', 0),
            reverse=True
        )
        
        jogos = []
        
        for evento in eventos_ordenados[:quantidade]:
            try:
                home_team = evento.get('homeTeam', {})
                away_team = evento.get('awayTeam', {})
                home_score = evento.get('homeScore', {})
                away_score = evento.get('awayScore', {})
                
                eh_casa = (home_team.get('id') == team_id)
                event_id = evento.get('id')
                
                adversario = away_team.get('name') if eh_casa else home_team.get('name')
                
                gols_feitos = home_score.get('current', 0) if eh_casa else away_score.get('current', 0)
                gols_sofridos = away_score.get('current', 0) if eh_casa else home_score.get('current', 0)
                
                # Busca estatísticas
                # Faltas
                keywords_faltas = ["fouls", "fouls committed", "faltas"]
                flt = _buscar_stats_evento_por_periodo(event_id, keywords_faltas)
                
                faltas_feitas_1t = flt["1ST"]["home"] if eh_casa else flt["1ST"]["away"]
                faltas_sofridas_1t = flt["1ST"]["away"] if eh_casa else flt["1ST"]["home"]
                faltas_feitas_2t = flt["2ND"]["home"] if eh_casa else flt["2ND"]["away"]
                faltas_sofridas_2t = flt["2ND"]["away"] if eh_casa else flt["2ND"]["home"]
                faltas_feitas_total = flt["ALL"]["home"] if eh_casa else flt["ALL"]["away"]
                faltas_sofridas_total = flt["ALL"]["away"] if eh_casa else flt["ALL"]["home"]
                
                # Se só tem total, distribui
                if faltas_feitas_1t == 0 and faltas_feitas_2t == 0 and faltas_feitas_total > 0:
                    faltas_feitas_1t = None
                    faltas_feitas_2t = None
                
                # Amarelos
                cart = _buscar_stats_evento_por_periodo(event_id, ["yellow card", "yellow cards"])
                
                amarelos_feitos_1t = cart["1ST"]["home"] if eh_casa else cart["1ST"]["away"]
                amarelos_sofridos_1t = cart["1ST"]["away"] if eh_casa else cart["1ST"]["home"]
                amarelos_feitos_2t = cart["2ND"]["home"] if eh_casa else cart["2ND"]["away"]
                amarelos_sofridos_2t = cart["2ND"]["away"] if eh_casa else cart["2ND"]["home"]
                amarelos_feitos_total = cart["ALL"]["home"] if eh_casa else cart["ALL"]["away"]
                amarelos_sofridos_total = cart["ALL"]["away"] if eh_casa else cart["ALL"]["home"]
                
                if amarelos_feitos_total == 0:
                    amarelos_feitos_total = amarelos_feitos_1t + amarelos_feitos_2t
                if amarelos_sofridos_total == 0:
                    amarelos_sofridos_total = amarelos_sofridos_1t + amarelos_sofridos_2t
                
                jogo_info = {
                    'adversario': adversario,
                    'eh_casa': eh_casa,
                    'placar': f"{gols_feitos}-{gols_sofridos}",
                    'faltas_feitas_1t': faltas_feitas_1t,
                    'faltas_sofridas_1t': faltas_sofridas_1t,
                    'faltas_feitas_2t': faltas_feitas_2t,
                    'faltas_sofridas_2t': faltas_sofridas_2t,
                    'faltas_feitas_total': faltas_feitas_total if faltas_feitas_total > 0 else (faltas_feitas_1t or 0) + (faltas_feitas_2t or 0),
                    'faltas_sofridas_total': faltas_sofridas_total if faltas_sofridas_total > 0 else (faltas_sofridas_1t or 0) + (faltas_sofridas_2t or 0),
                    'amarelos_feitos_1t': amarelos_feitos_1t,
                    'amarelos_sofridos_1t': amarelos_sofridos_1t,
                    'amarelos_feitos_2t': amarelos_feitos_2t,
                    'amarelos_sofridos_2t': amarelos_sofridos_2t,
                    'amarelos_feitos_total': amarelos_feitos_total,
                    'amarelos_sofridos_total': amarelos_sofridos_total,
                }
                
                jogos.append(jogo_info)
                time.sleep(0.3)
                
            except Exception:
                continue
        
        # Calcula médias
        if jogos:
            total_faltas_feitas = sum(j['faltas_feitas_total'] for j in jogos)
            total_faltas_sofridas = sum(j['faltas_sofridas_total'] for j in jogos)
            total_amarelos_feitos = sum(j['amarelos_feitos_total'] for j in jogos)
            total_amarelos_sofridos = sum(j['amarelos_sofridos_total'] for j in jogos)
            
            return {
                'jogos': jogos,
                'media_faltas_feitas': round(total_faltas_feitas / len(jogos), 1),
                'media_faltas_sofridas': round(total_faltas_sofridas / len(jogos), 1),
                'media_amarelos_feitos': round(total_amarelos_feitos / len(jogos), 1),
                'media_amarelos_sofridos': round(total_amarelos_sofridos / len(jogos), 1),
            }
        
        return None
        
    except Exception:
        return None

# ============================================================================
# GERAÇÃO DO HTML
# ============================================================================

def gerar_html_unificado(analises, timestamp, data_jogos):
    """Gera o relatório HTML unificado"""
    
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RefStats - Jogos do Dia {data_jogos}</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            padding: 20px;
            padding-top: 100px;
            min-height: 100vh;
            color: #e0e0e0;
        }}
        
        /* ========================================
           NAVBAR (igual ao Home)
           ======================================== */
        .navbar {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            z-index: 9997;
            background-image:
                linear-gradient(
                    rgba(10, 15, 30, 0.85),
                    rgba(10, 15, 30, 0.85)
                ),
                url("./assets/img/FundoMuroFundo.png");
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
            padding: 15px 50px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.6);
            border-bottom: 2px solid #e94560;
            backdrop-filter: blur(2px);
        }}
        
        .navbar-brand {{
            display: flex;
            align-items: center;
            gap: 12px;
            text-decoration: none;
        }}
        
        .logo-img {{
            height: 48px;
            width: auto;
            display: block;
        }}
        
        .navbar-brand .brand-text {{
            font-size: 1.8em;
            font-weight: bold;
            color: #e94560;
        }}
        
        .navbar-brand .brand-text span {{
            color: #3498db;
        }}
        
        .navbar-menu {{
            display: flex;
            gap: 10px;
        }}
        
        .navbar-menu a {{
            color: #e0e0e0;
            text-decoration: none;
            padding: 10px 20px;
            border-radius: 25px;
            transition: all 0.3s;
            font-weight: 500;
            border: 1px solid transparent;
        }}
        
        .navbar-menu a:hover {{
            background: rgba(233, 69, 96, 0.2);
            border-color: #e94560;
            color: #e94560;
        }}
        
        .navbar-menu a.active {{
            background: linear-gradient(135deg, #e94560 0%, #0f3460 100%);
            color: white;
        }}
        
        .menu-toggle {{
            display: none;
            background: none;
            border: none;
            color: #e0e0e0;
            font-size: 1.5em;
            cursor: pointer;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            width: 100%;
        }}
        
        .header {{
            background: linear-gradient(135deg, #0f3460 0%, #1a1a2e 100%);
            padding: 30px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            margin-bottom: 30px;
            text-align: center;
            border: 1px solid #e94560;
        }}
        
        .header h1 {{
            color: #e94560;
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
        
        .header p {{
            color: #a0a0a0;
            font-size: 1.1em;
        }}
        
        .jogo-card {{
            background: linear-gradient(135deg, #16213e 0%, #1a1a2e 100%);
            padding: 0;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            margin-bottom: 30px;
            border: 1px solid #0f3460;
            overflow: hidden;
            width: 100%;
            box-sizing: border-box;
        }}
        
        .jogo-header {{
            background: linear-gradient(135deg, #e94560 0%, #0f3460 100%);
            padding: 25px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .jogo-titulo {{
            font-size: 1.8em;
            color: white;
            font-weight: bold;
        }}
        
        .jogo-data {{
            text-align: right;
            color: white;
        }}
        
        .jogo-data .horario {{
            font-size: 1.5em;
            font-weight: bold;
        }}
        
        .jogo-data .data {{
            font-size: 1em;
            opacity: 0.9;
        }}
        
        .jogo-info-bar {{
            background: #0f3460;
            padding: 15px 30px;
            display: flex;
            gap: 25px;
            flex-wrap: wrap;
            font-size: 0.95em;
            color: #c0c0c0;
        }}
        
        .jogo-info-bar span {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        
        .jogo-info-bar .info-label {{
            color: #a0a0a0;
            font-size: 0.85em;
        }}
        
        .jogo-info-bar .info-value {{
            color: white;
            font-weight: 500;
        }}
        
        .jogo-content {{
            padding: 30px;
            width: 100%;
            box-sizing: border-box;
            display: block;
        }}
        
        /* Seções */
        .secao {{
            margin-bottom: 30px;
            width: 100%;
            box-sizing: border-box;
            display: flex;
            flex-direction: column;
            align-items: stretch;
        }}
        
        .secao-titulo {{
            font-size: 1.4em;
            color: #e94560;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #e94560;
            display: flex;
            align-items: center;
            gap: 10px;
            width: 100%;
            box-sizing: border-box;
        }}
        
        /* Tooltips */
        .tooltip {{
            position: relative;
            display: inline-flex;
            align-items: center;
            cursor: help;
        }}
        
        .tooltip .tooltip-icon {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 16px;
            height: 16px;
            background: #3498db;
            color: white;
            border-radius: 50%;
            font-size: 10px;
            font-weight: bold;
            margin-left: 5px;
            font-style: normal;
        }}
        
        .tooltip .tooltip-text {{
            visibility: hidden;
            width: 280px;
            background-color: #1a1a2e;
            color: #e0e0e0;
            text-align: left;
            border-radius: 8px;
            padding: 12px;
            position: absolute;
            z-index: 1000;
            bottom: 125%;
            left: 50%;
            margin-left: -140px;
            opacity: 0;
            transition: opacity 0.3s;
            font-size: 0.85em;
            line-height: 1.5;
            border: 1px solid #3498db;
            box-shadow: 0 5px 15px rgba(0,0,0,0.4);
        }}
        
        .tooltip .tooltip-text::after {{
            content: "";
            position: absolute;
            top: 100%;
            left: 50%;
            margin-left: -5px;
            border-width: 5px;
            border-style: solid;
            border-color: #3498db transparent transparent transparent;
        }}
        
        .tooltip:hover .tooltip-text {{
            visibility: visible;
            opacity: 1;
        }}
        
        /* Árbitro */
        .arbitro-card {{
            background: #0f3460;
            padding: 25px;
            border-radius: 12px;
            margin-bottom: 20px;
            width: 100%;
            box-sizing: border-box;
        }}
        
        .arbitro-nome {{
            font-size: 1.5em;
            color: white;
            font-weight: bold;
            margin-bottom: 5px;
        }}
        
        .arbitro-pais {{
            color: #a0a0a0;
            font-size: 1.1em;
            margin-bottom: 15px;
        }}
        
        .badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: 600;
            margin-left: 10px;
        }}
        
        .badge-liga {{
            background: #e94560;
            color: white;
        }}
        
        .badge-copa {{
            background: #f39c12;
            color: #1a1a2e;
        }}
        
        /* Métricas Grid */
        .metricas-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 15px;
            margin-top: 20px;
            width: 100%;
            box-sizing: border-box;
        }}
        
        .metrica-card {{
            background: #1a1a2e;
            padding: 15px;
            border-radius: 10px;
            text-align: center;
            border: 1px solid #0f3460;
            position: relative;
        }}
        
        .metrica-card .valor {{
            font-size: 1.8em;
            font-weight: bold;
            color: #e94560;
        }}
        
        .metrica-card .label {{
            font-size: 0.85em;
            color: #a0a0a0;
            margin-top: 5px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 5px;
        }}
        
        /* Perfil do Árbitro - MELHORADO v1.1 */
        .perfil-section {{
            background: linear-gradient(135deg, #1a1a2e 0%, #0f3460 100%);
            border-radius: 12px;
            padding: 20px;
            margin-top: 20px;
            border: 1px solid #3498db;
            width: 100%;
            box-sizing: border-box;
        }}
        
        .perfil-header {{
            display: flex;
            align-items: center;
            gap: 15px;
            margin-bottom: 15px;
        }}
        
        .perfil-titulo {{
            color: #3498db;
            font-size: 1.1em;
            font-weight: 600;
        }}
        
        .perfil-badges {{
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            align-items: center;
        }}
        
        .perfil-badge {{
            padding: 10px 20px;
            border-radius: 25px;
            font-weight: 600;
            font-size: 1em;
            display: flex;
            align-items: center;
            gap: 8px;
            /* Cor padrão caso a classe específica não seja aplicada */
            background: linear-gradient(135deg, #3498db 0%, #2980b9 100%);
            color: white;
            box-shadow: 0 4px 15px rgba(52, 152, 219, 0.4);
        }}
        
        .perfil-rigoroso {{
            background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
            color: white;
            box-shadow: 0 4px 15px rgba(231, 76, 60, 0.4);
        }}
        
        .perfil-medio {{
            background: linear-gradient(135deg, #f39c12 0%, #d68910 100%);
            color: #1a1a2e;
            box-shadow: 0 4px 15px rgba(243, 156, 18, 0.4);
        }}
        
        .perfil-permissivo {{
            background: linear-gradient(135deg, #27ae60 0%, #1e8449 100%);
            color: white;
            box-shadow: 0 4px 15px rgba(39, 174, 96, 0.4);
        }}
        
        .perfil-pipoqueiro {{
            background: linear-gradient(135deg, #9b59b6 0%, #7d3c98 100%);
            color: white;
            box-shadow: 0 4px 15px rgba(155, 89, 182, 0.4);
        }}
        
        .perfil-descricao {{
            color: #a0a0a0;
            font-size: 0.9em;
            margin-top: 10px;
            padding-top: 10px;
            border-top: 1px solid #0f3460;
        }}
        
        /* Tendências */
        .tendencias {{
            background: #1a1a2e;
            padding: 15px;
            border-radius: 10px;
            margin-top: 15px;
            border-left: 4px solid #e94560;
            width: 100%;
            box-sizing: border-box;
        }}
        
        .tendencia-item {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 0;
            border-bottom: 1px solid #0f3460;
        }}
        
        .tendencia-item:last-child {{
            border-bottom: none;
        }}
        
        /* Baseline */
        .baseline-section {{
            background: #1a1a2e;
            padding: 15px;
            border-radius: 10px;
            margin-top: 15px;
            width: 100%;
            box-sizing: border-box;
        }}
        
        .baseline-titulo {{
            color: #a0a0a0;
            font-size: 0.9em;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        
        .baseline-valores {{
            display: flex;
            gap: 30px;
            flex-wrap: wrap;
        }}
        
        .baseline-item {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        
        .baseline-item .valor {{
            font-size: 1.2em;
            font-weight: bold;
            color: #3498db;
        }}
        
        /* Notícias */
        .noticias-lista {{
            display: flex;
            flex-direction: column;
            gap: 15px;
            width: 100%;
            box-sizing: border-box;
        }}
        
        .noticia-card {{
            background: #1a1a2e;
            padding: 15px;
            border-radius: 10px;
            border-left: 4px solid #3498db;
            width: 100%;
            box-sizing: border-box;
        }}
        
        .noticia-titulo {{
            color: white;
            font-weight: 600;
            margin-bottom: 8px;
            font-size: 1em;
        }}
        
        .noticia-meta {{
            display: flex;
            gap: 15px;
            font-size: 0.85em;
            color: #a0a0a0;
            margin-bottom: 8px;
        }}
        
        .noticia-resumo {{
            font-size: 0.9em;
            color: #c0c0c0;
            margin-bottom: 10px;
        }}
        
        .noticia-link {{
            color: #e94560;
            text-decoration: none;
            font-size: 0.9em;
        }}
        
        .noticia-link:hover {{
            text-decoration: underline;
        }}
        
        .sem-noticias {{
            background: #1a1a2e;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            color: #a0a0a0;
            width: 100%;
            box-sizing: border-box;
        }}
        
        /* Container para scroll horizontal em tabelas (mobile) */
        .tabela-scroll {{
            width: 100%;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
            margin-top: 15px;
            border-radius: 10px;
        }}
        
        .tabela-scroll::-webkit-scrollbar {{
            height: 8px;
        }}
        
        .tabela-scroll::-webkit-scrollbar-track {{
            background: #1a1a2e;
            border-radius: 4px;
        }}
        
        .tabela-scroll::-webkit-scrollbar-thumb {{
            background: #e94560;
            border-radius: 4px;
        }}
        
        /* Tabelas */
        .tabela {{
            width: 100%;
            min-width: 700px;
            border-collapse: collapse;
            background: #1a1a2e;
            border-radius: 10px;
            overflow: hidden;
        }}
        
        .tabela thead {{
            background: linear-gradient(135deg, #e94560 0%, #0f3460 100%);
        }}
        
        .tabela th {{
            padding: 12px 15px;
            text-align: left;
            color: white;
            font-weight: 600;
            font-size: 0.9em;
            white-space: nowrap;
        }}
        
        .tabela td {{
            padding: 10px 15px;
            border-bottom: 1px solid #0f3460;
            font-size: 0.9em;
            white-space: nowrap;
        }}
        
        .tabela tbody tr:hover {{
            background: #0f3460;
        }}
        
        .tabela tbody tr:last-child td {{
            border-bottom: none;
        }}
        
        .stat-amarelo {{
            background: #f6e05e;
            color: #1a1a2e;
            padding: 2px 8px;
            border-radius: 4px;
            font-weight: bold;
        }}
        
        .stat-vermelho {{
            background: #fc8181;
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-weight: bold;
        }}
        
        /* Times Section */
        .times-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 25px;
            width: 100%;
            box-sizing: border-box;
        }}
        
        @media (max-width: 900px) {{
            .times-grid {{
                grid-template-columns: 1fr;
            }}
        }}
        
        .time-card {{
            background: #0f3460;
            border-radius: 12px;
            overflow: hidden;
            width: 100%;
            box-sizing: border-box;
        }}
        
        .time-header {{
            background: linear-gradient(135deg, #e94560 0%, #0f3460 100%);
            padding: 15px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .time-nome {{
            font-size: 1.3em;
            font-weight: bold;
            color: white;
        }}
        
        .time-posicao {{
            background: white;
            color: #e94560;
            padding: 8px 15px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 1.1em;
        }}
        
        .time-content {{
            padding: 20px;
            width: 100%;
            box-sizing: border-box;
        }}
        
        .proximos-jogos {{
            margin-bottom: 20px;
            width: 100%;
            box-sizing: border-box;
        }}
        
        .proximos-jogos h5 {{
            color: #a0a0a0;
            margin-bottom: 10px;
            font-size: 0.9em;
        }}
        
        .proximo-jogo {{
            background: #1a1a2e;
            padding: 12px 15px;
            border-radius: 8px;
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.9em;
            flex-wrap: wrap;
            gap: 8px;
        }}
        
        .proximo-jogo .local {{
            font-size: 1.2em;
        }}
        
        .proximo-jogo .adversario-info {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        
        .proximo-jogo .adversario-pos {{
            background: #e94560;
            color: white;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.8em;
            font-weight: bold;
        }}
        
        .proximo-jogo .campeonato {{
            color: #3498db;
            font-size: 0.85em;
        }}
        
        .medias-time {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
            margin-bottom: 20px;
            width: 100%;
            box-sizing: border-box;
        }}
        
        .media-item {{
            background: #1a1a2e;
            padding: 12px;
            border-radius: 8px;
            text-align: center;
        }}
        
        .media-item .valor {{
            font-size: 1.4em;
            font-weight: bold;
            color: #e94560;
        }}
        
        .media-item .label {{
            font-size: 0.75em;
            color: #a0a0a0;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 4px;
        }}
        
        .tabela-titulo {{
            display: flex;
            align-items: center;
            gap: 8px;
            color: #a0a0a0;
            margin: 15px 0 10px 0;
            font-size: 0.9em;
            width: 100%;
            box-sizing: border-box;
        }}
        
        .tabela-time {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.85em;
        }}
        
        .tabela-time th {{
            background: #1a1a2e;
            padding: 10px;
            text-align: center;
            color: #a0a0a0;
            font-weight: 600;
        }}
        
        .tabela-time td {{
            padding: 8px 10px;
            text-align: center;
            border-bottom: 1px solid #0f3460;
        }}
        
        /* Gráfico Comparativo de Amarelos */
        .grafico-comparativo {{
            background: #1a1a2e;
            border-radius: 10px;
            padding: 20px;
            border: 1px solid #0f3460;
        }}
        
        .grafico-container {{
            position: relative;
            height: 280px;
            width: 100%;
        }}
        
        .grafico-legenda {{
            display: flex;
            justify-content: center;
            gap: 20px;
            margin-top: 15px;
            flex-wrap: wrap;
        }}
        
        .legenda-item {{
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 0.9em;
        }}
        
        .legenda-cor {{
            width: 20px;
            height: 4px;
            border-radius: 2px;
        }}
        
        /* Card de Doação */
        .donation-section {{
            background: linear-gradient(135deg, #16213e 0%, #1a1a2e 100%);
            border-radius: 15px;
            padding: 35px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            border: 1px solid #0f3460;
            margin-top: 30px;
        }}
        
        .donation-section h2 {{
            color: #e94560;
            font-size: 1.6em;
            text-align: center;
            margin-bottom: 8px;
        }}
        
        .donation-section > p {{
            color: #a0a0a0;
            text-align: center;
            margin-bottom: 25px;
        }}
        
        .donation-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
        }}
        
        .donation-card {{
            background: rgba(15, 52, 96, 0.5);
            padding: 20px;
            border-radius: 12px;
            text-align: center;
            border: 1px solid #3498db;
        }}
        
        .donation-card h4 {{
            color: #3498db;
            font-size: 1.1em;
            margin-bottom: 8px;
        }}
        
        .donation-card p {{
            color: #a0a0a0;
            margin-bottom: 12px;
            font-size: 0.9em;
        }}
        
        .pix-key {{
            background: #1a1a2e;
            padding: 12px 15px;
            border-radius: 8px;
            font-family: monospace;
            color: #2ecc71;
            cursor: pointer;
            transition: all 0.3s;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            border: 1px solid #2ecc71;
            font-size: 0.9em;
        }}
        
        .pix-key:hover {{
            background: rgba(46, 204, 113, 0.1);
        }}
        
        .paypal-btn {{
            display: inline-block;
            background: #0070ba;
            color: white;
            text-decoration: none;
            padding: 12px 25px;
            border-radius: 25px;
            font-weight: 500;
            transition: all 0.3s;
        }}
        
        .paypal-btn:hover {{
            background: #005ea6;
            transform: scale(1.05);
        }}
        
        .donation-info {{
            background: rgba(52, 152, 219, 0.1);
            border-left: 4px solid #f1c40f;
            padding: 15px 20px;
            margin-top: 20px;
            border-radius: 0 10px 10px 0;
        }}
        
        .donation-info h4 {{
            color: #f1c40f;
            margin-bottom: 8px;
            font-size: 1em;
        }}
        
        .donation-info p {{
            color: #c0c0c0;
            line-height: 1.6;
            font-size: 0.9em;
            margin: 0;
        }}
        
        /* Footer */
        .footer {{
            background: linear-gradient(135deg, #0f3460 0%, #1a1a2e 100%);
            padding: 20px;
            border-radius: 15px;
            text-align: center;
            margin-top: 30px;
            color: #a0a0a0;
            border: 1px solid #0f3460;
        }}
        
        .footer strong {{
            color: #e94560;
        }}
        
        /* ========================================
           BARRA DE PESQUISA ESTILO CTRL+F v1.4
           ======================================== */
        .search-bar {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            z-index: 9999;
            background: linear-gradient(135deg, #1a1a2e 0%, #0f3460 100%);
            padding: 12px 20px;
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 12px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
            border-bottom: 2px solid #e94560;
            transform: translateY(-100%);
            transition: transform 0.3s ease;
            pointer-events: none;
        }}
        
        .search-bar.active {{
            transform: translateY(0);
            pointer-events: auto;
        }}
        
        body.search-active {{
            padding-top: 70px;
        }}
        
        .search-container {{
            display: flex;
            align-items: center;
            gap: 8px;
            background: #16213e;
            border-radius: 25px;
            padding: 6px 15px;
            border: 1px solid #3498db;
            max-width: 400px;
            flex: 1;
        }}
        
        .search-container:focus-within {{
            border-color: #e94560;
            box-shadow: 0 0 10px rgba(233, 69, 96, 0.3);
        }}
        
        .search-icon {{
            color: #a0a0a0;
            font-size: 16px;
        }}
        
        .search-input {{
            flex: 1;
            background: transparent;
            border: none;
            outline: none;
            color: white;
            font-size: 14px;
            padding: 8px 0;
        }}
        
        .search-input::placeholder {{
            color: #606060;
        }}
        
        .search-counter {{
            color: #a0a0a0;
            font-size: 13px;
            min-width: 60px;
            text-align: center;
            white-space: nowrap;
        }}
        
        .search-nav {{
            display: flex;
            gap: 4px;
        }}
        
        .search-nav button {{
            background: #0f3460;
            border: 1px solid #3498db;
            color: white;
            width: 32px;
            height: 32px;
            border-radius: 50%;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s;
            font-size: 14px;
        }}
        
        .search-nav button:hover:not(:disabled) {{
            background: #e94560;
            border-color: #e94560;
            transform: scale(1.1);
        }}
        
        .search-nav button:disabled {{
            opacity: 0.3;
            cursor: not-allowed;
        }}
        
        .search-close {{
            background: transparent;
            border: none;
            color: #a0a0a0;
            cursor: pointer;
            font-size: 20px;
            padding: 5px;
            transition: color 0.2s;
            margin-left: 5px;
        }}
        
        .search-close:hover {{
            color: #e94560;
        }}
        
        .search-toggle {{
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 9998;
            background: linear-gradient(135deg, #e94560 0%, #0f3460 100%);
            border: none;
            color: white;
            width: 50px;
            height: 50px;
            border-radius: 50%;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 4px 15px rgba(233, 69, 96, 0.4);
            transition: all 0.3s;
            font-size: 20px;
        }}
        
        .search-toggle:hover {{
            transform: scale(1.1);
            box-shadow: 0 6px 25px rgba(233, 69, 96, 0.6);
        }}
        
        .search-toggle.hidden {{
            opacity: 0;
            pointer-events: none;
        }}
        
        /* Highlight dos resultados */
        .search-highlight {{
            background: linear-gradient(135deg, #f6e05e 0%, #ecc94b 100%);
            color: #1a1a2e;
            padding: 2px 4px;
            border-radius: 3px;
            font-weight: bold;
            box-shadow: 0 2px 8px rgba(246, 224, 94, 0.4);
        }}
        
        .search-highlight.current {{
            background: linear-gradient(135deg, #e94560 0%, #ff6b6b 100%);
            color: white;
            box-shadow: 0 2px 12px rgba(233, 69, 96, 0.6);
            animation: pulse 1s infinite;
        }}
        
        @keyframes pulse {{
            0%, 100% {{ box-shadow: 0 2px 12px rgba(233, 69, 96, 0.6); }}
            50% {{ box-shadow: 0 2px 20px rgba(233, 69, 96, 0.9); }}
        }}
        
        /* Filtros de Perfil do Árbitro */
        .filter-container {{
            display: flex;
            align-items: center;
            gap: 6px;
            margin-left: 10px;
            padding-left: 10px;
            border-left: 1px solid #3498db;
        }}
        
        .filter-label {{
            color: #a0a0a0;
            font-size: 12px;
            margin-right: 4px;
        }}
        
        .filter-btn {{
            padding: 4px 10px;
            border: 1px solid #3498db;
            background: transparent;
            color: #a0a0a0;
            border-radius: 15px;
            cursor: pointer;
            font-size: 11px;
            transition: all 0.2s;
            white-space: nowrap;
        }}
        
        .filter-btn:hover {{
            background: rgba(52, 152, 219, 0.2);
            color: #e0e0e0;
        }}
        
        .filter-btn.active {{
            background: #3498db;
            color: white;
            border-color: #3498db;
        }}
        
        .filter-btn.rigoroso.active {{
            background: #e94560;
            border-color: #e94560;
        }}
        
        .filter-btn.medio.active {{
            background: #f6e05e;
            border-color: #f6e05e;
            color: #1a1a2e;
        }}
        
        .filter-btn.permissivo.active {{
            background: #2ecc71;
            border-color: #2ecc71;
        }}
        
        .filter-clear {{
            padding: 4px 8px;
            border: none;
            background: transparent;
            color: #e94560;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.2s;
        }}
        
        .filter-clear:hover {{
            color: #ff6b6b;
            transform: scale(1.1);
        }}
        
        .filter-clear.hidden {{
            display: none;
        }}
        
        /* Card oculto pelo filtro */
        .jogo-card.filtered-out {{
            display: none;
        }}
        
        /* Contador de filtro */
        .filter-counter {{
            color: #a0a0a0;
            font-size: 11px;
            margin-left: 6px;
        }}
        
        /* Responsivo - filtros em tela pequena */
        @media (max-width: 768px) {{
            .navbar {{
                padding: 15px 20px;
            }}
            
            .navbar-menu {{
                position: fixed;
                top: 70px;
                left: 0;
                right: 0;
                background: linear-gradient(135deg, #0f3460 0%, #1a1a2e 100%);
                flex-direction: column;
                padding: 20px;
                gap: 10px;
                transform: translateY(-150%);
                transition: transform 0.3s;
                border-bottom: 2px solid #e94560;
                z-index: 9996;
            }}
            
            .navbar-menu.active {{
                transform: translateY(0);
            }}
            
            .menu-toggle {{
                display: block;
            }}
            
            .logo-img {{
                height: 36px;
            }}
            
            body {{
                padding-top: 90px;
            }}
            
            /* Lupa no canto inferior direito no mobile */
            .search-toggle {{
                top: auto;
                bottom: 20px;
                right: 20px;
            }}
            
            .search-bar {{
                flex-wrap: wrap;
                padding: 10px;
                gap: 8px;
            }}
            
            .filter-container {{
                width: 100%;
                justify-content: center;
                border-left: none;
                padding-left: 0;
                margin-left: 0;
                padding-top: 8px;
                border-top: 1px solid #3498db;
            }}
        }}
        
        /* Tooltip da barra de pesquisa */
        .search-hint {{
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: #1a1a2e;
            color: #a0a0a0;
            padding: 10px 15px;
            border-radius: 8px;
            font-size: 12px;
            border: 1px solid #0f3460;
            opacity: 0;
            transition: opacity 0.3s;
            pointer-events: none;
        }}
        
        .search-hint.visible {{
            opacity: 1;
        }}
        
        .search-hint kbd {{
            background: #0f3460;
            padding: 2px 6px;
            border-radius: 4px;
            font-family: monospace;
            color: #e94560;
        }}
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <!-- Navbar (igual ao Home) -->
    <nav class="navbar">
        <a href="index.html" class="navbar-brand">
            <img src="./assets/img/LogoINICIO.png" alt="RefStats" class="logo-img">
        </a>
        
        <button class="menu-toggle" onclick="document.getElementById('navMenu').classList.toggle('active')" aria-label="Menu">
            ☰
        </button>
        
        <div class="navbar-menu" id="navMenu">
            <a href="index.html">INÍCIO</a>
            <a href="#" class="active">JOGOS DO DIA</a>
            <a href="refstats_historico.html">HISTÓRICO</a>
            <a href="refstats_contato.html">CONTATO</a>
        </div>
    </nav>
    
    <!-- Barra de Pesquisa v1.4 -->
    <div class="search-bar" id="searchBar">
        <div class="search-container">
            <span class="search-icon">🔍</span>
            <input type="text" class="search-input" id="searchInput" placeholder="Pesquisar na página..." autocomplete="off">
            <span class="search-counter" id="searchCounter"></span>
        </div>
        <div class="search-nav">
            <button id="searchPrev" title="Anterior (↑)" disabled>▲</button>
            <button id="searchNext" title="Próximo (↓)" disabled>▼</button>
        </div>
        <div class="filter-container">
            <span class="filter-label">Perfil:</span>
            <button class="filter-btn rigoroso" data-filter="Rigoroso" title="Mostrar árbitros rigorosos">🔴 Rigoroso</button>
            <button class="filter-btn medio" data-filter="Médio" title="Mostrar árbitros médios">🟡 Médio</button>
            <button class="filter-btn permissivo" data-filter="Permissivo" title="Mostrar árbitros permissivos">🟢 Permissivo</button>
            <button class="filter-clear hidden" id="filterClear" title="Limpar filtro">✕</button>
            <span class="filter-counter" id="filterCounter"></span>
        </div>
        <button class="search-close" id="searchClose" title="Fechar (Esc)">✕</button>
    </div>
    
    <!-- Botão flutuante para abrir pesquisa -->
    <button class="search-toggle" id="searchToggle" title="Pesquisar (Ctrl+F)">🔍</button>
    
    <!-- Dica de atalho -->
    <div class="search-hint" id="searchHint">
        Pressione <kbd>Ctrl</kbd> + <kbd>F</kbd> para pesquisar
    </div>
    
    <div class="container">
        <div class="header">
            <h1>⚽ Jogos do Dia</h1>
            <p>📅 {data_jogos} • {len(analises)} partida(s) analisada(s)</p>
        </div>
"""
    
    # Gera card para cada jogo
    for analise in analises:
        partida = analise['partida']
        arbitro = analise.get('arbitro')
        metricas = analise.get('metricas')
        noticias_arbitro = analise.get('noticias_arbitro', [])
        historico = analise.get('historico', [])
        stats_casa = analise.get('stats_casa')
        stats_fora = analise.get('stats_fora')
        colocacao_casa = analise.get('colocacao_casa')
        colocacao_fora = analise.get('colocacao_fora')
        proximos_casa = analise.get('proximos_casa', [])
        proximos_fora = analise.get('proximos_fora', [])
        estadio_info = analise.get('estadio_info')
        
        # Posições para o título
        pos_casa = f" ({colocacao_casa['posicao']}º)" if colocacao_casa else ""
        pos_fora = f" ({colocacao_fora['posicao']}º)" if colocacao_fora else ""
        
        # Info do estádio
        estadio_nome = estadio_info.get('nome', 'Não informado') if estadio_info else 'Não informado'
        estadio_cidade = estadio_info.get('cidade', '') if estadio_info else ''
        estadio_pais = estadio_info.get('pais', '') if estadio_info else ''
        
        # Perfil do árbitro para filtro
        perfil_arbitro = metricas.get('perfil', 'N/A') if metricas else 'N/A'
        
        html += f"""
        <div class="jogo-card" data-perfil="{perfil_arbitro}">
            <div class="jogo-header">
                <div class="jogo-titulo">{partida['time_casa']}{pos_casa} vs {partida['time_fora']}{pos_fora}</div>
                <div class="jogo-data">
                    <div class="horario">{partida['horario']}</div>
                    <div class="data">{partida['data']}</div>
                </div>
            </div>
            
            <div class="jogo-info-bar">
                <span>
                    <span class="info-label">🏆 Competição:</span>
                    <span class="info-value">{partida['liga_nome']}</span>
                </span>
                <span>
                    <span class="info-label">🏟️ Estádio:</span>
                    <span class="info-value">{estadio_nome}</span>
                </span>
                <span>
                    <span class="info-label">📍 Local:</span>
                    <span class="info-value">{estadio_cidade}{', ' + estadio_pais if estadio_pais else ''}</span>
                </span>
                {f'<span><span class="info-label">📋 Fase:</span><span class="info-value">{partida["fase"]}</span></span>' if partida['fase'] else ""}
            </div>
            
            <div class="jogo-content">
"""
        
        # Seção do Árbitro
        html += """
                <div class="secao">
                    <div class="secao-titulo">⚖️ Árbitro</div>
"""
        
        if arbitro:
            # Determina tipo de badge (Liga ou Copa)
            liga_nome_lower = partida['liga_nome'].lower()
            badge_tipo = 'badge-copa' if 'copa' in liga_nome_lower or 'cup' in liga_nome_lower else 'badge-liga'
            badge_texto = 'Copa' if 'copa' in liga_nome_lower or 'cup' in liga_nome_lower else 'Liga'
            
            html += f"""
                    <div class="arbitro-card">
                        <div class="arbitro-nome">
                            {arbitro['nome']}
                            <span class="badge {badge_tipo}">{badge_texto}</span>
                        </div>
                        <div class="arbitro-pais">🌍 {arbitro['pais']}</div>
"""
            
            if metricas:
                # Médias do Árbitro com tooltips
                html += """
                        <div class="metricas-grid">
"""
                html += f"""
                            <div class="metrica-card">
                                <div class="valor">{metricas['media_amarelos_10j']}</div>
                                <div class="label">
                                    📊 Média Amarelos (10j)
                                    <span class="tooltip">
                                        <span class="tooltip-icon">i</span>
                                        <span class="tooltip-text">Média de cartões amarelos por jogo nos últimos 10 jogos apitados pelo árbitro (soma dos dois times).</span>
                                    </span>
                                </div>
                            </div>
                            <div class="metrica-card">
                                <div class="valor">{metricas['media_amarelos_5j']}</div>
                                <div class="label">
                                    📊 Média Amarelos (5j)
                                    <span class="tooltip">
                                        <span class="tooltip-icon">i</span>
                                        <span class="tooltip-text">Média de cartões amarelos por jogo nos últimos 5 jogos apitados. Amostra menor, mas mais recente.</span>
                                    </span>
                                </div>
                            </div>
                            <div class="metrica-card">
                                <div class="valor">{metricas['media_amarelos_1t']}</div>
                                <div class="label">
                                    📊 Média Amarelos 1T
                                    <span class="tooltip">
                                        <span class="tooltip-icon">i</span>
                                        <span class="tooltip-text">Média de cartões amarelos aplicados apenas no 1º tempo (primeiros 45 minutos).</span>
                                    </span>
                                </div>
                            </div>
                            <div class="metrica-card">
                                <div class="valor">{metricas['media_amarelos_2t']}</div>
                                <div class="label">
                                    📊 Média Amarelos 2T
                                    <span class="tooltip">
                                        <span class="tooltip-icon">i</span>
                                        <span class="tooltip-text">Média de cartões amarelos aplicados apenas no 2º tempo (após os 45 minutos).</span>
                                    </span>
                                </div>
                            </div>
                            <div class="metrica-card">
                                <div class="valor">{metricas['media_faltas_10j']}</div>
                                <div class="label">
                                    📊 Média Faltas (10j)
                                    <span class="tooltip">
                                        <span class="tooltip-icon">i</span>
                                        <span class="tooltip-text">Média total de faltas por jogo nos últimos 10 jogos (soma dos dois times).</span>
                                    </span>
                                </div>
                            </div>
                            <div class="metrica-card">
                                <div class="valor">{metricas['media_faltas_5j']}</div>
                                <div class="label">
                                    📊 Média Faltas (5j)
                                    <span class="tooltip">
                                        <span class="tooltip-icon">i</span>
                                        <span class="tooltip-text">Média de faltas nos últimos 5 jogos. Amostra mais recente.</span>
                                    </span>
                                </div>
                            </div>
                            <div class="metrica-card">
                                <div class="valor">{metricas['media_faltas_1t']}</div>
                                <div class="label">
                                    📊 Média Faltas 1T
                                    <span class="tooltip">
                                        <span class="tooltip-icon">i</span>
                                        <span class="tooltip-text">Média de faltas cometidas no 1º tempo.</span>
                                    </span>
                                </div>
                            </div>
                            <div class="metrica-card">
                                <div class="valor">{metricas['media_faltas_2t']}</div>
                                <div class="label">
                                    📊 Média Faltas 2T
                                    <span class="tooltip">
                                        <span class="tooltip-icon">i</span>
                                        <span class="tooltip-text">Média de faltas cometidas no 2º tempo.</span>
                                    </span>
                                </div>
                            </div>
                            <div class="metrica-card">
                                <div class="valor">{metricas['media_vermelhos']}</div>
                                <div class="label">
                                    📊 Média Vermelhos
                                    <span class="tooltip">
                                        <span class="tooltip-icon">i</span>
                                        <span class="tooltip-text">Média de cartões vermelhos por jogo nos últimos 10 jogos.</span>
                                    </span>
                                </div>
                            </div>
                        </div>
"""
                
                # Perfil do Árbitro - MELHORADO
                perfil = metricas['perfil']
                # Mapeamento sem acentos para as classes CSS
                perfil_classes = {
                    'Rigoroso': 'perfil-rigoroso',
                    'Médio': 'perfil-medio',
                    'Permissivo': 'perfil-permissivo'
                }
                perfil_class = perfil_classes.get(perfil, 'perfil-medio')
                
                # Descrições dos perfis
                perfil_descricoes = {
                    'Rigoroso': 'Este árbitro aplica mais de 15% cartões amarelos acima da média da competição. Espere um jogo com mais cartões.',
                    'Médio': 'Este árbitro está na média da competição em termos de cartões amarelos. Comportamento equilibrado.',
                    'Permissivo': 'Este árbitro aplica mais de 15% menos cartões amarelos que a média da competição. Jogo pode ter menos cartões.'
                }
                
                html += f"""
                        <div class="perfil-section">
                            <div class="perfil-header">
                                <span class="perfil-titulo">📋 Perfil do Árbitro</span>
                                <span class="tooltip">
                                    <span class="tooltip-icon">i</span>
                                    <span class="tooltip-text">O perfil é calculado comparando a média de amarelos do árbitro com a média da competição (baseline). Rigoroso: +15% acima da média. Permissivo: -15% abaixo da média.</span>
                                </span>
                            </div>
                            <div class="perfil-badges">
                                <span class="perfil-badge {perfil_class}">
                                    {'🔴' if perfil == 'Rigoroso' else '🟡' if perfil == 'Médio' else '🟢'} {perfil}
                                </span>
"""
                if metricas.get('pipoqueiro_1t'):
                    html += """
                                <span class="perfil-badge perfil-pipoqueiro">
                                    🍿 Pipoqueiro 1T
                                    <span class="tooltip">
                                        <span class="tooltip-icon">i</span>
                                        <span class="tooltip-text">Mais de 50% dos cartões amarelos são aplicados no 1º tempo. Bom para apostas de cartões no 1T.</span>
                                    </span>
                                </span>
"""
                html += f"""
                            </div>
                            <div class="perfil-descricao">{perfil_descricoes.get(perfil, '')}</div>
                        </div>
"""
                
                # Baseline da Liga
                baseline = metricas.get('baseline')
                if baseline:
                    html += f"""
                        <div class="baseline-section">
                            <div class="baseline-titulo">
                                📈 Baseline da Competição ({baseline.get('liga', partida['liga_nome'])})
                                <span class="tooltip">
                                    <span class="tooltip-icon">i</span>
                                    <span class="tooltip-text">Valores médios históricos da competição. Usados como referência para classificar o perfil do árbitro.</span>
                                </span>
                            </div>
                            <div class="baseline-valores">
                                <div class="baseline-item">
                                    <span>Média Amarelos:</span>
                                    <span class="valor">{baseline.get('amarelos_total_jogo', '-')}</span>
                                </div>
                                <div class="baseline-item">
                                    <span>Média Faltas:</span>
                                    <span class="valor">{baseline.get('faltas_total_jogo', '-')}</span>
                                </div>
                            </div>
                        </div>
"""
                
                # Qualidade dos dados
                html += f"""
                        <div class="baseline-section">
                            <div class="baseline-titulo">
                                📉 Qualidade dos Dados
                                <span class="tooltip">
                                    <span class="tooltip-icon">i</span>
                                    <span class="tooltip-text">Percentual de jogos dos últimos 10 que possuem dados de faltas por tempo (1T/2T). Quanto maior, mais confiáveis as médias por tempo.</span>
                                </span>
                            </div>
                            <div class="baseline-valores">
                                <div class="baseline-item">
                                    <span>Disponibilidade Faltas 1T/2T:</span>
                                    <span class="valor">{metricas['qualidade_faltas_1t']}%</span>
                                </div>
                            </div>
                        </div>
"""
                
                # Tendências
                html += f"""
                        <div class="tendencias">
                            <div class="tendencia-item">
                                <span>
                                    % jogos com ≥5 amarelos (10j)
                                    <span class="tooltip">
                                        <span class="tooltip-icon">i</span>
                                        <span class="tooltip-text">Percentual de jogos onde o total de amarelos foi 5 ou mais. Útil para mercado de Over 4.5 cartões.</span>
                                    </span>
                                </span>
                                <span style="color: #e94560; font-weight: bold;">{metricas['pct_5mais_amarelos']}%</span>
                            </div>
                            <div class="tendencia-item">
                                <span>
                                    % jogos com ≥3 amarelos no 1T (10j)
                                    <span class="tooltip">
                                        <span class="tooltip-icon">i</span>
                                        <span class="tooltip-text">Percentual de jogos onde foram aplicados 3+ amarelos no 1º tempo. Útil para mercado de cartões no 1T.</span>
                                    </span>
                                </span>
                                <span style="color: #e94560; font-weight: bold;">{metricas['pct_3mais_amarelos_1t']}%</span>
                            </div>
                        </div>
"""
            
            html += """
                    </div>
"""
            
            # Notícias do Árbitro
            html += f"""
                    <div class="secao-titulo" style="margin-top: 25px;">📰 Notícias recentes envolvendo {arbitro['nome']}</div>
"""
            
            if noticias_arbitro:
                html += """
                    <div class="noticias-lista">
"""
                for noticia in noticias_arbitro:
                    html += f"""
                        <div class="noticia-card">
                            <div class="noticia-titulo">{noticia['titulo']}</div>
                            <div class="noticia-meta">
                                <span>📰 {noticia['fonte']}</span>
                                <span>📅 {noticia['data_formatada']}</span>
                            </div>
                            {f"<div class='noticia-resumo'>{noticia['resumo']}</div>" if noticia['resumo'] else ""}
                            <a href="{noticia['link']}" target="_blank" class="noticia-link">Ler mais →</a>
                        </div>
"""
                html += """
                    </div>
"""
            else:
                html += """
                    <div class="sem-noticias">ℹ️ Nenhuma notícia recente encontrada</div>
"""
            
            # Tabelas de Histórico do Árbitro
            if historico:
                jogos_mesma_liga = metricas.get('jogos_mesma_liga', []) if metricas else []
                jogos_outras = metricas.get('jogos_outras_ligas', []) if metricas else []
                
                # Histórico - Mesma Liga
                html += f"""
                    <div class="secao-titulo" style="margin-top: 25px;">📊 Histórico — {partida['liga_nome']}</div>
                    <div class="tabela-scroll">
                    <table class="tabela">
                        <thead>
                            <tr>
                                <th>Data</th>
                                <th>Partida</th>
                                <th>Placar</th>
                                <th>Faltas 1T</th>
                                <th>Faltas 2T</th>
                                <th>Faltas Total</th>
                                <th>Amarelos</th>
                                <th>Vermelhos</th>
                            </tr>
                        </thead>
                        <tbody>
"""
                
                if jogos_mesma_liga:
                    for jogo in jogos_mesma_liga[:10]:
                        f1c = jogo.get('faltas_1t_casa')
                        f1f = jogo.get('faltas_1t_fora')
                        f2c = jogo.get('faltas_2t_casa')
                        f2f = jogo.get('faltas_2t_fora')
                        ftc = jogo.get('faltas_total_casa')
                        ftf = jogo.get('faltas_total_fora')
                        
                        faltas_1t = "—" if (f1c is None or f1f is None) else str((f1c or 0) + (f1f or 0))
                        faltas_2t = "—" if (f2c is None or f2f is None) else str((f2c or 0) + (f2f or 0))
                        faltas_total = "—" if (ftc is None or ftf is None) else str((ftc or 0) + (ftf or 0))
                        
                        amarelos = (jogo.get('amarelos_total_casa', 0) or 0) + (jogo.get('amarelos_total_fora', 0) or 0)
                        vermelhos = (jogo.get('vermelhos_total_casa', 0) or 0) + (jogo.get('vermelhos_total_fora', 0) or 0)
                        
                        html += f"""
                            <tr>
                                <td>{jogo.get('data', '')}</td>
                                <td>{jogo.get('time_casa', '')} vs {jogo.get('time_fora', '')}</td>
                                <td style="font-weight: bold;">{jogo.get('placar_casa', 0)} - {jogo.get('placar_fora', 0)}</td>
                                <td>{faltas_1t}</td>
                                <td>{faltas_2t}</td>
                                <td>{faltas_total}</td>
                                <td><span class="stat-amarelo">{amarelos}</span></td>
                                <td><span class="stat-vermelho">{vermelhos}</span></td>
                            </tr>
"""
                else:
                    html += """
                            <tr>
                                <td colspan="8" style="text-align: center; color: #a0a0a0;">Nenhum jogo nesta competição</td>
                            </tr>
"""
                
                html += """
                        </tbody>
                    </table>
                    </div>
"""
                
                # Histórico - Outras Competições
                html += """
                    <div class="secao-titulo" style="margin-top: 25px;">📊 Histórico — Outras Competições</div>
                    <div class="tabela-scroll">
                    <table class="tabela">
                        <thead>
                            <tr>
                                <th>Data</th>
                                <th>Competição</th>
                                <th>Partida</th>
                                <th>Placar</th>
                                <th>Faltas 1T</th>
                                <th>Faltas 2T</th>
                                <th>Faltas Total</th>
                                <th>Amarelos</th>
                                <th>Vermelhos</th>
                            </tr>
                        </thead>
                        <tbody>
"""
                
                if jogos_outras:
                    for jogo in jogos_outras[:10]:
                        f1c = jogo.get('faltas_1t_casa')
                        f1f = jogo.get('faltas_1t_fora')
                        f2c = jogo.get('faltas_2t_casa')
                        f2f = jogo.get('faltas_2t_fora')
                        ftc = jogo.get('faltas_total_casa')
                        ftf = jogo.get('faltas_total_fora')
                        
                        faltas_1t = "—" if (f1c is None or f1f is None) else str((f1c or 0) + (f1f or 0))
                        faltas_2t = "—" if (f2c is None or f2f is None) else str((f2c or 0) + (f2f or 0))
                        faltas_total = "—" if (ftc is None or ftf is None) else str((ftc or 0) + (ftf or 0))
                        
                        amarelos = (jogo.get('amarelos_total_casa', 0) or 0) + (jogo.get('amarelos_total_fora', 0) or 0)
                        vermelhos = (jogo.get('vermelhos_total_casa', 0) or 0) + (jogo.get('vermelhos_total_fora', 0) or 0)
                        
                        html += f"""
                            <tr>
                                <td>{jogo.get('data', '')}</td>
                                <td>{jogo.get('campeonato', '')}</td>
                                <td>{jogo.get('time_casa', '')} vs {jogo.get('time_fora', '')}</td>
                                <td style="font-weight: bold;">{jogo.get('placar_casa', 0)} - {jogo.get('placar_fora', 0)}</td>
                                <td>{faltas_1t}</td>
                                <td>{faltas_2t}</td>
                                <td>{faltas_total}</td>
                                <td><span class="stat-amarelo">{amarelos}</span></td>
                                <td><span class="stat-vermelho">{vermelhos}</span></td>
                            </tr>
"""
                else:
                    html += """
                            <tr>
                                <td colspan="9" style="text-align: center; color: #a0a0a0;">Nenhum jogo em outras competições</td>
                            </tr>
"""
                
                html += """
                        </tbody>
                    </table>
                    </div>
"""
        
        else:
            html += """
                    <div class="sem-noticias">⚠️ Árbitro não informado para esta partida</div>
"""
        
        html += """
                </div>
"""
        
        # Seção dos Times
        html += """
                <div class="secao">
                    <div class="secao-titulo">⚽ Times</div>
                    <div class="times-grid">
"""
        
        # Time da Casa
        html += f"""
                        <div class="time-card">
                            <div class="time-header">
                                <div class="time-nome">🏠 {partida['time_casa']}</div>
                                {f"<div class='time-posicao'>{colocacao_casa['posicao']}º</div>" if colocacao_casa else ""}
                            </div>
                            <div class="time-content">
"""
        
        # Próximos jogos - Casa (MELHORADO v1.1)
        if proximos_casa:
            html += """
                                <div class="proximos-jogos">
                                    <h5>📅 Próximos 3 Jogos</h5>
"""
            for jogo in proximos_casa:
                pos_adv = jogo.get('colocacao_adversario')
                pos_adv_html = f"<span class='adversario-pos'>{pos_adv['posicao']}º</span>" if pos_adv else ""
                campeonato_html = f"<span class='campeonato'>{jogo['campeonato']}</span>" if jogo.get('campeonato') else ""
                fase_html = f"<span style='color: #a0a0a0;'>({jogo['fase']})</span>" if jogo.get('fase') else ""
                
                html += f"""
                                    <div class="proximo-jogo">
                                        <span class="local">{jogo['local']}</span>
                                        <span class="adversario-info">
                                            {jogo['adversario']}
                                            {pos_adv_html}
                                        </span>
                                        <span style="color: #a0a0a0;">{jogo['data']}</span>
                                        {campeonato_html}
                                        {fase_html}
                                    </div>
"""
            html += """
                                </div>
"""
        
        # Médias do Time Casa com tooltips
        if stats_casa:
            html += f"""
                                <div class="medias-time">
                                    <div class="media-item">
                                        <div class="valor">{stats_casa['media_faltas_feitas']}</div>
                                        <div class="label">
                                            Faltas Pró
                                            <span class="tooltip">
                                                <span class="tooltip-icon">i</span>
                                                <span class="tooltip-text">Média de faltas COMETIDAS pelo time nos últimos 5 jogos.</span>
                                            </span>
                                        </div>
                                    </div>
                                    <div class="media-item">
                                        <div class="valor">{stats_casa['media_faltas_sofridas']}</div>
                                        <div class="label">
                                            Faltas Contra
                                            <span class="tooltip">
                                                <span class="tooltip-icon">i</span>
                                                <span class="tooltip-text">Média de faltas SOFRIDAS pelo time nos últimos 5 jogos (cometidas pelo adversário).</span>
                                            </span>
                                        </div>
                                    </div>
                                    <div class="media-item">
                                        <div class="valor">{stats_casa['media_amarelos_feitos']}</div>
                                        <div class="label">
                                            Amarelos Pró
                                            <span class="tooltip">
                                                <span class="tooltip-icon">i</span>
                                                <span class="tooltip-text">Média de cartões amarelos RECEBIDOS pelo time nos últimos 5 jogos.</span>
                                            </span>
                                        </div>
                                    </div>
                                    <div class="media-item">
                                        <div class="valor">{stats_casa['media_amarelos_sofridos']}</div>
                                        <div class="label">
                                            Amarelos Contra
                                            <span class="tooltip">
                                                <span class="tooltip-icon">i</span>
                                                <span class="tooltip-text">Média de cartões amarelos do ADVERSÁRIO nos últimos 5 jogos.</span>
                                            </span>
                                        </div>
                                    </div>
                                </div>
"""
            
            # Tabela de Faltas - Casa
            html += """
                                <div class="tabela-titulo">
                                    📊 Faltas - Últimos 5 Jogos
                                    <span class="tooltip">
                                        <span class="tooltip-icon">i</span>
                                        <span class="tooltip-text"><strong>Pró:</strong> Faltas cometidas pelo time.<br><strong>Contra:</strong> Faltas sofridas (cometidas pelo adversário).</span>
                                    </span>
                                </div>
                                <table class="tabela-time">
                                    <thead>
                                        <tr>
                                            <th>Adversário</th>
                                            <th>Local</th>
                                            <th>Pró</th>
                                            <th>Contra</th>
                                        </tr>
                                    </thead>
                                    <tbody>
"""
            for jogo in stats_casa['jogos'][:5]:
                local = '🏠' if jogo['eh_casa'] else '✈️'
                html += f"""
                                        <tr>
                                            <td>{jogo['adversario']}</td>
                                            <td>{local}</td>
                                            <td>{jogo['faltas_feitas_total']}</td>
                                            <td>{jogo['faltas_sofridas_total']}</td>
                                        </tr>
"""
            html += """
                                    </tbody>
                                </table>
"""
            
            # Tabela de Amarelos - Casa
            html += """
                                <div class="tabela-titulo">
                                    📊 Amarelos - Últimos 5 Jogos
                                    <span class="tooltip">
                                        <span class="tooltip-icon">i</span>
                                        <span class="tooltip-text"><strong>Pró:</strong> Cartões recebidos pelo time.<br><strong>Contra:</strong> Cartões recebidos pelo adversário.</span>
                                    </span>
                                </div>
                                <table class="tabela-time">
                                    <thead>
                                        <tr>
                                            <th>Adversário</th>
                                            <th>Local</th>
                                            <th>Pró</th>
                                            <th>Contra</th>
                                        </tr>
                                    </thead>
                                    <tbody>
"""
            for jogo in stats_casa['jogos'][:5]:
                local = '🏠' if jogo['eh_casa'] else '✈️'
                html += f"""
                                        <tr>
                                            <td>{jogo['adversario']}</td>
                                            <td>{local}</td>
                                            <td><span class="stat-amarelo">{jogo['amarelos_feitos_total']}</span></td>
                                            <td><span class="stat-amarelo">{jogo['amarelos_sofridos_total']}</span></td>
                                        </tr>
"""
            html += """
                                    </tbody>
                                </table>
"""
        
        html += """
                            </div>
                        </div>
"""
        
        # Time de Fora
        html += f"""
                        <div class="time-card">
                            <div class="time-header">
                                <div class="time-nome">✈️ {partida['time_fora']}</div>
                                {f"<div class='time-posicao'>{colocacao_fora['posicao']}º</div>" if colocacao_fora else ""}
                            </div>
                            <div class="time-content">
"""
        
        # Próximos jogos - Fora (MELHORADO v1.1)
        if proximos_fora:
            html += """
                                <div class="proximos-jogos">
                                    <h5>📅 Próximos 3 Jogos</h5>
"""
            for jogo in proximos_fora:
                pos_adv = jogo.get('colocacao_adversario')
                pos_adv_html = f"<span class='adversario-pos'>{pos_adv['posicao']}º</span>" if pos_adv else ""
                campeonato_html = f"<span class='campeonato'>{jogo['campeonato']}</span>" if jogo.get('campeonato') else ""
                fase_html = f"<span style='color: #a0a0a0;'>({jogo['fase']})</span>" if jogo.get('fase') else ""
                
                html += f"""
                                    <div class="proximo-jogo">
                                        <span class="local">{jogo['local']}</span>
                                        <span class="adversario-info">
                                            {jogo['adversario']}
                                            {pos_adv_html}
                                        </span>
                                        <span style="color: #a0a0a0;">{jogo['data']}</span>
                                        {campeonato_html}
                                        {fase_html}
                                    </div>
"""
            html += """
                                </div>
"""
        
        # Médias do Time Fora com tooltips
        if stats_fora:
            html += f"""
                                <div class="medias-time">
                                    <div class="media-item">
                                        <div class="valor">{stats_fora['media_faltas_feitas']}</div>
                                        <div class="label">
                                            Faltas Pró
                                            <span class="tooltip">
                                                <span class="tooltip-icon">i</span>
                                                <span class="tooltip-text">Média de faltas COMETIDAS pelo time nos últimos 5 jogos.</span>
                                            </span>
                                        </div>
                                    </div>
                                    <div class="media-item">
                                        <div class="valor">{stats_fora['media_faltas_sofridas']}</div>
                                        <div class="label">
                                            Faltas Contra
                                            <span class="tooltip">
                                                <span class="tooltip-icon">i</span>
                                                <span class="tooltip-text">Média de faltas SOFRIDAS pelo time nos últimos 5 jogos (cometidas pelo adversário).</span>
                                            </span>
                                        </div>
                                    </div>
                                    <div class="media-item">
                                        <div class="valor">{stats_fora['media_amarelos_feitos']}</div>
                                        <div class="label">
                                            Amarelos Pró
                                            <span class="tooltip">
                                                <span class="tooltip-icon">i</span>
                                                <span class="tooltip-text">Média de cartões amarelos RECEBIDOS pelo time nos últimos 5 jogos.</span>
                                            </span>
                                        </div>
                                    </div>
                                    <div class="media-item">
                                        <div class="valor">{stats_fora['media_amarelos_sofridos']}</div>
                                        <div class="label">
                                            Amarelos Contra
                                            <span class="tooltip">
                                                <span class="tooltip-icon">i</span>
                                                <span class="tooltip-text">Média de cartões amarelos do ADVERSÁRIO nos últimos 5 jogos.</span>
                                            </span>
                                        </div>
                                    </div>
                                </div>
"""
            
            # Tabela de Faltas - Fora
            html += """
                                <div class="tabela-titulo">
                                    📊 Faltas - Últimos 5 Jogos
                                    <span class="tooltip">
                                        <span class="tooltip-icon">i</span>
                                        <span class="tooltip-text"><strong>Pró:</strong> Faltas cometidas pelo time.<br><strong>Contra:</strong> Faltas sofridas (cometidas pelo adversário).</span>
                                    </span>
                                </div>
                                <table class="tabela-time">
                                    <thead>
                                        <tr>
                                            <th>Adversário</th>
                                            <th>Local</th>
                                            <th>Pró</th>
                                            <th>Contra</th>
                                        </tr>
                                    </thead>
                                    <tbody>
"""
            for jogo in stats_fora['jogos'][:5]:
                local = '🏠' if jogo['eh_casa'] else '✈️'
                html += f"""
                                        <tr>
                                            <td>{jogo['adversario']}</td>
                                            <td>{local}</td>
                                            <td>{jogo['faltas_feitas_total']}</td>
                                            <td>{jogo['faltas_sofridas_total']}</td>
                                        </tr>
"""
            html += """
                                    </tbody>
                                </table>
"""
            
            # Tabela de Amarelos - Fora
            html += """
                                <div class="tabela-titulo">
                                    📊 Amarelos - Últimos 5 Jogos
                                    <span class="tooltip">
                                        <span class="tooltip-icon">i</span>
                                        <span class="tooltip-text"><strong>Pró:</strong> Cartões recebidos pelo time.<br><strong>Contra:</strong> Cartões recebidos pelo adversário.</span>
                                    </span>
                                </div>
                                <table class="tabela-time">
                                    <thead>
                                        <tr>
                                            <th>Adversário</th>
                                            <th>Local</th>
                                            <th>Pró</th>
                                            <th>Contra</th>
                                        </tr>
                                    </thead>
                                    <tbody>
"""
            for jogo in stats_fora['jogos'][:5]:
                local = '🏠' if jogo['eh_casa'] else '✈️'
                html += f"""
                                        <tr>
                                            <td>{jogo['adversario']}</td>
                                            <td>{local}</td>
                                            <td><span class="stat-amarelo">{jogo['amarelos_feitos_total']}</span></td>
                                            <td><span class="stat-amarelo">{jogo['amarelos_sofridos_total']}</span></td>
                                        </tr>
"""
            html += """
                                    </tbody>
                                </table>
"""
        
        # Fecha a seção dos Times
        html += """
                            </div>
                        </div>
                    </div>
                </div>
            </div>
"""
        
        # ====== NOVA SEÇÃO: Gráfico Comparativo de Amarelos ======
        # Coleta dados para o gráfico
        grafico_id = f"grafico_{partida['id']}"
        
        # Dados do árbitro - verifica se tem 5 jogos na liga
        amarelos_arbitro = []
        arbitro_fonte = "geral"  # padrão
        
        if metricas:
            amarelos_liga = metricas.get('amarelos_5j_liga', [])
            amarelos_geral = metricas.get('amarelos_5j_geral', [])
            
            # Se tem 5 jogos na liga, usa dados da liga
            if len(amarelos_liga) >= 5:
                amarelos_arbitro = amarelos_liga[:5]
                arbitro_fonte = "na liga"
            else:
                # Caso contrário, usa dados gerais
                amarelos_arbitro = amarelos_geral[:5] if amarelos_geral else []
                arbitro_fonte = "geral"
        
        # Preenche com 0 se tiver menos de 5 jogos
        while len(amarelos_arbitro) < 5:
            amarelos_arbitro.append(0)
        # Inverte para mostrar do mais antigo ao mais recente
        amarelos_arbitro = amarelos_arbitro[::-1]
        
        # Dados do time da casa (últimos 5 jogos)
        amarelos_casa = []
        if stats_casa and stats_casa.get('jogos'):
            for jogo in stats_casa['jogos'][:5]:
                amarelos_casa.append(jogo.get('amarelos_feitos_total', 0))
        while len(amarelos_casa) < 5:
            amarelos_casa.append(0)
        amarelos_casa = amarelos_casa[::-1]
        
        # Dados do time de fora (últimos 5 jogos)
        amarelos_fora = []
        if stats_fora and stats_fora.get('jogos'):
            for jogo in stats_fora['jogos'][:5]:
                amarelos_fora.append(jogo.get('amarelos_feitos_total', 0))
        while len(amarelos_fora) < 5:
            amarelos_fora.append(0)
        amarelos_fora = amarelos_fora[::-1]
        
        html += f"""
                <!-- Seção Comparativo de Amarelos -->
                <div class="secao">
                    <div class="secao-titulo">📊 Comparativo de Amarelos - Últimos 5 Jogos</div>
                    <div class="grafico-comparativo">
                        <div class="grafico-container">
                            <canvas id="{grafico_id}"></canvas>
                        </div>
                        <div class="grafico-legenda">
                            <div class="legenda-item">
                                <div class="legenda-cor" style="background: #e94560;"></div>
                                <span>🗣️ Árbitro <small style="color: #a0a0a0;">({arbitro_fonte})</small></span>
                            </div>
                            <div class="legenda-item">
                                <div class="legenda-cor" style="background: #3498db;"></div>
                                <span>🏠 {partida['time_casa']}</span>
                            </div>
                            <div class="legenda-item">
                                <div class="legenda-cor" style="background: #2ecc71;"></div>
                                <span>✈️ {partida['time_fora']}</span>
                            </div>
                        </div>
                    </div>
                    <script>
                    (function() {{
                        const ctx = document.getElementById('{grafico_id}').getContext('2d');
                        new Chart(ctx, {{
                            type: 'line',
                            data: {{
                                labels: ['Jogo 1', 'Jogo 2', 'Jogo 3', 'Jogo 4', 'Jogo 5'],
                                datasets: [
                                    {{
                                        label: 'Árbitro',
                                        data: {amarelos_arbitro},
                                        borderColor: '#e94560',
                                        backgroundColor: 'rgba(233, 69, 96, 0.1)',
                                        borderWidth: 3,
                                        pointRadius: 5,
                                        pointBackgroundColor: '#e94560',
                                        tension: 0.3,
                                        fill: false
                                    }},
                                    {{
                                        label: 'Time Casa',
                                        data: {amarelos_casa},
                                        borderColor: '#3498db',
                                        backgroundColor: 'rgba(52, 152, 219, 0.1)',
                                        borderWidth: 3,
                                        pointRadius: 5,
                                        pointBackgroundColor: '#3498db',
                                        tension: 0.3,
                                        fill: false
                                    }},
                                    {{
                                        label: 'Time Fora',
                                        data: {amarelos_fora},
                                        borderColor: '#2ecc71',
                                        backgroundColor: 'rgba(46, 204, 113, 0.1)',
                                        borderWidth: 3,
                                        pointRadius: 5,
                                        pointBackgroundColor: '#2ecc71',
                                        tension: 0.3,
                                        fill: false
                                    }}
                                ]
                            }},
                            options: {{
                                responsive: true,
                                maintainAspectRatio: false,
                                plugins: {{
                                    legend: {{
                                        display: false
                                    }},
                                    tooltip: {{
                                        backgroundColor: '#1a1a2e',
                                        titleColor: '#e94560',
                                        bodyColor: '#e0e0e0',
                                        borderColor: '#0f3460',
                                        borderWidth: 1,
                                        padding: 10,
                                        displayColors: true
                                    }}
                                }},
                                scales: {{
                                    y: {{
                                        beginAtZero: true,
                                        max: 10,
                                        ticks: {{
                                            color: '#a0a0a0',
                                            stepSize: 2
                                        }},
                                        grid: {{
                                            color: 'rgba(255, 255, 255, 0.1)'
                                        }}
                                    }},
                                    x: {{
                                        ticks: {{
                                            color: '#a0a0a0'
                                        }},
                                        grid: {{
                                            color: 'rgba(255, 255, 255, 0.1)'
                                        }}
                                    }}
                                }}
                            }}
                        }});
                    }})();
                    </script>
"""
        
        # Fecha seção do gráfico, jogo-content e jogo-card
        html += """
                </div>
            </div>
        </div>
"""
    
    # Card de Doação
    html += """
        <!-- Card de Doação -->
        <div class="donation-section">
            <h2>💖 Apoie o RefStats</h2>
            <p>O RefStats é gratuito e mantido com dedicação. Se você gosta do projeto, considere fazer uma doação!</p>
            
            <div class="donation-grid">
                <div class="donation-card">
                    <h4>🔲 PIX (Brasil)</h4>
                    <p>Rápido, fácil e sem taxas</p>
                    <div class="pix-key" onclick="copyPix()">
                        <span id="pixKey">seuemail@exemplo.com</span>
                        <span>📋</span>
                    </div>
                </div>
                
                <div class="donation-card">
                    <h4>🅿️ PayPal</h4>
                    <p>Para doações internacionais</p>
                    <a href="https://paypal.me/seuusuario" target="_blank" class="paypal-btn">
                        Doar via PayPal
                    </a>
                </div>
            </div>
            
            <div class="donation-info">
                <h4>💡 Por que doar?</h4>
                <p>Suas doações ajudam a manter o servidor online, melhorar as funcionalidades e adicionar novas features. Qualquer valor é bem-vindo e nos motiva a continuar!</p>
            </div>
        </div>
"""
    
    # Footer
    html += f"""
        <div class="footer">
            <p><strong>⚽ RefStats - Jogos do Dia</strong></p>
            <p>
                <a href="refstats_termos.html" style="color: #3498db; text-decoration: none;">Termos de Uso</a> | 
                <a href="refstats_privacidade.html" style="color: #3498db; text-decoration: none;">Política de Privacidade</a> | 
                <a href="refstats_aviso_legal.html" style="color: #3498db; text-decoration: none;">Aviso Legal</a> |
                <a href="refstats_faq.html" style="color: #3498db; text-decoration: none;">FAQ</a>
            </p>
            <p style="margin-top: 10px; font-size: 0.9em;">Dados coletados de fontes confiáveis • {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
            <p style="margin-top: 5px; font-size: 0.85em; color: #3498db;">💡 Use Ctrl+F ou clique em 🔍 para pesquisar e filtrar por perfil do árbitro</p>
            <p style="margin-top: 10px; font-size: 0.8em; color: #e94560;">⚠️ Este site é apenas para fins informativos. Aposte com responsabilidade.</p>
        </div>
    </div>
"""
    
    # JavaScript da Barra de Pesquisa (fora da f-string para evitar conflitos com chaves)
    html += """
    <!-- JavaScript da Barra de Pesquisa v1.4 -->
    <script>
    (function() {
        // Elementos
        const searchBar = document.getElementById('searchBar');
        const searchInput = document.getElementById('searchInput');
        const searchCounter = document.getElementById('searchCounter');
        const searchPrev = document.getElementById('searchPrev');
        const searchNext = document.getElementById('searchNext');
        const searchClose = document.getElementById('searchClose');
        const searchToggle = document.getElementById('searchToggle');
        const searchHint = document.getElementById('searchHint');
        
        // Estado
        let highlights = [];
        let currentIndex = -1;
        let searchTimeout = null;
        
        // Mostra dica por 5 segundos ao carregar
        setTimeout(() => {
            searchHint.classList.add('visible');
            setTimeout(() => searchHint.classList.remove('visible'), 5000);
        }, 1000);
        
        // Abre a barra de pesquisa
        function openSearch() {
            searchBar.classList.add('active');
            document.body.classList.add('search-active');
            searchToggle.classList.add('hidden');
            searchInput.focus();
        }
        
        // Fecha a barra de pesquisa
        function closeSearch() {
            searchBar.classList.remove('active');
            document.body.classList.remove('search-active');
            searchToggle.classList.remove('hidden');
            clearHighlights();
            searchInput.value = '';
            searchCounter.textContent = '';
        }
        
        // Limpa os highlights
        function clearHighlights() {
            highlights.forEach(span => {
                const parent = span.parentNode;
                parent.replaceChild(document.createTextNode(span.textContent), span);
                parent.normalize();
            });
            highlights = [];
            currentIndex = -1;
            updateNavButtons();
        }
        
        // Atualiza botões de navegação
        function updateNavButtons() {
            searchPrev.disabled = highlights.length === 0;
            searchNext.disabled = highlights.length === 0;
        }
        
        // Realiza a pesquisa
        function performSearch(query) {
            clearHighlights();
            
            if (!query || query.length === 0) {
                searchCounter.textContent = '';
                return;
            }
            
            const container = document.querySelector('.container');
            const walker = document.createTreeWalker(
                container,
                NodeFilter.SHOW_TEXT,
                null,
                false
            );
            
            const nodesToProcess = [];
            let node;
            while (node = walker.nextNode()) {
                // Ignora textos dentro de scripts, styles e tooltips
                const parent = node.parentElement;
                const isInTooltip = parent.closest('.tooltip-text') !== null;
                
                if (parent.tagName !== 'SCRIPT' && 
                    parent.tagName !== 'STYLE' &&
                    !isInTooltip &&
                    node.textContent.trim().length > 0) {
                    nodesToProcess.push(node);
                }
            }
            
            const regex = new RegExp(`(${escapeRegex(query)})`, 'gi');
            
            nodesToProcess.forEach(textNode => {
                const text = textNode.textContent;
                if (regex.test(text)) {
                    regex.lastIndex = 0;
                    const fragment = document.createDocumentFragment();
                    let lastIndex = 0;
                    let match;
                    
                    while ((match = regex.exec(text)) !== null) {
                        // Texto antes do match
                        if (match.index > lastIndex) {
                            fragment.appendChild(document.createTextNode(text.slice(lastIndex, match.index)));
                        }
                        
                        // O match destacado
                        const span = document.createElement('span');
                        span.className = 'search-highlight';
                        span.textContent = match[1];
                        fragment.appendChild(span);
                        highlights.push(span);
                        
                        lastIndex = regex.lastIndex;
                    }
                    
                    // Texto depois do último match
                    if (lastIndex < text.length) {
                        fragment.appendChild(document.createTextNode(text.slice(lastIndex)));
                    }
                    
                    textNode.parentNode.replaceChild(fragment, textNode);
                }
            });
            
            // Atualiza contador
            if (highlights.length > 0) {
                currentIndex = 0;
                updateCurrentHighlight();
                searchCounter.textContent = `1 de ${highlights.length}`;
            } else {
                searchCounter.textContent = 'Nenhum resultado';
            }
            
            updateNavButtons();
        }
        
        // Escapa caracteres especiais para regex
        function escapeRegex(string) {
            var specials = ['.', '*', '+', '?', '^', '$', '{', '}', '(', ')', '|', '[', ']', '\\\\'];
            var result = string;
            specials.forEach(function(char) {
                result = result.split(char).join('\\\\' + char);
            });
            return result;
        }
        
        // Atualiza o highlight atual
        function updateCurrentHighlight() {
            highlights.forEach((span, index) => {
                span.classList.toggle('current', index === currentIndex);
            });
            
            if (highlights[currentIndex]) {
                highlights[currentIndex].scrollIntoView({
                    behavior: 'smooth',
                    block: 'center'
                });
            }
        }
        
        // Vai para o próximo resultado
        function goToNext() {
            if (highlights.length === 0) return;
            currentIndex = (currentIndex + 1) % highlights.length;
            updateCurrentHighlight();
            searchCounter.textContent = `${currentIndex + 1} de ${highlights.length}`;
        }
        
        // Vai para o resultado anterior
        function goToPrev() {
            if (highlights.length === 0) return;
            currentIndex = (currentIndex - 1 + highlights.length) % highlights.length;
            updateCurrentHighlight();
            searchCounter.textContent = `${currentIndex + 1} de ${highlights.length}`;
        }
        
        // Event Listeners
        searchToggle.addEventListener('click', openSearch);
        searchClose.addEventListener('click', closeSearch);
        
        searchInput.addEventListener('input', function(e) {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                performSearch(e.target.value);
            }, 150);
        });
        
        searchNext.addEventListener('click', goToNext);
        searchPrev.addEventListener('click', goToPrev);
        
        // Atalhos de teclado
        document.addEventListener('keydown', function(e) {
            // Ctrl+F ou Cmd+F para abrir
            if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
                e.preventDefault();
                openSearch();
            }
            
            // Se a barra está aberta
            if (searchBar.classList.contains('active')) {
                // Esc para fechar
                if (e.key === 'Escape') {
                    closeSearch();
                }
                
                // Enter ou F3 para próximo
                if (e.key === 'Enter' || e.key === 'F3') {
                    e.preventDefault();
                    if (e.shiftKey) {
                        goToPrev();
                    } else {
                        goToNext();
                    }
                }
                
                // Setas para navegar
                if (e.key === 'ArrowDown' && document.activeElement === searchInput) {
                    e.preventDefault();
                    goToNext();
                }
                if (e.key === 'ArrowUp' && document.activeElement === searchInput) {
                    e.preventDefault();
                    goToPrev();
                }
            }
        });
        
        // ========================================
        // FILTRO POR PERFIL DO ÁRBITRO
        // ========================================
        
        const filterBtns = document.querySelectorAll('.filter-btn');
        const filterClear = document.getElementById('filterClear');
        const filterCounter = document.getElementById('filterCounter');
        let activeFilter = null;
        
        // Aplica filtro
        function applyFilter(perfil) {
            const cards = document.querySelectorAll('.jogo-card');
            let visibleCount = 0;
            let totalCount = cards.length;
            
            cards.forEach(card => {
                const cardPerfil = card.getAttribute('data-perfil');
                if (perfil === null || cardPerfil === perfil) {
                    card.classList.remove('filtered-out');
                    visibleCount++;
                } else {
                    card.classList.add('filtered-out');
                }
            });
            
            // Atualiza contador
            if (perfil) {
                filterCounter.textContent = `${visibleCount}/${totalCount}`;
            } else {
                filterCounter.textContent = '';
            }
            
            // Mostra/esconde botão limpar
            if (perfil) {
                filterClear.classList.remove('hidden');
            } else {
                filterClear.classList.add('hidden');
            }
        }
        
        // Clique nos botões de filtro
        filterBtns.forEach(btn => {
            btn.addEventListener('click', function() {
                const perfil = this.getAttribute('data-filter');
                
                // Se já está ativo, desativa
                if (this.classList.contains('active')) {
                    this.classList.remove('active');
                    activeFilter = null;
                    applyFilter(null);
                } else {
                    // Remove active de todos
                    filterBtns.forEach(b => b.classList.remove('active'));
                    // Ativa este
                    this.classList.add('active');
                    activeFilter = perfil;
                    applyFilter(perfil);
                }
            });
        });
        
        // Botão limpar filtro
        filterClear.addEventListener('click', function() {
            filterBtns.forEach(b => b.classList.remove('active'));
            activeFilter = null;
            applyFilter(null);
        });
        
    })();
    
    // Função para copiar PIX
    function copyPix() {
        const pixKey = document.getElementById('pixKey').textContent;
        navigator.clipboard.writeText(pixKey).then(() => {
            alert('✅ Chave PIX copiada: ' + pixKey);
        }).catch(() => {
            // Fallback para navegadores antigos
            const textarea = document.createElement('textarea');
            textarea.value = pixKey;
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
            alert('✅ Chave PIX copiada: ' + pixKey);
        });
    }
    </script>
</body>
</html>
"""
    
    return html

# ============================================================================
# FUNÇÃO PRINCIPAL
# ============================================================================

def main():
    """Função principal do sistema"""
    print("=" * 70)
    print("  ⚽ REFSTATS - JOGOS DO DIA v1.5")
    print("  Análise de Árbitros + Times")
    print("=" * 70)
    print()
    
    # Solicita a data
    data_str = input("📅 Digite a data das partidas (DD/MM/YYYY) [ENTER para hoje]: ").strip()
    
    if not data_str:
        data_str = datetime.now().strftime('%d/%m/%Y')
        print(f"   ➡️ Usando data de hoje: {data_str}")
    
    # Valida o formato da data
    try:
        datetime.strptime(data_str, '%d/%m/%Y')
    except ValueError:
        print("\n❌ Formato de data inválido! Use DD/MM/YYYY")
        return
    
    print()
    print("=" * 70)
    
    # Busca partidas do dia
    partidas = buscar_partidas_do_dia(data_str)
    
    if not partidas:
        print("\n⚠️ Nenhuma partida encontrada para esta data")
        return
    
    # Analisa cada partida
    print("\n" + "=" * 70)
    print("  🔍 ANALISANDO PARTIDAS")
    print("=" * 70)
    
    analises = []
    
    for idx, partida in enumerate(partidas, 1):
        print(f"\n[{idx}/{len(partidas)}] {partida['time_casa']} vs {partida['time_fora']}")
        print(f"      🏆 {partida['liga_nome']}")
        
        analise = {'partida': partida}
        
        # 0. Busca info do estádio via API (v1.1)
        print(f"      🏟️ Buscando informações do estádio...")
        try:
            estadio_info = buscar_info_estadio_evento(partida['id'])
            analise['estadio_info'] = estadio_info
            if estadio_info:
                print(f"         ✅ {estadio_info['nome']} - {estadio_info['cidade']}")
        except:
            analise['estadio_info'] = None
        
        # 1. Busca árbitro
        print(f"      🔍 Buscando árbitro...")
        arbitro = buscar_arbitro_partida(partida['id'])
        analise['arbitro'] = arbitro
        
        if arbitro:
            # 2. Busca histórico do árbitro (ANTES da data_alvo)
            print(f"      📊 Analisando histórico do árbitro...")
            historico = buscar_ultimas_partidas_arbitro(arbitro['id'], quantidade=10, data_alvo=data_str)
            analise['historico'] = historico
            
            # 3. Calcula métricas do árbitro
            if historico:
                metricas = calcular_metricas_arbitro(historico, partida['liga_id'])
                analise['metricas'] = metricas
            
            # 4. Busca notícias do árbitro (v1.1: PT + EN)
            print(f"      📰 Buscando notícias sobre o árbitro (PT + EN)...")
            noticias = buscar_noticias_arbitro(arbitro['nome'], arbitro.get('pais', ''))
            analise['noticias_arbitro'] = noticias
            print(f"         ✅ {len(noticias)} notícia(s) encontrada(s)")
        
        # 5. Busca colocação dos times
        print(f"      📊 Buscando colocação de {partida['time_casa']}...")
        colocacao_casa = buscar_colocacao_time(partida['time_casa_id'], partida['liga_id'])
        analise['colocacao_casa'] = colocacao_casa
        if colocacao_casa:
            print(f"         ✅ {colocacao_casa['posicao']}º lugar")
        
        print(f"      📊 Buscando colocação de {partida['time_fora']}...")
        colocacao_fora = buscar_colocacao_time(partida['time_fora_id'], partida['liga_id'])
        analise['colocacao_fora'] = colocacao_fora
        if colocacao_fora:
            print(f"         ✅ {colocacao_fora['posicao']}º lugar")
        
        # 6. Busca próximos jogos (APÓS a data_alvo)
        print(f"      📅 Buscando próximos jogos...")
        proximos_casa = buscar_proximos_jogos(partida['time_casa_id'], data_alvo=data_str)
        proximos_fora = buscar_proximos_jogos(partida['time_fora_id'], data_alvo=data_str)
        analise['proximos_casa'] = proximos_casa
        analise['proximos_fora'] = proximos_fora
        
        # 7. Busca estatísticas dos times (ANTES da data_alvo)
        print(f"      📊 Buscando estatísticas de {partida['time_casa']}...")
        stats_casa = buscar_ultimos_jogos_time(partida['time_casa_id'], data_alvo=data_str)
        analise['stats_casa'] = stats_casa
        
        print(f"      📊 Buscando estatísticas de {partida['time_fora']}...")
        stats_fora = buscar_ultimos_jogos_time(partida['time_fora_id'], data_alvo=data_str)
        analise['stats_fora'] = stats_fora
        
        analises.append(analise)
        
        print()
        time.sleep(1)  # Delay para não sobrecarregar API
    
    # Gera relatório
    print("\n" + "=" * 70)
    print("  📄 GERANDO RELATÓRIO HTML")
    print("=" * 70)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    html_content = gerar_html_unificado(analises, timestamp, data_str)
    
    # Garante que as pastas existem
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    historico_dir = os.path.join("Historico")
    os.makedirs(historico_dir, exist_ok=True)
    
    # Salva como JOGOS_DO_DIA.html (link fixo para o Home) - pasta raiz
    filename_atual = os.path.join("JOGOS_DO_DIA.html")
    with open(filename_atual, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    # Para o histórico, ajusta os links para usar ../ (voltar uma pasta)
    html_historico = html_content.replace('href="index.html', 'href="/RefStats/index.html')
    html_historico = html_historico.replace('href="JOGOS_DO_DIA.html', 'href="../JOGOS_DO_DIA.html')
    html_historico = html_historico.replace('href="refstats_historico.html', 'href="../refstats_historico.html')
    html_historico = html_historico.replace('href="refstats_contato.html', 'href="../refstats_contato.html')
    html_historico = html_historico.replace('href="refstats_termos.html', 'href="../refstats_termos.html')
    html_historico = html_historico.replace('href="refstats_privacidade.html', 'href="../refstats_privacidade.html')
    html_historico = html_historico.replace('href="refstats_aviso_legal.html', 'href="../refstats_aviso_legal.html')
    html_historico = html_historico.replace('href="refstats_faq.html', 'href="../refstats_faq.html')
    html_historico = html_historico.replace('src="./assets/img/LogoINICIO.png', 'src="./assets/img/LogoINICIO.png')
    html_historico = html_historico.replace('url("./assets/img/FundoMuroFundo.png")', 'url("./assets/img/FundoMuroFundo.png")')
    
    # Salva arquivo com data na pasta Historico/
    data_arquivo = data_str.replace('/', '')
    filename_historico = os.path.join(historico_dir, f"JOGOS_DO_DIA_{data_arquivo}.html")
    with open(filename_historico, 'w', encoding='utf-8') as f:
        f.write(html_historico)
    
    # Resumo final
    print()
    print("=" * 70)
    print("  ✅ ANÁLISE CONCLUÍDA!")
    print("=" * 70)
    print()
    print("📊 RESUMO:")
    print(f"   • Partidas analisadas: {len(analises)}")
    print(f"   • Árbitros identificados: {sum(1 for a in analises if a.get('arbitro'))}")
    print()
    print("📄 Arquivos salvos:")
    print(f"   • {filename_atual} (página atual)")
    print(f"   • {filename_historico} (histórico)")
    print()
    print("🆕 NOVIDADES v1.5:")
    print("   ✅ Navbar integrada com Home do RefStats")
    print("   ✅ Título 'Jogos do Dia' com data consultada")
    print("   ✅ Filtro por perfil do árbitro")
    print("   ✅ Gráfico comparativo de amarelos")
    print()
    print("💡 Abra o arquivo HTML no seu navegador para visualizar!")
    print()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("\n❌ ERRO FATAL:")
        print(e)
        import traceback
        traceback.print_exc()
    finally:
        input("\nPressione ENTER para fechar...")