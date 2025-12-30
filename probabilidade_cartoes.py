#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
SISTEMA DE ANÁLISE PROBABILÍSTICA DE CARTÕES
=============================================================================
Autor: RefStats
Descrição: Lê arquivos HTML de jogos do dia e gera análise probabilística
           usando Distribuição de Poisson para previsão de cartões.

ESTRUTURA DE PASTAS:
    /Historico/       → Arquivos de entrada (JOGOS_DO_DIA_*.html)
    /Probabilidade/   → Arquivos de saída (PROBABILIDADE_*.html)
=============================================================================
"""

import os
import re
import math
import glob
from datetime import datetime
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import Optional


# =============================================================================
# CLASSES DE DADOS
# =============================================================================

@dataclass
class DadosArbitro:
    """Armazena os dados extraídos do árbitro."""
    nome: str
    pais: str
    media_amarelos_10j: float
    media_amarelos_5j: float
    media_amarelos_1t: float
    media_amarelos_2t: float
    media_faltas_10j: float
    media_faltas_5j: float
    media_vermelhos: float
    perfil: str  # Rigoroso, Médio, Permissivo


@dataclass
class DadosTime:
    """Armazena os dados extraídos de cada time."""
    nome: str
    posicao: str
    faltas_pro: float      # Média de faltas cometidas
    faltas_contra: float   # Média de faltas sofridas
    amarelos_pro: float    # Média de cartões recebidos
    amarelos_contra: float # Média de cartões do adversário


@dataclass
class DadosBaseline:
    """Armazena o baseline da competição."""
    competicao: str
    media_amarelos: float
    media_faltas: float


@dataclass
class DadosPartida:
    """Armazena todos os dados de uma partida."""
    liga: str
    data: str
    horario: str
    estadio: str
    local: str
    fase: str
    time_mandante: DadosTime
    time_visitante: DadosTime
    arbitro: DadosArbitro
    baseline: DadosBaseline
    perfil_card: str  # data-perfil do card original


# =============================================================================
# FUNÇÕES DE EXTRAÇÃO DE DADOS
# =============================================================================

def extrair_valor_float(texto: str) -> float:
    """
    Extrai um valor numérico de um texto.
    
    Exemplo:
        '4.7' → 4.7
        'N/D' → 0.0
    """
    if not texto:
        return 0.0
    
    # Remove caracteres não numéricos exceto ponto e vírgula
    texto_limpo = re.sub(r'[^\d.,\-]', '', texto.strip())
    texto_limpo = texto_limpo.replace(',', '.')
    
    try:
        return float(texto_limpo)
    except (ValueError, TypeError):
        return 0.0


def extrair_texto_limpo(elemento) -> str:
    """Extrai texto limpo de um elemento BeautifulSoup, removendo tooltips."""
    if not elemento:
        return ""
    
    # Cria uma cópia para não modificar o original
    elemento_copia = BeautifulSoup(str(elemento), 'html.parser')
    
    # Remove tooltips
    for tooltip in elemento_copia.find_all(class_='tooltip'):
        tooltip.decompose()
    
    return elemento_copia.get_text(strip=True)


def extrair_dados_arbitro(secao_arbitro) -> Optional[DadosArbitro]:
    """
    Extrai dados do árbitro a partir da seção HTML.
    
    Estrutura esperada:
        - .arbitro-nome: nome do árbitro
        - .arbitro-pais: país
        - .metrica-card: métricas (amarelos, faltas, etc.)
        - .perfil-badge: perfil (Rigoroso, Médio, Permissivo)
    """
    if not secao_arbitro:
        return None
    
    # Nome do árbitro
    nome_elem = secao_arbitro.find(class_='arbitro-nome')
    nome = extrair_texto_limpo(nome_elem).replace('Liga', '').strip() if nome_elem else "Desconhecido"
    
    # País
    pais_elem = secao_arbitro.find(class_='arbitro-pais')
    pais = pais_elem.get_text(strip=True).replace('🌍', '').strip() if pais_elem else "N/D"
    
    # Métricas - procura por todos os metrica-card
    metricas = {}
    for metrica in secao_arbitro.find_all(class_='metrica-card'):
        valor_elem = metrica.find(class_='valor')
        label_elem = metrica.find(class_='label')
        
        if valor_elem and label_elem:
            valor = extrair_valor_float(valor_elem.get_text())
            label = extrair_texto_limpo(label_elem).lower()
            
            # Mapeia o label para a métrica correspondente
            if 'amarelos (10j)' in label:
                metricas['amarelos_10j'] = valor
            elif 'amarelos (5j)' in label:
                metricas['amarelos_5j'] = valor
            elif 'amarelos 1t' in label:
                metricas['amarelos_1t'] = valor
            elif 'amarelos 2t' in label:
                metricas['amarelos_2t'] = valor
            elif 'faltas (10j)' in label:
                metricas['faltas_10j'] = valor
            elif 'faltas (5j)' in label:
                metricas['faltas_5j'] = valor
            elif 'vermelhos' in label:
                metricas['vermelhos'] = valor
    
    # Perfil do árbitro
    perfil_elem = secao_arbitro.find(class_='perfil-badge')
    perfil = extrair_texto_limpo(perfil_elem) if perfil_elem else "Médio"
    # Limpa emojis e espaços extras
    perfil = re.sub(r'[🟢🟡🔴⚠️]', '', perfil).strip()
    
    return DadosArbitro(
        nome=nome,
        pais=pais,
        media_amarelos_10j=metricas.get('amarelos_10j', 0.0),
        media_amarelos_5j=metricas.get('amarelos_5j', 0.0),
        media_amarelos_1t=metricas.get('amarelos_1t', 0.0),
        media_amarelos_2t=metricas.get('amarelos_2t', 0.0),
        media_faltas_10j=metricas.get('faltas_10j', 0.0),
        media_faltas_5j=metricas.get('faltas_5j', 0.0),
        media_vermelhos=metricas.get('vermelhos', 0.0),
        perfil=perfil
    )


def extrair_dados_baseline(secao_arbitro) -> Optional[DadosBaseline]:
    """
    Extrai dados do baseline da competição.
    
    Estrutura esperada:
        - .baseline-titulo: nome da competição
        - .baseline-item: valores (Média Amarelos, Média Faltas)
    """
    if not secao_arbitro:
        return None
    
    baseline_section = secao_arbitro.find(class_='baseline-section')
    if not baseline_section:
        return DadosBaseline(competicao="N/D", media_amarelos=5.0, media_faltas=28.0)
    
    # Nome da competição
    titulo_elem = baseline_section.find(class_='baseline-titulo')
    competicao = "N/D"
    if titulo_elem:
        texto = extrair_texto_limpo(titulo_elem)
        # Extrai o nome entre parênteses se existir
        match = re.search(r'\(([^)]+)\)', texto)
        if match:
            competicao = match.group(1)
    
    # Valores
    media_amarelos = 5.0
    media_faltas = 28.0
    
    for item in baseline_section.find_all(class_='baseline-item'):
        texto = item.get_text(strip=True).lower()
        valor_elem = item.find(class_='valor')
        
        if valor_elem:
            valor = extrair_valor_float(valor_elem.get_text())
            
            if 'amarelos' in texto:
                media_amarelos = valor
            elif 'faltas' in texto:
                media_faltas = valor
    
    return DadosBaseline(
        competicao=competicao,
        media_amarelos=media_amarelos,
        media_faltas=media_faltas
    )


def extrair_dados_time(time_card, is_mandante: bool) -> Optional[DadosTime]:
    """
    Extrai dados de um time a partir do seu card.
    
    Estrutura esperada:
        - .time-nome: nome do time
        - .time-posicao: posição na tabela
        - .medias-time > .media-item: médias (Faltas Pró, Faltas Contra, etc.)
    """
    if not time_card:
        return None
    
    # Nome do time
    nome_elem = time_card.find(class_='time-nome')
    nome = nome_elem.get_text(strip=True).replace('🏠', '').replace('✈️', '').strip() if nome_elem else "Desconhecido"
    
    # Posição
    pos_elem = time_card.find(class_='time-posicao')
    posicao = pos_elem.get_text(strip=True) if pos_elem else "N/D"
    
    # Médias
    medias = {}
    medias_container = time_card.find(class_='medias-time')
    
    if medias_container:
        for media_item in medias_container.find_all(class_='media-item'):
            valor_elem = media_item.find(class_='valor')
            label_elem = media_item.find(class_='label')
            
            if valor_elem and label_elem:
                valor = extrair_valor_float(valor_elem.get_text())
                label = extrair_texto_limpo(label_elem).lower()
                
                if 'faltas pró' in label:
                    medias['faltas_pro'] = valor
                elif 'faltas contra' in label:
                    medias['faltas_contra'] = valor
                elif 'amarelos pró' in label:
                    medias['amarelos_pro'] = valor
                elif 'amarelos contra' in label:
                    medias['amarelos_contra'] = valor
    
    return DadosTime(
        nome=nome,
        posicao=posicao,
        faltas_pro=medias.get('faltas_pro', 0.0),
        faltas_contra=medias.get('faltas_contra', 0.0),
        amarelos_pro=medias.get('amarelos_pro', 0.0),
        amarelos_contra=medias.get('amarelos_contra', 0.0)
    )


def extrair_partida(card) -> Optional[DadosPartida]:
    """
    Extrai todos os dados de uma partida a partir do card HTML.
    """
    # Perfil do card (data-perfil)
    perfil_card = card.get('data-perfil', 'Médio')
    
    # Header - Times e horário
    header = card.find(class_='jogo-header')
    titulo_elem = header.find(class_='jogo-titulo') if header else None
    titulo = titulo_elem.get_text(strip=True) if titulo_elem else "N/D vs N/D"
    
    # Extrai nomes dos times e posições do título
    # Formato: "Time A (Xº) vs Time B (Yº)"
    time_mandante_nome = "Mandante"
    time_visitante_nome = "Visitante"
    
    if ' vs ' in titulo:
        partes = titulo.split(' vs ')
        if len(partes) == 2:
            time_mandante_nome = re.sub(r'\s*\(\d+º?\)\s*', '', partes[0]).strip()
            time_visitante_nome = re.sub(r'\s*\(\d+º?\)\s*', '', partes[1]).strip()
    
    # Data e horário
    data_elem = card.find(class_='jogo-data')
    horario = "N/D"
    data = "N/D"
    
    if data_elem:
        horario_elem = data_elem.find(class_='horario')
        data_dia_elem = data_elem.find(class_='data')
        horario = horario_elem.get_text(strip=True) if horario_elem else "N/D"
        data = data_dia_elem.get_text(strip=True) if data_dia_elem else "N/D"
    
    # Info bar - Competição, estádio, local, fase
    info_bar = card.find(class_='jogo-info-bar')
    liga = "N/D"
    estadio = "N/D"
    local = "N/D"
    fase = "N/D"
    
    if info_bar:
        for span in info_bar.find_all('span', recursive=False):
            texto = span.get_text(strip=True)
            
            if 'Competição:' in texto:
                valor_elem = span.find(class_='info-value')
                liga = valor_elem.get_text(strip=True) if valor_elem else "N/D"
            elif 'Estádio:' in texto:
                valor_elem = span.find(class_='info-value')
                estadio = valor_elem.get_text(strip=True) if valor_elem else "N/D"
            elif 'Local:' in texto:
                valor_elem = span.find(class_='info-value')
                local = valor_elem.get_text(strip=True) if valor_elem else "N/D"
            elif 'Fase:' in texto:
                valor_elem = span.find(class_='info-value')
                fase = valor_elem.get_text(strip=True) if valor_elem else "N/D"
    
    # Seção do árbitro
    secao_arbitro = card.find(class_='arbitro-card')
    arbitro = extrair_dados_arbitro(secao_arbitro)
    baseline = extrair_dados_baseline(secao_arbitro)
    
    # Seção dos times
    time_cards = card.find_all(class_='time-card')
    time_mandante = None
    time_visitante = None
    
    if len(time_cards) >= 2:
        time_mandante = extrair_dados_time(time_cards[0], is_mandante=True)
        time_visitante = extrair_dados_time(time_cards[1], is_mandante=False)
    elif len(time_cards) == 1:
        time_mandante = extrair_dados_time(time_cards[0], is_mandante=True)
    
    # Cria dados padrão se não encontrou
    if not arbitro:
        arbitro = DadosArbitro(
            nome="N/D", pais="N/D", media_amarelos_10j=4.5, media_amarelos_5j=4.5,
            media_amarelos_1t=1.5, media_amarelos_2t=3.0, media_faltas_10j=28.0,
            media_faltas_5j=28.0, media_vermelhos=0.3, perfil="Médio"
        )
    
    if not baseline:
        baseline = DadosBaseline(competicao="N/D", media_amarelos=5.0, media_faltas=28.0)
    
    if not time_mandante:
        time_mandante = DadosTime(
            nome=time_mandante_nome, posicao="N/D",
            faltas_pro=12.0, faltas_contra=12.0,
            amarelos_pro=2.0, amarelos_contra=2.0
        )
    
    if not time_visitante:
        time_visitante = DadosTime(
            nome=time_visitante_nome, posicao="N/D",
            faltas_pro=12.0, faltas_contra=12.0,
            amarelos_pro=2.0, amarelos_contra=2.0
        )
    
    return DadosPartida(
        liga=liga,
        data=data,
        horario=horario,
        estadio=estadio,
        local=local,
        fase=fase,
        time_mandante=time_mandante,
        time_visitante=time_visitante,
        arbitro=arbitro,
        baseline=baseline,
        perfil_card=perfil_card
    )


# =============================================================================
# CÁLCULOS MATEMÁTICOS - DISTRIBUIÇÃO DE POISSON
# =============================================================================

def calcular_fatorial(n: int) -> int:
    """
    Calcula o fatorial de n.
    
    Fatorial: n! = n × (n-1) × (n-2) × ... × 1
    
    Exemplo:
        5! = 5 × 4 × 3 × 2 × 1 = 120
    """
    if n < 0:
        return 1
    return math.factorial(n)


def poisson_probabilidade(k: int, lambda_: float) -> float:
    """
    Calcula a probabilidade exata de k eventos usando Distribuição de Poisson.
    
    FÓRMULA:
        P(Y = k) = (e^(-λ) × λ^k) / k!
    
    Onde:
        - λ (lambda): expectativa média de eventos (cartões esperados)
        - k: número exato de eventos que queremos calcular
        - e: constante de Euler (≈ 2.71828)
    
    QUANDO USAR POISSON:
        - Eventos independentes
        - Taxa média conhecida
        - Condições normais de jogo
    
    Args:
        k: Número de cartões (0, 1, 2, 3, ...)
        lambda_: Taxa esperada de cartões (λ)
    
    Returns:
        Probabilidade de exatamente k cartões (entre 0 e 1)
    """
    if lambda_ <= 0:
        return 0.0 if k > 0 else 1.0
    
    # P(Y = k) = (e^(-λ) × λ^k) / k!
    return (math.exp(-lambda_) * (lambda_ ** k)) / calcular_fatorial(k)


def binomial_negativa_probabilidade(k: int, r: float, p: float) -> float:
    """
    Calcula a probabilidade usando Distribuição Binomial Negativa.
    
    FÓRMULA:
        P(Y = k) = C(k + r - 1, k) × p^r × (1-p)^k
    
    Onde:
        - r: parâmetro de dispersão (relacionado à variância)
        - p: probabilidade de "sucesso" 
        - k: número de eventos
    
    QUANDO USAR BINOMIAL NEGATIVA:
        - Árbitro rigoroso (maior variância)
        - Jogos decisivos (imprevisibilidade)
        - Média do árbitro muito acima da liga
        - Captura melhor a SOBREDISPERSÃO dos dados
    
    RELAÇÃO COM LAMBDA:
        - p = r / (r + λ)
        - E[Y] = λ (mesma média que Poisson)
        - Var[Y] = λ + λ²/r (variância maior que Poisson)
    
    Args:
        k: Número de cartões (0, 1, 2, 3, ...)
        r: Parâmetro de dispersão (quanto menor, maior a variância)
        p: Probabilidade derivada de r e λ
    
    Returns:
        Probabilidade de exatamente k cartões (entre 0 e 1)
    """
    if r <= 0 or p <= 0 or p >= 1:
        return 0.0
    
    # Coeficiente binomial usando função gamma
    # C(k + r - 1, k) = Γ(k + r) / (Γ(r) × k!)
    try:
        coef = math.gamma(k + r) / (math.gamma(r) * calcular_fatorial(k))
        prob = coef * (p ** r) * ((1 - p) ** k)
        return prob
    except (ValueError, OverflowError):
        return 0.0


def converter_lambda_para_negbin(lambda_: float, dispersao: float = 3.0) -> tuple:
    """
    Converte λ (Poisson) para parâmetros da Binomial Negativa.
    
    A Binomial Negativa é parametrizada de forma que:
        - Média = λ (igual à Poisson)
        - Variância = λ + λ²/r (maior que Poisson)
    
    Args:
        lambda_: Taxa esperada (média)
        dispersao: Parâmetro r (quanto menor, maior a variância)
                   Valores típicos: 2-5 para futebol
    
    Returns:
        Tupla (r, p) para usar na função binomial_negativa_probabilidade
    """
    r = dispersao
    p = r / (r + lambda_)
    return (r, p)


def poisson_cumulativa(k_max: int, lambda_: float) -> float:
    """
    Calcula P(Y ≤ k_max) - probabilidade de até k_max eventos (Poisson).
    
    É a soma de todas as probabilidades de 0 até k_max:
        P(Y ≤ k) = P(Y=0) + P(Y=1) + ... + P(Y=k)
    """
    return sum(poisson_probabilidade(i, lambda_) for i in range(k_max + 1))


def negbin_cumulativa(k_max: int, r: float, p: float) -> float:
    """
    Calcula P(Y ≤ k_max) - probabilidade de até k_max eventos (Binomial Negativa).
    """
    return sum(binomial_negativa_probabilidade(i, r, p) for i in range(k_max + 1))


def calcular_over(linha: float, lambda_: float, modelo: str = "Poisson", dispersao: float = 3.0) -> float:
    """
    Calcula probabilidade de OVER (mais que X cartões).
    
    FÓRMULA:
        P(Over X) = 1 - P(Y ≤ X)
                  = 1 - [P(0) + P(1) + ... + P(X)]
    
    Args:
        linha: Linha do mercado (2.5, 3.5, 4.5, etc.)
        lambda_: Taxa esperada de cartões
        modelo: "Poisson" ou "Binomial Negativa"
        dispersao: Parâmetro r para Binomial Negativa
    
    Returns:
        Probabilidade em decimal (0 a 1)
    """
    k_max = int(linha)  # 2.5 → 2, 3.5 → 3, etc.
    
    if modelo == "Binomial Negativa":
        r, p = converter_lambda_para_negbin(lambda_, dispersao)
        return 1 - negbin_cumulativa(k_max, r, p)
    else:
        return 1 - poisson_cumulativa(k_max, lambda_)


def calcular_under(linha: float, lambda_: float, modelo: str = "Poisson", dispersao: float = 3.0) -> float:
    """
    Calcula probabilidade de UNDER (menos que X cartões).
    
    FÓRMULA:
        P(Under X) = P(Y ≤ X-1) = P(0) + P(1) + ... + P(X-1)
    
    Para Under 3.5, precisamos de P(Y ≤ 3):
        P(Under 3.5) = P(0) + P(1) + P(2) + P(3)
    
    Args:
        linha: Linha do mercado (2.5, 3.5, 4.5, etc.)
        lambda_: Taxa esperada de cartões
        modelo: "Poisson" ou "Binomial Negativa"
        dispersao: Parâmetro r para Binomial Negativa
    
    Returns:
        Probabilidade em decimal (0 a 1)
    """
    k_max = int(linha)  # 3.5 → 3, 4.5 → 4, etc.
    
    if modelo == "Binomial Negativa":
        r, p = converter_lambda_para_negbin(lambda_, dispersao)
        return negbin_cumulativa(k_max, r, p)
    else:
        return poisson_cumulativa(k_max, lambda_)


# =============================================================================
# CÁLCULO DO LAMBDA (λ) - EXPECTATIVA DE CARTÕES
# =============================================================================

@dataclass
class CalculoLambda:
    """Armazena todos os passos do cálculo do Lambda (MODELO ADITIVO)."""
    # Base
    lambda_base: float              # Média base da liga
    
    # Ajustes aditivos
    delta_arbitro: float            # Ajuste do árbitro (aditivo)
    delta_times: float              # Ajuste dos times (aditivo)
    ajuste_recencia: float          # Ajuste de recência (aditivo)
    
    # Lambda final
    lambda_final: float             # Lambda final calculado
    
    # Valores intermediários para exibição
    media_5j_arbitro: float
    media_10j_arbitro: float
    media_arbitro_ponderada: float
    amarelos_mandante: float
    amarelos_visitante: float
    soma_amarelos_times: float
    
    # Fator de recência (capado)
    fator_recencia_raw: float
    fator_recencia_capado: float
    
    # Modelo utilizado
    modelo_utilizado: str           # "Poisson" ou "Binomial Negativa"
    motivo_modelo: str              # Explicação do motivo


def calcular_lambda(partida: DadosPartida) -> CalculoLambda:
    """
    Calcula o Lambda (λ) usando MODELO ADITIVO CALIBRADO.
    
    PRINCÍPIOS DO NOVO MODELO:
    ==========================
    - NÃO utiliza multiplicação excessiva de fatores
    - Foco em estimativa ESTÁVEL, ADITIVA e CAUSAL
    - Evita extremos artificiais de λ
    - Reduz UNDER falso e OVER inflado
    
    METODOLOGIA:
    ============
    
    1) LAMBDA BASE DA LIGA (λ_base):
       λ_base = média histórica de cartões da competição
    
    2) AJUSTE DO ÁRBITRO (Δ_arbitro):
       média_ponderada = (0.6 × média_5j + 0.4 × média_10j)
       Δ_arbitro = 0.8 × (média_ponderada - média_liga)
       
       → Se positivo: árbitro dá mais cartões que a média
       → Se negativo: árbitro dá menos cartões que a média
    
    3) AJUSTE DOS TIMES (Δ_times):
       soma_cartões = cartões_mandante + cartões_visitante
       Δ_times = 0.6 × (soma_cartões - média_liga)
       
       → Captura o perfil disciplinar combinado dos times
    
    4) AJUSTE DE RECÊNCIA (CAPADO entre 0.95 e 1.05):
       F_raw = 1 + ((média_5j - média_10j) / média_10j)
       F_capado = max(0.95, min(1.05, F_raw))
       ajuste_recencia = λ_base × (F_capado - 1)
       
       → Recência NÃO domina o modelo
    
    5) LAMBDA FINAL (SOMA ADITIVA):
       λ_final = λ_base + Δ_arbitro + Δ_times + ajuste_recencia
    
    6) ESCOLHA DO MODELO:
       - Poisson: padrão
       - Binomial Negativa: árbitro rigoroso OU média > liga + 1.0
    
    Returns:
        CalculoLambda com todos os valores calculados
    """
    
    # ==========================================================
    # 1) LAMBDA BASE DA LIGA
    # ==========================================================
    lambda_base = partida.baseline.media_amarelos
    if lambda_base <= 0:
        lambda_base = 5.0  # Valor padrão se não disponível
    
    # ==========================================================
    # 2) AJUSTE DO ÁRBITRO (Δ_arbitro)
    # ==========================================================
    media_5j = partida.arbitro.media_amarelos_5j
    media_10j = partida.arbitro.media_amarelos_10j
    
    # Se não tiver dados de 5j, usa 10j para ambos
    if media_5j <= 0:
        media_5j = media_10j
    if media_10j <= 0:
        media_10j = media_5j
    if media_5j <= 0 and media_10j <= 0:
        media_5j = media_10j = lambda_base
    
    # Média ponderada do árbitro (60% recente, 40% histórico)
    media_arbitro_ponderada = (0.6 * media_5j) + (0.4 * media_10j)
    
    # Delta do árbitro (diferença em relação à liga)
    delta_arbitro_raw = media_arbitro_ponderada - lambda_base
    
    # Aplicar peso de 0.8 para suavizar o ajuste
    delta_arbitro = 0.8 * delta_arbitro_raw
    
    # ==========================================================
    # 3) AJUSTE DOS TIMES (Δ_times)
    # ==========================================================
    amarelos_mandante = partida.time_mandante.amarelos_pro
    amarelos_visitante = partida.time_visitante.amarelos_pro
    
    # Se não tiver dados, usa metade da média da liga
    if amarelos_mandante <= 0:
        amarelos_mandante = lambda_base / 2
    if amarelos_visitante <= 0:
        amarelos_visitante = lambda_base / 2
    
    # Soma dos cartões esperados dos times
    soma_amarelos_times = amarelos_mandante + amarelos_visitante
    
    # Delta dos times (diferença em relação à liga)
    delta_times_raw = soma_amarelos_times - lambda_base
    
    # Aplicar peso de 0.6 para suavizar o ajuste
    delta_times = 0.6 * delta_times_raw
    
    # ==========================================================
    # 4) AJUSTE DE RECÊNCIA (CAPADO)
    # ==========================================================
    # Calcular fator de recência raw
    if media_10j > 0:
        fator_recencia_raw = 1.0 + ((media_5j - media_10j) / media_10j)
    else:
        fator_recencia_raw = 1.0
    
    # CAPAR entre 0.95 e 1.05 (recência não domina o modelo)
    fator_recencia_capado = max(0.95, min(1.05, fator_recencia_raw))
    
    # Ajuste de recência (aditivo)
    ajuste_recencia = lambda_base * (fator_recencia_capado - 1.0)
    
    # ==========================================================
    # 5) LAMBDA FINAL (MODELO ADITIVO)
    # ==========================================================
    lambda_final = lambda_base + delta_arbitro + delta_times + ajuste_recencia
    
    # Garantir que λ não seja negativo ou excessivo
    lambda_final = max(2.0, min(10.0, lambda_final))
    
    # ==========================================================
    # 6) ESCOLHA DO MODELO PROBABILÍSTICO
    # ==========================================================
    # Usar Binomial Negativa quando:
    # - Árbitro for "Rigoroso"
    # - Média do árbitro > média da liga + 1.0
    # - Jogo decisivo/mata-mata (identificado pela fase)
    
    usar_binomial_negativa = False
    motivos = []
    
    # Verificar perfil do árbitro
    perfil = partida.arbitro.perfil.lower()
    if 'rigoroso' in perfil:
        usar_binomial_negativa = True
        motivos.append("Árbitro classificado como Rigoroso")
    
    # Verificar se média do árbitro é muito acima da liga
    if media_arbitro_ponderada > (lambda_base + 1.0):
        usar_binomial_negativa = True
        motivos.append(f"Média do árbitro ({media_arbitro_ponderada:.1f}) > média da liga + 1.0 ({lambda_base + 1.0:.1f})")
    
    # Verificar se é jogo decisivo (mata-mata, final, semi, etc.)
    fase_lower = partida.fase.lower() if partida.fase else ""
    fases_decisivas = ['final', 'semi', 'quarta', 'oitava', 'mata', 'eliminat', 'decisiv', 'playoff']
    if any(f in fase_lower for f in fases_decisivas):
        usar_binomial_negativa = True
        motivos.append(f"Jogo decisivo/mata-mata ({partida.fase})")
    
    if usar_binomial_negativa:
        modelo_utilizado = "Binomial Negativa"
        motivo_modelo = " | ".join(motivos)
    else:
        modelo_utilizado = "Poisson"
        motivo_modelo = "Condições normais de jogo (padrão)"
    
    return CalculoLambda(
        lambda_base=lambda_base,
        delta_arbitro=delta_arbitro,
        delta_times=delta_times,
        ajuste_recencia=ajuste_recencia,
        lambda_final=lambda_final,
        media_5j_arbitro=media_5j,
        media_10j_arbitro=media_10j,
        media_arbitro_ponderada=media_arbitro_ponderada,
        amarelos_mandante=amarelos_mandante,
        amarelos_visitante=amarelos_visitante,
        soma_amarelos_times=soma_amarelos_times,
        fator_recencia_raw=fator_recencia_raw,
        fator_recencia_capado=fator_recencia_capado,
        modelo_utilizado=modelo_utilizado,
        motivo_modelo=motivo_modelo
    )


# =============================================================================
# GERAÇÃO DO HTML
# =============================================================================

def gerar_css_adicional() -> str:
    """Gera CSS adicional para as seções de cálculo."""
    return """
        /* Seções de Cálculo */
        .calculo-section {
            background: #1a1a2e;
            border-radius: 10px;
            padding: 20px;
            margin: 15px 0;
            border: 1px solid #0f3460;
        }
        
        .calculo-titulo {
            color: #3498db;
            font-size: 1.1em;
            font-weight: bold;
            margin-bottom: 15px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .calculo-passo {
            background: rgba(15, 52, 96, 0.3);
            padding: 15px;
            border-radius: 8px;
            margin: 10px 0;
            border-left: 3px solid #e94560;
        }
        
        .calculo-passo-titulo {
            color: #e94560;
            font-weight: bold;
            margin-bottom: 8px;
        }
        
        .calculo-formula {
            font-family: 'Courier New', monospace;
            background: #0f3460;
            padding: 10px 15px;
            border-radius: 5px;
            color: #2ecc71;
            margin: 8px 0;
            overflow-x: auto;
        }
        
        .calculo-resultado {
            color: #f6e05e;
            font-weight: bold;
            font-size: 1.1em;
        }
        
        /* Modelo Matemático */
        .modelo-box {
            background: linear-gradient(135deg, rgba(52, 152, 219, 0.1) 0%, rgba(15, 52, 96, 0.3) 100%);
            border: 2px solid #3498db;
            border-radius: 10px;
            padding: 20px;
            margin: 15px 0;
        }
        
        .modelo-formula-principal {
            text-align: center;
            font-size: 1.3em;
            font-family: 'Courier New', monospace;
            color: #2ecc71;
            padding: 15px;
            background: #0f3460;
            border-radius: 8px;
            margin: 15px 0;
        }
        
        .modelo-explicacao {
            color: #a0a0a0;
            font-size: 0.95em;
            line-height: 1.6;
        }
        
        .modelo-explicacao strong {
            color: #e94560;
        }
        
        /* Probabilidades */
        .prob-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 15px 0;
        }
        
        .prob-card {
            background: #16213e;
            border-radius: 10px;
            padding: 20px;
            text-align: center;
            border: 1px solid #0f3460;
            transition: all 0.3s;
        }
        
        .prob-card:hover {
            border-color: #e94560;
            transform: translateY(-3px);
        }
        
        .prob-card.destaque {
            border-color: #2ecc71;
            box-shadow: 0 0 15px rgba(46, 204, 113, 0.3);
        }
        
        .prob-mercado {
            color: #a0a0a0;
            font-size: 0.9em;
            margin-bottom: 5px;
        }
        
        .prob-valor {
            font-size: 2em;
            font-weight: bold;
            color: #e94560;
        }
        
        .prob-card.destaque .prob-valor {
            color: #2ecc71;
        }
        
        .prob-descricao {
            color: #606060;
            font-size: 0.8em;
            margin-top: 5px;
        }
        
        /* Interpretação */
        .interpretacao-box {
            background: linear-gradient(135deg, rgba(233, 69, 96, 0.1) 0%, rgba(15, 52, 96, 0.2) 100%);
            border-left: 4px solid #e94560;
            border-radius: 0 10px 10px 0;
            padding: 20px;
            margin: 20px 0;
        }
        
        .interpretacao-titulo {
            color: #e94560;
            font-weight: bold;
            font-size: 1.1em;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .interpretacao-texto {
            color: #c0c0c0;
            line-height: 1.7;
        }
        
        .lambda-destaque {
            display: inline-block;
            background: #e94560;
            color: white;
            padding: 3px 10px;
            border-radius: 15px;
            font-weight: bold;
        }
        
        /* Dados utilizados */
        .dados-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 10px;
            margin: 15px 0;
        }
        
        .dado-item {
            background: rgba(15, 52, 96, 0.3);
            padding: 12px;
            border-radius: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .dado-label {
            color: #a0a0a0;
            font-size: 0.9em;
        }
        
        .dado-valor {
            color: #e94560;
            font-weight: bold;
            font-size: 1.1em;
        }
    """


def gerar_secao_dados(partida: DadosPartida, calculo: CalculoLambda) -> str:
    """Gera a seção de dados utilizados no cálculo."""
    return f"""
        <div class="calculo-section">
            <div class="calculo-titulo">📊 Dados Utilizados no Cálculo</div>
            
            <div class="dados-grid">
                <div class="dado-item">
                    <span class="dado-label">Média da Liga (λ_base):</span>
                    <span class="dado-valor">{calculo.lambda_base:.2f}</span>
                </div>
                <div class="dado-item">
                    <span class="dado-label">Árbitro (5j):</span>
                    <span class="dado-valor">{calculo.media_5j_arbitro:.2f}</span>
                </div>
                <div class="dado-item">
                    <span class="dado-label">Árbitro (10j):</span>
                    <span class="dado-valor">{calculo.media_10j_arbitro:.2f}</span>
                </div>
                <div class="dado-item">
                    <span class="dado-label">{partida.time_mandante.nome}:</span>
                    <span class="dado-valor">{calculo.amarelos_mandante:.2f} cart.</span>
                </div>
                <div class="dado-item">
                    <span class="dado-label">{partida.time_visitante.nome}:</span>
                    <span class="dado-valor">{calculo.amarelos_visitante:.2f} cart.</span>
                </div>
                <div class="dado-item">
                    <span class="dado-label">Perfil Árbitro:</span>
                    <span class="dado-valor">{partida.arbitro.perfil}</span>
                </div>
            </div>
        </div>
    """


def gerar_secao_calculo(calculo: CalculoLambda, partida: DadosPartida) -> str:
    """Gera a seção de cálculos passo a passo (MODELO ADITIVO)."""
    
    # Sinal para exibição
    sinal_arbitro = "+" if calculo.delta_arbitro >= 0 else ""
    sinal_times = "+" if calculo.delta_times >= 0 else ""
    sinal_recencia = "+" if calculo.ajuste_recencia >= 0 else ""
    
    # Interpretações
    if calculo.delta_arbitro > 0.3:
        texto_arbitro = "↑ Árbitro ACIMA da média da liga"
        cor_arbitro = "#e94560"
    elif calculo.delta_arbitro < -0.3:
        texto_arbitro = "↓ Árbitro ABAIXO da média da liga"
        cor_arbitro = "#2ecc71"
    else:
        texto_arbitro = "≈ Árbitro na MÉDIA da liga"
        cor_arbitro = "#f6e05e"
    
    if calculo.delta_times > 0.3:
        texto_times = "↑ Times com perfil ACIMA da média"
        cor_times = "#e94560"
    elif calculo.delta_times < -0.3:
        texto_times = "↓ Times com perfil ABAIXO da média"
        cor_times = "#2ecc71"
    else:
        texto_times = "≈ Times na MÉDIA da liga"
        cor_times = "#f6e05e"
    
    return f"""
        <div class="calculo-section">
            <div class="calculo-titulo">🧮 Construção do Lambda (λ) — MODELO ADITIVO</div>
            
            <div class="calculo-passo">
                <div class="calculo-passo-titulo">1️⃣ Lambda Base da Liga (λ_base)</div>
                <div class="calculo-formula">λ_base = {calculo.lambda_base:.2f}</div>
                <p style="color: #a0a0a0; font-size: 0.9em;">
                    Ponto de partida: média histórica de cartões da {partida.baseline.competicao}
                </p>
            </div>
            
            <div class="calculo-passo">
                <div class="calculo-passo-titulo">2️⃣ Ajuste do Árbitro (Δ_arbitro)</div>
                <div class="calculo-formula">
                    média_ponderada = (0.6 × {calculo.media_5j_arbitro:.2f}) + (0.4 × {calculo.media_10j_arbitro:.2f}) = {calculo.media_arbitro_ponderada:.2f}
                </div>
                <div class="calculo-formula">
                    Δ_arbitro = 0.8 × ({calculo.media_arbitro_ponderada:.2f} - {calculo.lambda_base:.2f}) = <span class="calculo-resultado">{sinal_arbitro}{calculo.delta_arbitro:.2f}</span>
                </div>
                <p style="color: {cor_arbitro}; font-size: 0.9em; font-weight: bold;">
                    {texto_arbitro}
                </p>
            </div>
            
            <div class="calculo-passo">
                <div class="calculo-passo-titulo">3️⃣ Ajuste dos Times (Δ_times)</div>
                <div class="calculo-formula">
                    soma_cartões = {calculo.amarelos_mandante:.2f} + {calculo.amarelos_visitante:.2f} = {calculo.soma_amarelos_times:.2f}
                </div>
                <div class="calculo-formula">
                    Δ_times = 0.6 × ({calculo.soma_amarelos_times:.2f} - {calculo.lambda_base:.2f}) = <span class="calculo-resultado">{sinal_times}{calculo.delta_times:.2f}</span>
                </div>
                <p style="color: {cor_times}; font-size: 0.9em; font-weight: bold;">
                    {texto_times}
                </p>
            </div>
            
            <div class="calculo-passo">
                <div class="calculo-passo-titulo">4️⃣ Ajuste de Recência (CAPADO entre 0.95 e 1.05)</div>
                <div class="calculo-formula">
                    F_raw = 1 + (({calculo.media_5j_arbitro:.2f} - {calculo.media_10j_arbitro:.2f}) / {calculo.media_10j_arbitro:.2f}) = {calculo.fator_recencia_raw:.4f}
                </div>
                <div class="calculo-formula">
                    F_capado = max(0.95, min(1.05, {calculo.fator_recencia_raw:.4f})) = <span class="calculo-resultado">{calculo.fator_recencia_capado:.4f}</span>
                </div>
                <div class="calculo-formula">
                    ajuste_recencia = {calculo.lambda_base:.2f} × ({calculo.fator_recencia_capado:.4f} - 1) = <span class="calculo-resultado">{sinal_recencia}{calculo.ajuste_recencia:.2f}</span>
                </div>
                <p style="color: #a0a0a0; font-size: 0.9em;">
                    ⚠️ Recência CAPADA para não dominar o modelo (±5% máximo)
                </p>
            </div>
            
            <div class="calculo-passo" style="border-color: #2ecc71;">
                <div class="calculo-passo-titulo" style="color: #2ecc71;">5️⃣ Lambda Final (SOMA ADITIVA)</div>
                <div class="calculo-formula">
                    λ_final = λ_base + Δ_arbitro + Δ_times + ajuste_recencia
                </div>
                <div class="calculo-formula">
                    λ_final = {calculo.lambda_base:.2f} {sinal_arbitro}{calculo.delta_arbitro:.2f} {sinal_times}{calculo.delta_times:.2f} {sinal_recencia}{calculo.ajuste_recencia:.2f}
                </div>
                <div class="calculo-formula" style="font-size: 1.2em;">
                    λ_final = <span class="calculo-resultado" style="font-size: 1.3em;">{calculo.lambda_final:.2f} cartões</span>
                </div>
            </div>
        </div>
    """


def gerar_secao_modelo(calculo: CalculoLambda) -> str:
    """Gera a seção explicando o modelo matemático utilizado (DINÂMICO)."""
    
    if calculo.modelo_utilizado == "Binomial Negativa":
        cor_modelo = "#e94560"
        explicacao_modelo = """
            <p><strong>Por que Binomial Negativa neste jogo?</strong></p>
            <p style="color: #f6e05e;">
                """ + calculo.motivo_modelo + """
            </p>
            <p style="margin-top: 10px;">
                A Binomial Negativa captura melhor a <strong>sobredispersão</strong> (variância maior que a média), 
                comum em jogos com árbitros rigorosos ou partidas decisivas onde há mais imprevisibilidade.
            </p>
            <p style="margin-top: 10px;">
                <strong>Diferença prática:</strong> As probabilidades de extremos (muito poucos ou muitos cartões) 
                são MAIORES que na Poisson, refletindo a incerteza adicional.
            </p>
        """
        formula_html = """
            <div class="modelo-formula-principal">
                P(Y = k) = C(k + r - 1, k) × p<sup>r</sup> × (1-p)<sup>k</sup>
            </div>
            <p style="text-align: center; color: #a0a0a0; font-size: 0.9em;">
                Onde: r = parâmetro de dispersão, p = r/(r+λ)
            </p>
        """
    else:
        cor_modelo = "#2ecc71"
        explicacao_modelo = """
            <p><strong>Por que Poisson neste jogo?</strong></p>
            <p style="color: #2ecc71;">
                """ + calculo.motivo_modelo + """
            </p>
            <p style="margin-top: 10px;">
                A distribuição de Poisson é adequada quando os eventos (cartões) são:
            </p>
            <ul style="margin: 10px 0; padding-left: 20px; color: #a0a0a0;">
                <li>Independentes entre si</li>
                <li>Ocorrem com taxa média conhecida (λ)</li>
                <li>Variância aproximadamente igual à média</li>
            </ul>
        """
        formula_html = """
            <div class="modelo-formula-principal">
                P(Y = k) = (e<sup>-λ</sup> × λ<sup>k</sup>) ÷ k!
            </div>
        """
    
    return f"""
        <div class="modelo-box" style="border-color: {cor_modelo};">
            <div class="calculo-titulo">📈 Modelo Matemático: <span style="color: {cor_modelo};">{calculo.modelo_utilizado}</span></div>
            
            {formula_html}
            
            <div class="modelo-explicacao">
                {explicacao_modelo}
                
                <p style="margin-top: 15px;"><strong>Variáveis da fórmula:</strong></p>
                <ul style="padding-left: 20px;">
                    <li><strong>λ (lambda) = {calculo.lambda_final:.2f}</strong>: Expectativa de cartões calculada</li>
                    <li><strong>k</strong>: Número exato de cartões que queremos calcular</li>
                    <li><strong>e</strong>: Constante de Euler (≈ 2.71828)</li>
                </ul>
            </div>
        </div>
    """


def gerar_secao_probabilidades(calculo: CalculoLambda) -> str:
    """Gera a seção de probabilidades calculadas (com modelo dinâmico)."""
    
    lambda_ = calculo.lambda_final
    modelo = calculo.modelo_utilizado
    
    # Calcula as probabilidades usando o modelo apropriado
    over_25 = calcular_over(2.5, lambda_, modelo) * 100
    over_35 = calcular_over(3.5, lambda_, modelo) * 100
    over_45 = calcular_over(4.5, lambda_, modelo) * 100
    over_55 = calcular_over(5.5, lambda_, modelo) * 100
    under_35 = calcular_under(3.5, lambda_, modelo) * 100
    under_45 = calcular_under(4.5, lambda_, modelo) * 100
    under_55 = calcular_under(5.5, lambda_, modelo) * 100
    
    # Determina qual é a melhor aposta (maior probabilidade)
    melhores = [
        ('Over 2.5', over_25),
        ('Over 3.5', over_35),
        ('Over 4.5', over_45),
        ('Under 3.5', under_35),
        ('Under 4.5', under_45),
    ]
    
    # Encontra probabilidades acima de 55% (valor arbitrário para destaque)
    destaques = [m[0] for m in melhores if m[1] >= 55]
    
    # Cor do modelo
    cor_modelo = "#e94560" if modelo == "Binomial Negativa" else "#2ecc71"
    
    return f"""
        <div class="calculo-section">
            <div class="calculo-titulo">🎯 Probabilidades Calculadas</div>
            <p style="color: {cor_modelo}; margin-bottom: 15px; font-weight: bold;">
                λ = {lambda_:.2f} | Modelo: {modelo}
            </p>
            
            <div class="prob-grid">
                <div class="prob-card {'destaque' if 'Over 2.5' in destaques else ''}">
                    <div class="prob-mercado">Over 2.5 Cartões</div>
                    <div class="prob-valor">{over_25:.2f}%</div>
                    <div class="prob-descricao">3 ou mais cartões</div>
                </div>
                
                <div class="prob-card {'destaque' if 'Over 3.5' in destaques else ''}">
                    <div class="prob-mercado">Over 3.5 Cartões</div>
                    <div class="prob-valor">{over_35:.2f}%</div>
                    <div class="prob-descricao">4 ou mais cartões</div>
                </div>
                
                <div class="prob-card {'destaque' if 'Over 4.5' in destaques else ''}">
                    <div class="prob-mercado">Over 4.5 Cartões</div>
                    <div class="prob-valor">{over_45:.2f}%</div>
                    <div class="prob-descricao">5 ou mais cartões</div>
                </div>
                
                <div class="prob-card">
                    <div class="prob-mercado">Over 5.5 Cartões</div>
                    <div class="prob-valor">{over_55:.2f}%</div>
                    <div class="prob-descricao">6 ou mais cartões</div>
                </div>
                
                <div class="prob-card {'destaque' if 'Under 3.5' in destaques else ''}">
                    <div class="prob-mercado">Under 3.5 Cartões</div>
                    <div class="prob-valor">{under_35:.2f}%</div>
                    <div class="prob-descricao">3 ou menos cartões</div>
                </div>
                
                <div class="prob-card {'destaque' if 'Under 4.5' in destaques else ''}">
                    <div class="prob-mercado">Under 4.5 Cartões</div>
                    <div class="prob-valor">{under_45:.2f}%</div>
                    <div class="prob-descricao">4 ou menos cartões</div>
                </div>
                
                <div class="prob-card">
                    <div class="prob-mercado">Under 5.5 Cartões</div>
                    <div class="prob-valor">{under_55:.2f}%</div>
                    <div class="prob-descricao">5 ou menos cartões</div>
                </div>
            </div>
            
            <p style="color: #606060; font-size: 0.85em; text-align: center; margin-top: 15px;">
                * Cards em destaque (verde) indicam probabilidades ≥ 55%
            </p>
        </div>
    """


def gerar_interpretacao(calculo: CalculoLambda, partida: DadosPartida) -> str:
    """Gera a interpretação final dos resultados (sem linguagem de aposta)."""
    
    lambda_ = calculo.lambda_final
    
    # Determina a tendência baseada no lambda
    if lambda_ >= 5.5:
        tendencia = "ELEVADA"
        descricao = "expectativa elevada de cartões"
        cor = "#e94560"
    elif lambda_ <= 3.5:
        tendencia = "BAIXA"
        descricao = "expectativa baixa de cartões"
        cor = "#2ecc71"
    else:
        tendencia = "MODERADA"
        descricao = "expectativa moderada de cartões"
        cor = "#f6e05e"
    
    # Texto sobre os ajustes
    ajustes_texto = []
    
    if calculo.delta_arbitro > 0.3:
        ajustes_texto.append(f"O árbitro {partida.arbitro.nome} possui histórico <strong>acima</strong> da média da competição (+{calculo.delta_arbitro:.2f}).")
    elif calculo.delta_arbitro < -0.3:
        ajustes_texto.append(f"O árbitro {partida.arbitro.nome} possui histórico <strong>abaixo</strong> da média da competição ({calculo.delta_arbitro:.2f}).")
    else:
        ajustes_texto.append(f"O árbitro {partida.arbitro.nome} está na <strong>média</strong> da competição.")
    
    if calculo.delta_times > 0.3:
        ajustes_texto.append(f"O perfil combinado dos times indica tendência de <strong>mais</strong> cartões (+{calculo.delta_times:.2f}).")
    elif calculo.delta_times < -0.3:
        ajustes_texto.append(f"O perfil combinado dos times indica tendência de <strong>menos</strong> cartões ({calculo.delta_times:.2f}).")
    
    ajustes_html = " ".join(ajustes_texto)
    
    # Cor do modelo
    cor_modelo = "#e94560" if calculo.modelo_utilizado == "Binomial Negativa" else "#2ecc71"
    
    return f"""
        <div class="interpretacao-box">
            <div class="interpretacao-titulo">🧠 Interpretação Estatística</div>
            
            <div class="interpretacao-texto">
                <p>
                    Com base no <strong>modelo aditivo calibrado</strong>, a expectativa matemática 
                    desta partida é de <span class="lambda-destaque">{lambda_:.2f} cartões</span>.
                </p>
                
                <p style="margin-top: 12px;">
                    {ajustes_html}
                </p>
                
                <p style="margin-top: 12px;">
                    O perfil combinado indica <strong style="color: {cor};">{tendencia}</strong> ({descricao}).
                </p>
                
                <p style="margin-top: 12px;">
                    <strong>Modelo utilizado:</strong> <span style="color: {cor_modelo};">{calculo.modelo_utilizado}</span>
                    <br><span style="font-size: 0.9em; color: #a0a0a0;">{calculo.motivo_modelo}</span>
                </p>
                
                <div style="margin-top: 20px; padding: 15px; background: rgba(52, 152, 219, 0.1); border-radius: 8px; border-left: 3px solid #3498db;">
                    <p style="font-size: 0.9em; color: #a0a0a0; margin: 0;">
                        ℹ️ <strong>Nota metodológica:</strong> As probabilidades representam frequência esperada no longo prazo. 
                        Erros individuais fazem parte de modelos probabilísticos e não invalidam a metodologia.
                    </p>
                </div>
                
                <p style="margin-top: 15px; font-size: 0.85em; color: #606060;">
                    ⚠️ Esta análise é puramente estatística. Fatores externos como clima, 
                    rivalidade histórica e importância do jogo podem influenciar o resultado real.
                </p>
            </div>
        </div>
    """


def gerar_card_probabilidade(partida: DadosPartida, calculo: CalculoLambda) -> str:
    """Gera o card completo com análise de probabilidade."""
    
    return f"""
        <div class="jogo-card" data-perfil="{partida.perfil_card}">
            <div class="jogo-header">
                <div class="jogo-titulo">{partida.time_mandante.nome} ({partida.time_mandante.posicao}) vs {partida.time_visitante.nome} ({partida.time_visitante.posicao})</div>
                <div class="jogo-data">
                    <div class="horario">{partida.horario}</div>
                    <div class="data">{partida.data}</div>
                </div>
            </div>
            
            <div class="jogo-info-bar">
                <span>
                    <span class="info-label">🏆 Competição:</span>
                    <span class="info-value">{partida.liga}</span>
                </span>
                <span>
                    <span class="info-label">🏟️ Estádio:</span>
                    <span class="info-value">{partida.estadio}</span>
                </span>
                <span>
                    <span class="info-label">⚖️ Árbitro:</span>
                    <span class="info-value">{partida.arbitro.nome}</span>
                </span>
                <span>
                    <span class="info-label">📊 Modelo:</span>
                    <span class="info-value" style="color: {'#e94560' if calculo.modelo_utilizado == 'Binomial Negativa' else '#2ecc71'};">{calculo.modelo_utilizado}</span>
                </span>
            </div>
            
            <div class="jogo-content">
                <div class="secao">
                    <div class="secao-titulo">📊 Análise Probabilística de Cartões</div>
                    
                    {gerar_secao_dados(partida, calculo)}
                    
                    {gerar_secao_calculo(calculo, partida)}
                    
                    {gerar_secao_modelo(calculo)}
                    
                    {gerar_secao_probabilidades(calculo)}
                    
                    {gerar_interpretacao(calculo, partida)}
                </div>
            </div>
        </div>
    """


def gerar_html_completo(partidas: list, data_arquivo: str, css_original: str) -> str:
    """Gera o HTML completo com todas as partidas analisadas."""
    
    # Gera os cards de probabilidade
    cards_html = ""
    for partida in partidas:
        calculo = calcular_lambda(partida)
        cards_html += gerar_card_probabilidade(partida, calculo)
    
    # CSS adicional para as seções de cálculo
    css_adicional = gerar_css_adicional()
    
    # Timestamp para o footer
    timestamp_geracao = datetime.now().strftime('%d/%m/%Y %H:%M')
    
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RefStats - Análise Probabilística {data_arquivo}</title>
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
                url("../assets/img/FundoMuroFundo.png");
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
        
        .footer a {{
            color: #3498db;
            text-decoration: none;
        }}
        
        .footer a:hover {{
            text-decoration: underline;
        }}
        
        /* Responsivo */
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
            
            .jogo-header {{
                flex-direction: column;
                gap: 15px;
                text-align: center;
            }}
            
            .jogo-data {{
                text-align: center;
            }}
            
            .jogo-titulo {{
                font-size: 1.4em;
            }}
        }}
        
        {css_adicional}
    </style>
</head>
<body>
    <!-- Navbar (igual ao Home) -->
    <nav class="navbar">
        <a href="../index.html" class="navbar-brand">
            <img src="../assets/img/LogoINICIO.png" alt="RefStats" class="logo-img">
        </a>
        
        <button class="menu-toggle" onclick="document.getElementById('navMenu').classList.toggle('active')" aria-label="Menu">
            ☰
        </button>
        
        <div class="navbar-menu" id="navMenu">
            <a href="../index.html">INÍCIO</a>
            <a href="../JOGOS_DO_DIA.html">JOGOS DO DIA</a>
            <a href="../refstats_historico.html">HISTÓRICO</a>
            <a href="../refstats_contato.html">CONTATO</a>
        </div>
    </nav>
    
    <div class="container">
        <div class="header">
            <h1>📊 Análise Probabilística de Cartões</h1>
            <p>📅 {data_arquivo} • {len(partidas)} partida(s) analisada(s)</p>
            <p style="color: #3498db; margin-top: 10px;">Modelo Aditivo Calibrado + Seleção Dinâmica (Poisson / Binomial Negativa)</p>
        </div>
        
        {cards_html}
        
        <div class="footer">
            <p><strong>📊 RefStats - Análise Probabilística de Cartões</strong></p>
            <p>
                <a href="../refstats_termos.html">Termos de Uso</a> | 
                <a href="../refstats_privacidade.html">Política de Privacidade</a> | 
                <a href="../refstats_aviso_legal.html">Aviso Legal</a> |
                <a href="../refstats_faq.html">FAQ</a>
            </p>
            <p style="margin-top: 15px; font-size: 0.9em;">
                <strong>Modelo:</strong> Aditivo Calibrado com seleção dinâmica (Poisson / Binomial Negativa)
            </p>
            <p style="margin-top: 10px; font-size: 0.85em; color: #a0a0a0;">
                Gerado em {timestamp_geracao}
            </p>
            <div style="margin-top: 15px; padding: 15px; background: rgba(52, 152, 219, 0.1); border-radius: 8px;">
                <p style="font-size: 0.85em; color: #3498db; margin: 0;">
                    ℹ️ <strong>Aviso Metodológico:</strong> As probabilidades representam frequência esperada no longo prazo. 
                    Erros individuais fazem parte de modelos probabilísticos e não invalidam a metodologia.
                </p>
            </div>
            <p style="margin-top: 15px; font-size: 0.8em; color: #e94560;">
                ⚠️ Este site é apenas para fins informativos e educacionais. 
                Não utilizamos linguagem de aposta, dicas ou palpites. 
                O foco é exclusivamente previsão estatística.
            </p>
        </div>
    </div>
</body>
</html>
"""


# =============================================================================
# FUNÇÃO PRINCIPAL
# =============================================================================

def extrair_css_original(soup: BeautifulSoup) -> str:
    """Extrai o CSS original do arquivo HTML."""
    style_tag = soup.find('style')
    if style_tag:
        return style_tag.get_text()
    return ""


def processar_arquivo(caminho_entrada: str, pasta_saida: str) -> bool:
    """
    Processa um arquivo HTML de jogos do dia.
    
    Args:
        caminho_entrada: Caminho completo do arquivo de entrada
        pasta_saida: Pasta onde salvar o arquivo de saída
    
    Returns:
        True se processado com sucesso, False caso contrário
    """
    print(f"\n{'='*60}")
    print(f"📂 Processando: {os.path.basename(caminho_entrada)}")
    print(f"{'='*60}")
    
    try:
        # Lê o arquivo HTML
        with open(caminho_entrada, 'r', encoding='utf-8') as f:
            conteudo = f.read()
        
        soup = BeautifulSoup(conteudo, 'html.parser')
        
        # Extrai CSS original
        css_original = extrair_css_original(soup)
        
        # Encontra todos os cards de jogo
        cards = soup.find_all(class_='jogo-card')
        print(f"✅ Encontrados {len(cards)} jogos no arquivo")
        
        if not cards:
            print("⚠️ Nenhum jogo encontrado no arquivo!")
            return False
        
        # Extrai dados de cada partida
        partidas = []
        for i, card in enumerate(cards, 1):
            partida = extrair_partida(card)
            if partida:
                partidas.append(partida)
                print(f"   {i}. {partida.time_mandante.nome} vs {partida.time_visitante.nome}")
        
        print(f"\n✅ {len(partidas)} partidas extraídas com sucesso")
        
        # Extrai a data do nome do arquivo
        # Formato: JOGOS_DO_DIA_07122025.html → 07/12/2025
        nome_arquivo = os.path.basename(caminho_entrada)
        match = re.search(r'(\d{2})(\d{2})(\d{4})', nome_arquivo)
        if match:
            data_arquivo = f"{match.group(1)}/{match.group(2)}/{match.group(3)}"
            data_saida = f"{match.group(1)}{match.group(2)}{match.group(3)}"
        else:
            data_arquivo = datetime.now().strftime("%d/%m/%Y")
            data_saida = datetime.now().strftime("%d%m%Y")
        
        # Gera o HTML de saída
        html_saida = gerar_html_completo(partidas, data_arquivo, css_original)
        
        # Cria pasta de saída se não existir
        os.makedirs(pasta_saida, exist_ok=True)
        
        # Salva o arquivo
        nome_saida = f"PROBABILIDADE_{data_saida}.html"
        caminho_saida = os.path.join(pasta_saida, nome_saida)
        
        with open(caminho_saida, 'w', encoding='utf-8') as f:
            f.write(html_saida)
        
        print(f"\n✅ Arquivo salvo: {caminho_saida}")
        return True
        
    except Exception as e:
        print(f"\n❌ Erro ao processar arquivo: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """
    Função principal - processa todos os arquivos na pasta Historico.
    """
    print("""
╔═══════════════════════════════════════════════════════════════╗
║     SISTEMA DE ANÁLISE PROBABILÍSTICA DE CARTÕES              ║
║          Modelo Aditivo + Poisson / Binomial Negativa         ║
╚═══════════════════════════════════════════════════════════════╝
    """)
    
    # Define as pastas
    pasta_atual = os.path.dirname(os.path.abspath(__file__))
    pasta_historico = os.path.join(pasta_atual, "Historico")
    pasta_probabilidade = os.path.join(pasta_atual, "Probabilidade")
    
    print(f"📁 Pasta de entrada: {pasta_historico}")
    print(f"📁 Pasta de saída: {pasta_probabilidade}")
    
    # Verifica se a pasta de entrada existe
    if not os.path.exists(pasta_historico):
        print(f"\n⚠️ Pasta 'Historico' não encontrada!")
        print(f"   Criando pasta: {pasta_historico}")
        os.makedirs(pasta_historico, exist_ok=True)
        print(f"\n📌 Coloque os arquivos JOGOS_DO_DIA_*.html na pasta 'Historico' e execute novamente.")
        return
    
    # Busca arquivos HTML na pasta
    padrao = os.path.join(pasta_historico, "JOGOS_DO_DIA_*.html")
    arquivos = glob.glob(padrao)
    
    if not arquivos:
        print(f"\n⚠️ Nenhum arquivo encontrado com o padrão 'JOGOS_DO_DIA_*.html'")
        print(f"   na pasta: {pasta_historico}")
        return
    
    print(f"\n📋 Arquivos encontrados: {len(arquivos)}")
    
    # Processa cada arquivo
    sucessos = 0
    falhas = 0
    
    for arquivo in sorted(arquivos):
        if processar_arquivo(arquivo, pasta_probabilidade):
            sucessos += 1
        else:
            falhas += 1
    
    # Resumo final
    print(f"""
╔═══════════════════════════════════════════════════════════════╗
║                      RESUMO DO PROCESSAMENTO                  ║
╠═══════════════════════════════════════════════════════════════╣
║  ✅ Arquivos processados com sucesso: {sucessos:3d}                     ║
║  ❌ Arquivos com falha: {falhas:3d}                                   ║
║  📁 Pasta de saída: Probabilidade/                            ║
╚═══════════════════════════════════════════════════════════════╝
    """)


if __name__ == "__main__":
    main()
