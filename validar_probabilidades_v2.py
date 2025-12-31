#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
SISTEMA DE VALIDAÇÃO DE PROBABILIDADES - V2.0
=============================================================================
Autor: RefStats
Versão: 2.0

COMPATÍVEL COM:
    - HTML V2.0 (Neg. Binomial + Shrinkage + Calibração)
    - Extrai p_raw e p_calibrado
    - Extrai intervalos de confiança [P10, P50, P90]
    - Extrai λ_shrunk e qualidade dos dados
    - Identifica bloqueios (variância, qualidade)

MÉTRICAS DE AVALIAÇÃO:
    - Taxa de acerto (por mercado e geral)
    - Brier Score (calibração)
    - Log Loss (discriminação)
    - Curva de confiabilidade por bins
    - Análise de destaques vs bloqueados

SISTEMA DE APRENDIZADO:
    - Coleta dados estruturados de cada validação
    - Descobre Regras de Ouro automaticamente
    - Regras com ≥75% de acerto são destacadas

ESTRUTURA DE PASTAS:
    /Probabilidade/                    → Arquivos de entrada (PROBABILIDADE_*.html)
    /Probabilidade/Relatorio/          → Relatórios de validação gerados
    /Calibracao/                       → Dados de calibração e aprendizado
=============================================================================
"""

import os
import re
import glob
import json
import math
import time
import requests
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from bs4 import BeautifulSoup
from collections import defaultdict

# Importa módulo de aprendizado
try:
    from aprendizado_avancado import (
        obter_banco_aprendizado,
        obter_motor_aprendizado,
        retreinar_regras,
        criar_dados_partida_aprendizado,
        criar_resultado_mercado_aprendizado,
        RegistroAprendizado,
        RegraDeOuro,
        gerar_guia_metodologia_html,
        gerar_css_guia
    )
    APRENDIZADO_DISPONIVEL = True
except ImportError:
    APRENDIZADO_DISPONIVEL = False
    print("⚠️ Módulo de aprendizado não encontrado. Funcionalidade limitada.")


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

REQUEST_DELAY = 1.0


# =============================================================================
# CLASSES DE DADOS
# =============================================================================

@dataclass
class PrevisaoMercadoV2:
    """Representa uma previsão de mercado V2.0."""
    mercado: str                    # Ex: "Over 2.5 Cartões"
    tipo: str                       # "over" ou "under"
    linha: float                    # 2.5, 3.5, etc.
    
    p_raw: float                    # Probabilidade raw (%)
    p_calibrado: float              # Probabilidade calibrada (%)
    
    eh_destaque: bool               # Classe "destaque"
    eh_bloqueado: bool              # Classe "bloqueado"
    motivo_bloqueio: str = ""       # "variância" ou "qualidade"
    
    def verificar_acerto(self, cartoes_reais: int) -> bool:
        """Verifica se a previsão acertou."""
        if self.tipo == "over":
            return cartoes_reais > self.linha
        else:
            return cartoes_reais <= self.linha


@dataclass
class IntervaloConfiancaV2:
    """Intervalo de confiança extraído do HTML."""
    p10: int
    p50: int
    p90: int
    variancia_alta: bool = False


@dataclass
class PartidaPrevisaoV2:
    """Representa uma partida com suas previsões V2.0."""
    time_mandante: str
    time_visitante: str
    data: str
    horario: str
    competicao: str
    arbitro: str
    
    # Dados V2.0
    lambda_shrunk: float
    tendencia: str                  # ELEVADA, MODERADA, BAIXA
    qualidade_score: float          # 0-100
    modelo: str                     # "Negative Binomial" ou "Poisson"
    
    # Dados extras para aprendizado
    media_arbitro_5j: float = 0.0
    media_arbitro_10j: float = 0.0
    perfil_arbitro: str = "Médio"
    
    # NOVOS - Dados de cálculo para aprendizado expandido
    delta_arbitro: float = 0.0
    delta_times: float = 0.0
    peso_shrinkage: float = 0.5
    soma_cartoes_times: float = 0.0
    completude_arbitro: float = 0.0
    lambda_raw: float = 0.0
    
    # Intervalo
    intervalo: IntervaloConfiancaV2 = None
    
    # Previsões
    previsoes: List[PrevisaoMercadoV2] = field(default_factory=list)
    
    # Dados reais (preenchidos após busca)
    cartoes_reais: Optional[int] = None
    placar: Optional[str] = None
    status: str = "pendente"
    
    # Regras de ouro ativadas
    regras_ativadas: List[any] = field(default_factory=list)
    
    def get_destaques(self) -> List[PrevisaoMercadoV2]:
        """Retorna apenas as previsões com destaque."""
        return [p for p in self.previsoes if p.eh_destaque]
    
    def get_bloqueados(self) -> List[PrevisaoMercadoV2]:
        """Retorna previsões bloqueadas."""
        return [p for p in self.previsoes if p.eh_bloqueado]


@dataclass
class ResultadoValidacaoV2:
    """Resultado da validação de uma previsão V2.0."""
    partida: PartidaPrevisaoV2
    mercado: PrevisaoMercadoV2
    cartoes_reais: int
    acertou: bool
    
    # Para métricas
    p_usado: float                  # p_calibrado usado para avaliação
    outcome: int                    # 1 se acertou, 0 se errou


@dataclass
class MetricasAvaliacao:
    """Métricas de avaliação do modelo."""
    # Básicas
    total_previsoes: int
    acertos: int
    erros: int
    taxa_acerto: float
    
    # Calibração
    brier_score: float              # Quanto menor, melhor (0 = perfeito)
    log_loss: float                 # Quanto menor, melhor
    
    # Por bins de probabilidade
    calibracao_por_bin: Dict[str, Dict] = field(default_factory=dict)


@dataclass
class RelatorioValidacaoV2:
    """Relatório completo de validação V2.0."""
    data_arquivo: str
    total_partidas: int
    partidas_encontradas: int
    partidas_nao_encontradas: int
    
    # Estatísticas de destaques
    total_destaques: int
    destaques_acertos: int
    destaques_erros: int
    taxa_acerto_destaques: float
    
    # Estatísticas de bloqueados
    total_bloqueados: int
    bloqueados_acertos: int         # Se não estivesse bloqueado, teria acertado?
    bloqueados_evitados: int        # Erros evitados pelo bloqueio
    
    # Métricas por mercado
    metricas_por_mercado: Dict[str, MetricasAvaliacao] = field(default_factory=dict)
    
    # Métricas gerais
    metricas_gerais: MetricasAvaliacao = None
    
    # Detalhes
    validacoes: List[ResultadoValidacaoV2] = field(default_factory=list)
    partidas: List[PartidaPrevisaoV2] = field(default_factory=list)


# =============================================================================
# FUNÇÕES DE EXTRAÇÃO DO HTML V2.0
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


def extrair_intervalo(card) -> IntervaloConfiancaV2:
    """Extrai o intervalo de confiança do card."""
    p10, p50, p90 = 0, 0, 0
    variancia_alta = False
    
    # Busca os elementos de intervalo
    p10_elem = card.find(class_='intervalo-p10')
    p50_elem = card.find(class_='intervalo-p50')
    p90_elem = card.find(class_='intervalo-p90')
    
    if p10_elem:
        div = p10_elem.find('div')
        if div:
            p10 = int(extrair_valor_float(div.get_text()))
    
    if p50_elem:
        div = p50_elem.find('div')
        if div:
            p50 = int(extrair_valor_float(div.get_text()))
    
    if p90_elem:
        div = p90_elem.find('div')
        if div:
            p90 = int(extrair_valor_float(div.get_text()))
    
    # Verifica aviso de variância alta
    aviso = card.find(class_='intervalo-aviso')
    if aviso:
        variancia_alta = True
    
    return IntervaloConfiancaV2(
        p10=p10,
        p50=p50,
        p90=p90,
        variancia_alta=variancia_alta
    )


def extrair_previsoes_v2(card) -> List[PrevisaoMercadoV2]:
    """Extrai as previsões de probabilidade de um card V2.0."""
    previsoes = []
    
    prob_cards = card.find_all(class_='prob-card')
    
    for prob_card in prob_cards:
        # Classes
        classes = prob_card.get('class', [])
        eh_destaque = 'destaque' in classes
        eh_bloqueado = 'bloqueado' in classes
        
        # Mercado
        mercado_elem = prob_card.find(class_='prob-mercado')
        if not mercado_elem:
            continue
        mercado = mercado_elem.get_text(strip=True)
        
        # p_raw
        raw_elem = prob_card.find(class_='prob-raw')
        p_raw = 0.0
        if raw_elem:
            p_raw = extrair_valor_float(raw_elem.get_text())
        
        # p_calibrado
        calibrado_elem = prob_card.find(class_='prob-calibrado')
        p_calibrado = 0.0
        if calibrado_elem:
            p_calibrado = extrair_valor_float(calibrado_elem.get_text())
        
        # Tipo e linha
        mercado_lower = mercado.lower()
        if 'over' in mercado_lower:
            tipo = 'over'
        elif 'under' in mercado_lower:
            tipo = 'under'
        else:
            continue
        
        match = re.search(r'(\d+\.?\d*)', mercado)
        linha = float(match.group(1)) if match else 0.0
        
        # Motivo do bloqueio
        motivo_bloqueio = ""
        if eh_bloqueado:
            bloqueio_elem = prob_card.find(class_='prob-bloqueio')
            if bloqueio_elem:
                texto = bloqueio_elem.get_text().lower()
                if 'variância' in texto or 'variancia' in texto:
                    motivo_bloqueio = "variância"
                elif 'qualidade' in texto or 'dados' in texto:
                    motivo_bloqueio = "qualidade"
                else:
                    motivo_bloqueio = "outro"
        
        previsoes.append(PrevisaoMercadoV2(
            mercado=mercado,
            tipo=tipo,
            linha=linha,
            p_raw=p_raw,
            p_calibrado=p_calibrado,
            eh_destaque=eh_destaque,
            eh_bloqueado=eh_bloqueado,
            motivo_bloqueio=motivo_bloqueio
        ))
    
    return previsoes


def extrair_partidas_v2(html_path: str) -> List[PartidaPrevisaoV2]:
    """Extrai todas as partidas de um arquivo HTML V2.0."""
    partidas = []
    
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            conteudo = f.read()
        
        soup = BeautifulSoup(conteudo, 'html.parser')
        cards = soup.find_all(class_='jogo-card')
        
        for card in cards:
            try:
                # Título (times)
                titulo_elem = card.find(class_='jogo-titulo')
                titulo = titulo_elem.get_text(strip=True) if titulo_elem else ""
                
                # Limpa emojis
                titulo = re.sub(r'[🏠✈️⚽🏆📊🎯📈]', '', titulo).strip()
                
                if ' vs ' in titulo:
                    partes = titulo.split(' vs ')
                    time_mandante = re.sub(r'\s*\([^)]*\)\s*', '', partes[0]).strip()
                    time_visitante = re.sub(r'\s*\([^)]*\)\s*', '', partes[1]).strip() if len(partes) > 1 else ""
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
                
                # Info bar
                info_bar = card.find(class_='jogo-info-bar')
                competicao = ""
                arbitro = ""
                lambda_shrunk = 0.0
                tendencia = "MODERADA"
                
                if info_bar:
                    spans = info_bar.find_all('span', recursive=False)
                    for span in spans:
                        texto = span.get_text()
                        valor_elem = span.find(class_='info-value')
                        if valor_elem:
                            valor = valor_elem.get_text(strip=True)
                            if '🏆' in texto:
                                competicao = valor
                            elif '⚖️' in texto:
                                arbitro = valor
                            elif '📊' in texto or 'λ' in texto:
                                match = re.search(r'[\d.]+', valor)
                                if match:
                                    lambda_shrunk = float(match.group())
                            elif '📈' in texto:
                                tendencia = valor
                
                # Qualidade dos dados
                qualidade_score = 0.0
                qualidade_box = card.find(class_='qualidade-box')
                if qualidade_box:
                    score_elem = qualidade_box.find(class_='qualidade-score-valor')
                    if score_elem:
                        qualidade_score = extrair_valor_float(score_elem.get_text())
                
                # Modelo
                modelo = "Negative Binomial"
                modelo_box = card.find(class_='modelo-box')
                if modelo_box:
                    titulo_modelo = modelo_box.find(class_='calculo-titulo')
                    if titulo_modelo:
                        texto = titulo_modelo.get_text()
                        if 'Poisson' in texto and 'Negative' not in texto:
                            modelo = "Poisson"
                
                # Lambda do texto (fallback)
                if lambda_shrunk == 0:
                    texto_lambda = card.find(string=re.compile(r'λ_shrunk\s*=\s*[\d.]+'))
                    if texto_lambda:
                        match = re.search(r'λ_shrunk\s*=\s*([\d.]+)', texto_lambda)
                        if match:
                            lambda_shrunk = float(match.group(1))
                
                # DADOS EXTRAS PARA APRENDIZADO
                media_arbitro_5j = 0.0
                media_arbitro_10j = 0.0
                perfil_arbitro = "Médio"
                
                # NOVOS - Dados de cálculo
                delta_arbitro = 0.0
                delta_times = 0.0
                peso_shrinkage = 0.5
                soma_cartoes_times = 0.0
                completude_arbitro = 0.0
                lambda_raw = 0.0
                
                # Tenta extrair do texto do cálculo
                texto_calculo = card.get_text()
                
                # Busca média 5j (formato: 0.6 × 4.4)
                match_5j = re.search(r'0\.6\s*×\s*([\d.]+)', texto_calculo)
                if match_5j:
                    media_arbitro_5j = float(match_5j.group(1))
                
                # Busca média 10j (formato: 0.4 × 4.7)
                match_10j = re.search(r'0\.4\s*×\s*([\d.]+)', texto_calculo)
                if match_10j:
                    media_arbitro_10j = float(match_10j.group(1))
                
                # Busca perfil do árbitro
                perfil_match = re.search(r'(Rigoroso|Permissivo|Médio)', texto_calculo)
                if perfil_match:
                    perfil_arbitro = perfil_match.group(1)
                
                # Busca Δ_arbitro (formato: Δ_arbitro = ... = +0.15 ou -0.15)
                delta_arb_match = re.search(r'Δ_arbitro\s*=.*?=\s*([+-]?[\d.]+)', texto_calculo)
                if delta_arb_match:
                    delta_arbitro = float(delta_arb_match.group(1))
                
                # Busca Δ_times (formato: Δ_times = ... = +0.15 ou -0.15)
                delta_times_match = re.search(r'Δ_times\s*=.*?=\s*([+-]?[\d.]+)', texto_calculo)
                if delta_times_match:
                    delta_times = float(delta_times_match.group(1))
                
                # Busca peso shrinkage (formato: Peso (w) 0.51)
                shrinkage_box = card.find(class_='shrinkage-box')
                if shrinkage_box:
                    items = shrinkage_box.find_all(class_='shrinkage-item')
                    for item in items:
                        label = item.find(class_='shrinkage-label')
                        valor = item.find(class_='shrinkage-valor')
                        if label and valor:
                            label_texto = label.get_text().lower()
                            if 'peso' in label_texto or 'w' in label_texto:
                                peso_shrinkage = extrair_valor_float(valor.get_text())
                            elif 'raw' in label_texto:
                                lambda_raw = extrair_valor_float(valor.get_text())
                
                # Busca soma cartões times (formato: soma_cartões = 2.00 + 1.20 = 3.20)
                soma_match = re.search(r'soma_cart[oõ]es\s*=\s*[\d.]+\s*\+\s*[\d.]+\s*=\s*([\d.]+)', texto_calculo)
                if soma_match:
                    soma_cartoes_times = float(soma_match.group(1))
                
                # Busca completude árbitro
                if qualidade_box:
                    itens = qualidade_box.find_all(class_='qualidade-item')
                    for item in itens:
                        texto_item = item.get_text()
                        if 'Completude Árbitro' in texto_item:
                            # Pega o segundo span (o valor)
                            spans = item.find_all('span')
                            if len(spans) >= 2:
                                completude_arbitro = extrair_valor_float(spans[1].get_text())
                
                # Intervalo de confiança
                intervalo = extrair_intervalo(card)
                
                # Previsões
                previsoes = extrair_previsoes_v2(card)
                
                partida = PartidaPrevisaoV2(
                    time_mandante=time_mandante,
                    time_visitante=time_visitante,
                    data=data,
                    horario=horario,
                    competicao=competicao,
                    arbitro=arbitro,
                    lambda_shrunk=lambda_shrunk,
                    tendencia=tendencia,
                    qualidade_score=qualidade_score,
                    modelo=modelo,
                    media_arbitro_5j=media_arbitro_5j,
                    media_arbitro_10j=media_arbitro_10j,
                    perfil_arbitro=perfil_arbitro,
                    # Novos campos
                    delta_arbitro=delta_arbitro,
                    delta_times=delta_times,
                    peso_shrinkage=peso_shrinkage,
                    soma_cartoes_times=soma_cartoes_times,
                    completude_arbitro=completude_arbitro,
                    lambda_raw=lambda_raw,
                    intervalo=intervalo,
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
    
    nome = unicodedata.normalize('NFKD', nome)
    nome = ''.join(c for c in nome if not unicodedata.combining(c))
    nome = nome.lower()
    nome = re.sub(r'[^a-z0-9\s]', '', nome)
    
    sufixos = ['fc', 'cf', 'sc', 'ac', 'ec', 'se', 'cr', 'rc', 'cd', 'ud', 'sd', 
               'club', 'city', 'united', 'athletic', 'atletico', 'real', 
               'sporting', 'deportivo', 'racing']
    palavras = nome.split()
    palavras = [p for p in palavras if p not in sufixos]
    
    return ' '.join(palavras).strip()


def buscar_partida_sofascore(time_mandante: str, time_visitante: str, data: str) -> Optional[dict]:
    """Busca uma partida na API do SofaScore."""
    try:
        data_obj = datetime.strptime(data, '%d/%m/%Y')
        data_api = data_obj.strftime('%Y-%m-%d')
        
        url = f"{BASE_URL}/sport/football/scheduled-events/{data_api}"
        dados = fazer_requisicao(url)
        
        if not dados or 'events' not in dados:
            return None
        
        mandante_norm = normalizar_nome_time(time_mandante)
        visitante_norm = normalizar_nome_time(time_visitante)
        
        melhor_match = None
        melhor_score = 0
        
        for evento in dados['events']:
            home_team = evento.get('homeTeam', {}).get('name', '')
            away_team = evento.get('awayTeam', {}).get('name', '')
            
            home_norm = normalizar_nome_time(home_team)
            away_norm = normalizar_nome_time(away_team)
            
            score = 0
            
            if mandante_norm == home_norm:
                score += 10
            elif mandante_norm in home_norm or home_norm in mandante_norm:
                score += 5
            else:
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
        
        if melhor_score >= 4:
            return melhor_match
        
        return None
        
    except Exception:
        return None


def buscar_cartoes_partida(event_id: int) -> Optional[int]:
    """Busca o total de cartões amarelos de uma partida."""
    try:
        url = f"{BASE_URL}/event/{event_id}/statistics"
        dados = fazer_requisicao(url)
        
        if dados and 'statistics' in dados:
            for grupo in dados['statistics']:
                for item in grupo.get('groups', []):
                    for stat in item.get('statisticsItems', []):
                        nome = stat.get('name', '').lower()
                        if 'yellow' in nome and 'card' in nome:
                            home = int(stat.get('home', 0) or 0)
                            away = int(stat.get('away', 0) or 0)
                            return home + away
        
        # Fallback: incidentes
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
# FUNÇÕES DE CÁLCULO DE MÉTRICAS
# =============================================================================

def calcular_brier_score(validacoes: List[ResultadoValidacaoV2]) -> float:
    """
    Calcula o Brier Score.
    
    Brier Score = (1/N) × Σ(p - o)²
    
    Onde:
        - p: probabilidade prevista (0 a 1)
        - o: outcome real (0 ou 1)
    
    Quanto MENOR, melhor. 0 = perfeito.
    """
    if not validacoes:
        return 1.0
    
    soma = 0.0
    for v in validacoes:
        p = v.p_usado / 100  # Converte para 0-1
        o = v.outcome
        soma += (p - o) ** 2
    
    return soma / len(validacoes)


def calcular_log_loss(validacoes: List[ResultadoValidacaoV2]) -> float:
    """
    Calcula o Log Loss (Cross-Entropy Loss).
    
    Log Loss = -(1/N) × Σ[o×log(p) + (1-o)×log(1-p)]
    
    Quanto MENOR, melhor.
    """
    if not validacoes:
        return 10.0
    
    eps = 1e-15  # Para evitar log(0)
    soma = 0.0
    
    for v in validacoes:
        p = max(eps, min(1 - eps, v.p_usado / 100))
        o = v.outcome
        
        if o == 1:
            soma -= math.log(p)
        else:
            soma -= math.log(1 - p)
    
    return soma / len(validacoes)


def calcular_calibracao_por_bin(validacoes: List[ResultadoValidacaoV2]) -> Dict[str, Dict]:
    """
    Calcula a taxa de acerto real por bins de probabilidade.
    
    Bins: 50-55, 55-60, 60-65, 65-70, 70-75, 75-80, 80+
    """
    bins = {
        '50-55': {'min': 50, 'max': 55, 'total': 0, 'acertos': 0},
        '55-60': {'min': 55, 'max': 60, 'total': 0, 'acertos': 0},
        '60-65': {'min': 60, 'max': 65, 'total': 0, 'acertos': 0},
        '65-70': {'min': 65, 'max': 70, 'total': 0, 'acertos': 0},
        '70-75': {'min': 70, 'max': 75, 'total': 0, 'acertos': 0},
        '75-80': {'min': 75, 'max': 80, 'total': 0, 'acertos': 0},
        '80+': {'min': 80, 'max': 100, 'total': 0, 'acertos': 0},
    }
    
    for v in validacoes:
        p = v.p_usado
        for nome, bin_data in bins.items():
            if bin_data['min'] <= p < bin_data['max'] or (nome == '80+' and p >= 80):
                bin_data['total'] += 1
                if v.outcome == 1:
                    bin_data['acertos'] += 1
                break
    
    # Calcula taxas
    for nome, bin_data in bins.items():
        if bin_data['total'] > 0:
            bin_data['taxa_real'] = bin_data['acertos'] / bin_data['total'] * 100
            bin_data['taxa_esperada'] = (bin_data['min'] + bin_data['max']) / 2
        else:
            bin_data['taxa_real'] = 0
            bin_data['taxa_esperada'] = (bin_data['min'] + bin_data['max']) / 2
    
    return bins


def calcular_metricas(validacoes: List[ResultadoValidacaoV2]) -> MetricasAvaliacao:
    """Calcula todas as métricas para um conjunto de validações."""
    
    total = len(validacoes)
    acertos = sum(1 for v in validacoes if v.outcome == 1)
    erros = total - acertos
    taxa = (acertos / total * 100) if total > 0 else 0.0
    
    brier = calcular_brier_score(validacoes)
    log_loss = calcular_log_loss(validacoes)
    calibracao = calcular_calibracao_por_bin(validacoes)
    
    return MetricasAvaliacao(
        total_previsoes=total,
        acertos=acertos,
        erros=erros,
        taxa_acerto=taxa,
        brier_score=brier,
        log_loss=log_loss,
        calibracao_por_bin=calibracao
    )


# =============================================================================
# FUNÇÕES DE VALIDAÇÃO
# =============================================================================

def validar_partida_v2(partida: PartidaPrevisaoV2) -> List[ResultadoValidacaoV2]:
    """Valida as previsões de uma partida V2.0."""
    resultados = []
    
    if partida.cartoes_reais is None:
        return resultados
    
    for previsao in partida.previsoes:
        acertou = previsao.verificar_acerto(partida.cartoes_reais)
        
        resultado = ResultadoValidacaoV2(
            partida=partida,
            mercado=previsao,
            cartoes_reais=partida.cartoes_reais,
            acertou=acertou,
            p_usado=previsao.p_calibrado,
            outcome=1 if acertou else 0
        )
        
        resultados.append(resultado)
    
    return resultados


def gerar_relatorio_v2(partidas: List[PartidaPrevisaoV2], data_arquivo: str) -> RelatorioValidacaoV2:
    """Gera o relatório de validação V2.0."""
    
    total_partidas = len(partidas)
    partidas_encontradas = sum(1 for p in partidas if p.status == "encontrado")
    partidas_nao_encontradas = total_partidas - partidas_encontradas
    
    # Valida todas as partidas
    todas_validacoes = []
    for partida in partidas:
        if partida.status == "encontrado":
            todas_validacoes.extend(validar_partida_v2(partida))
    
    # Estatísticas de destaques
    destaques_validacoes = [v for v in todas_validacoes if v.mercado.eh_destaque]
    total_destaques = len(destaques_validacoes)
    destaques_acertos = sum(1 for v in destaques_validacoes if v.acertou)
    destaques_erros = total_destaques - destaques_acertos
    taxa_acerto_destaques = (destaques_acertos / total_destaques * 100) if total_destaques > 0 else 0.0
    
    # Estatísticas de bloqueados
    bloqueados_validacoes = [v for v in todas_validacoes if v.mercado.eh_bloqueado]
    total_bloqueados = len(bloqueados_validacoes)
    bloqueados_acertos = sum(1 for v in bloqueados_validacoes if v.acertou)
    bloqueados_evitados = total_bloqueados - bloqueados_acertos  # Erros evitados
    
    # Métricas por mercado
    metricas_por_mercado = {}
    validacoes_por_mercado = defaultdict(list)
    
    for v in todas_validacoes:
        validacoes_por_mercado[v.mercado.mercado].append(v)
    
    for mercado, validacoes in validacoes_por_mercado.items():
        metricas_por_mercado[mercado] = calcular_metricas(validacoes)
    
    # Métricas gerais (apenas destaques)
    metricas_gerais = calcular_metricas(destaques_validacoes) if destaques_validacoes else None
    
    return RelatorioValidacaoV2(
        data_arquivo=data_arquivo,
        total_partidas=total_partidas,
        partidas_encontradas=partidas_encontradas,
        partidas_nao_encontradas=partidas_nao_encontradas,
        total_destaques=total_destaques,
        destaques_acertos=destaques_acertos,
        destaques_erros=destaques_erros,
        taxa_acerto_destaques=taxa_acerto_destaques,
        total_bloqueados=total_bloqueados,
        bloqueados_acertos=bloqueados_acertos,
        bloqueados_evitados=bloqueados_evitados,
        metricas_por_mercado=metricas_por_mercado,
        metricas_gerais=metricas_gerais,
        validacoes=todas_validacoes,
        partidas=partidas
    )


# =============================================================================
# GERAÇÃO DO HTML DO RELATÓRIO V2.0
# =============================================================================

def gerar_html_relatorio_v2(relatorio: RelatorioValidacaoV2) -> str:
    """Gera o HTML do relatório de validação V2.0."""
    
    timestamp = datetime.now().strftime('%d/%m/%Y %H:%M')
    
    # Cor da taxa de acerto
    if relatorio.taxa_acerto_destaques >= 60:
        cor_taxa = "#2ecc71"
    elif relatorio.taxa_acerto_destaques >= 50:
        cor_taxa = "#f6e05e"
    else:
        cor_taxa = "#e94560"
    
    # CSS do guia
    css_guia = ""
    if APRENDIZADO_DISPONIVEL:
        css_guia = gerar_css_guia()
    
    # Seção de Regras de Ouro
    regras_html = ""
    if APRENDIZADO_DISPONIVEL:
        pasta_atual = os.path.dirname(os.path.abspath(__file__))
        pasta_calibracao = os.path.join(pasta_atual, "Calibracao")
        banco = obter_banco_aprendizado(pasta_calibracao)
        
        if banco.regras:
            regras_rows = ""
            for r in banco.regras[:10]:  # Top 10
                cor_nivel = r.cor
                regras_rows += f'''
                    <tr>
                        <td><span style="color: {cor_nivel}; font-weight: bold;">{r.nivel}</span></td>
                        <td>{r.mercado}</td>
                        <td>{r.descricao}</td>
                        <td style="font-weight: bold; color: #2ecc71;">{r.taxa_acerto:.1f}%</td>
                        <td>{r.acertos}/{r.total_amostras}</td>
                    </tr>
                '''
            
            regras_html = f'''
                <div class="section">
                    <div class="section-title">🏆 Regras de Ouro Descobertas</div>
                    <p style="color: #a0a0a0; margin-bottom: 15px;">
                        Combinações de fatores com alta taxa de acerto histórica.
                    </p>
                    
                    <table>
                        <thead>
                            <tr>
                                <th>Nível</th>
                                <th>Mercado</th>
                                <th>Condições</th>
                                <th>Taxa</th>
                                <th>Amostras</th>
                            </tr>
                        </thead>
                        <tbody>
                            {regras_rows}
                        </tbody>
                    </table>
                    
                    <div style="margin-top: 15px; padding: 15px; background: rgba(255, 215, 0, 0.1); border-radius: 8px; border-left: 4px solid #ffd700;">
                        <p style="margin: 0; color: #ffd700;">
                            💡 <strong>Dica:</strong> Quando uma partida ativar uma Regra de Ouro, ela terá um indicador especial no relatório de probabilidades.
                        </p>
                    </div>
                </div>
            '''
        else:
            regras_html = f'''
                <div class="section">
                    <div class="section-title">🏆 Regras de Ouro</div>
                    <div style="text-align: center; padding: 30px; color: #a0a0a0;">
                        <p style="font-size: 3em;">🔬</p>
                        <p>Nenhuma regra de ouro descoberta ainda.</p>
                        <p style="font-size: 0.9em; margin-top: 10px;">
                            Continue validando partidas para que o sistema descubra padrões de alta taxa de acerto!
                        </p>
                        <p style="font-size: 0.85em; margin-top: 5px; color: #3498db;">
                            Mínimo necessário: 8 amostras com ≥75% de acerto
                        </p>
                    </div>
                </div>
            '''
    
    # Guia de metodologia
    guia_html = ""
    if APRENDIZADO_DISPONIVEL:
        guia_html = gerar_guia_metodologia_html()
    
    # Seção de métricas gerais
    metricas_html = ""
    if relatorio.metricas_gerais:
        m = relatorio.metricas_gerais
        
        # Interpretação do Brier Score
        if m.brier_score < 0.20:
            brier_cor = "#2ecc71"
            brier_texto = "Excelente"
        elif m.brier_score < 0.25:
            brier_cor = "#f6e05e"
            brier_texto = "Bom"
        else:
            brier_cor = "#e94560"
            brier_texto = "Precisa melhorar"
        
        # Curva de calibração
        calibracao_rows = ""
        for nome, bin_data in m.calibracao_por_bin.items():
            if bin_data['total'] > 0:
                diff = bin_data['taxa_real'] - bin_data['taxa_esperada']
                diff_cor = "#2ecc71" if abs(diff) < 5 else ("#f6e05e" if abs(diff) < 10 else "#e94560")
                calibracao_rows += f"""
                    <tr>
                        <td>{nome}%</td>
                        <td>{bin_data['total']}</td>
                        <td>{bin_data['taxa_esperada']:.0f}%</td>
                        <td style="color: {diff_cor}; font-weight: bold;">{bin_data['taxa_real']:.1f}%</td>
                        <td style="color: {diff_cor};">{diff:+.1f}%</td>
                    </tr>
                """
        
        metricas_html = f"""
            <div class="section">
                <div class="section-title">📊 Métricas de Calibração (Destaques)</div>
                
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-valor" style="color: {brier_cor};">{m.brier_score:.4f}</div>
                        <div class="stat-label">Brier Score</div>
                        <div style="font-size: 0.8em; color: {brier_cor};">{brier_texto}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-valor">{m.log_loss:.4f}</div>
                        <div class="stat-label">Log Loss</div>
                    </div>
                </div>
                
                <div style="margin-top: 20px;">
                    <h4 style="color: #e94560; margin-bottom: 10px;">📈 Curva de Confiabilidade</h4>
                    <p style="color: #a0a0a0; font-size: 0.9em; margin-bottom: 15px;">
                        Compara a probabilidade prevista com a taxa de acerto real por faixa.
                    </p>
                    <table style="width: 100%;">
                        <thead>
                            <tr>
                                <th>Faixa</th>
                                <th>N</th>
                                <th>Esperado</th>
                                <th>Real</th>
                                <th>Δ</th>
                            </tr>
                        </thead>
                        <tbody>
                            {calibracao_rows}
                        </tbody>
                    </table>
                    <p style="color: #a0a0a0; font-size: 0.8em; margin-top: 10px;">
                        Um modelo bem calibrado tem taxa real ≈ taxa esperada em cada faixa.
                    </p>
                </div>
            </div>
        """
    
    # Tabela de partidas
    tabela_partidas = ""
    for partida in relatorio.partidas:
        status_icon = "✅" if partida.status == "encontrado" else "❌"
        cartoes = str(partida.cartoes_reais) if partida.cartoes_reais is not None else "N/D"
        placar = partida.placar if partida.placar else "N/D"
        
        # Destaques
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
            destaques_html += f'<span style="color: {cor}; margin-right: 8px;">{icon} {d.mercado} ({d.p_calibrado:.0f}%)</span>'
        
        # Bloqueados
        bloqueados = partida.get_bloqueados()
        bloqueados_html = ""
        for b in bloqueados:
            if partida.cartoes_reais is not None:
                teria_acertado = b.verificar_acerto(partida.cartoes_reais)
                icon = "🛡️" if not teria_acertado else "⚠️"
                cor = "#f1c40f"
            else:
                icon = "🚫"
                cor = "#a0a0a0"
            bloqueados_html += f'<span style="color: {cor}; margin-right: 8px;" title="Bloqueado: {b.motivo_bloqueio}">{icon} {b.mercado}</span>'
        
        # Intervalo
        intervalo_html = ""
        if partida.intervalo:
            intervalo_html = f"[{partida.intervalo.p10}-{partida.intervalo.p90}]"
        
        tabela_partidas += f"""
            <tr>
                <td>{status_icon}</td>
                <td>{partida.time_mandante} vs {partida.time_visitante}</td>
                <td>{partida.competicao}</td>
                <td style="color: #9b59b6;">{partida.lambda_shrunk:.2f}</td>
                <td>{intervalo_html}</td>
                <td style="font-weight: bold; color: #3498db;">{cartoes}</td>
                <td>{placar}</td>
                <td>{destaques_html}</td>
                <td>{bloqueados_html}</td>
            </tr>
        """
    
    # Tabela de estatísticas por mercado
    tabela_mercados = ""
    for mercado, m in sorted(relatorio.metricas_por_mercado.items()):
        cor = "#2ecc71" if m.taxa_acerto >= 50 else "#e94560"
        tabela_mercados += f"""
            <tr>
                <td>{mercado}</td>
                <td>{m.total_previsoes}</td>
                <td>{m.acertos}</td>
                <td>{m.erros}</td>
                <td style="color: {cor}; font-weight: bold;">{m.taxa_acerto:.1f}%</td>
                <td>{m.brier_score:.4f}</td>
            </tr>
        """
    
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RefStats - Relatório de Validação V2.0 - {relatorio.data_arquivo}</title>
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
        
        .version-badge {{
            display: inline-block;
            background: linear-gradient(135deg, #9b59b6 0%, #3498db 100%);
            color: white;
            padding: 5px 15px;
            border-radius: 15px;
            font-size: 0.85em;
            margin-top: 10px;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
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
            font-size: 2.2em;
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
        
        .bloqueados-box {{
            background: rgba(241, 196, 15, 0.1);
            border: 1px solid #f1c40f;
            border-radius: 10px;
            padding: 20px;
            margin-top: 20px;
        }}
        
        .interpretacao {{
            background: rgba(233, 69, 96, 0.1);
            border-left: 4px solid #e94560;
            padding: 20px;
            border-radius: 0 10px 10px 0;
            margin-top: 20px;
        }}
        
        {css_guia}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Relatório de Validação V2.0</h1>
            <p>📅 Partidas de {relatorio.data_arquivo}</p>
            <p style="margin-top: 5px; color: #a0a0a0;">Gerado em {timestamp}</p>
            <div class="version-badge">
                Neg. Binomial + Shrinkage + Calibração + Aprendizado
            </div>
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
            <div class="section-title">📈 Resumo dos Destaques vs Bloqueados</div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-valor" style="color: #2ecc71;">{relatorio.destaques_acertos}</div>
                    <div class="stat-label">✅ Destaques Acertos</div>
                </div>
                <div class="stat-card">
                    <div class="stat-valor" style="color: #e94560;">{relatorio.destaques_erros}</div>
                    <div class="stat-label">❌ Destaques Erros</div>
                </div>
                <div class="stat-card">
                    <div class="stat-valor" style="color: #f1c40f;">{relatorio.total_bloqueados}</div>
                    <div class="stat-label">🚫 Bloqueados</div>
                </div>
                <div class="stat-card">
                    <div class="stat-valor" style="color: #9b59b6;">{relatorio.bloqueados_evitados}</div>
                    <div class="stat-label">🛡️ Erros Evitados</div>
                </div>
            </div>
            
            <div class="bloqueados-box">
                <h4 style="color: #f1c40f; margin-bottom: 10px;">🛡️ Análise de Bloqueios</h4>
                <p>
                    Dos <strong>{relatorio.total_bloqueados}</strong> mercados bloqueados (por variância ou qualidade):
                </p>
                <ul style="margin: 10px 0 0 20px;">
                    <li><strong style="color: #2ecc71;">{relatorio.bloqueados_evitados}</strong> teriam ERRADO → bloqueio correto ✅</li>
                    <li><strong style="color: #e94560;">{relatorio.bloqueados_acertos}</strong> teriam ACERTADO → bloqueio desnecessário ⚠️</li>
                </ul>
                <p style="margin-top: 10px; font-size: 0.9em; color: #a0a0a0;">
                    Taxa de eficácia do bloqueio: <strong>{(relatorio.bloqueados_evitados / relatorio.total_bloqueados * 100) if relatorio.total_bloqueados > 0 else 0:.1f}%</strong>
                </p>
            </div>
            
            <div class="interpretacao">
                <h4 style="color: #e94560; margin-bottom: 10px;">🧠 Interpretação</h4>
                <p>
                    Das <strong>{relatorio.total_destaques}</strong> previsões destacadas,
                    <strong>{relatorio.destaques_acertos}</strong> acertaram, 
                    resultando em taxa de <strong style="color: {cor_taxa};">{relatorio.taxa_acerto_destaques:.1f}%</strong>.
                </p>
                <p style="margin-top: 10px; font-size: 0.9em; color: #a0a0a0;">
                    Para um modelo bem calibrado, espera-se que destaques com ~60% de probabilidade 
                    acertem ~60% das vezes no longo prazo.
                </p>
            </div>
        </div>
        
        {metricas_html}
        
        {regras_html}
        
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
                        <th>Brier</th>
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
                            <th>St</th>
                            <th>Partida</th>
                            <th>Comp.</th>
                            <th>λ</th>
                            <th>Interv.</th>
                            <th>Cart.</th>
                            <th>Placar</th>
                            <th>Destaques</th>
                            <th>Bloq.</th>
                        </tr>
                    </thead>
                    <tbody>
                        {tabela_partidas}
                    </tbody>
                </table>
            </div>
        </div>
        
        {guia_html}
        
        <div class="footer">
            <p><strong>📊 RefStats - Validação V2.0</strong></p>
            <p style="margin-top: 10px; font-size: 0.85em;">
                Métricas: Brier Score, Log Loss, Curva de Confiabilidade
            </p>
            <p style="margin-top: 5px; font-size: 0.85em;">
                {timestamp}
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

def processar_arquivo_v2(caminho: str, pasta_saida: str) -> Optional[RelatorioValidacaoV2]:
    """Processa um arquivo de probabilidade V2.0 e gera relatório."""
    
    nome_arquivo = os.path.basename(caminho)
    print(f"\n{'='*60}")
    print(f"📂 Processando: {nome_arquivo}")
    print(f"{'='*60}")
    
    # Extrai data
    match = re.search(r'(\d{2})(\d{2})(\d{4})', nome_arquivo)
    if match:
        data_arquivo = f"{match.group(1)}/{match.group(2)}/{match.group(3)}"
    else:
        data_arquivo = "Data desconhecida"
    
    # Extrai partidas
    partidas = extrair_partidas_v2(caminho)
    
    if not partidas:
        print("   ⚠️ Nenhuma partida encontrada")
        return None
    
    print(f"   ✅ {len(partidas)} partida(s) encontrada(s)")
    
    # Busca resultados
    print("\n   🔍 Buscando resultados reais...")
    
    for i, partida in enumerate(partidas, 1):
        print(f"      [{i}/{len(partidas)}] {partida.time_mandante} vs {partida.time_visitante}...", end=" ")
        
        evento = buscar_partida_sofascore(
            partida.time_mandante,
            partida.time_visitante,
            partida.data
        )
        
        if evento:
            event_id = evento.get('id')
            status = evento.get('status', {}).get('type', '')
            
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
                    print(f"⚠️ Cartões N/D ({placar})")
            else:
                print(f"⏳ Não finalizado")
        else:
            print("❌ Não encontrado")
            partida.status = "não encontrado"
        
        time.sleep(REQUEST_DELAY)
    
    # Gera relatório
    print("\n   📊 Gerando relatório...")
    relatorio = gerar_relatorio_v2(partidas, data_arquivo)
    html = gerar_html_relatorio_v2(relatorio)
    
    # Salva
    os.makedirs(pasta_saida, exist_ok=True)
    nome_saida = nome_arquivo.replace('PROBABILIDADE_', 'RELATORIO_V2_').replace('.html', '_validacao.html')
    caminho_saida = os.path.join(pasta_saida, nome_saida)
    
    with open(caminho_saida, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"\n   ✅ Relatório salvo: {caminho_saida}")
    
    # Resumo
    print(f"\n   📈 RESUMO:")
    print(f"      • Partidas validadas: {relatorio.partidas_encontradas}/{relatorio.total_partidas}")
    print(f"      • Destaques: {relatorio.destaques_acertos}/{relatorio.total_destaques} acertos ({relatorio.taxa_acerto_destaques:.1f}%)")
    print(f"      • Bloqueados: {relatorio.total_bloqueados} ({relatorio.bloqueados_evitados} erros evitados)")
    
    if relatorio.metricas_gerais:
        print(f"      • Brier Score: {relatorio.metricas_gerais.brier_score:.4f}")
        print(f"      • Log Loss: {relatorio.metricas_gerais.log_loss:.4f}")
    
    return relatorio


def main():
    """Função principal."""
    print("""
╔═══════════════════════════════════════════════════════════════╗
║     SISTEMA DE VALIDAÇÃO DE PROBABILIDADES - V2.0             ║
║       Brier Score • Log Loss • Curva de Confiabilidade        ║
╚═══════════════════════════════════════════════════════════════╝
    """)
    
    pasta_atual = os.path.dirname(os.path.abspath(__file__))
    pasta_probabilidade = os.path.join(pasta_atual, "Probabilidade")
    pasta_relatorio = os.path.join(pasta_probabilidade, "Relatorio")
    
    print(f"📁 Pasta de entrada: {pasta_probabilidade}")
    print(f"📁 Pasta de saída: {pasta_relatorio}")
    
    if not os.path.exists(pasta_probabilidade):
        print(f"\n⚠️ Pasta 'Probabilidade' não encontrada!")
        return
    
    padrao = os.path.join(pasta_probabilidade, "PROBABILIDADE_*.html")
    arquivos = glob.glob(padrao)
    
    if not arquivos:
        print(f"\n⚠️ Nenhum arquivo PROBABILIDADE_*.html encontrado")
        return
    
    print(f"\n📋 Arquivos encontrados: {len(arquivos)}")
    
    # Menu de modo
    print("\n🔧 Modo de operação:")
    print("   [1] Automático (API SofaScore)")
    print("   [2] Manual (digitar resultados)")
    print("   [3] CSV (importar de arquivo)")
    
    modo = input("\n   Escolha [1/2/3] (ENTER para automático): ").strip()
    
    if modo == "2":
        processar_modo_manual_v2(arquivos, pasta_relatorio)
    elif modo == "3":
        processar_modo_csv_v2(arquivos, pasta_relatorio)
    else:
        processar_modo_automatico_v2(arquivos, pasta_relatorio)


def processar_modo_automatico_v2(arquivos: list, pasta_saida: str):
    """Processa no modo automático."""
    relatorios = []
    
    for arquivo in sorted(arquivos):
        relatorio = processar_arquivo_v2(arquivo, pasta_saida)
        if relatorio:
            relatorios.append(relatorio)
    
    # Alimenta calibradores com os resultados
    if relatorios:
        pasta_atual = os.path.dirname(os.path.abspath(__file__))
        pasta_calibracao = os.path.join(pasta_atual, "Calibracao")
        alimentar_calibradores(relatorios, pasta_calibracao)
    
    exibir_resumo_final_v2(relatorios)


def processar_modo_manual_v2(arquivos: list, pasta_saida: str):
    """Processa no modo manual."""
    
    relatorios = []
    
    for arquivo in sorted(arquivos):
        nome_arquivo = os.path.basename(arquivo)
        print(f"\n{'='*60}")
        print(f"📂 Arquivo: {nome_arquivo}")
        print(f"{'='*60}")
        
        match = re.search(r'(\d{2})(\d{2})(\d{4})', nome_arquivo)
        data_arquivo = f"{match.group(1)}/{match.group(2)}/{match.group(3)}" if match else "?"
        
        partidas = extrair_partidas_v2(arquivo)
        
        if not partidas:
            continue
        
        print(f"\n   📝 Digite os resultados (cartões) ou ENTER para pular:")
        
        for i, partida in enumerate(partidas, 1):
            prompt = f"   [{i}/{len(partidas)}] {partida.time_mandante} vs {partida.time_visitante}: "
            resultado = input(prompt).strip()
            
            if resultado.lower() == 'q':
                break
            
            if resultado.isdigit():
                partida.cartoes_reais = int(resultado)
                partida.status = "encontrado"
                print(f"            ✅ {resultado} cartões")
        
        # Gera relatório
        relatorio = gerar_relatorio_v2(partidas, data_arquivo)
        html = gerar_html_relatorio_v2(relatorio)
        
        os.makedirs(pasta_saida, exist_ok=True)
        nome_saida = nome_arquivo.replace('PROBABILIDADE_', 'RELATORIO_V2_').replace('.html', '_validacao.html')
        caminho_saida = os.path.join(pasta_saida, nome_saida)
        
        with open(caminho_saida, 'w', encoding='utf-8') as f:
            f.write(html)
        
        print(f"\n   ✅ Relatório salvo: {caminho_saida}")
        relatorios.append(relatorio)
    
    # Alimenta calibradores com os resultados
    if relatorios:
        pasta_atual = os.path.dirname(os.path.abspath(__file__))
        pasta_calibracao = os.path.join(pasta_atual, "Calibracao")
        alimentar_calibradores(relatorios, pasta_calibracao)
    
    exibir_resumo_final_v2(relatorios)


def processar_modo_csv_v2(arquivos: list, pasta_saida: str):
    """Processa usando CSV."""
    
    pasta_atual = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(pasta_atual, "resultados.csv")
    
    print(f"\n📄 Procurando: {csv_path}")
    
    if not os.path.exists(csv_path):
        print(f"\n⚠️ Arquivo 'resultados.csv' não encontrado!")
        print(f"\n   Formato esperado:")
        print(f"   data,mandante,visitante,cartoes,placar")
        
        # Cria template
        template = "data,mandante,visitante,cartoes,placar\n"
        for arquivo in arquivos:
            partidas = extrair_partidas_v2(arquivo)
            for p in partidas:
                template += f"{p.data},{p.time_mandante},{p.time_visitante},,\n"
        
        with open(csv_path, 'w', encoding='utf-8') as f:
            f.write(template)
        
        print(f"\n   ✅ Template criado: {csv_path}")
        return
    
    # Carrega CSV
    resultados = {}
    with open(csv_path, 'r', encoding='utf-8') as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith('#') or linha.startswith('data'):
                continue
            
            partes = linha.split(',')
            if len(partes) >= 4 and partes[3].strip().isdigit():
                chave = f"{partes[1].strip().lower()}_{partes[2].strip().lower()}"
                resultados[chave] = {
                    'cartoes': int(partes[3].strip()),
                    'placar': partes[4].strip() if len(partes) > 4 else None
                }
    
    print(f"   ✅ {len(resultados)} resultados carregados")
    
    relatorios = []
    
    for arquivo in sorted(arquivos):
        nome_arquivo = os.path.basename(arquivo)
        match = re.search(r'(\d{2})(\d{2})(\d{4})', nome_arquivo)
        data_arquivo = f"{match.group(1)}/{match.group(2)}/{match.group(3)}" if match else "?"
        
        partidas = extrair_partidas_v2(arquivo)
        
        for partida in partidas:
            chave = f"{partida.time_mandante.lower()}_{partida.time_visitante.lower()}"
            if chave in resultados:
                partida.cartoes_reais = resultados[chave]['cartoes']
                partida.placar = resultados[chave]['placar']
                partida.status = "encontrado"
        
        relatorio = gerar_relatorio_v2(partidas, data_arquivo)
        html = gerar_html_relatorio_v2(relatorio)
        
        os.makedirs(pasta_saida, exist_ok=True)
        nome_saida = nome_arquivo.replace('PROBABILIDADE_', 'RELATORIO_V2_').replace('.html', '_validacao.html')
        caminho_saida = os.path.join(pasta_saida, nome_saida)
        
        with open(caminho_saida, 'w', encoding='utf-8') as f:
            f.write(html)
        
        print(f"   ✅ {nome_saida}")
        relatorios.append(relatorio)
    
    # Alimenta calibradores com os resultados
    if relatorios:
        pasta_calibracao = os.path.join(pasta_atual, "Calibracao")
        alimentar_calibradores(relatorios, pasta_calibracao)
    
    exibir_resumo_final_v2(relatorios)


def alimentar_calibradores(relatorios: List[RelatorioValidacaoV2], pasta_calibracao: str):
    """
    Alimenta os calibradores com os resultados das validações.
    
    Este é o "aprendizado" do sistema:
    - Cada resultado de validação é um ponto de dados
    - O calibrador aprende a relação entre p_raw e taxa de acerto real
    - Na próxima execução, p_calibrado será mais preciso
    """
    from collections import defaultdict
    import pickle
    
    print("\n📚 Alimentando calibradores com resultados...")
    
    # Agrupa validações por mercado
    validacoes_por_mercado = defaultdict(list)
    
    for relatorio in relatorios:
        for validacao in relatorio.validacoes:
            mercado = validacao.mercado.mercado
            p_raw = validacao.mercado.p_raw
            acertou = validacao.acertou
            validacoes_por_mercado[mercado].append((p_raw, acertou))
    
    os.makedirs(pasta_calibracao, exist_ok=True)
    
    # Para cada mercado, atualiza o calibrador
    for mercado, dados in validacoes_por_mercado.items():
        nome_arquivo = mercado.replace(" ", "_").replace(".", "") + ".pkl"
        caminho = os.path.join(pasta_calibracao, nome_arquivo)
        
        # Carrega dados existentes ou cria novo
        dados_existentes = {'pontos_x': [], 'pontos_y': [], 'mapa': None}
        
        if os.path.exists(caminho):
            try:
                with open(caminho, 'rb') as f:
                    dados_existentes = pickle.load(f)
            except:
                pass
        
        # Adiciona novos pontos
        for p_raw, acertou in dados:
            dados_existentes['pontos_x'].append(p_raw)
            dados_existentes['pontos_y'].append(1.0 if acertou else 0.0)
        
        # Recalcula mapa de calibração se tiver dados suficientes
        if len(dados_existentes['pontos_x']) >= 10:
            # Agrupa em bins de 5%
            bins = defaultdict(list)
            for x, y in zip(dados_existentes['pontos_x'], dados_existentes['pontos_y']):
                bin_idx = int(x / 5) * 5
                bins[bin_idx].append(y)
            
            # Calcula média por bin
            mapa = {}
            for bin_idx, valores in bins.items():
                if len(valores) >= 2:  # Mínimo 2 amostras por bin
                    mapa[bin_idx] = sum(valores) / len(valores) * 100
            
            # Aplica monotonicidade (para Over, deve ser crescente)
            if 'Over' in mercado and mapa:
                chaves = sorted(mapa.keys())
                for i in range(1, len(chaves)):
                    if mapa[chaves[i]] < mapa[chaves[i-1]]:
                        media = (mapa[chaves[i]] + mapa[chaves[i-1]]) / 2
                        mapa[chaves[i]] = media
                        mapa[chaves[i-1]] = media
            
            dados_existentes['mapa'] = mapa
        
        # Salva
        dados_existentes['mercado'] = mercado
        with open(caminho, 'wb') as f:
            pickle.dump(dados_existentes, f)
        
        n_pontos = len(dados_existentes['pontos_x'])
        n_novos = len(dados)
        print(f"   ✅ {mercado}: +{n_novos} pontos (total: {n_pontos})")
    
    print(f"\n   📁 Calibradores salvos em: {pasta_calibracao}")
    
    # Mostra status dos calibradores
    print("\n   📊 Status dos Calibradores:")
    for mercado in sorted(validacoes_por_mercado.keys()):
        nome_arquivo = mercado.replace(" ", "_").replace(".", "") + ".pkl"
        caminho = os.path.join(pasta_calibracao, nome_arquivo)
        
        if os.path.exists(caminho):
            with open(caminho, 'rb') as f:
                dados = pickle.load(f)
            
            n_pontos = len(dados.get('pontos_x', []))
            tem_mapa = dados.get('mapa') is not None
            
            if tem_mapa:
                status = "🟢 Ativo"
            elif n_pontos >= 5:
                status = "🟡 Quase (precisa de mais dados)"
            else:
                status = "🔴 Inativo"
            
            print(f"      {mercado}: {n_pontos} amostras → {status}")
    
    # =========================================================================
    # SISTEMA DE APRENDIZADO AVANÇADO
    # =========================================================================
    if APRENDIZADO_DISPONIVEL:
        alimentar_banco_aprendizado(relatorios, pasta_calibracao)


def alimentar_banco_aprendizado(relatorios: List[RelatorioValidacaoV2], pasta_calibracao: str):
    """Alimenta o banco de aprendizado com os resultados das validações."""
    
    print("\n🧠 Alimentando Sistema de Aprendizado Avançado...")
    
    banco = obter_banco_aprendizado(pasta_calibracao)
    registros_adicionados = 0
    
    for relatorio in relatorios:
        for partida in relatorio.partidas:
            if partida.status != "encontrado" or partida.cartoes_reais is None:
                continue
            
            # Cria dados da partida para aprendizado
            dados_partida = criar_dados_partida_aprendizado(
                data=partida.data,
                time_mandante=partida.time_mandante,
                time_visitante=partida.time_visitante,
                competicao=partida.competicao,
                lambda_shrunk=partida.lambda_shrunk,
                qualidade_score=partida.qualidade_score,
                media_arbitro_5j=partida.media_arbitro_5j,
                media_arbitro_10j=partida.media_arbitro_10j,
                intervalo_p10=partida.intervalo.p10 if partida.intervalo else 0,
                intervalo_p90=partida.intervalo.p90 if partida.intervalo else 10,
                perfil_arbitro=partida.perfil_arbitro,
                modelo=partida.modelo,
                # Novos parâmetros
                delta_arbitro=partida.delta_arbitro,
                delta_times=partida.delta_times,
                peso_shrinkage=partida.peso_shrinkage,
                soma_cartoes_times=partida.soma_cartoes_times,
                completude_arbitro=partida.completude_arbitro,
                lambda_raw=partida.lambda_raw
            )
            
            # Para cada previsão, cria um registro
            for previsao in partida.previsoes:
                acertou = previsao.verificar_acerto(partida.cartoes_reais)
                
                resultado_mercado = criar_resultado_mercado_aprendizado(
                    mercado=previsao.mercado,
                    tipo=previsao.tipo,
                    linha=previsao.linha,
                    p_raw=previsao.p_raw,
                    p_calibrado=previsao.p_calibrado,
                    eh_destaque=previsao.eh_destaque,
                    acertou=acertou,
                    cartoes_reais=partida.cartoes_reais
                )
                
                registro = RegistroAprendizado(
                    partida=dados_partida,
                    resultado=resultado_mercado
                )
                
                banco.adicionar_registro(registro)
                registros_adicionados += 1
    
    banco.salvar()
    print(f"   ✅ +{registros_adicionados} registros adicionados ao banco")
    print(f"   📊 Total no banco: {banco.total_registros()} registros")
    
    # Retreina regras se tiver dados suficientes
    if banco.total_registros() >= 20:
        print("\n🔬 Retreinando Regras de Ouro...")
        regras = retreinar_regras(pasta_calibracao)
        
        if regras:
            print(f"   ✅ {len(regras)} regra(s) descoberta(s)!")
            print("\n   🏆 Top 5 Regras:")
            for i, r in enumerate(regras[:5], 1):
                print(f"      {i}. [{r.nivel}] {r.mercado}")
                print(f"         {r.descricao}")
                print(f"         Taxa: {r.taxa_acerto:.1f}% ({r.acertos}/{r.total_amostras})")
        else:
            print("   ℹ️ Nenhuma regra de ouro encontrada ainda")
            print("   💡 Continue validando para descobrir padrões!")


def exibir_resumo_final_v2(relatorios: list):
    """Exibe resumo final."""
    if not relatorios:
        return
    
    total_destaques = sum(r.total_destaques for r in relatorios)
    total_acertos = sum(r.destaques_acertos for r in relatorios)
    total_bloqueados = sum(r.total_bloqueados for r in relatorios)
    total_evitados = sum(r.bloqueados_evitados for r in relatorios)
    taxa_geral = (total_acertos / total_destaques * 100) if total_destaques > 0 else 0
    
    print(f"""
╔═══════════════════════════════════════════════════════════════╗
║                    RESUMO GERAL V2.0                          ║
╠═══════════════════════════════════════════════════════════════╣
║  📁 Arquivos processados: {len(relatorios):3d}                              ║
║  🎯 Total de destaques: {total_destaques:4d}                               ║
║  ✅ Acertos: {total_acertos:4d}                                            ║
║  📈 Taxa de acerto: {taxa_geral:5.1f}%                                  ║
║  🚫 Bloqueados: {total_bloqueados:4d}                                       ║
║  🛡️ Erros evitados: {total_evitados:4d}                                   ║
╚═══════════════════════════════════════════════════════════════╝
    """)
    
    print("✅ Processamento concluído!")


if __name__ == "__main__":
    main()
