#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
SISTEMA DE VALIDAÇÃO DE PROBABILIDADES - BACKTESTING
=============================================================================
Autor: RefStats
Descrição: Valida as previsões de probabilidade comparando com resultados reais.
           Busca cartões via SofaScore API e gera relatório de acertos/erros.

ESTRUTURA DE PASTAS:
    /Probabilidade/                    → Arquivos de entrada (PROBABILIDADE_*.html)
    /Probabilidade/Relatorio/          → Relatórios de validação gerados
=============================================================================
"""

import os
import re
import glob
import json
import time
import requests
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from bs4 import BeautifulSoup
from collections import defaultdict


# =============================================================================
# CONFIGURAÇÕES
# =============================================================================

BASE_URL = 'https://api.sofascore.com/api/v1'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
    'Referer': 'https://www.sofascore.com/'
}

# Delay entre requisições para não sobrecarregar a API
REQUEST_DELAY = 1.0


# =============================================================================
# CLASSES DE DADOS
# =============================================================================

@dataclass
class PrevisaoMercado:
    """Representa uma previsão de mercado (Over/Under X.5)."""
    mercado: str                # Ex: "Over 2.5 Cartões"
    probabilidade: float        # Ex: 84.17
    destaque: bool              # Se tinha classe "destaque" (>= 55%)
    tipo: str                   # "over" ou "under"
    linha: float                # 2.5, 3.5, 4.5, etc.
    
    def verificar_acerto(self, cartoes_reais: int) -> bool:
        """Verifica se a previsão acertou."""
        if self.tipo == "over":
            return cartoes_reais > self.linha
        else:  # under
            return cartoes_reais <= self.linha


@dataclass
class PartidaPrevisao:
    """Representa uma partida com suas previsões."""
    time_mandante: str
    time_visitante: str
    data: str                   # DD/MM/YYYY
    horario: str
    competicao: str
    arbitro: str
    lambda_previsto: float
    modelo: str                 # "Poisson" ou "Binomial Negativa"
    previsoes: List[PrevisaoMercado] = field(default_factory=list)
    
    # Dados reais (preenchidos após busca)
    cartoes_reais: Optional[int] = None
    placar: Optional[str] = None
    status: str = "pendente"    # "pendente", "encontrado", "não encontrado"
    
    def get_destaques(self) -> List[PrevisaoMercado]:
        """Retorna apenas as previsões com destaque (>= 55%)."""
        return [p for p in self.previsoes if p.destaque]


@dataclass
class ResultadoValidacao:
    """Resultado da validação de uma previsão."""
    partida: PartidaPrevisao
    mercado: PrevisaoMercado
    cartoes_reais: int
    acertou: bool
    diferenca: float            # Diferença entre cartões reais e linha


@dataclass
class RelatorioValidacao:
    """Relatório completo de validação."""
    data_arquivo: str
    total_partidas: int
    partidas_encontradas: int
    partidas_nao_encontradas: int
    
    # Estatísticas de destaques (>= 55%)
    total_destaques: int
    destaques_acertos: int
    destaques_erros: int
    taxa_acerto_destaques: float
    
    # Estatísticas por mercado
    stats_por_mercado: Dict[str, Dict[str, float]] = field(default_factory=dict)
    
    # Detalhes
    validacoes: List[ResultadoValidacao] = field(default_factory=list)
    partidas: List[PartidaPrevisao] = field(default_factory=list)


# =============================================================================
# FUNÇÕES DE EXTRAÇÃO DO HTML
# =============================================================================

def extrair_valor_float(texto: str) -> float:
    """Extrai um valor float de um texto."""
    if not texto:
        return 0.0
    texto_limpo = re.sub(r'[^\d.,\-]', '', texto.strip())
    texto_limpo = texto_limpo.replace(',', '.')
    try:
        return float(texto_limpo)
    except (ValueError, TypeError):
        return 0.0


def extrair_previsoes_do_card(card) -> List[PrevisaoMercado]:
    """Extrai as previsões de probabilidade de um card."""
    previsoes = []
    
    prob_cards = card.find_all(class_='prob-card')
    
    for prob_card in prob_cards:
        # Verifica se tem destaque
        classes = prob_card.get('class', [])
        destaque = 'destaque' in classes
        
        # Extrai mercado e probabilidade
        mercado_elem = prob_card.find(class_='prob-mercado')
        valor_elem = prob_card.find(class_='prob-valor')
        
        if mercado_elem and valor_elem:
            mercado = mercado_elem.get_text(strip=True)
            probabilidade = extrair_valor_float(valor_elem.get_text())
            
            # Determina tipo e linha
            mercado_lower = mercado.lower()
            if 'over' in mercado_lower:
                tipo = 'over'
            elif 'under' in mercado_lower:
                tipo = 'under'
            else:
                continue
            
            # Extrai a linha (2.5, 3.5, 4.5, etc.)
            match = re.search(r'(\d+\.?\d*)', mercado)
            linha = float(match.group(1)) if match else 0.0
            
            previsoes.append(PrevisaoMercado(
                mercado=mercado,
                probabilidade=probabilidade,
                destaque=destaque,
                tipo=tipo,
                linha=linha
            ))
    
    return previsoes


def extrair_partidas_do_html(html_path: str) -> List[PartidaPrevisao]:
    """Extrai todas as partidas de um arquivo HTML de probabilidade."""
    partidas = []
    
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            conteudo = f.read()
        
        soup = BeautifulSoup(conteudo, 'html.parser')
        
        # Encontra todos os cards de jogo
        cards = soup.find_all(class_='jogo-card')
        
        for card in cards:
            try:
                # Título (times)
                titulo_elem = card.find(class_='jogo-titulo')
                titulo = titulo_elem.get_text(strip=True) if titulo_elem else ""
                
                # Extrai nomes dos times
                if ' vs ' in titulo:
                    partes = titulo.split(' vs ')
                    time_mandante = re.sub(r'\s*\(\d+º?\)\s*', '', partes[0]).strip()
                    time_visitante = re.sub(r'\s*\(\d+º?\)\s*', '', partes[1]).strip() if len(partes) > 1 else ""
                else:
                    time_mandante = titulo
                    time_visitante = ""
                
                # Data e horário
                data_elem = card.find(class_='jogo-data')
                data = ""
                horario = ""
                if data_elem:
                    horario_elem = data_elem.find(class_='horario')
                    data_dia_elem = data_elem.find(class_='data')
                    horario = horario_elem.get_text(strip=True) if horario_elem else ""
                    data = data_dia_elem.get_text(strip=True) if data_dia_elem else ""
                
                # Info bar (competição, árbitro, modelo)
                info_bar = card.find(class_='jogo-info-bar')
                competicao = ""
                arbitro = ""
                modelo = "Poisson"
                
                if info_bar:
                    for span in info_bar.find_all('span', recursive=False):
                        texto = span.get_text(strip=True)
                        valor_elem = span.find(class_='info-value')
                        if valor_elem:
                            valor = valor_elem.get_text(strip=True)
                            if 'Competição' in texto:
                                competicao = valor
                            elif 'Árbitro' in texto:
                                arbitro = valor
                            elif 'Modelo' in texto:
                                modelo = valor
                
                # Lambda
                lambda_previsto = 0.0
                lambda_text = card.find(string=re.compile(r'λ\s*='))
                if lambda_text:
                    match = re.search(r'λ\s*=\s*([\d.]+)', lambda_text)
                    if match:
                        lambda_previsto = float(match.group(1))
                
                # Alternativa: busca no calculo-resultado
                if lambda_previsto == 0:
                    resultado_elem = card.find(class_='calculo-resultado')
                    if resultado_elem and 'cartões' in resultado_elem.get_text():
                        lambda_previsto = extrair_valor_float(resultado_elem.get_text())
                
                # Extrai previsões
                previsoes = extrair_previsoes_do_card(card)
                
                partida = PartidaPrevisao(
                    time_mandante=time_mandante,
                    time_visitante=time_visitante,
                    data=data,
                    horario=horario,
                    competicao=competicao,
                    arbitro=arbitro,
                    lambda_previsto=lambda_previsto,
                    modelo=modelo,
                    previsoes=previsoes
                )
                
                partidas.append(partida)
                
            except Exception as e:
                print(f"      ⚠️ Erro ao extrair card: {e}")
                continue
        
        return partidas
        
    except Exception as e:
        print(f"   ❌ Erro ao ler arquivo: {e}")
        return []


# =============================================================================
# FUNÇÕES DE BUSCA NA API
# =============================================================================

def fazer_requisicao(url: str) -> Optional[dict]:
    """Faz uma requisição à API com tratamento de erros."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception:
        return None


def normalizar_nome_time(nome: str) -> str:
    """Normaliza o nome do time para comparação."""
    import unicodedata
    
    # Remove acentos
    nome = unicodedata.normalize('NFKD', nome)
    nome = ''.join(c for c in nome if not unicodedata.combining(c))
    
    # Converte para minúsculo e remove caracteres especiais
    nome = nome.lower()
    nome = re.sub(r'[^a-z0-9\s]', '', nome)
    
    # Remove sufixos comuns
    sufixos = ['fc', 'cf', 'sc', 'ac', 'ec', 'se', 'cr', 'rc', 'cd', 'ud', 'sd', 
               'club', 'city', 'united', 'athletic', 'atletico', 'real', 
               'sporting', 'deportivo', 'racing']
    palavras = nome.split()
    palavras = [p for p in palavras if p not in sufixos]
    
    return ' '.join(palavras).strip()


def buscar_partida_sofascore(time_mandante: str, time_visitante: str, data: str) -> Optional[dict]:
    """
    Busca uma partida na API do SofaScore.
    
    Args:
        time_mandante: Nome do time mandante
        time_visitante: Nome do time visitante
        data: Data no formato DD/MM/YYYY
    
    Returns:
        Dicionário com dados da partida ou None se não encontrar
    """
    try:
        # Converte data para formato da API (YYYY-MM-DD)
        data_obj = datetime.strptime(data, '%d/%m/%Y')
        data_api = data_obj.strftime('%Y-%m-%d')
        
        # Busca eventos do dia
        url = f"{BASE_URL}/sport/football/scheduled-events/{data_api}"
        dados = fazer_requisicao(url)
        
        if not dados or 'events' not in dados:
            return None
        
        # Normaliza nomes para comparação
        mandante_norm = normalizar_nome_time(time_mandante)
        visitante_norm = normalizar_nome_time(time_visitante)
        
        # Procura a partida - busca mais flexível
        melhor_match = None
        melhor_score = 0
        
        for evento in dados['events']:
            home_team = evento.get('homeTeam', {}).get('name', '')
            away_team = evento.get('awayTeam', {}).get('name', '')
            
            home_norm = normalizar_nome_time(home_team)
            away_norm = normalizar_nome_time(away_team)
            
            # Calcula score de similaridade
            score = 0
            
            # Match exato
            if mandante_norm == home_norm:
                score += 10
            elif mandante_norm in home_norm or home_norm in mandante_norm:
                score += 5
            else:
                # Match por palavras
                for p in mandante_norm.split():
                    if len(p) > 3 and p in home_norm:
                        score += 2
            
            if visitante_norm == away_norm:
                score += 10
            elif visitante_norm in away_norm or away_norm in visitante_norm:
                score += 5
            else:
                for p in visitante_norm.split():
                    if len(p) > 3 and p in away_norm:
                        score += 2
            
            if score > melhor_score:
                melhor_score = score
                melhor_match = evento
        
        # Retorna se score mínimo atingido
        if melhor_score >= 4:
            return melhor_match
        
        return None
        
    except Exception as e:
        # Não exibe erro detalhado para não poluir output
        return None


def buscar_cartoes_partida(event_id: int) -> Optional[int]:
    """
    Busca o total de cartões amarelos de uma partida.
    
    Args:
        event_id: ID do evento no SofaScore
    
    Returns:
        Total de cartões amarelos ou None se não encontrar
    """
    try:
        # Busca estatísticas da partida
        url = f"{BASE_URL}/event/{event_id}/statistics"
        dados = fazer_requisicao(url)
        
        if not dados or 'statistics' not in dados:
            return None
        
        # Procura por cartões amarelos
        for grupo in dados['statistics']:
            for item in grupo.get('groups', []):
                for stat in item.get('statisticsItems', []):
                    nome = stat.get('name', '').lower()
                    if 'yellow' in nome and 'card' in nome:
                        home = int(stat.get('home', 0) or 0)
                        away = int(stat.get('away', 0) or 0)
                        return home + away
        
        # Alternativa: busca nos incidentes
        url_incidents = f"{BASE_URL}/event/{event_id}/incidents"
        dados_incidents = fazer_requisicao(url_incidents)
        
        if dados_incidents and 'incidents' in dados_incidents:
            cartoes = 0
            for incident in dados_incidents['incidents']:
                tipo = incident.get('incidentType', '').lower()
                if tipo == 'card':
                    card_type = incident.get('incidentClass', '').lower()
                    if 'yellow' in card_type and 'red' not in card_type:
                        cartoes += 1
            if cartoes > 0:
                return cartoes
        
        return None
        
    except Exception:
        return None


def buscar_placar_partida(evento: dict) -> Optional[str]:
    """Extrai o placar de uma partida."""
    try:
        home_score = evento.get('homeScore', {}).get('current', 0)
        away_score = evento.get('awayScore', {}).get('current', 0)
        return f"{home_score} x {away_score}"
    except:
        return None


# =============================================================================
# FUNÇÕES DE VALIDAÇÃO
# =============================================================================

def validar_partida(partida: PartidaPrevisao) -> List[ResultadoValidacao]:
    """Valida as previsões de uma partida."""
    resultados = []
    
    if partida.cartoes_reais is None:
        return resultados
    
    for previsao in partida.previsoes:
        acertou = previsao.verificar_acerto(partida.cartoes_reais)
        
        # Calcula diferença
        if previsao.tipo == 'over':
            diferenca = partida.cartoes_reais - previsao.linha
        else:
            diferenca = previsao.linha - partida.cartoes_reais
        
        resultado = ResultadoValidacao(
            partida=partida,
            mercado=previsao,
            cartoes_reais=partida.cartoes_reais,
            acertou=acertou,
            diferenca=diferenca
        )
        
        resultados.append(resultado)
    
    return resultados


def gerar_relatorio(partidas: List[PartidaPrevisao], data_arquivo: str) -> RelatorioValidacao:
    """Gera o relatório de validação."""
    
    # Contadores gerais
    total_partidas = len(partidas)
    partidas_encontradas = sum(1 for p in partidas if p.status == "encontrado")
    partidas_nao_encontradas = total_partidas - partidas_encontradas
    
    # Valida todas as partidas
    todas_validacoes = []
    for partida in partidas:
        if partida.status == "encontrado":
            todas_validacoes.extend(validar_partida(partida))
    
    # Estatísticas de destaques (>= 55%)
    destaques_validacoes = [v for v in todas_validacoes if v.mercado.destaque]
    total_destaques = len(destaques_validacoes)
    destaques_acertos = sum(1 for v in destaques_validacoes if v.acertou)
    destaques_erros = total_destaques - destaques_acertos
    taxa_acerto_destaques = (destaques_acertos / total_destaques * 100) if total_destaques > 0 else 0.0
    
    # Estatísticas por mercado
    stats_por_mercado = defaultdict(lambda: {'total': 0, 'acertos': 0, 'taxa': 0.0})
    
    for v in todas_validacoes:
        mercado = v.mercado.mercado
        stats_por_mercado[mercado]['total'] += 1
        if v.acertou:
            stats_por_mercado[mercado]['acertos'] += 1
    
    # Calcula taxas
    for mercado, stats in stats_por_mercado.items():
        if stats['total'] > 0:
            stats['taxa'] = stats['acertos'] / stats['total'] * 100
    
    return RelatorioValidacao(
        data_arquivo=data_arquivo,
        total_partidas=total_partidas,
        partidas_encontradas=partidas_encontradas,
        partidas_nao_encontradas=partidas_nao_encontradas,
        total_destaques=total_destaques,
        destaques_acertos=destaques_acertos,
        destaques_erros=destaques_erros,
        taxa_acerto_destaques=taxa_acerto_destaques,
        stats_por_mercado=dict(stats_por_mercado),
        validacoes=todas_validacoes,
        partidas=partidas
    )


# =============================================================================
# GERAÇÃO DO HTML DO RELATÓRIO
# =============================================================================

def gerar_html_relatorio(relatorio: RelatorioValidacao) -> str:
    """Gera o HTML do relatório de validação."""
    
    timestamp = datetime.now().strftime('%d/%m/%Y %H:%M')
    
    # Cor da taxa de acerto
    if relatorio.taxa_acerto_destaques >= 60:
        cor_taxa = "#2ecc71"  # Verde
    elif relatorio.taxa_acerto_destaques >= 50:
        cor_taxa = "#f6e05e"  # Amarelo
    else:
        cor_taxa = "#e94560"  # Vermelho
    
    # Gera tabela de partidas
    tabela_partidas = ""
    for partida in relatorio.partidas:
        status_icon = "✅" if partida.status == "encontrado" else "❌"
        cartoes = str(partida.cartoes_reais) if partida.cartoes_reais is not None else "N/D"
        placar = partida.placar if partida.placar else "N/D"
        
        # Destaques da partida
        destaques = partida.get_destaques()
        destaques_html = ""
        for d in destaques:
            if partida.cartoes_reais is not None:
                acertou = d.verificar_acerto(partida.cartoes_reais)
                icon = "✅" if acertou else "❌"
                cor = "#2ecc71" if acertou else "#e94560"
            else:
                icon = "⏳"
                cor = "#a0a0a0"
            destaques_html += f'<span style="color: {cor}; margin-right: 10px;">{icon} {d.mercado} ({d.probabilidade:.1f}%)</span>'
        
        tabela_partidas += f"""
            <tr>
                <td>{status_icon}</td>
                <td>{partida.time_mandante} vs {partida.time_visitante}</td>
                <td>{partida.competicao}</td>
                <td>{partida.lambda_previsto:.2f}</td>
                <td style="font-weight: bold; color: #3498db;">{cartoes}</td>
                <td>{placar}</td>
                <td>{destaques_html}</td>
            </tr>
        """
    
    # Gera tabela de estatísticas por mercado
    tabela_mercados = ""
    for mercado, stats in sorted(relatorio.stats_por_mercado.items()):
        cor = "#2ecc71" if stats['taxa'] >= 50 else "#e94560"
        tabela_mercados += f"""
            <tr>
                <td>{mercado}</td>
                <td>{stats['total']}</td>
                <td>{stats['acertos']}</td>
                <td>{stats['total'] - stats['acertos']}</td>
                <td style="color: {cor}; font-weight: bold;">{stats['taxa']:.1f}%</td>
            </tr>
        """
    
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RefStats - Relatório de Validação {relatorio.data_arquivo}</title>
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
            min-height: 100vh;
            color: #e0e0e0;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
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
            font-size: 2.2em;
            margin-bottom: 10px;
        }}
        
        .header p {{
            color: #a0a0a0;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .stat-card {{
            background: linear-gradient(135deg, #16213e 0%, #1a1a2e 100%);
            padding: 25px;
            border-radius: 15px;
            text-align: center;
            border: 1px solid #0f3460;
        }}
        
        .stat-card.destaque {{
            border-color: {cor_taxa};
            box-shadow: 0 0 20px rgba(46, 204, 113, 0.2);
        }}
        
        .stat-valor {{
            font-size: 2.5em;
            font-weight: bold;
            color: #e94560;
        }}
        
        .stat-card.destaque .stat-valor {{
            color: {cor_taxa};
        }}
        
        .stat-label {{
            color: #a0a0a0;
            margin-top: 5px;
            font-size: 0.9em;
        }}
        
        .section {{
            background: linear-gradient(135deg, #16213e 0%, #1a1a2e 100%);
            padding: 25px;
            border-radius: 15px;
            margin-bottom: 30px;
            border: 1px solid #0f3460;
        }}
        
        .section-title {{
            color: #e94560;
            font-size: 1.4em;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #e94560;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9em;
        }}
        
        th {{
            background: #0f3460;
            color: #e0e0e0;
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }}
        
        td {{
            padding: 12px;
            border-bottom: 1px solid #0f3460;
        }}
        
        tr:hover {{
            background: rgba(15, 52, 96, 0.3);
        }}
        
        .footer {{
            background: linear-gradient(135deg, #0f3460 0%, #1a1a2e 100%);
            padding: 20px;
            border-radius: 15px;
            text-align: center;
            color: #a0a0a0;
            border: 1px solid #0f3460;
        }}
        
        .legenda {{
            background: rgba(52, 152, 219, 0.1);
            padding: 15px;
            border-radius: 8px;
            margin-top: 15px;
            font-size: 0.85em;
            color: #a0a0a0;
        }}
        
        .interpretacao {{
            background: rgba(233, 69, 96, 0.1);
            border-left: 4px solid #e94560;
            padding: 20px;
            border-radius: 0 10px 10px 0;
            margin-top: 20px;
        }}
        
        .interpretacao h3 {{
            color: #e94560;
            margin-bottom: 10px;
        }}
        
        .tag-acerto {{
            background: #2ecc71;
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.8em;
        }}
        
        .tag-erro {{
            background: #e94560;
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.8em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Relatório de Validação</h1>
            <p>📅 Partidas de {relatorio.data_arquivo}</p>
            <p style="margin-top: 5px;">Gerado em {timestamp}</p>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-valor">{relatorio.total_partidas}</div>
                <div class="stat-label">Total de Partidas</div>
            </div>
            <div class="stat-card">
                <div class="stat-valor">{relatorio.partidas_encontradas}</div>
                <div class="stat-label">Partidas Validadas</div>
            </div>
            <div class="stat-card">
                <div class="stat-valor">{relatorio.total_destaques}</div>
                <div class="stat-label">Previsões em Destaque</div>
            </div>
            <div class="stat-card destaque">
                <div class="stat-valor">{relatorio.taxa_acerto_destaques:.1f}%</div>
                <div class="stat-label">Taxa de Acerto (Destaques)</div>
            </div>
        </div>
        
        <div class="section">
            <div class="section-title">📈 Resumo dos Destaques (≥ 55%)</div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-valor" style="color: #2ecc71;">{relatorio.destaques_acertos}</div>
                    <div class="stat-label">✅ Acertos</div>
                </div>
                <div class="stat-card">
                    <div class="stat-valor" style="color: #e94560;">{relatorio.destaques_erros}</div>
                    <div class="stat-label">❌ Erros</div>
                </div>
            </div>
            
            <div class="interpretacao">
                <h3>🧠 Interpretação</h3>
                <p>
                    Das <strong>{relatorio.total_destaques}</strong> previsões marcadas como destaque (probabilidade ≥ 55%),
                    <strong>{relatorio.destaques_acertos}</strong> acertaram o resultado, 
                    representando uma taxa de acerto de <strong style="color: {cor_taxa};">{relatorio.taxa_acerto_destaques:.1f}%</strong>.
                </p>
                <p style="margin-top: 10px; font-size: 0.9em; color: #a0a0a0;">
                    ℹ️ Para um modelo probabilístico, espera-se que previsões com 55-65% de probabilidade 
                    acertem aproximadamente 55-65% das vezes no longo prazo.
                </p>
            </div>
        </div>
        
        <div class="section">
            <div class="section-title">📊 Estatísticas por Mercado</div>
            
            <table>
                <thead>
                    <tr>
                        <th>Mercado</th>
                        <th>Total</th>
                        <th>Acertos</th>
                        <th>Erros</th>
                        <th>Taxa</th>
                    </tr>
                </thead>
                <tbody>
                    {tabela_mercados}
                </tbody>
            </table>
        </div>
        
        <div class="section">
            <div class="section-title">⚽ Detalhes por Partida</div>
            
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr>
                            <th>Status</th>
                            <th>Partida</th>
                            <th>Competição</th>
                            <th>λ Previsto</th>
                            <th>Cartões Reais</th>
                            <th>Placar</th>
                            <th>Destaques</th>
                        </tr>
                    </thead>
                    <tbody>
                        {tabela_partidas}
                    </tbody>
                </table>
            </div>
            
            <div class="legenda">
                <strong>Legenda:</strong><br>
                ✅ = Previsão correta | ❌ = Previsão incorreta | ⏳ = Aguardando dados<br>
                <strong>Destaque:</strong> Previsões com probabilidade ≥ 55% (marcadas em verde no arquivo original)
            </div>
        </div>
        
        <div class="footer">
            <p><strong>📊 RefStats - Sistema de Validação de Probabilidades</strong></p>
            <p style="margin-top: 10px; font-size: 0.85em;">
                Dados obtidos via SofaScore API • {timestamp}
            </p>
            <p style="margin-top: 10px; font-size: 0.8em; color: #e94560;">
                ⚠️ Este relatório é para fins de análise e validação do modelo estatístico.
            </p>
        </div>
    </div>
</body>
</html>
"""
    
    return html


# =============================================================================
# FUNÇÃO PRINCIPAL
# =============================================================================

def processar_arquivo_probabilidade(caminho: str, pasta_saida: str) -> Optional[RelatorioValidacao]:
    """Processa um arquivo de probabilidade e gera relatório."""
    
    nome_arquivo = os.path.basename(caminho)
    print(f"\n{'='*60}")
    print(f"📂 Processando: {nome_arquivo}")
    print(f"{'='*60}")
    
    # Extrai data do nome do arquivo
    match = re.search(r'(\d{2})(\d{2})(\d{4})', nome_arquivo)
    if match:
        data_arquivo = f"{match.group(1)}/{match.group(2)}/{match.group(3)}"
    else:
        data_arquivo = "Data desconhecida"
    
    # Extrai partidas do HTML
    partidas = extrair_partidas_do_html(caminho)
    
    if not partidas:
        print("   ⚠️ Nenhuma partida encontrada no arquivo")
        return None
    
    print(f"   ✅ {len(partidas)} partida(s) encontrada(s)")
    
    # Busca dados reais para cada partida
    print("\n   🔍 Buscando resultados reais...")
    
    for i, partida in enumerate(partidas, 1):
        print(f"      [{i}/{len(partidas)}] {partida.time_mandante} vs {partida.time_visitante}...", end=" ")
        
        # Busca a partida na API
        evento = buscar_partida_sofascore(
            partida.time_mandante,
            partida.time_visitante,
            partida.data
        )
        
        if evento:
            event_id = evento.get('id')
            status = evento.get('status', {}).get('type', '')
            
            # Só busca cartões se o jogo já terminou
            if status == 'finished':
                cartoes = buscar_cartoes_partida(event_id)
                placar = buscar_placar_partida(evento)
                
                if cartoes is not None:
                    partida.cartoes_reais = cartoes
                    partida.placar = placar
                    partida.status = "encontrado"
                    print(f"✅ {cartoes} cartões ({placar})")
                else:
                    partida.status = "encontrado"
                    partida.placar = placar
                    print(f"⚠️ Cartões não disponíveis ({placar})")
            else:
                print(f"⏳ Jogo não finalizado ({status})")
                partida.status = "pendente"
        else:
            print("❌ Não encontrado")
            partida.status = "não encontrado"
        
        time.sleep(REQUEST_DELAY)
    
    # Gera relatório
    print("\n   📊 Gerando relatório...")
    relatorio = gerar_relatorio(partidas, data_arquivo)
    
    # Gera HTML
    html = gerar_html_relatorio(relatorio)
    
    # Salva arquivo
    os.makedirs(pasta_saida, exist_ok=True)
    
    nome_saida = nome_arquivo.replace('PROBABILIDADE_', 'RELATORIO_').replace('.html', '_validacao.html')
    caminho_saida = os.path.join(pasta_saida, nome_saida)
    
    with open(caminho_saida, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"\n   ✅ Relatório salvo: {caminho_saida}")
    
    # Resumo
    print(f"\n   📈 RESUMO:")
    print(f"      • Partidas validadas: {relatorio.partidas_encontradas}/{relatorio.total_partidas}")
    print(f"      • Destaques: {relatorio.destaques_acertos}/{relatorio.total_destaques} acertos")
    print(f"      • Taxa de acerto: {relatorio.taxa_acerto_destaques:.1f}%")
    
    return relatorio


def main():
    """Função principal."""
    print("""
╔═══════════════════════════════════════════════════════════════╗
║     SISTEMA DE VALIDAÇÃO DE PROBABILIDADES                    ║
║                     Backtesting                               ║
╚═══════════════════════════════════════════════════════════════╝
    """)
    
    # Define as pastas
    pasta_atual = os.path.dirname(os.path.abspath(__file__))
    pasta_probabilidade = os.path.join(pasta_atual, "Probabilidade")
    pasta_relatorio = os.path.join(pasta_probabilidade, "Relatorio")
    
    print(f"📁 Pasta de entrada: {pasta_probabilidade}")
    print(f"📁 Pasta de saída: {pasta_relatorio}")
    
    # Verifica se a pasta existe
    if not os.path.exists(pasta_probabilidade):
        print(f"\n⚠️ Pasta 'Probabilidade' não encontrada!")
        print(f"   Crie a pasta e coloque os arquivos PROBABILIDADE_*.html")
        return
    
    # Busca arquivos
    padrao = os.path.join(pasta_probabilidade, "PROBABILIDADE_*.html")
    arquivos = glob.glob(padrao)
    
    if not arquivos:
        print(f"\n⚠️ Nenhum arquivo PROBABILIDADE_*.html encontrado")
        return
    
    print(f"\n📋 Arquivos encontrados: {len(arquivos)}")
    
    # Pergunta o modo de operação
    print("\n🔧 Modo de operação:")
    print("   [1] Automático (busca via API SofaScore)")
    print("   [2] Manual (entrada de resultados pelo usuário)")
    print("   [3] Arquivo CSV (importar resultados de um CSV)")
    
    modo = input("\n   Escolha [1/2/3] (ENTER para automático): ").strip()
    
    if modo == "2":
        processar_modo_manual(arquivos, pasta_relatorio)
    elif modo == "3":
        processar_modo_csv(arquivos, pasta_relatorio)
    else:
        processar_modo_automatico(arquivos, pasta_relatorio)


def processar_modo_automatico(arquivos: list, pasta_saida: str):
    """Processa arquivos no modo automático (API)."""
    relatorios = []
    
    for arquivo in sorted(arquivos):
        relatorio = processar_arquivo_probabilidade(arquivo, pasta_saida)
        if relatorio:
            relatorios.append(relatorio)
    
    exibir_resumo_final(relatorios)


def processar_modo_manual(arquivos: list, pasta_saida: str):
    """Processa arquivos no modo manual (entrada pelo usuário)."""
    
    for arquivo in sorted(arquivos):
        nome_arquivo = os.path.basename(arquivo)
        print(f"\n{'='*60}")
        print(f"📂 Arquivo: {nome_arquivo}")
        print(f"{'='*60}")
        
        # Extrai data do nome do arquivo
        match = re.search(r'(\d{2})(\d{2})(\d{4})', nome_arquivo)
        if match:
            data_arquivo = f"{match.group(1)}/{match.group(2)}/{match.group(3)}"
        else:
            data_arquivo = "Data desconhecida"
        
        # Extrai partidas
        partidas = extrair_partidas_do_html(arquivo)
        
        if not partidas:
            print("   ⚠️ Nenhuma partida encontrada")
            continue
        
        print(f"\n   📝 Digite os resultados (cartões) ou ENTER para pular:")
        print(f"   (Digite 'q' para finalizar este arquivo)\n")
        
        for i, partida in enumerate(partidas, 1):
            prompt = f"   [{i}/{len(partidas)}] {partida.time_mandante} vs {partida.time_visitante}: "
            resultado = input(prompt).strip()
            
            if resultado.lower() == 'q':
                break
            
            if resultado.isdigit():
                partida.cartoes_reais = int(resultado)
                partida.status = "encontrado"
                print(f"            ✅ {resultado} cartões registrados")
            elif resultado:
                # Tenta extrair número do texto
                numeros = re.findall(r'\d+', resultado)
                if numeros:
                    partida.cartoes_reais = int(numeros[0])
                    partida.status = "encontrado"
                    print(f"            ✅ {numeros[0]} cartões registrados")
                else:
                    print(f"            ⏭️ Pulando")
            else:
                print(f"            ⏭️ Pulando")
        
        # Gera relatório
        print("\n   📊 Gerando relatório...")
        relatorio = gerar_relatorio(partidas, data_arquivo)
        html = gerar_html_relatorio(relatorio)
        
        # Salva
        os.makedirs(pasta_saida, exist_ok=True)
        nome_saida = nome_arquivo.replace('PROBABILIDADE_', 'RELATORIO_').replace('.html', '_validacao.html')
        caminho_saida = os.path.join(pasta_saida, nome_saida)
        
        with open(caminho_saida, 'w', encoding='utf-8') as f:
            f.write(html)
        
        print(f"\n   ✅ Relatório salvo: {caminho_saida}")
        
        # Resumo
        if relatorio.total_destaques > 0:
            print(f"\n   📈 RESUMO:")
            print(f"      • Partidas validadas: {relatorio.partidas_encontradas}/{relatorio.total_partidas}")
            print(f"      • Destaques: {relatorio.destaques_acertos}/{relatorio.total_destaques} acertos")
            print(f"      • Taxa de acerto: {relatorio.taxa_acerto_destaques:.1f}%")


def processar_modo_csv(arquivos: list, pasta_saida: str):
    """Processa arquivos usando um CSV com resultados."""
    
    pasta_atual = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(pasta_atual, "resultados.csv")
    
    print(f"\n📄 Procurando arquivo de resultados: {csv_path}")
    
    if not os.path.exists(csv_path):
        print(f"\n⚠️ Arquivo 'resultados.csv' não encontrado!")
        print(f"\n   Crie um arquivo CSV com o formato:")
        print(f"   data,mandante,visitante,cartoes,placar")
        print(f"   01/12/2025,Rayo Vallecano,Valencia,5,2x1")
        print(f"   01/12/2025,Bologna,Cremonese,4,1x0")
        
        # Cria template
        template = "data,mandante,visitante,cartoes,placar\n"
        template += "# Preencha abaixo (linhas começando com # são ignoradas)\n"
        
        for arquivo in arquivos:
            partidas = extrair_partidas_do_html(arquivo)
            for p in partidas:
                template += f"{p.data},{p.time_mandante},{p.time_visitante},,\n"
        
        with open(csv_path, 'w', encoding='utf-8') as f:
            f.write(template)
        
        print(f"\n   ✅ Template criado: {csv_path}")
        print(f"   Preencha os resultados e execute novamente.")
        return
    
    # Carrega resultados do CSV
    resultados = {}
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            for linha in f:
                linha = linha.strip()
                if not linha or linha.startswith('#'):
                    continue
                
                partes = linha.split(',')
                if len(partes) >= 4 and partes[3].strip().isdigit():
                    chave = f"{partes[1].strip().lower()}_{partes[2].strip().lower()}_{partes[0].strip()}"
                    resultados[chave] = {
                        'cartoes': int(partes[3].strip()),
                        'placar': partes[4].strip() if len(partes) > 4 else None
                    }
    except Exception as e:
        print(f"   ❌ Erro ao ler CSV: {e}")
        return
    
    print(f"   ✅ {len(resultados)} resultados carregados do CSV")
    
    # Processa arquivos
    relatorios = []
    
    for arquivo in sorted(arquivos):
        nome_arquivo = os.path.basename(arquivo)
        print(f"\n{'='*60}")
        print(f"📂 Processando: {nome_arquivo}")
        print(f"{'='*60}")
        
        # Extrai data
        match = re.search(r'(\d{2})(\d{2})(\d{4})', nome_arquivo)
        if match:
            data_arquivo = f"{match.group(1)}/{match.group(2)}/{match.group(3)}"
        else:
            data_arquivo = "Data desconhecida"
        
        partidas = extrair_partidas_do_html(arquivo)
        
        if not partidas:
            continue
        
        print(f"   ✅ {len(partidas)} partida(s) encontrada(s)")
        
        # Aplica resultados do CSV
        for partida in partidas:
            chave = f"{partida.time_mandante.lower()}_{partida.time_visitante.lower()}_{partida.data}"
            
            if chave in resultados:
                partida.cartoes_reais = resultados[chave]['cartoes']
                partida.placar = resultados[chave]['placar']
                partida.status = "encontrado"
            else:
                # Tenta match parcial
                for k, v in resultados.items():
                    if (partida.time_mandante.lower()[:5] in k and 
                        partida.time_visitante.lower()[:5] in k):
                        partida.cartoes_reais = v['cartoes']
                        partida.placar = v['placar']
                        partida.status = "encontrado"
                        break
        
        # Conta encontrados
        encontrados = sum(1 for p in partidas if p.status == "encontrado")
        print(f"   📊 {encontrados}/{len(partidas)} partidas com resultado no CSV")
        
        # Gera relatório
        relatorio = gerar_relatorio(partidas, data_arquivo)
        html = gerar_html_relatorio(relatorio)
        
        os.makedirs(pasta_saida, exist_ok=True)
        nome_saida = nome_arquivo.replace('PROBABILIDADE_', 'RELATORIO_').replace('.html', '_validacao.html')
        caminho_saida = os.path.join(pasta_saida, nome_saida)
        
        with open(caminho_saida, 'w', encoding='utf-8') as f:
            f.write(html)
        
        print(f"   ✅ Relatório salvo: {caminho_saida}")
        relatorios.append(relatorio)
    
    exibir_resumo_final(relatorios)


def exibir_resumo_final(relatorios: list):
    """Exibe o resumo final de todos os relatórios."""
    if relatorios:
        total_destaques = sum(r.total_destaques for r in relatorios)
        total_acertos = sum(r.destaques_acertos for r in relatorios)
        taxa_geral = (total_acertos / total_destaques * 100) if total_destaques > 0 else 0
        
        print(f"""
╔═══════════════════════════════════════════════════════════════╗
║                    RESUMO GERAL                               ║
╠═══════════════════════════════════════════════════════════════╣
║  📁 Arquivos processados: {len(relatorios):3d}                              ║
║  🎯 Total de destaques: {total_destaques:4d}                               ║
║  ✅ Acertos: {total_acertos:4d}                                            ║
║  📈 Taxa de acerto geral: {taxa_geral:5.1f}%                            ║
╚═══════════════════════════════════════════════════════════════╝
        """)
    
    print("\n✅ Processamento concluído!")


if __name__ == "__main__":
    main()
