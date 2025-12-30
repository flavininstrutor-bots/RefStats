#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
SISTEMA DE ANÁLISE PROBABILÍSTICA DE CARTÕES - V2.0
=============================================================================
Autor: RefStats
Versão: 2.0

NOVIDADES V2.0:
==============
✅ Modelo Negative Binomial (melhor para sobredispersão)
✅ Shrinkage Bayesiano (regularização do λ)
✅ Calibração por Mercado (Isotonic Regression)
✅ Intervalos de Confiança [p10, p50, p90]
✅ Score de Qualidade dos Dados (0-100)
✅ Regras de Destaque Inteligentes
✅ Métricas de Avaliação (Brier Score, Log Loss)
✅ Transparência Total no HTML

ESTRUTURA DE PASTAS:
    /Historico/       → Arquivos de entrada (JOGOS_DO_DIA_*.html)
    /Probabilidade/   → Arquivos de saída (PROBABILIDADE_*.html)
    /Calibracao/      → Dados de calibração por mercado
=============================================================================
"""

import os
import re
import math
import glob
import json
import pickle
from datetime import datetime
from bs4 import BeautifulSoup
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from collections import defaultdict


# =============================================================================
# CONFIGURAÇÕES GLOBAIS
# =============================================================================

# Parâmetros de dispersão (r) por liga para Negative Binomial
# Quanto MENOR o r, MAIOR a sobredispersão (variância > média)
# Valores estimados empiricamente (podem ser ajustados com mais dados)
DISPERSAO_POR_LIGA = {
    # Brasil - Ligas mais "quentes"
    "Brasileirão Série A": 3.0,
    "Brasileirão Série B": 2.8,
    "Copa do Brasil": 2.5,       # Copas têm mais variância
    "Série C Brasil": 2.6,
    "Série D Brasil": 2.4,
    
    # Europa - Top 5
    "Premier League": 4.0,       # Mais previsível
    "La Liga": 3.5,
    "LaLiga": 3.5,
    "Bundesliga": 4.5,           # Menos cartões, mais previsível
    "Serie A": 3.2,
    "Ligue 1": 3.8,
    
    # Copas Europeias
    "Champions League": 3.0,
    "Europa League": 3.0,
    "Conference League": 2.8,
    
    # Sul-América
    "Copa Libertadores": 2.3,    # Alta variância
    "Copa Sudamericana": 2.5,
    "Primera División Argentina": 2.8,
    "Primeira Liga Argentina": 2.8,
    
    # Outros
    "Championship": 3.5,
    "Liga Portugal": 3.2,
}

# Dispersão padrão (fallback) quando liga não está mapeada
DISPERSAO_GLOBAL = 3.0

# Thresholds para destaques por mercado
THRESHOLDS_DESTAQUE = {
    "Over 2.5 Cartões": 55,
    "Over 3.5 Cartões": 55,
    "Over 4.5 Cartões": 58,
    "Over 5.5 Cartões": 60,     # Mais exigente para mercados altos
    "Under 3.5 Cartões": 55,
    "Under 4.5 Cartões": 55,
    "Under 5.5 Cartões": 55,
}

# Pesos para cálculo de qualidade dos dados
PESOS_QUALIDADE = {
    'completude_arbitro': 25,    # Dados do árbitro completos
    'completude_times': 20,      # Dados dos times completos
    'amostra_arbitro': 20,       # Quantidade de jogos do árbitro
    'amostra_times': 15,         # Quantidade de jogos dos times
    'recencia': 10,              # Dados recentes disponíveis
    'competicao_mapeada': 10,    # Competição conhecida
}


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
    n_jogos_disponiveis: int = 10  # Quantidade de jogos no histórico


@dataclass
class DadosTime:
    """Armazena os dados extraídos de cada time."""
    nome: str
    posicao: str
    faltas_pro: float
    faltas_contra: float
    amarelos_pro: float
    amarelos_contra: float
    n_jogos_disponiveis: int = 5  # Quantidade de jogos no histórico


@dataclass
class DadosBaseline:
    """Armazena o baseline da competição."""
    competicao: str
    media_amarelos: float
    media_faltas: float
    eh_copa: bool = False  # Copa vs Liga (comportamentos diferentes)


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
    perfil_card: str


@dataclass
class QualidadeDados:
    """Avalia a qualidade dos dados disponíveis (0-100)."""
    score_total: float
    completude_arbitro: float      # 0-100
    completude_times: float        # 0-100
    amostra_arbitro: float         # 0-100
    amostra_times: float           # 0-100
    recencia: float                # 0-100
    competicao_mapeada: float      # 0-100
    
    # Detalhes
    campos_faltantes: List[str] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)


@dataclass
class CalculoLambda:
    """Armazena todos os passos do cálculo do Lambda (MODELO ADITIVO + SHRINKAGE)."""
    # Base
    lambda_base: float
    
    # Ajustes aditivos
    delta_arbitro: float
    delta_times: float
    ajuste_recencia: float
    
    # Lambda antes do shrinkage
    lambda_final_raw: float
    
    # Shrinkage bayesiano
    peso_shrinkage: float           # w (0 a 1)
    lambda_shrunk: float            # λ final após shrinkage
    razao_shrinkage: str            # Explicação do peso
    
    # Valores intermediários
    media_5j_arbitro: float
    media_10j_arbitro: float
    media_arbitro_ponderada: float
    amarelos_mandante: float
    amarelos_visitante: float
    soma_amarelos_times: float
    fator_recencia_raw: float
    fator_recencia_capado: float
    
    # Modelo utilizado
    modelo_utilizado: str           # "Negative Binomial" ou "Poisson"
    dispersao_r: float              # Parâmetro r para NegBin
    motivo_modelo: str
    
    # Qualidade
    qualidade_dados: QualidadeDados = None


@dataclass
class IntervaloConfianca:
    """Intervalo de confiança para quantidade de cartões."""
    p10: int                        # Percentil 10 (limite inferior)
    p25: int                        # Percentil 25
    p50: int                        # Mediana
    p75: int                        # Percentil 75
    p90: int                        # Percentil 90 (limite superior)
    variancia_alta: bool            # Se (p90 - p10) > threshold


@dataclass
class ProbabilidadeMercado:
    """Probabilidade para um mercado específico."""
    mercado: str                    # Ex: "Over 3.5 Cartões"
    tipo: str                       # "over" ou "under"
    linha: float                    # 3.5
    
    p_raw: float                    # Probabilidade do modelo (0-100)
    p_calibrado: float              # Probabilidade após calibração (0-100)
    
    threshold_destaque: float       # Threshold para este mercado
    eh_destaque: bool               # Se deve ser destacado
    
    # Razões para não destacar
    bloqueio_variancia: bool = False
    bloqueio_qualidade: bool = False


@dataclass
class ResultadoAnalise:
    """Resultado completo da análise de uma partida."""
    partida: DadosPartida
    calculo: CalculoLambda
    intervalo: IntervaloConfianca
    probabilidades: List[ProbabilidadeMercado]
    
    # Resumo
    mercados_destaque: List[str] = field(default_factory=list)
    tendencia: str = "NEUTRA"       # ALTA, MODERADA, BAIXA
    cor_tendencia: str = "#f6e05e"


# =============================================================================
# FUNÇÕES AUXILIARES
# =============================================================================

def extrair_valor_float(texto: str) -> float:
    """Extrai um valor numérico de um texto."""
    if not texto:
        return 0.0
    texto_limpo = re.sub(r'[^\d.,\-]', '', texto.strip())
    texto_limpo = texto_limpo.replace(',', '.')
    try:
        return float(texto_limpo)
    except (ValueError, TypeError):
        return 0.0


def calcular_fatorial(n: int) -> int:
    """Calcula o fatorial de n."""
    if n <= 1:
        return 1
    resultado = 1
    for i in range(2, n + 1):
        resultado *= i
    return resultado


def obter_dispersao_liga(liga: str) -> float:
    """Obtém o parâmetro de dispersão (r) para uma liga."""
    # Busca exata
    if liga in DISPERSAO_POR_LIGA:
        return DISPERSAO_POR_LIGA[liga]
    
    # Busca parcial
    liga_lower = liga.lower()
    for nome, r in DISPERSAO_POR_LIGA.items():
        if nome.lower() in liga_lower or liga_lower in nome.lower():
            return r
    
    # Fallback
    return DISPERSAO_GLOBAL


def eh_competicao_copa(liga: str) -> bool:
    """Verifica se é uma competição de copa (mata-mata)."""
    termos_copa = ['copa', 'cup', 'taça', 'taca', 'libertadores', 'sudamericana', 
                   'champions', 'europa league', 'conference']
    liga_lower = liga.lower()
    return any(termo in liga_lower for termo in termos_copa)


# =============================================================================
# AVALIAÇÃO DE QUALIDADE DOS DADOS
# =============================================================================

def avaliar_qualidade_dados(partida: DadosPartida) -> QualidadeDados:
    """
    Avalia a qualidade dos dados disponíveis para uma partida.
    
    Retorna um score de 0 a 100 que influencia:
    - O peso do shrinkage
    - Se mercados podem ser destacados
    - A confiança geral da previsão
    """
    campos_faltantes = []
    avisos = []
    
    # 1) COMPLETUDE DO ÁRBITRO (25 pontos)
    arbitro = partida.arbitro
    pontos_arbitro = 0
    campos_arbitro = [
        (arbitro.media_amarelos_10j, "Árbitro: média 10j"),
        (arbitro.media_amarelos_5j, "Árbitro: média 5j"),
        (arbitro.media_faltas_10j, "Árbitro: faltas 10j"),
    ]
    
    for valor, campo in campos_arbitro:
        if valor > 0:
            pontos_arbitro += 33.33
        else:
            campos_faltantes.append(campo)
    
    completude_arbitro = min(100, pontos_arbitro)
    
    # 2) COMPLETUDE DOS TIMES (20 pontos)
    mandante = partida.time_mandante
    visitante = partida.time_visitante
    pontos_times = 0
    
    if mandante.amarelos_pro > 0:
        pontos_times += 25
    else:
        campos_faltantes.append(f"{mandante.nome}: amarelos")
    
    if mandante.faltas_pro > 0:
        pontos_times += 25
    else:
        campos_faltantes.append(f"{mandante.nome}: faltas")
    
    if visitante.amarelos_pro > 0:
        pontos_times += 25
    else:
        campos_faltantes.append(f"{visitante.nome}: amarelos")
    
    if visitante.faltas_pro > 0:
        pontos_times += 25
    else:
        campos_faltantes.append(f"{visitante.nome}: faltas")
    
    completude_times = pontos_times
    
    # 3) AMOSTRA DO ÁRBITRO (20 pontos)
    n_jogos_arb = arbitro.n_jogos_disponiveis
    if n_jogos_arb >= 10:
        amostra_arbitro = 100
    elif n_jogos_arb >= 5:
        amostra_arbitro = 70
    elif n_jogos_arb >= 3:
        amostra_arbitro = 40
        avisos.append("Amostra pequena do árbitro (<5 jogos)")
    else:
        amostra_arbitro = 20
        avisos.append("Amostra muito pequena do árbitro (<3 jogos)")
    
    # 4) AMOSTRA DOS TIMES (15 pontos)
    n_jogos_times = min(mandante.n_jogos_disponiveis, visitante.n_jogos_disponiveis)
    if n_jogos_times >= 5:
        amostra_times = 100
    elif n_jogos_times >= 3:
        amostra_times = 60
        avisos.append("Amostra pequena dos times (<5 jogos)")
    else:
        amostra_times = 30
        avisos.append("Amostra muito pequena dos times (<3 jogos)")
    
    # 5) RECÊNCIA (10 pontos)
    # Se temos média de 5j diferente de 10j, temos dados recentes
    if arbitro.media_amarelos_5j > 0 and arbitro.media_amarelos_5j != arbitro.media_amarelos_10j:
        recencia = 100
    elif arbitro.media_amarelos_5j > 0:
        recencia = 70
    else:
        recencia = 30
        avisos.append("Dados de recência limitados")
    
    # 6) COMPETIÇÃO MAPEADA (10 pontos)
    liga = partida.baseline.competicao
    if liga in DISPERSAO_POR_LIGA:
        competicao_mapeada = 100
    elif any(nome.lower() in liga.lower() for nome in DISPERSAO_POR_LIGA.keys()):
        competicao_mapeada = 70
    else:
        competicao_mapeada = 40
        avisos.append(f"Competição não mapeada: {liga}")
    
    # SCORE TOTAL PONDERADO
    score_total = (
        completude_arbitro * PESOS_QUALIDADE['completude_arbitro'] / 100 +
        completude_times * PESOS_QUALIDADE['completude_times'] / 100 +
        amostra_arbitro * PESOS_QUALIDADE['amostra_arbitro'] / 100 +
        amostra_times * PESOS_QUALIDADE['amostra_times'] / 100 +
        recencia * PESOS_QUALIDADE['recencia'] / 100 +
        competicao_mapeada * PESOS_QUALIDADE['competicao_mapeada'] / 100
    )
    
    return QualidadeDados(
        score_total=score_total,
        completude_arbitro=completude_arbitro,
        completude_times=completude_times,
        amostra_arbitro=amostra_arbitro,
        amostra_times=amostra_times,
        recencia=recencia,
        competicao_mapeada=competicao_mapeada,
        campos_faltantes=campos_faltantes,
        avisos=avisos
    )


# =============================================================================
# FUNÇÕES MATEMÁTICAS - DISTRIBUIÇÕES
# =============================================================================

def poisson_pmf(k: int, lambda_: float) -> float:
    """
    Função de massa de probabilidade da Poisson.
    P(Y = k) = (e^(-λ) × λ^k) / k!
    """
    if lambda_ <= 0:
        return 1.0 if k == 0 else 0.0
    if k < 0:
        return 0.0
    
    return (math.exp(-lambda_) * (lambda_ ** k)) / calcular_fatorial(k)


def negative_binomial_pmf(k: int, r: float, p: float) -> float:
    """
    Função de massa de probabilidade da Negative Binomial.
    
    Parametrização:
        - r: parâmetro de dispersão (quanto menor, maior a variância)
        - p: probabilidade de "sucesso" = r / (r + μ)
        - μ: média esperada
    
    P(Y = k) = C(k + r - 1, k) × p^r × (1-p)^k
    
    QUANDO USAR:
        - Variância > Média (sobredispersão)
        - Eventos com clustering (cartões tendem a vir em grupos)
        - Árbitros rigorosos (mais variabilidade)
    """
    if r <= 0 or p <= 0 or p >= 1 or k < 0:
        return 0.0
    
    try:
        # Coeficiente binomial generalizado usando função gamma
        # C(k + r - 1, k) = Γ(k + r) / (Γ(r) × k!)
        log_coef = math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1)
        coef = math.exp(log_coef)
        
        prob = coef * (p ** r) * ((1 - p) ** k)
        return max(0.0, min(1.0, prob))
    except (ValueError, OverflowError):
        return 0.0


def converter_lambda_para_negbin(lambda_: float, r: float) -> Tuple[float, float]:
    """
    Converte parâmetros de Poisson para Negative Binomial.
    
    Relação:
        - μ (média) = λ
        - p = r / (r + λ)
        - Variância = λ + λ²/r  (maior que Poisson quando r < ∞)
    
    Returns:
        Tupla (r, p)
    """
    if lambda_ <= 0:
        return (r, 0.999)
    
    p = r / (r + lambda_)
    return (r, max(0.001, min(0.999, p)))


def calcular_cdf(k_max: int, lambda_: float, r: float, usar_negbin: bool = True) -> float:
    """
    Calcula a função de distribuição acumulada P(Y ≤ k_max).
    """
    prob_acum = 0.0
    
    if usar_negbin and r > 0:
        _, p = converter_lambda_para_negbin(lambda_, r)
        for i in range(k_max + 1):
            prob_acum += negative_binomial_pmf(i, r, p)
    else:
        for i in range(k_max + 1):
            prob_acum += poisson_pmf(i, lambda_)
    
    return min(1.0, prob_acum)


def calcular_percentis(lambda_: float, r: float, usar_negbin: bool = True) -> IntervaloConfianca:
    """
    Calcula percentis da distribuição para criar intervalo de confiança.
    """
    # Calcula probabilidades acumuladas até um máximo razoável
    max_k = int(lambda_ * 3) + 10
    
    cdf_values = []
    for k in range(max_k + 1):
        cdf = calcular_cdf(k, lambda_, r, usar_negbin)
        cdf_values.append((k, cdf))
    
    # Encontra percentis
    def encontrar_percentil(p_alvo):
        for k, cdf in cdf_values:
            if cdf >= p_alvo:
                return k
        return cdf_values[-1][0]
    
    p10 = encontrar_percentil(0.10)
    p25 = encontrar_percentil(0.25)
    p50 = encontrar_percentil(0.50)
    p75 = encontrar_percentil(0.75)
    p90 = encontrar_percentil(0.90)
    
    # Alta variância se intervalo [p10, p90] é muito largo
    amplitude = p90 - p10
    variancia_alta = amplitude > 6  # Mais de 6 cartões de diferença
    
    return IntervaloConfianca(
        p10=p10,
        p25=p25,
        p50=p50,
        p75=p75,
        p90=p90,
        variancia_alta=variancia_alta
    )


# =============================================================================
# CALIBRAÇÃO DE PROBABILIDADES
# =============================================================================

class CalibradorIsotonico:
    """
    Calibrador usando Isotonic Regression.
    
    Mapeia probabilidades "raw" do modelo para probabilidades calibradas
    baseadas em dados históricos de validação.
    """
    
    def __init__(self, mercado: str):
        self.mercado = mercado
        self.pontos_x = []  # Probabilidades raw
        self.pontos_y = []  # Taxa de acerto real
        self.treinado = False
        self._mapa_calibracao = None
    
    def adicionar_ponto(self, p_raw: float, acertou: bool):
        """Adiciona um ponto de calibração."""
        self.pontos_x.append(p_raw)
        self.pontos_y.append(1.0 if acertou else 0.0)
        self.treinado = False
    
    def treinar(self):
        """Treina o calibrador com regressão isotônica."""
        if len(self.pontos_x) < 10:
            # Sem dados suficientes, usa identidade
            self._mapa_calibracao = None
            self.treinado = True
            return
        
        # Ordena por probabilidade raw
        pares = sorted(zip(self.pontos_x, self.pontos_y))
        
        # Agrupa em bins de 5%
        bins = defaultdict(list)
        for x, y in pares:
            bin_idx = int(x / 5) * 5
            bins[bin_idx].append(y)
        
        # Calcula média por bin (isso é uma aproximação da isotonic regression)
        self._mapa_calibracao = {}
        for bin_idx, valores in bins.items():
            self._mapa_calibracao[bin_idx] = sum(valores) / len(valores) * 100
        
        # Aplica monotonicidade (isotonic constraint)
        chaves_ordenadas = sorted(self._mapa_calibracao.keys())
        for i in range(1, len(chaves_ordenadas)):
            k_atual = chaves_ordenadas[i]
            k_anterior = chaves_ordenadas[i-1]
            if self._mapa_calibracao[k_atual] < self._mapa_calibracao[k_anterior]:
                # Viola monotonicidade, ajusta
                media = (self._mapa_calibracao[k_atual] + self._mapa_calibracao[k_anterior]) / 2
                self._mapa_calibracao[k_atual] = media
                self._mapa_calibracao[k_anterior] = media
        
        self.treinado = True
    
    def calibrar(self, p_raw: float) -> float:
        """Calibra uma probabilidade."""
        if not self.treinado:
            self.treinar()
        
        if self._mapa_calibracao is None:
            # Sem calibração, retorna raw
            return p_raw
        
        # Encontra o bin
        bin_idx = int(p_raw / 5) * 5
        
        if bin_idx in self._mapa_calibracao:
            return self._mapa_calibracao[bin_idx]
        
        # Interpolação simples
        chaves = sorted(self._mapa_calibracao.keys())
        if bin_idx < chaves[0]:
            return self._mapa_calibracao[chaves[0]]
        if bin_idx > chaves[-1]:
            return self._mapa_calibracao[chaves[-1]]
        
        # Interpola entre vizinhos
        for i, k in enumerate(chaves[:-1]):
            if k <= bin_idx < chaves[i+1]:
                # Interpolação linear
                t = (bin_idx - k) / (chaves[i+1] - k)
                return (1-t) * self._mapa_calibracao[k] + t * self._mapa_calibracao[chaves[i+1]]
        
        return p_raw
    
    def salvar(self, caminho: str):
        """Salva o calibrador em arquivo."""
        dados = {
            'mercado': self.mercado,
            'pontos_x': self.pontos_x,
            'pontos_y': self.pontos_y,
            'mapa': self._mapa_calibracao
        }
        with open(caminho, 'wb') as f:
            pickle.dump(dados, f)
    
    @classmethod
    def carregar(cls, caminho: str) -> 'CalibradorIsotonico':
        """Carrega um calibrador de arquivo."""
        with open(caminho, 'rb') as f:
            dados = pickle.load(f)
        
        calibrador = cls(dados['mercado'])
        calibrador.pontos_x = dados['pontos_x']
        calibrador.pontos_y = dados['pontos_y']
        calibrador._mapa_calibracao = dados['mapa']
        calibrador.treinado = True
        return calibrador


# Gerenciador global de calibradores
class GerenciadorCalibracao:
    """Gerencia calibradores para todos os mercados."""
    
    def __init__(self, pasta_calibracao: str = None):
        self.calibradores: Dict[str, CalibradorIsotonico] = {}
        self.pasta = pasta_calibracao
        
        # Mercados suportados
        self.mercados = [
            "Over 2.5 Cartões",
            "Over 3.5 Cartões",
            "Over 4.5 Cartões",
            "Over 5.5 Cartões",
            "Under 3.5 Cartões",
            "Under 4.5 Cartões",
            "Under 5.5 Cartões",
        ]
        
        # Inicializa calibradores
        for mercado in self.mercados:
            self.calibradores[mercado] = CalibradorIsotonico(mercado)
        
        # Tenta carregar calibração existente
        if pasta_calibracao:
            self.carregar_todos()
    
    def calibrar(self, mercado: str, p_raw: float) -> float:
        """Calibra uma probabilidade para um mercado."""
        if mercado in self.calibradores:
            return self.calibradores[mercado].calibrar(p_raw)
        return p_raw
    
    def adicionar_resultado(self, mercado: str, p_raw: float, acertou: bool):
        """Adiciona um resultado de validação."""
        if mercado in self.calibradores:
            self.calibradores[mercado].adicionar_ponto(p_raw, acertou)
    
    def retreinar_todos(self):
        """Retreina todos os calibradores."""
        for calibrador in self.calibradores.values():
            calibrador.treinar()
    
    def salvar_todos(self):
        """Salva todos os calibradores."""
        if not self.pasta:
            return
        
        os.makedirs(self.pasta, exist_ok=True)
        for mercado, calibrador in self.calibradores.items():
            nome_arquivo = mercado.replace(" ", "_").replace(".", "") + ".pkl"
            caminho = os.path.join(self.pasta, nome_arquivo)
            calibrador.salvar(caminho)
    
    def carregar_todos(self):
        """Carrega todos os calibradores."""
        if not self.pasta or not os.path.exists(self.pasta):
            return
        
        for mercado in self.mercados:
            nome_arquivo = mercado.replace(" ", "_").replace(".", "") + ".pkl"
            caminho = os.path.join(self.pasta, nome_arquivo)
            if os.path.exists(caminho):
                try:
                    self.calibradores[mercado] = CalibradorIsotonico.carregar(caminho)
                except:
                    pass


# Instância global
_gerenciador_calibracao: GerenciadorCalibracao = None

def obter_gerenciador_calibracao(pasta: str = None) -> GerenciadorCalibracao:
    """Obtém ou cria o gerenciador de calibração."""
    global _gerenciador_calibracao
    if _gerenciador_calibracao is None:
        _gerenciador_calibracao = GerenciadorCalibracao(pasta)
    return _gerenciador_calibracao


# =============================================================================
# CÁLCULO DO LAMBDA COM SHRINKAGE BAYESIANO
# =============================================================================

def calcular_peso_shrinkage(qualidade: QualidadeDados, n_jogos_arbitro: int) -> Tuple[float, str]:
    """
    Calcula o peso do shrinkage bayesiano.
    
    CONCEITO:
        λ_shrunk = w × λ_final + (1-w) × λ_liga
        
        - w = 1: Confiança total no modelo (sem shrinkage)
        - w = 0: Usa apenas média da liga (shrinkage máximo)
    
    O peso w depende de:
        1. Qualidade geral dos dados (score 0-100)
        2. Número de jogos do árbitro
        3. Completude dos dados
    
    Returns:
        Tupla (peso_w, razao_explicativa)
    """
    # Base: score de qualidade normalizado
    w_base = qualidade.score_total / 100
    
    # Ajuste por amostra do árbitro
    if n_jogos_arbitro >= 10:
        fator_amostra = 1.0
    elif n_jogos_arbitro >= 7:
        fator_amostra = 0.9
    elif n_jogos_arbitro >= 5:
        fator_amostra = 0.75
    elif n_jogos_arbitro >= 3:
        fator_amostra = 0.5
    else:
        fator_amostra = 0.3
    
    # Ajuste por completude
    fator_completude = (qualidade.completude_arbitro + qualidade.completude_times) / 200
    
    # Peso final
    w = w_base * fator_amostra * (0.5 + 0.5 * fator_completude)
    w = max(0.3, min(0.95, w))  # Limita entre 0.3 e 0.95
    
    # Razão explicativa
    razoes = []
    if qualidade.score_total < 60:
        razoes.append(f"Qualidade baixa ({qualidade.score_total:.0f}/100)")
    if n_jogos_arbitro < 5:
        razoes.append(f"Poucos jogos do árbitro ({n_jogos_arbitro})")
    if qualidade.completude_arbitro < 70:
        razoes.append("Dados do árbitro incompletos")
    if qualidade.completude_times < 70:
        razoes.append("Dados dos times incompletos")
    
    if not razoes:
        if w >= 0.8:
            razao = "Alta confiança nos dados"
        else:
            razao = "Confiança moderada nos dados"
    else:
        razao = " | ".join(razoes)
    
    return (w, razao)


def calcular_lambda(partida: DadosPartida) -> CalculoLambda:
    """
    Calcula o Lambda (λ) usando MODELO ADITIVO CALIBRADO + SHRINKAGE BAYESIANO.
    
    METODOLOGIA V2.0:
    =================
    
    1) LAMBDA BASE DA LIGA (λ_base):
       - Média histórica de cartões da competição
    
    2) AJUSTE DO ÁRBITRO (Δ_arbitro):
       - média_ponderada = (0.6 × média_5j + 0.4 × média_10j)
       - Δ_arbitro = 0.8 × (média_ponderada - média_liga)
    
    3) AJUSTE DOS TIMES (Δ_times):
       - soma_cartões = cartões_mandante + cartões_visitante
       - Δ_times = 0.6 × (soma_cartões - média_liga)
    
    4) AJUSTE DE RECÊNCIA (CAPADO ±5%):
       - F_raw = 1 + ((média_5j - média_10j) / média_10j)
       - F_capado = clamp(F_raw, 0.95, 1.05)
       - ajuste_recencia = λ_base × (F_capado - 1)
    
    5) LAMBDA RAW (SOMA ADITIVA):
       - λ_raw = λ_base + Δ_arbitro + Δ_times + ajuste_recencia
    
    6) SHRINKAGE BAYESIANO:
       - w = peso baseado na qualidade dos dados
       - λ_shrunk = w × λ_raw + (1-w) × λ_base
    
    7) MODELO NEGATIVE BINOMIAL:
       - Usa parâmetro r específico da liga
       - Captura sobredispersão (var > média)
    """
    
    # Avalia qualidade dos dados primeiro
    qualidade = avaliar_qualidade_dados(partida)
    
    # ==========================================================
    # 1) LAMBDA BASE DA LIGA
    # ==========================================================
    lambda_base = partida.baseline.media_amarelos
    if lambda_base <= 0:
        lambda_base = 5.0  # Fallback
    
    # ==========================================================
    # 2) AJUSTE DO ÁRBITRO
    # ==========================================================
    media_5j = partida.arbitro.media_amarelos_5j
    media_10j = partida.arbitro.media_amarelos_10j
    
    if media_5j <= 0:
        media_5j = media_10j
    if media_10j <= 0:
        media_10j = media_5j
    if media_5j <= 0 and media_10j <= 0:
        media_5j = media_10j = lambda_base
    
    media_arbitro_ponderada = (0.6 * media_5j) + (0.4 * media_10j)
    delta_arbitro = 0.8 * (media_arbitro_ponderada - lambda_base)
    
    # ==========================================================
    # 3) AJUSTE DOS TIMES
    # ==========================================================
    amarelos_mandante = partida.time_mandante.amarelos_pro
    amarelos_visitante = partida.time_visitante.amarelos_pro
    
    if amarelos_mandante <= 0:
        amarelos_mandante = lambda_base / 2
    if amarelos_visitante <= 0:
        amarelos_visitante = lambda_base / 2
    
    soma_amarelos_times = amarelos_mandante + amarelos_visitante
    delta_times = 0.6 * (soma_amarelos_times - lambda_base)
    
    # ==========================================================
    # 4) AJUSTE DE RECÊNCIA (CAPADO)
    # ==========================================================
    if media_10j > 0:
        fator_recencia_raw = 1.0 + ((media_5j - media_10j) / media_10j)
    else:
        fator_recencia_raw = 1.0
    
    fator_recencia_capado = max(0.95, min(1.05, fator_recencia_raw))
    ajuste_recencia = lambda_base * (fator_recencia_capado - 1.0)
    
    # ==========================================================
    # 5) LAMBDA RAW (SOMA ADITIVA)
    # ==========================================================
    lambda_raw = lambda_base + delta_arbitro + delta_times + ajuste_recencia
    lambda_raw = max(2.0, min(10.0, lambda_raw))
    
    # ==========================================================
    # 6) SHRINKAGE BAYESIANO
    # ==========================================================
    n_jogos = partida.arbitro.n_jogos_disponiveis
    peso_w, razao_shrinkage = calcular_peso_shrinkage(qualidade, n_jogos)
    
    lambda_shrunk = peso_w * lambda_raw + (1 - peso_w) * lambda_base
    lambda_shrunk = max(2.0, min(10.0, lambda_shrunk))
    
    # ==========================================================
    # 7) MODELO E DISPERSÃO
    # ==========================================================
    dispersao_r = obter_dispersao_liga(partida.baseline.competicao)
    
    # Ajusta dispersão baseado no perfil do árbitro
    perfil = partida.arbitro.perfil.lower()
    if 'rigoroso' in perfil:
        dispersao_r *= 0.85  # Mais variável
    elif 'permissivo' in perfil:
        dispersao_r *= 1.1   # Menos variável
    
    # Define modelo
    usar_negbin = True
    motivos = ["Negative Binomial captura melhor a sobredispersão de cartões"]
    
    if eh_competicao_copa(partida.liga):
        dispersao_r *= 0.9  # Copas têm mais variância
        motivos.append("Copa/Mata-mata: maior variabilidade")
    
    if qualidade.score_total < 50:
        motivos.append("Dados limitados: incerteza aumentada")
    
    return CalculoLambda(
        lambda_base=lambda_base,
        delta_arbitro=delta_arbitro,
        delta_times=delta_times,
        ajuste_recencia=ajuste_recencia,
        lambda_final_raw=lambda_raw,
        peso_shrinkage=peso_w,
        lambda_shrunk=lambda_shrunk,
        razao_shrinkage=razao_shrinkage,
        media_5j_arbitro=media_5j,
        media_10j_arbitro=media_10j,
        media_arbitro_ponderada=media_arbitro_ponderada,
        amarelos_mandante=amarelos_mandante,
        amarelos_visitante=amarelos_visitante,
        soma_amarelos_times=soma_amarelos_times,
        fator_recencia_raw=fator_recencia_raw,
        fator_recencia_capado=fator_recencia_capado,
        modelo_utilizado="Negative Binomial",
        dispersao_r=dispersao_r,
        motivo_modelo=" | ".join(motivos),
        qualidade_dados=qualidade
    )


# =============================================================================
# CÁLCULO DE PROBABILIDADES
# =============================================================================

def calcular_probabilidades_mercados(
    lambda_shrunk: float,
    dispersao_r: float,
    qualidade: QualidadeDados,
    intervalo: IntervaloConfianca,
    gerenciador: GerenciadorCalibracao = None
) -> List[ProbabilidadeMercado]:
    """
    Calcula probabilidades para todos os mercados com calibração.
    """
    probabilidades = []
    
    mercados = [
        ("Over 2.5 Cartões", "over", 2.5),
        ("Over 3.5 Cartões", "over", 3.5),
        ("Over 4.5 Cartões", "over", 4.5),
        ("Over 5.5 Cartões", "over", 5.5),
        ("Under 3.5 Cartões", "under", 3.5),
        ("Under 4.5 Cartões", "under", 4.5),
        ("Under 5.5 Cartões", "under", 5.5),
    ]
    
    for mercado, tipo, linha in mercados:
        # Calcula probabilidade raw
        k_max = int(linha)
        cdf = calcular_cdf(k_max, lambda_shrunk, dispersao_r, usar_negbin=True)
        
        if tipo == "over":
            p_raw = (1 - cdf) * 100
        else:
            p_raw = cdf * 100
        
        # Calibra
        if gerenciador:
            p_calibrado = gerenciador.calibrar(mercado, p_raw)
        else:
            p_calibrado = p_raw
        
        # Threshold e destaque
        threshold = THRESHOLDS_DESTAQUE.get(mercado, 55)
        
        # Verifica bloqueios
        bloqueio_variancia = False
        bloqueio_qualidade = False
        
        # Mercados altos (Over 5.5) têm regras mais rígidas
        if linha >= 5.5:
            if intervalo.variancia_alta:
                bloqueio_variancia = True
            if qualidade.score_total < 60:
                bloqueio_qualidade = True
        
        # Define se é destaque
        eh_destaque = (
            p_calibrado >= threshold and
            not bloqueio_variancia and
            not bloqueio_qualidade
        )
        
        probabilidades.append(ProbabilidadeMercado(
            mercado=mercado,
            tipo=tipo,
            linha=linha,
            p_raw=p_raw,
            p_calibrado=p_calibrado,
            threshold_destaque=threshold,
            eh_destaque=eh_destaque,
            bloqueio_variancia=bloqueio_variancia,
            bloqueio_qualidade=bloqueio_qualidade
        ))
    
    return probabilidades


def analisar_partida(partida: DadosPartida, gerenciador: GerenciadorCalibracao = None) -> ResultadoAnalise:
    """
    Realiza análise completa de uma partida.
    """
    # Calcula lambda com shrinkage
    calculo = calcular_lambda(partida)
    
    # Calcula intervalos de confiança
    intervalo = calcular_percentis(calculo.lambda_shrunk, calculo.dispersao_r, usar_negbin=True)
    
    # Calcula probabilidades com calibração
    probabilidades = calcular_probabilidades_mercados(
        calculo.lambda_shrunk,
        calculo.dispersao_r,
        calculo.qualidade_dados,
        intervalo,
        gerenciador
    )
    
    # Identifica destaques
    mercados_destaque = [p.mercado for p in probabilidades if p.eh_destaque]
    
    # Define tendência
    lambda_s = calculo.lambda_shrunk
    if lambda_s >= 5.5:
        tendencia = "ELEVADA"
        cor_tendencia = "#e94560"
    elif lambda_s <= 3.5:
        tendencia = "BAIXA"
        cor_tendencia = "#2ecc71"
    else:
        tendencia = "MODERADA"
        cor_tendencia = "#f6e05e"
    
    return ResultadoAnalise(
        partida=partida,
        calculo=calculo,
        intervalo=intervalo,
        probabilidades=probabilidades,
        mercados_destaque=mercados_destaque,
        tendencia=tendencia,
        cor_tendencia=cor_tendencia
    )


# =============================================================================
# FUNÇÕES DE EXTRAÇÃO DO HTML
# =============================================================================

def extrair_dados_arbitro(card) -> DadosArbitro:
    """Extrai os dados do árbitro de um card de jogo."""
    
    nome = ""
    pais = ""
    media_10j = 0.0
    media_5j = 0.0
    media_1t = 0.0
    media_2t = 0.0
    media_faltas_10j = 0.0
    media_faltas_5j = 0.0
    media_vermelhos = 0.0
    perfil = "Médio"
    n_jogos = 10
    
    # Busca seção do árbitro
    secoes = card.find_all(class_='secao')
    
    for secao in secoes:
        titulo = secao.find(class_='secao-titulo')
        if not titulo or 'rbitro' not in titulo.get_text():
            continue
        
        # Nome e país
        nome_elem = secao.find(class_='arbitro-nome')
        if nome_elem:
            nome = nome_elem.get_text(strip=True)
        
        pais_elem = secao.find(class_='arbitro-pais')
        if pais_elem:
            pais = pais_elem.get_text(strip=True)
        
        # Perfil
        badge = secao.find(class_='badge')
        if badge:
            perfil = badge.get_text(strip=True)
        
        # Métricas
        metricas = secao.find_all(class_='metrica-item')
        for metrica in metricas:
            texto = metrica.get_text()
            valor_elem = metrica.find(class_='metrica-valor')
            if not valor_elem:
                continue
            
            valor = extrair_valor_float(valor_elem.get_text())
            texto_lower = texto.lower()
            
            if '10j' in texto_lower or '10 j' in texto_lower:
                if 'amarelo' in texto_lower or 'cartõ' in texto_lower or 'cartoe' in texto_lower:
                    media_10j = valor
                elif 'falta' in texto_lower:
                    media_faltas_10j = valor
            elif '5j' in texto_lower or '5 j' in texto_lower:
                if 'amarelo' in texto_lower or 'cartõ' in texto_lower or 'cartoe' in texto_lower:
                    media_5j = valor
                elif 'falta' in texto_lower:
                    media_faltas_5j = valor
            elif '1t' in texto_lower or '1º t' in texto_lower:
                if 'amarelo' in texto_lower:
                    media_1t = valor
            elif '2t' in texto_lower or '2º t' in texto_lower:
                if 'amarelo' in texto_lower:
                    media_2t = valor
            elif 'vermelho' in texto_lower:
                media_vermelhos = valor
        
        break
    
    # Tenta buscar na info-bar
    if not nome:
        info_bar = card.find(class_='jogo-info-bar')
        if info_bar:
            for span in info_bar.find_all('span'):
                texto = span.get_text()
                if 'rbitro' in texto:
                    valor_elem = span.find(class_='info-value')
                    if valor_elem:
                        nome = valor_elem.get_text(strip=True)
                    break
    
    return DadosArbitro(
        nome=nome or "Não informado",
        pais=pais,
        media_amarelos_10j=media_10j,
        media_amarelos_5j=media_5j,
        media_amarelos_1t=media_1t,
        media_amarelos_2t=media_2t,
        media_faltas_10j=media_faltas_10j,
        media_faltas_5j=media_faltas_5j,
        media_vermelhos=media_vermelhos,
        perfil=perfil,
        n_jogos_disponiveis=n_jogos
    )


def extrair_dados_baseline(card, liga: str) -> DadosBaseline:
    """Extrai o baseline da competição."""
    
    media_amarelos = 5.0
    media_faltas = 25.0
    
    # Busca na seção de análise
    textos = card.find_all(string=re.compile(r'Média.*Liga|Baseline|média.*competição', re.I))
    
    for texto in textos:
        parent = texto.parent
        if parent:
            match = re.search(r'(\d+[.,]\d+)', parent.get_text())
            if match:
                media_amarelos = float(match.group(1).replace(',', '.'))
                break
    
    # Fallback para ligas conhecidas
    MEDIAS_LIGAS = {
        "Brasileirão Série A": 5.4,
        "Brasileirão Série B": 5.6,
        "Premier League": 5.0,
        "La Liga": 5.2,
        "LaLiga": 5.2,
        "Bundesliga": 4.2,
        "Serie A": 4.6,
        "Ligue 1": 4.0,
        "Copa Libertadores": 6.0,
        "Copa Sudamericana": 5.8,
    }
    
    for nome_liga, media in MEDIAS_LIGAS.items():
        if nome_liga.lower() in liga.lower() or liga.lower() in nome_liga.lower():
            media_amarelos = media
            break
    
    return DadosBaseline(
        competicao=liga,
        media_amarelos=media_amarelos,
        media_faltas=media_faltas,
        eh_copa=eh_competicao_copa(liga)
    )


def extrair_dados_time(card, eh_mandante: bool) -> DadosTime:
    """Extrai os dados de um time."""
    
    nome = ""
    posicao = "N/D"
    faltas_pro = 0.0
    faltas_contra = 0.0
    amarelos_pro = 0.0
    amarelos_contra = 0.0
    n_jogos = 5
    
    # Busca pelo título
    titulo_elem = card.find(class_='jogo-titulo')
    if titulo_elem:
        titulo = titulo_elem.get_text(strip=True)
        
        # Remove emojis comuns
        titulo = re.sub(r'[🏠✈️⚽🏆📊🎯]', '', titulo)
        titulo = titulo.strip()
        
        if ' vs ' in titulo:
            partes = titulo.split(' vs ')
            if eh_mandante:
                nome_part = partes[0]
            else:
                nome_part = partes[1] if len(partes) > 1 else ""
            
            # Limpa espaços extras
            nome_part = ' '.join(nome_part.split())
            
            # Extrai nome e posição
            match = re.match(r'(.+?)\s*\((\d+)º?\)', nome_part)
            if match:
                nome = match.group(1).strip()
                posicao = f"{match.group(2)}º"
            else:
                # Tenta extrair N/D
                match2 = re.match(r'(.+?)\s*\(N/D\)', nome_part)
                if match2:
                    nome = match2.group(1).strip()
                    posicao = "N/D"
                else:
                    nome = nome_part.strip()
    
    # Busca estatísticas nos cards de time
    time_cards = card.find_all(class_='time-card')
    target_idx = 0 if eh_mandante else 1
    
    if len(time_cards) > target_idx:
        time_card = time_cards[target_idx]
        
        # Nome
        nome_elem = time_card.find(class_='time-nome')
        if nome_elem:
            nome = nome_elem.get_text(strip=True)
        
        # Posição
        pos_elem = time_card.find(class_='time-posicao')
        if pos_elem:
            posicao = pos_elem.get_text(strip=True)
        
        # Médias
        media_items = time_card.find_all(class_='media-item')
        for item in media_items:
            label = item.find(class_='label')
            valor_elem = item.find(class_='valor')
            
            if label and valor_elem:
                texto = label.get_text().lower()
                valor = extrair_valor_float(valor_elem.get_text())
                
                if 'falta' in texto:
                    if 'pró' in texto or 'pro' in texto or 'cometida' in texto:
                        faltas_pro = valor
                    elif 'contra' in texto or 'sofrida' in texto:
                        faltas_contra = valor
                elif 'amarelo' in texto or 'cartõ' in texto:
                    if 'pró' in texto or 'pro' in texto or 'recebido' in texto:
                        amarelos_pro = valor
                    elif 'contra' in texto:
                        amarelos_contra = valor
    
    return DadosTime(
        nome=nome or ("Time Casa" if eh_mandante else "Time Fora"),
        posicao=posicao,
        faltas_pro=faltas_pro,
        faltas_contra=faltas_contra,
        amarelos_pro=amarelos_pro,
        amarelos_contra=amarelos_contra,
        n_jogos_disponiveis=n_jogos
    )


def extrair_partida(card) -> Optional[DadosPartida]:
    """Extrai todos os dados de uma partida de um card HTML."""
    
    try:
        # Liga/Competição
        liga = ""
        info_bar = card.find(class_='jogo-info-bar')
        if info_bar:
            for span in info_bar.find_all('span'):
                texto = span.get_text()
                if 'Competição' in texto:
                    valor_elem = span.find(class_='info-value')
                    if valor_elem:
                        liga = valor_elem.get_text(strip=True)
                    break
        
        # Data e horário
        data = ""
        horario = ""
        data_elem = card.find(class_='jogo-data')
        if data_elem:
            horario_elem = data_elem.find(class_='horario')
            data_dia_elem = data_elem.find(class_='data')
            if horario_elem:
                horario = horario_elem.get_text(strip=True)
            if data_dia_elem:
                data = data_dia_elem.get_text(strip=True)
        
        # Estádio e local
        estadio = "Não informado"
        local = ""
        if info_bar:
            for span in info_bar.find_all('span'):
                texto = span.get_text()
                if 'Estádio' in texto:
                    valor_elem = span.find(class_='info-value')
                    if valor_elem:
                        estadio = valor_elem.get_text(strip=True)
                elif 'Local' in texto:
                    valor_elem = span.find(class_='info-value')
                    if valor_elem:
                        local = valor_elem.get_text(strip=True)
        
        # Fase (se disponível)
        fase = ""
        
        # Perfil do card
        perfil_card = card.get('data-perfil', 'Médio')
        
        # Dados
        arbitro = extrair_dados_arbitro(card)
        time_mandante = extrair_dados_time(card, eh_mandante=True)
        time_visitante = extrair_dados_time(card, eh_mandante=False)
        baseline = extrair_dados_baseline(card, liga)
        
        return DadosPartida(
            liga=liga or "Competição não identificada",
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
        
    except Exception as e:
        print(f"   ⚠️ Erro ao extrair partida: {e}")
        return None


def processar_arquivo(caminho_entrada: str, gerenciador: GerenciadorCalibracao = None) -> List[ResultadoAnalise]:
    """Processa um arquivo HTML e retorna as análises."""
    
    resultados = []
    
    try:
        with open(caminho_entrada, 'r', encoding='utf-8') as f:
            conteudo = f.read()
        
        soup = BeautifulSoup(conteudo, 'html.parser')
        cards = soup.find_all(class_='jogo-card')
        
        print(f"✅ Encontrados {len(cards)} jogos no arquivo")
        
        for i, card in enumerate(cards, 1):
            partida = extrair_partida(card)
            
            if partida:
                print(f"   {i}. {partida.time_mandante.nome} vs {partida.time_visitante.nome}")
                resultado = analisar_partida(partida, gerenciador)
                resultados.append(resultado)
        
        print(f"\n✅ {len(resultados)} partidas analisadas com sucesso")
        
    except Exception as e:
        print(f"❌ Erro ao processar arquivo: {e}")
    
    return resultados


# =============================================================================
# GERAÇÃO DO HTML
# =============================================================================

def gerar_css_adicional() -> str:
    """Gera CSS adicional para as novas seções."""
    return """
        /* Seções de cálculo */
        .calculo-section {
            background: rgba(15, 52, 96, 0.3);
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            border: 1px solid #0f3460;
        }
        
        .calculo-titulo {
            color: #e94560;
            font-size: 1.2em;
            margin-bottom: 15px;
            font-weight: bold;
        }
        
        .dados-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 12px;
        }
        
        .dado-item {
            background: #1a1a2e;
            padding: 12px;
            border-radius: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .dado-label {
            color: #a0a0a0;
            font-size: 0.85em;
        }
        
        .dado-valor {
            color: #e94560;
            font-weight: bold;
        }
        
        .calculo-passo {
            background: #1a1a2e;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 12px;
            border-left: 3px solid #3498db;
        }
        
        .calculo-passo-titulo {
            color: #3498db;
            font-weight: bold;
            margin-bottom: 8px;
        }
        
        .calculo-formula {
            font-family: 'Courier New', monospace;
            color: #e0e0e0;
            padding: 8px;
            background: rgba(0,0,0,0.2);
            border-radius: 4px;
            margin: 8px 0;
            font-size: 0.95em;
        }
        
        .calculo-resultado {
            color: #2ecc71;
            font-weight: bold;
        }
        
        /* Shrinkage */
        .shrinkage-box {
            background: linear-gradient(135deg, rgba(52, 152, 219, 0.1), rgba(155, 89, 182, 0.1));
            border: 1px solid #9b59b6;
            border-radius: 10px;
            padding: 20px;
            margin: 20px 0;
        }
        
        .shrinkage-titulo {
            color: #9b59b6;
            font-size: 1.1em;
            font-weight: bold;
            margin-bottom: 15px;
        }
        
        .shrinkage-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            text-align: center;
        }
        
        .shrinkage-item {
            background: #1a1a2e;
            padding: 15px;
            border-radius: 8px;
        }
        
        .shrinkage-valor {
            font-size: 1.8em;
            font-weight: bold;
            color: #9b59b6;
        }
        
        .shrinkage-label {
            color: #a0a0a0;
            font-size: 0.85em;
            margin-top: 5px;
        }
        
        /* Qualidade dos dados */
        .qualidade-box {
            background: rgba(46, 204, 113, 0.1);
            border: 1px solid #2ecc71;
            border-radius: 10px;
            padding: 20px;
            margin: 20px 0;
        }
        
        .qualidade-titulo {
            color: #2ecc71;
            font-size: 1.1em;
            font-weight: bold;
            margin-bottom: 15px;
        }
        
        .qualidade-score {
            text-align: center;
            margin-bottom: 15px;
        }
        
        .qualidade-score-valor {
            font-size: 3em;
            font-weight: bold;
        }
        
        .qualidade-barra {
            height: 8px;
            background: #1a1a2e;
            border-radius: 4px;
            overflow: hidden;
            margin: 5px 0;
        }
        
        .qualidade-barra-fill {
            height: 100%;
            border-radius: 4px;
            transition: width 0.3s;
        }
        
        .qualidade-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 0;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        
        .qualidade-item:last-child {
            border-bottom: none;
        }
        
        /* Intervalo de confiança */
        .intervalo-box {
            background: rgba(241, 196, 15, 0.1);
            border: 1px solid #f1c40f;
            border-radius: 10px;
            padding: 20px;
            margin: 20px 0;
            text-align: center;
        }
        
        .intervalo-titulo {
            color: #f1c40f;
            font-size: 1.1em;
            font-weight: bold;
            margin-bottom: 15px;
        }
        
        .intervalo-visual {
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 10px;
            margin: 20px 0;
            font-size: 1.2em;
        }
        
        .intervalo-numero {
            background: #1a1a2e;
            padding: 10px 15px;
            border-radius: 8px;
            font-weight: bold;
        }
        
        .intervalo-p10 { color: #3498db; }
        .intervalo-p50 { color: #f1c40f; font-size: 1.5em; }
        .intervalo-p90 { color: #e74c3c; }
        
        .intervalo-aviso {
            background: rgba(231, 76, 60, 0.2);
            color: #e74c3c;
            padding: 10px;
            border-radius: 8px;
            margin-top: 10px;
            font-size: 0.9em;
        }
        
        /* Modelo box */
        .modelo-box {
            background: rgba(52, 152, 219, 0.1);
            border: 1px solid #3498db;
            border-radius: 10px;
            padding: 20px;
            margin: 20px 0;
        }
        
        .modelo-formula-principal {
            font-size: 1.3em;
            text-align: center;
            padding: 20px;
            background: #1a1a2e;
            border-radius: 8px;
            font-family: 'Times New Roman', serif;
            color: #e0e0e0;
        }
        
        .modelo-explicacao {
            margin-top: 15px;
            color: #a0a0a0;
            font-size: 0.95em;
        }
        
        /* Probabilidades */
        .prob-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 15px;
        }
        
        .prob-card {
            background: #1a1a2e;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            border: 2px solid #0f3460;
            transition: all 0.3s;
        }
        
        .prob-card.destaque {
            border-color: #2ecc71;
            box-shadow: 0 0 15px rgba(46, 204, 113, 0.3);
        }
        
        .prob-card.bloqueado {
            border-color: #e74c3c;
            opacity: 0.7;
        }
        
        .prob-mercado {
            color: #a0a0a0;
            font-size: 0.9em;
            margin-bottom: 10px;
        }
        
        .prob-valores {
            display: flex;
            justify-content: center;
            gap: 15px;
            margin-bottom: 10px;
        }
        
        .prob-raw {
            color: #808080;
            font-size: 0.9em;
        }
        
        .prob-calibrado {
            font-size: 1.8em;
            font-weight: bold;
            color: #e94560;
        }
        
        .prob-card.destaque .prob-calibrado {
            color: #2ecc71;
        }
        
        .prob-descricao {
            color: #606060;
            font-size: 0.8em;
        }
        
        .prob-bloqueio {
            color: #e74c3c;
            font-size: 0.75em;
            margin-top: 5px;
        }
        
        /* Interpretação */
        .interpretacao-box {
            background: linear-gradient(135deg, #16213e 0%, #1a1a2e 100%);
            border-radius: 10px;
            padding: 25px;
            margin-top: 20px;
            border: 1px solid #e94560;
        }
        
        .interpretacao-titulo {
            color: #e94560;
            font-size: 1.2em;
            margin-bottom: 15px;
            font-weight: bold;
        }
        
        .interpretacao-texto {
            color: #e0e0e0;
            line-height: 1.6;
        }
        
        .lambda-destaque {
            background: #e94560;
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-weight: bold;
        }
        
        @media (max-width: 768px) {
            .shrinkage-grid {
                grid-template-columns: 1fr;
            }
            
            .intervalo-visual {
                flex-wrap: wrap;
            }
        }
    """


def gerar_secao_qualidade(qualidade: QualidadeDados) -> str:
    """Gera a seção de qualidade dos dados."""
    
    # Cor do score
    if qualidade.score_total >= 70:
        cor_score = "#2ecc71"
    elif qualidade.score_total >= 50:
        cor_score = "#f1c40f"
    else:
        cor_score = "#e74c3c"
    
    # Gera barras de qualidade
    def barra(valor, cor):
        return f'''
            <div class="qualidade-barra">
                <div class="qualidade-barra-fill" style="width: {valor}%; background: {cor};"></div>
            </div>
        '''
    
    avisos_html = ""
    if qualidade.avisos:
        avisos_html = '<div style="margin-top: 10px; color: #f1c40f; font-size: 0.85em;">'
        for aviso in qualidade.avisos[:3]:  # Máximo 3 avisos
            avisos_html += f'<div>⚠️ {aviso}</div>'
        avisos_html += '</div>'
    
    return f'''
        <div class="qualidade-box" style="border-color: {cor_score};">
            <div class="qualidade-titulo" style="color: {cor_score};">📊 Qualidade dos Dados</div>
            
            <div class="qualidade-score">
                <div class="qualidade-score-valor" style="color: {cor_score};">{qualidade.score_total:.0f}</div>
                <div style="color: #a0a0a0;">de 100 pontos</div>
            </div>
            
            <div class="qualidade-item">
                <span>Completude Árbitro</span>
                <span style="color: {cor_score};">{qualidade.completude_arbitro:.0f}%</span>
            </div>
            {barra(qualidade.completude_arbitro, cor_score)}
            
            <div class="qualidade-item">
                <span>Completude Times</span>
                <span style="color: {cor_score};">{qualidade.completude_times:.0f}%</span>
            </div>
            {barra(qualidade.completude_times, cor_score)}
            
            <div class="qualidade-item">
                <span>Amostra Árbitro</span>
                <span style="color: {cor_score};">{qualidade.amostra_arbitro:.0f}%</span>
            </div>
            {barra(qualidade.amostra_arbitro, cor_score)}
            
            <div class="qualidade-item">
                <span>Recência</span>
                <span style="color: {cor_score};">{qualidade.recencia:.0f}%</span>
            </div>
            {barra(qualidade.recencia, cor_score)}
            
            {avisos_html}
        </div>
    '''


def gerar_secao_calculo(resultado: ResultadoAnalise) -> str:
    """Gera a seção de cálculo do lambda."""
    
    c = resultado.calculo
    
    sinal_arb = "+" if c.delta_arbitro >= 0 else ""
    sinal_tim = "+" if c.delta_times >= 0 else ""
    sinal_rec = "+" if c.ajuste_recencia >= 0 else ""
    
    return f'''
        <div class="calculo-section">
            <div class="calculo-titulo">🧮 Construção do Lambda (λ) — MODELO ADITIVO + SHRINKAGE</div>
            
            <div class="calculo-passo">
                <div class="calculo-passo-titulo">1️⃣ Lambda Base da Liga</div>
                <div class="calculo-formula">λ_base = {c.lambda_base:.2f}</div>
                <p style="color: #a0a0a0; font-size: 0.9em;">
                    Média histórica de cartões da {resultado.partida.baseline.competicao}
                </p>
            </div>
            
            <div class="calculo-passo">
                <div class="calculo-passo-titulo">2️⃣ Ajuste do Árbitro (Δ_arbitro)</div>
                <div class="calculo-formula">
                    média_ponderada = (0.6 × {c.media_5j_arbitro:.2f}) + (0.4 × {c.media_10j_arbitro:.2f}) = {c.media_arbitro_ponderada:.2f}
                </div>
                <div class="calculo-formula">
                    Δ_arbitro = 0.8 × ({c.media_arbitro_ponderada:.2f} - {c.lambda_base:.2f}) = <span class="calculo-resultado">{sinal_arb}{c.delta_arbitro:.2f}</span>
                </div>
            </div>
            
            <div class="calculo-passo">
                <div class="calculo-passo-titulo">3️⃣ Ajuste dos Times (Δ_times)</div>
                <div class="calculo-formula">
                    soma_cartões = {c.amarelos_mandante:.2f} + {c.amarelos_visitante:.2f} = {c.soma_amarelos_times:.2f}
                </div>
                <div class="calculo-formula">
                    Δ_times = 0.6 × ({c.soma_amarelos_times:.2f} - {c.lambda_base:.2f}) = <span class="calculo-resultado">{sinal_tim}{c.delta_times:.2f}</span>
                </div>
            </div>
            
            <div class="calculo-passo">
                <div class="calculo-passo-titulo">4️⃣ Ajuste de Recência (CAPADO ±5%)</div>
                <div class="calculo-formula">
                    F_raw = {c.fator_recencia_raw:.4f} → F_capado = {c.fator_recencia_capado:.4f}
                </div>
                <div class="calculo-formula">
                    ajuste_recencia = {c.lambda_base:.2f} × ({c.fator_recencia_capado:.4f} - 1) = <span class="calculo-resultado">{sinal_rec}{c.ajuste_recencia:.2f}</span>
                </div>
            </div>
            
            <div class="calculo-passo" style="border-color: #f1c40f;">
                <div class="calculo-passo-titulo" style="color: #f1c40f;">5️⃣ Lambda Raw (Soma Aditiva)</div>
                <div class="calculo-formula">
                    λ_raw = {c.lambda_base:.2f} {sinal_arb}{c.delta_arbitro:.2f} {sinal_tim}{c.delta_times:.2f} {sinal_rec}{c.ajuste_recencia:.2f} = <span class="calculo-resultado">{c.lambda_final_raw:.2f}</span>
                </div>
            </div>
        </div>
        
        <div class="shrinkage-box">
            <div class="shrinkage-titulo">📐 Shrinkage Bayesiano</div>
            <p style="color: #a0a0a0; margin-bottom: 15px; font-size: 0.9em;">
                λ_shrunk = w × λ_raw + (1-w) × λ_base → Regulariza estimativas com dados limitados
            </p>
            
            <div class="shrinkage-grid">
                <div class="shrinkage-item">
                    <div class="shrinkage-valor">{c.peso_shrinkage:.2f}</div>
                    <div class="shrinkage-label">Peso (w)</div>
                </div>
                <div class="shrinkage-item">
                    <div class="shrinkage-valor">{c.lambda_final_raw:.2f}</div>
                    <div class="shrinkage-label">λ Raw</div>
                </div>
                <div class="shrinkage-item">
                    <div class="shrinkage-valor" style="color: #2ecc71;">{c.lambda_shrunk:.2f}</div>
                    <div class="shrinkage-label">λ Shrunk (Final)</div>
                </div>
            </div>
            
            <p style="color: #a0a0a0; margin-top: 15px; font-size: 0.85em; text-align: center;">
                💡 {c.razao_shrinkage}
            </p>
        </div>
    '''


def gerar_secao_intervalo(intervalo: IntervaloConfianca) -> str:
    """Gera a seção de intervalo de confiança."""
    
    aviso = ""
    if intervalo.variancia_alta:
        aviso = '''
            <div class="intervalo-aviso">
                ⚠️ Alta variância detectada. Mercados extremos (Over 5.5) não serão destacados.
            </div>
        '''
    
    return f'''
        <div class="intervalo-box">
            <div class="intervalo-titulo">📈 Faixa Provável de Cartões (Intervalo de Confiança)</div>
            
            <div class="intervalo-visual">
                <div class="intervalo-numero intervalo-p10">
                    <div>{intervalo.p10}</div>
                    <div style="font-size: 0.6em; color: #a0a0a0;">P10</div>
                </div>
                <span style="color: #a0a0a0;">—</span>
                <div class="intervalo-numero intervalo-p50">
                    <div>{intervalo.p50}</div>
                    <div style="font-size: 0.6em; color: #a0a0a0;">Mediana</div>
                </div>
                <span style="color: #a0a0a0;">—</span>
                <div class="intervalo-numero intervalo-p90">
                    <div>{intervalo.p90}</div>
                    <div style="font-size: 0.6em; color: #a0a0a0;">P90</div>
                </div>
            </div>
            
            <p style="color: #a0a0a0; font-size: 0.85em;">
                80% dos jogos com perfil semelhante têm entre <strong>{intervalo.p10}</strong> e <strong>{intervalo.p90}</strong> cartões
            </p>
            
            {aviso}
        </div>
    '''


def gerar_secao_modelo(resultado: ResultadoAnalise) -> str:
    """Gera a seção do modelo matemático."""
    
    c = resultado.calculo
    
    return f'''
        <div class="modelo-box">
            <div class="calculo-titulo">📊 Modelo: {c.modelo_utilizado}</div>
            
            <div class="modelo-formula-principal">
                P(Y = k) = C(k + r - 1, k) × p<sup>r</sup> × (1-p)<sup>k</sup>
            </div>
            
            <div style="text-align: center; margin-top: 10px; color: #a0a0a0;">
                r = {c.dispersao_r:.2f} | λ = {c.lambda_shrunk:.2f} | p = {c.dispersao_r / (c.dispersao_r + c.lambda_shrunk):.4f}
            </div>
            
            <div class="modelo-explicacao">
                <p><strong>Por que Negative Binomial?</strong></p>
                <ul style="margin: 10px 0; padding-left: 20px;">
                    <li>Poisson assume variância = média, mas cartões frequentemente têm var > média</li>
                    <li>O parâmetro r={c.dispersao_r:.2f} captura a sobredispersão da {resultado.partida.liga}</li>
                    <li>Melhora previsões nas caudas (Over 5.5, Under 2.5)</li>
                </ul>
                <p style="margin-top: 10px; color: #3498db;">{c.motivo_modelo}</p>
            </div>
        </div>
    '''


def gerar_secao_probabilidades(resultado: ResultadoAnalise) -> str:
    """Gera a seção de probabilidades."""
    
    cards_html = ""
    
    for p in resultado.probabilidades:
        # Classes
        classes = "prob-card"
        if p.eh_destaque:
            classes += " destaque"
        elif p.bloqueio_variancia or p.bloqueio_qualidade:
            classes += " bloqueado"
        
        # Razão do bloqueio
        bloqueio_html = ""
        if p.bloqueio_variancia:
            bloqueio_html = '<div class="prob-bloqueio">🚫 Variância alta</div>'
        elif p.bloqueio_qualidade:
            bloqueio_html = '<div class="prob-bloqueio">🚫 Dados insuficientes</div>'
        
        cards_html += f'''
            <div class="{classes}">
                <div class="prob-mercado">{p.mercado}</div>
                <div class="prob-valores">
                    <span class="prob-raw">Raw: {p.p_raw:.1f}%</span>
                </div>
                <div class="prob-calibrado">{p.p_calibrado:.1f}%</div>
                <div class="prob-descricao">
                    {"≥" if p.tipo == "over" else "≤"} {int(p.linha)} cartões
                </div>
                {bloqueio_html}
            </div>
        '''
    
    return f'''
        <div class="calculo-section">
            <div class="calculo-titulo">🎯 Probabilidades (Raw → Calibrado)</div>
            <p style="color: #a0a0a0; margin-bottom: 15px; font-size: 0.9em;">
                λ_shrunk = {resultado.calculo.lambda_shrunk:.2f} | Modelo: {resultado.calculo.modelo_utilizado}
            </p>
            
            <div class="prob-grid">
                {cards_html}
            </div>
            
            <p style="color: #606060; font-size: 0.85em; text-align: center; margin-top: 15px;">
                ✅ Destaques: p_calibrado ≥ threshold do mercado | Sem bloqueios de variância ou qualidade
            </p>
        </div>
    '''


def gerar_secao_interpretacao(resultado: ResultadoAnalise) -> str:
    """Gera a seção de interpretação final."""
    
    c = resultado.calculo
    q = c.qualidade_dados
    
    # Destaques
    if resultado.mercados_destaque:
        destaques_texto = ", ".join(resultado.mercados_destaque)
    else:
        destaques_texto = "Nenhum mercado atingiu o threshold com confiança suficiente"
    
    return f'''
        <div class="interpretacao-box">
            <div class="interpretacao-titulo">🧠 Interpretação Estatística</div>
            
            <div class="interpretacao-texto">
                <p>
                    Com base no <strong>modelo aditivo + shrinkage bayesiano</strong>, 
                    a expectativa final é de <span class="lambda-destaque">{c.lambda_shrunk:.2f} cartões</span>.
                </p>
                
                <p style="margin-top: 12px;">
                    <strong>Tendência:</strong> <span style="color: {resultado.cor_tendencia}; font-weight: bold;">
                    {resultado.tendencia}</span>
                </p>
                
                <p style="margin-top: 12px;">
                    <strong>Destaques:</strong> {destaques_texto}
                </p>
                
                <p style="margin-top: 12px;">
                    <strong>Qualidade dos dados:</strong> {q.score_total:.0f}/100
                    (Shrinkage w={c.peso_shrinkage:.2f})
                </p>
                
                <div style="margin-top: 20px; padding: 15px; background: rgba(52, 152, 219, 0.1); border-radius: 8px; border-left: 3px solid #3498db;">
                    <p style="font-size: 0.9em; color: #a0a0a0; margin: 0;">
                        ℹ️ <strong>Nota:</strong> Probabilidades calibradas representam frequência esperada no longo prazo.
                        A calibração é baseada em histórico de validações por mercado.
                    </p>
                </div>
            </div>
        </div>
    '''


def gerar_card_completo(resultado: ResultadoAnalise) -> str:
    """Gera o card completo de uma partida."""
    
    p = resultado.partida
    c = resultado.calculo
    
    # Limpa nomes dos times (remove emojis que podem ter vindo do HTML original)
    nome_mandante = re.sub(r'[🏠✈️⚽🏆📊🎯]', '', p.time_mandante.nome).strip()
    nome_visitante = re.sub(r'[🏠✈️⚽🏆📊🎯]', '', p.time_visitante.nome).strip()
    
    return f'''
        <div class="jogo-card" data-perfil="{p.perfil_card}">
            <div class="jogo-header">
                <div class="jogo-titulo">{nome_mandante} ({p.time_mandante.posicao}) vs {nome_visitante} ({p.time_visitante.posicao})</div>
                <div class="jogo-data">
                    <div class="horario">{p.horario}</div>
                    <div class="data">{p.data}</div>
                </div>
            </div>
            
            <div class="jogo-info-bar">
                <span>
                    <span class="info-label">🏆</span>
                    <span class="info-value">{p.liga}</span>
                </span>
                <span>
                    <span class="info-label">⚖️</span>
                    <span class="info-value">{p.arbitro.nome}</span>
                </span>
                <span>
                    <span class="info-label">📊</span>
                    <span class="info-value" style="color: #9b59b6;">λ = {c.lambda_shrunk:.2f}</span>
                </span>
                <span>
                    <span class="info-label">📈</span>
                    <span class="info-value" style="color: {resultado.cor_tendencia};">{resultado.tendencia}</span>
                </span>
            </div>
            
            <div class="jogo-content">
                <div class="secao">
                    <div class="secao-titulo">📊 Análise Probabilística V2.0</div>
                    
                    {gerar_secao_calculo(resultado)}
                    
                    {gerar_secao_qualidade(c.qualidade_dados)}
                    
                    {gerar_secao_modelo(resultado)}
                    
                    {gerar_secao_intervalo(resultado.intervalo)}
                    
                    {gerar_secao_probabilidades(resultado)}
                    
                    {gerar_secao_interpretacao(resultado)}
                </div>
            </div>
        </div>
    '''


def gerar_html_completo(resultados: List[ResultadoAnalise], data_arquivo: str) -> str:
    """Gera o HTML completo com todas as partidas."""
    
    timestamp = datetime.now().strftime('%d/%m/%Y %H:%M')
    css_adicional = gerar_css_adicional()
    
    # Gera cards
    cards_html = ""
    for resultado in resultados:
        cards_html += gerar_card_completo(resultado)
    
    return f'''<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RefStats - Análise Probabilística V2.0 - {data_arquivo}</title>
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
        
        .navbar {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            z-index: 9997;
            background-image:
                linear-gradient(rgba(10, 15, 30, 0.85), rgba(10, 15, 30, 0.85)),
                url("../assets/img/FundoMuroFundo.png");
            background-size: cover;
            padding: 15px 50px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.6);
            border-bottom: 2px solid #e94560;
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
        
        .header .version-badge {{
            display: inline-block;
            background: linear-gradient(135deg, #9b59b6 0%, #3498db 100%);
            color: white;
            padding: 5px 15px;
            border-radius: 15px;
            font-size: 0.85em;
            margin-top: 10px;
        }}
        
        .jogo-card {{
            background: linear-gradient(135deg, #16213e 0%, #1a1a2e 100%);
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            margin-bottom: 30px;
            border: 1px solid #0f3460;
            overflow: hidden;
        }}
        
        .jogo-header {{
            background: linear-gradient(135deg, #e94560 0%, #0f3460 100%);
            padding: 25px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .jogo-titulo {{
            font-size: 1.6em;
            color: white;
            font-weight: bold;
        }}
        
        .jogo-data {{
            text-align: right;
            color: white;
        }}
        
        .jogo-data .horario {{
            font-size: 1.4em;
            font-weight: bold;
        }}
        
        .jogo-info-bar {{
            background: #0f3460;
            padding: 15px 30px;
            display: flex;
            gap: 25px;
            flex-wrap: wrap;
        }}
        
        .jogo-info-bar span {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        
        .jogo-info-bar .info-label {{
            color: #a0a0a0;
        }}
        
        .jogo-info-bar .info-value {{
            color: white;
            font-weight: 500;
        }}
        
        .jogo-content {{
            padding: 30px;
        }}
        
        .secao {{
            margin-bottom: 20px;
        }}
        
        .secao-titulo {{
            font-size: 1.4em;
            color: #e94560;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #e94560;
        }}
        
        .footer {{
            background: linear-gradient(135deg, #0f3460 0%, #1a1a2e 100%);
            padding: 25px;
            border-radius: 15px;
            text-align: center;
            margin-top: 30px;
            color: #a0a0a0;
            border: 1px solid #0f3460;
        }}
        
        @media (max-width: 768px) {{
            .navbar {{
                padding: 15px 20px;
            }}
            
            .jogo-header {{
                flex-direction: column;
                gap: 15px;
                text-align: center;
            }}
            
            .jogo-titulo {{
                font-size: 1.3em;
            }}
        }}
        
        {css_adicional}
    </style>
</head>
<body>
    <nav class="navbar">
        <a href="../index.html" class="navbar-brand">
            <img src="../assets/img/LogoINICIO.png" alt="RefStats" class="logo-img">
        </a>
        
        <div class="navbar-menu">
            <a href="../index.html">INÍCIO</a>
            <a href="../JOGOS_DO_DIA.html">JOGOS DO DIA</a>
            <a href="../refstats_historico.html">HISTÓRICO</a>
        </div>
    </nav>
    
    <div class="container">
        <div class="header">
            <h1>📊 Análise Probabilística de Cartões</h1>
            <p>📅 {data_arquivo} • {len(resultados)} partida(s) analisada(s)</p>
            <div class="version-badge">
                V2.0: Neg. Binomial + Shrinkage + Calibração
            </div>
        </div>
        
        {cards_html}
        
        <div class="footer">
            <p><strong>📊 RefStats - Análise Probabilística V2.0</strong></p>
            <p style="margin-top: 10px;">
                <a href="../refstats_termos.html" style="color: #3498db;">Termos</a> | 
                <a href="../refstats_privacidade.html" style="color: #3498db;">Privacidade</a> | 
                <a href="../refstats_aviso_legal.html" style="color: #3498db;">Aviso Legal</a>
            </p>
            <p style="margin-top: 15px; font-size: 0.85em;">
                Modelo: Negative Binomial + Shrinkage Bayesiano + Calibração Isotônica
            </p>
            <p style="margin-top: 5px; font-size: 0.85em;">
                Gerado em {timestamp}
            </p>
            <div style="margin-top: 15px; padding: 15px; background: rgba(52, 152, 219, 0.1); border-radius: 8px; display: inline-block;">
                <p style="font-size: 0.85em; color: #3498db; margin: 0;">
                    ℹ️ Probabilidades representam frequência esperada no longo prazo.
                    Erros individuais são parte natural de modelos probabilísticos.
                </p>
            </div>
            <p style="margin-top: 15px; font-size: 0.8em; color: #e94560;">
                ⚠️ Conteúdo informativo e educacional. Não constitui conselho de apostas.
            </p>
        </div>
    </div>
</body>
</html>
'''


# =============================================================================
# FUNÇÃO PRINCIPAL
# =============================================================================

def main():
    """Função principal."""
    print("""
╔═══════════════════════════════════════════════════════════════╗
║     SISTEMA DE ANÁLISE PROBABILÍSTICA DE CARTÕES              ║
║                        VERSÃO 2.0                             ║
║  Neg. Binomial + Shrinkage + Calibração + Intervalos          ║
╚═══════════════════════════════════════════════════════════════╝
    """)
    
    # Define pastas
    pasta_atual = os.path.dirname(os.path.abspath(__file__))
    pasta_historico = os.path.join(pasta_atual, "Historico")
    pasta_probabilidade = os.path.join(pasta_atual, "Probabilidade")
    pasta_calibracao = os.path.join(pasta_atual, "Calibracao")
    
    print(f"📁 Pasta de entrada: {pasta_historico}")
    print(f"📁 Pasta de saída: {pasta_probabilidade}")
    print(f"📁 Pasta de calibração: {pasta_calibracao}")
    
    # Cria pastas se não existirem
    os.makedirs(pasta_historico, exist_ok=True)
    os.makedirs(pasta_probabilidade, exist_ok=True)
    os.makedirs(pasta_calibracao, exist_ok=True)
    
    # Inicializa gerenciador de calibração
    gerenciador = obter_gerenciador_calibracao(pasta_calibracao)
    
    # Busca arquivos
    padrao = os.path.join(pasta_historico, "JOGOS_DO_DIA_*.html")
    arquivos = glob.glob(padrao)
    
    if not arquivos:
        print("\n⚠️ Nenhum arquivo JOGOS_DO_DIA_*.html encontrado em Historico/")
        print("   Coloque os arquivos HTML na pasta e execute novamente.")
        return
    
    print(f"\n📋 Arquivos encontrados: {len(arquivos)}")
    
    # Processa cada arquivo
    arquivos_sucesso = 0
    arquivos_falha = 0
    
    for arquivo in sorted(arquivos):
        nome_arquivo = os.path.basename(arquivo)
        print(f"\n{'='*60}")
        print(f"📂 Processando: {nome_arquivo}")
        print(f"{'='*60}")
        
        # Extrai data do nome
        match = re.search(r'(\d{2})(\d{2})(\d{4})', nome_arquivo)
        if match:
            data_arquivo = f"{match.group(1)}/{match.group(2)}/{match.group(3)}"
        else:
            data_arquivo = "Data não identificada"
        
        # Processa
        resultados = processar_arquivo(arquivo, gerenciador)
        
        if resultados:
            # Gera HTML
            html = gerar_html_completo(resultados, data_arquivo)
            
            # Salva
            nome_saida = nome_arquivo.replace("JOGOS_DO_DIA_", "PROBABILIDADE_")
            caminho_saida = os.path.join(pasta_probabilidade, nome_saida)
            
            with open(caminho_saida, 'w', encoding='utf-8') as f:
                f.write(html)
            
            print(f"\n✅ Arquivo salvo: {caminho_saida}")
            arquivos_sucesso += 1
        else:
            print(f"\n❌ Falha ao processar arquivo")
            arquivos_falha += 1
    
    # Resumo
    print(f"""
╔═══════════════════════════════════════════════════════════════╗
║                    RESUMO DO PROCESSAMENTO                    ║
╠═══════════════════════════════════════════════════════════════╣
║  ✅ Arquivos processados com sucesso: {arquivos_sucesso:3d}                     ║
║  ❌ Arquivos com falha: {arquivos_falha:3d}                                   ║
║  📁 Pasta de saída: Probabilidade/                            ║
╚═══════════════════════════════════════════════════════════════╝
    """)


if __name__ == "__main__":
    main()
