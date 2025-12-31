#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
SISTEMA DE APRENDIZADO AVANÇADO - RefStats V2.0
=============================================================================
Autor: RefStats

OBJETIVO:
    Analisar padrões históricos de acertos/erros e descobrir automaticamente
    quais COMBINAÇÕES de fatores levam a taxas de acerto mais altas.

COMO FUNCIONA:
    1. Coleta dados estruturados de cada validação
    2. Agrupa por combinações de fatores (árbitro, liga, lambda, etc.)
    3. Calcula taxa de acerto de cada combinação
    4. Identifica "Regras de Ouro" (combinações com ≥75% de acerto)
    5. Aplica regras nas novas previsões

REGRAS DE OURO:
    - Mínimo 8 amostras para validar uma regra
    - Taxa de acerto ≥ 75% para ser considerada "de ouro"
    - Taxa de acerto ≥ 85% = "Regra Platina"
    - Taxa de acerto ≥ 90% = "Regra Diamante"
=============================================================================
"""

import os
import json
import pickle
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple
from collections import defaultdict


# =============================================================================
# CONFIGURAÇÕES
# =============================================================================

# Mínimo de amostras para uma regra ser válida
MIN_AMOSTRAS_REGRA = 8

# Thresholds de taxa de acerto
THRESHOLD_OURO = 75.0
THRESHOLD_PLATINA = 85.0
THRESHOLD_DIAMANTE = 90.0

# Mercados excluídos das Regras de Ouro
# (mercados com odds muito baixas que não compensam apostar)
MERCADOS_EXCLUIDOS_REGRAS = [
    'Under 5.5 Cartões',   # Odds ~1.20 ou menos - quase sempre acerta mas não compensa
    # 'Over 2.5 Cartões',  # Descomentar se quiser excluir também
]

# Fatores que serão analisados (EXPANDIDO V2.1)
FATORES_ANALISE = [
    # Fatores básicos
    'faixa_lambda',           # Baixo, Médio, Alto
    'perfil_arbitro',         # Rigoroso, Médio, Permissivo
    'tipo_competicao',        # Liga, Copa
    'faixa_qualidade',        # Baixa, Média, Alta
    'variancia',              # Baixa, Alta
    'faixa_prob',             # 55-60, 60-65, 65-70, 70-75, 75+
    'tendencia_recente',      # Subindo, Estável, Descendo
    'regiao_competicao',      # Brasil, Europa, América, Outro
    
    # NOVOS - Fatores de cálculo
    'faixa_delta_arbitro',    # Negativo, Neutro, Positivo, Muito Positivo
    'faixa_delta_times',      # Negativo, Neutro, Positivo, Muito Positivo
    'faixa_peso_shrinkage',   # Baixo, Médio, Alto
    'faixa_media_arb_5j',     # Baixa, Média, Alta, Muito Alta
    'faixa_amplitude',        # Estreita, Média, Larga
    'completude_dados',       # Incompleto, Parcial, Completo
    'faixa_soma_times',       # Baixa, Média, Alta
]


# =============================================================================
# CLASSES DE DADOS
# =============================================================================

@dataclass
class DadosPartidaAprendizado:
    """Dados estruturados de uma partida para aprendizado."""
    
    # Identificação
    data: str
    time_mandante: str
    time_visitante: str
    competicao: str
    
    # Fatores numéricos básicos
    lambda_shrunk: float
    qualidade_score: float
    media_arbitro_5j: float
    media_arbitro_10j: float
    intervalo_amplitude: int  # p90 - p10
    
    # Fatores categóricos
    perfil_arbitro: str       # Rigoroso, Médio, Permissivo
    modelo: str               # Negative Binomial, Poisson
    
    # NOVOS - Fatores numéricos de cálculo
    delta_arbitro: float = 0.0        # Ajuste do árbitro vs liga
    delta_times: float = 0.0          # Ajuste dos times vs liga
    peso_shrinkage: float = 0.5       # Peso w do shrinkage
    soma_cartoes_times: float = 0.0   # Soma cartões mandante + visitante
    completude_arbitro: float = 0.0   # % completude dados árbitro
    lambda_raw: float = 0.0           # Lambda antes do shrinkage
    
    # Fatores derivados básicos (calculados)
    faixa_lambda: str = ""           # Baixo (<4), Médio (4-5.5), Alto (>5.5)
    tipo_competicao: str = ""        # Liga, Copa
    faixa_qualidade: str = ""        # Baixa (<50), Média (50-70), Alta (>70)
    variancia: str = ""              # Baixa (amp<=5), Alta (amp>5)
    tendencia_recente: str = ""      # Subindo, Estável, Descendo
    regiao_competicao: str = ""      # Brasil, Europa, América, Outro
    
    # NOVOS - Fatores derivados de cálculo
    faixa_delta_arbitro: str = ""    # Negativo, Neutro, Positivo, Muito Positivo
    faixa_delta_times: str = ""      # Negativo, Neutro, Positivo, Muito Positivo
    faixa_peso_shrinkage: str = ""   # Baixo, Médio, Alto
    faixa_media_arb_5j: str = ""     # Baixa, Média, Alta, Muito Alta
    faixa_amplitude: str = ""        # Estreita, Média, Larga
    completude_dados: str = ""       # Incompleto, Parcial, Completo
    faixa_soma_times: str = ""       # Baixa, Média, Alta
    
    def calcular_fatores_derivados(self):
        """Calcula os fatores derivados a partir dos dados brutos."""
        
        # Faixa Lambda
        if self.lambda_shrunk < 4.0:
            self.faixa_lambda = "Baixo"
        elif self.lambda_shrunk <= 5.5:
            self.faixa_lambda = "Médio"
        else:
            self.faixa_lambda = "Alto"
        
        # Tipo de competição
        termos_copa = ['copa', 'cup', 'taça', 'libertadores', 'sudamericana', 
                       'champions', 'europa league', 'conference']
        comp_lower = self.competicao.lower()
        self.tipo_competicao = "Copa" if any(t in comp_lower for t in termos_copa) else "Liga"
        
        # Faixa de qualidade
        if self.qualidade_score < 50:
            self.faixa_qualidade = "Baixa"
        elif self.qualidade_score <= 70:
            self.faixa_qualidade = "Média"
        else:
            self.faixa_qualidade = "Alta"
        
        # Variância
        self.variancia = "Alta" if self.intervalo_amplitude > 5 else "Baixa"
        
        # Tendência recente
        if self.media_arbitro_5j > 0 and self.media_arbitro_10j > 0:
            diff = self.media_arbitro_5j - self.media_arbitro_10j
            if diff > 0.5:
                self.tendencia_recente = "Subindo"
            elif diff < -0.5:
                self.tendencia_recente = "Descendo"
            else:
                self.tendencia_recente = "Estável"
        else:
            self.tendencia_recente = "Desconhecido"
        
        # Região da competição
        brasil = ['brasileirão', 'série', 'copa do brasil', 'paulista', 'carioca', 
                  'mineiro', 'gaúcho', 'paranaense', 'betano']
        europa = ['premier', 'la liga', 'laliga', 'bundesliga', 'serie a', 'ligue 1',
                  'champions', 'europa league', 'eredivisie', 'primeira liga']
        america = ['libertadores', 'sudamericana', 'mls', 'liga mx', 'argentina',
                   'copa america']
        
        if any(t in comp_lower for t in brasil):
            self.regiao_competicao = "Brasil"
        elif any(t in comp_lower for t in europa):
            self.regiao_competicao = "Europa"
        elif any(t in comp_lower for t in america):
            self.regiao_competicao = "América"
        else:
            self.regiao_competicao = "Outro"
        
        # =========================================================================
        # NOVOS FATORES DERIVADOS
        # =========================================================================
        
        # Faixa Delta Árbitro (quanto o árbitro desvia da média da liga)
        if self.delta_arbitro < -0.5:
            self.faixa_delta_arbitro = "Negativo"
        elif self.delta_arbitro <= 0.5:
            self.faixa_delta_arbitro = "Neutro"
        elif self.delta_arbitro <= 1.0:
            self.faixa_delta_arbitro = "Positivo"
        else:
            self.faixa_delta_arbitro = "Muito Positivo"
        
        # Faixa Delta Times (quanto os times desviam da média)
        if self.delta_times < -0.5:
            self.faixa_delta_times = "Negativo"
        elif self.delta_times <= 0.5:
            self.faixa_delta_times = "Neutro"
        elif self.delta_times <= 1.0:
            self.faixa_delta_times = "Positivo"
        else:
            self.faixa_delta_times = "Muito Positivo"
        
        # Faixa Peso Shrinkage (confiança nos dados)
        if self.peso_shrinkage < 0.5:
            self.faixa_peso_shrinkage = "Baixo"
        elif self.peso_shrinkage <= 0.7:
            self.faixa_peso_shrinkage = "Médio"
        else:
            self.faixa_peso_shrinkage = "Alto"
        
        # Faixa Média Árbitro 5j
        if self.media_arbitro_5j < 4.0:
            self.faixa_media_arb_5j = "Baixa"
        elif self.media_arbitro_5j <= 5.0:
            self.faixa_media_arb_5j = "Média"
        elif self.media_arbitro_5j <= 6.0:
            self.faixa_media_arb_5j = "Alta"
        else:
            self.faixa_media_arb_5j = "Muito Alta"
        
        # Faixa Amplitude (previsibilidade)
        if self.intervalo_amplitude <= 4:
            self.faixa_amplitude = "Estreita"
        elif self.intervalo_amplitude <= 6:
            self.faixa_amplitude = "Média"
        else:
            self.faixa_amplitude = "Larga"
        
        # Completude dos dados
        if self.completude_arbitro < 50:
            self.completude_dados = "Incompleto"
        elif self.completude_arbitro < 80:
            self.completude_dados = "Parcial"
        else:
            self.completude_dados = "Completo"
        
        # Faixa Soma Times (perfil dos times)
        if self.soma_cartoes_times < 4.0:
            self.faixa_soma_times = "Baixa"
        elif self.soma_cartoes_times <= 5.5:
            self.faixa_soma_times = "Média"
        else:
            self.faixa_soma_times = "Alta"


@dataclass
class ResultadoMercadoAprendizado:
    """Resultado de um mercado específico para aprendizado."""
    mercado: str              # Ex: "Over 3.5 Cartões"
    tipo: str                 # "over" ou "under"
    linha: float              # 3.5
    p_raw: float              # Probabilidade raw
    p_calibrado: float        # Probabilidade calibrada
    eh_destaque: bool         # Se foi destacado
    acertou: bool             # Se acertou
    cartoes_reais: int        # Quantidade real de cartões
    
    # Faixa de probabilidade
    faixa_prob: str = ""      # 55-60, 60-65, etc.
    
    def calcular_faixa_prob(self):
        """Calcula a faixa de probabilidade."""
        p = self.p_calibrado
        if p < 55:
            self.faixa_prob = "<55"
        elif p < 60:
            self.faixa_prob = "55-60"
        elif p < 65:
            self.faixa_prob = "60-65"
        elif p < 70:
            self.faixa_prob = "65-70"
        elif p < 75:
            self.faixa_prob = "70-75"
        elif p < 80:
            self.faixa_prob = "75-80"
        else:
            self.faixa_prob = "80+"


@dataclass
class RegistroAprendizado:
    """Um registro completo para aprendizado (partida + resultado de um mercado)."""
    partida: DadosPartidaAprendizado
    resultado: ResultadoMercadoAprendizado
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class RegraDeOuro:
    """Uma regra descoberta pelo sistema de aprendizado."""
    id: int
    mercado: str                      # Ex: "Over 3.5 Cartões"
    condicoes: Dict[str, str]         # Ex: {"faixa_lambda": "Alto", "perfil_arbitro": "Rigoroso"}
    
    # Estatísticas
    total_amostras: int
    acertos: int
    taxa_acerto: float
    
    # Classificação
    nivel: str                        # "Ouro", "Platina", "Diamante"
    cor: str                          # Cor para exibição
    
    # Descrição legível
    descricao: str = ""
    
    def gerar_descricao(self):
        """Gera descrição legível da regra."""
        partes = []
        
        mapa_nomes = {
            'faixa_lambda': 'λ',
            'perfil_arbitro': 'Árbitro',
            'tipo_competicao': 'Tipo',
            'faixa_qualidade': 'Qualidade',
            'variancia': 'Variância',
            'faixa_prob': 'Prob',
            'tendencia_recente': 'Tendência',
            'regiao_competicao': 'Região',
        }
        
        for fator, valor in self.condicoes.items():
            nome = mapa_nomes.get(fator, fator)
            partes.append(f"{nome}={valor}")
        
        self.descricao = " + ".join(partes)


# =============================================================================
# BANCO DE DADOS DE APRENDIZADO
# =============================================================================

class BancoAprendizado:
    """Gerencia o banco de dados de aprendizado."""
    
    def __init__(self, caminho: str):
        self.caminho = caminho
        self.registros: List[RegistroAprendizado] = []
        self.regras: List[RegraDeOuro] = []
        self.carregar()
    
    def carregar(self):
        """Carrega dados do arquivo."""
        if os.path.exists(self.caminho):
            try:
                with open(self.caminho, 'rb') as f:
                    dados = pickle.load(f)
                    self.registros = dados.get('registros', [])
                    self.regras = dados.get('regras', [])
            except Exception as e:
                print(f"   ⚠️ Erro ao carregar banco de aprendizado: {e}")
                self.registros = []
                self.regras = []
    
    def salvar(self):
        """Salva dados no arquivo."""
        os.makedirs(os.path.dirname(self.caminho) or '.', exist_ok=True)
        with open(self.caminho, 'wb') as f:
            pickle.dump({
                'registros': self.registros,
                'regras': self.regras
            }, f)
    
    def adicionar_registro(self, registro: RegistroAprendizado):
        """Adiciona um novo registro."""
        self.registros.append(registro)
    
    def total_registros(self) -> int:
        """Retorna total de registros."""
        return len(self.registros)
    
    def total_por_mercado(self) -> Dict[str, int]:
        """Retorna total de registros por mercado."""
        contagem = defaultdict(int)
        for r in self.registros:
            contagem[r.resultado.mercado] += 1
        return dict(contagem)


# =============================================================================
# MOTOR DE DESCOBERTA DE REGRAS
# =============================================================================

class MotorAprendizado:
    """Motor de descoberta de regras de ouro."""
    
    def __init__(self, banco: BancoAprendizado):
        self.banco = banco
    
    def descobrir_regras(self) -> List[RegraDeOuro]:
        """Descobre todas as regras de ouro nos dados."""
        
        print("\n🔬 Analisando padrões nos dados...")
        
        todas_regras = []
        
        # Agrupa registros por mercado
        por_mercado = defaultdict(list)
        for r in self.banco.registros:
            por_mercado[r.resultado.mercado].append(r)
        
        # Para cada mercado, analisa combinações
        for mercado, registros in por_mercado.items():
            # FILTRO: Pula mercados excluídos (odds muito baixas)
            if mercado in MERCADOS_EXCLUIDOS_REGRAS:
                print(f"   ⏭️ {mercado}: pulado (odds baixas)")
                continue
            
            if len(registros) < MIN_AMOSTRAS_REGRA:
                continue
            
            print(f"   📊 {mercado}: {len(registros)} amostras")
            
            # Testa combinações de 1, 2 e 3 fatores
            regras_mercado = []
            
            for n_fatores in [1, 2, 3]:
                novas_regras = self._testar_combinacoes(mercado, registros, n_fatores)
                regras_mercado.extend(novas_regras)
            
            # Remove regras redundantes (mantém as mais específicas)
            regras_mercado = self._filtrar_redundantes(regras_mercado)
            
            todas_regras.extend(regras_mercado)
        
        # Ordena por taxa de acerto
        todas_regras.sort(key=lambda r: (-r.taxa_acerto, -r.total_amostras))
        
        # Atribui IDs
        for i, regra in enumerate(todas_regras, 1):
            regra.id = i
            regra.gerar_descricao()
        
        return todas_regras
    
    def _testar_combinacoes(self, mercado: str, registros: List[RegistroAprendizado], 
                           n_fatores: int) -> List[RegraDeOuro]:
        """Testa combinações de n fatores."""
        from itertools import combinations
        
        regras = []
        
        # Gera todas as combinações de fatores
        for fatores in combinations(FATORES_ANALISE, n_fatores):
            # Agrupa registros por valores dos fatores selecionados
            grupos = defaultdict(list)
            
            for r in registros:
                # Extrai valores dos fatores
                valores = []
                for fator in fatores:
                    valor = getattr(r.partida, fator, None)
                    if valor is None or valor == "" or valor == "Desconhecido":
                        break
                    valores.append((fator, valor))
                
                if len(valores) == n_fatores:
                    chave = tuple(valores)
                    grupos[chave].append(r)
            
            # Analisa cada grupo
            for chave, grupo in grupos.items():
                if len(grupo) < MIN_AMOSTRAS_REGRA:
                    continue
                
                acertos = sum(1 for r in grupo if r.resultado.acertou)
                taxa = acertos / len(grupo) * 100
                
                if taxa >= THRESHOLD_OURO:
                    # Determina nível
                    if taxa >= THRESHOLD_DIAMANTE:
                        nivel = "Diamante"
                        cor = "#b9f2ff"  # Azul claro brilhante
                    elif taxa >= THRESHOLD_PLATINA:
                        nivel = "Platina"
                        cor = "#e5e4e2"  # Cinza prateado
                    else:
                        nivel = "Ouro"
                        cor = "#ffd700"  # Dourado
                    
                    regra = RegraDeOuro(
                        id=0,
                        mercado=mercado,
                        condicoes=dict(chave),
                        total_amostras=len(grupo),
                        acertos=acertos,
                        taxa_acerto=taxa,
                        nivel=nivel,
                        cor=cor
                    )
                    regras.append(regra)
        
        return regras
    
    def _filtrar_redundantes(self, regras: List[RegraDeOuro]) -> List[RegraDeOuro]:
        """Remove regras redundantes, mantendo as mais específicas."""
        if not regras:
            return []
        
        # Ordena por número de condições (mais específicas primeiro)
        regras.sort(key=lambda r: -len(r.condicoes))
        
        filtradas = []
        for regra in regras:
            # Verifica se esta regra é subconjunto de alguma já aceita
            eh_redundante = False
            for aceita in filtradas:
                if self._eh_subconjunto(regra.condicoes, aceita.condicoes):
                    # A regra aceita já cobre esta
                    eh_redundante = True
                    break
            
            if not eh_redundante:
                filtradas.append(regra)
        
        return filtradas
    
    def _eh_subconjunto(self, menor: Dict, maior: Dict) -> bool:
        """Verifica se menor é subconjunto de maior."""
        for k, v in menor.items():
            if k not in maior or maior[k] != v:
                return False
        return True
    
    def verificar_regras(self, partida: DadosPartidaAprendizado, 
                        mercado: str, p_calibrado: float) -> List[RegraDeOuro]:
        """Verifica quais regras uma partida ativa."""
        
        regras_ativadas = []
        
        # Calcula faixa de probabilidade
        if p_calibrado < 55:
            faixa_prob = "<55"
        elif p_calibrado < 60:
            faixa_prob = "55-60"
        elif p_calibrado < 65:
            faixa_prob = "60-65"
        elif p_calibrado < 70:
            faixa_prob = "65-70"
        elif p_calibrado < 75:
            faixa_prob = "70-75"
        elif p_calibrado < 80:
            faixa_prob = "75-80"
        else:
            faixa_prob = "80+"
        
        for regra in self.banco.regras:
            if regra.mercado != mercado:
                continue
            
            # Verifica se todas as condições são satisfeitas
            todas_ok = True
            for fator, valor_esperado in regra.condicoes.items():
                if fator == 'faixa_prob':
                    valor_real = faixa_prob
                else:
                    valor_real = getattr(partida, fator, None)
                
                if valor_real != valor_esperado:
                    todas_ok = False
                    break
            
            if todas_ok:
                regras_ativadas.append(regra)
        
        # Ordena por taxa de acerto
        regras_ativadas.sort(key=lambda r: -r.taxa_acerto)
        
        return regras_ativadas


# =============================================================================
# FUNÇÕES DE INTEGRAÇÃO
# =============================================================================

def criar_dados_partida_aprendizado(
    data: str,
    time_mandante: str,
    time_visitante: str,
    competicao: str,
    lambda_shrunk: float,
    qualidade_score: float,
    media_arbitro_5j: float,
    media_arbitro_10j: float,
    intervalo_p10: int,
    intervalo_p90: int,
    perfil_arbitro: str,
    modelo: str,
    # NOVOS parâmetros opcionais
    delta_arbitro: float = 0.0,
    delta_times: float = 0.0,
    peso_shrinkage: float = 0.5,
    soma_cartoes_times: float = 0.0,
    completude_arbitro: float = 0.0,
    lambda_raw: float = 0.0
) -> DadosPartidaAprendizado:
    """Cria dados estruturados de uma partida para aprendizado."""
    
    partida = DadosPartidaAprendizado(
        data=data,
        time_mandante=time_mandante,
        time_visitante=time_visitante,
        competicao=competicao,
        lambda_shrunk=lambda_shrunk,
        qualidade_score=qualidade_score,
        media_arbitro_5j=media_arbitro_5j,
        media_arbitro_10j=media_arbitro_10j,
        intervalo_amplitude=intervalo_p90 - intervalo_p10,
        perfil_arbitro=perfil_arbitro,
        modelo=modelo,
        # Novos campos
        delta_arbitro=delta_arbitro,
        delta_times=delta_times,
        peso_shrinkage=peso_shrinkage,
        soma_cartoes_times=soma_cartoes_times,
        completude_arbitro=completude_arbitro,
        lambda_raw=lambda_raw
    )
    
    partida.calcular_fatores_derivados()
    
    return partida


def criar_resultado_mercado_aprendizado(
    mercado: str,
    tipo: str,
    linha: float,
    p_raw: float,
    p_calibrado: float,
    eh_destaque: bool,
    acertou: bool,
    cartoes_reais: int
) -> ResultadoMercadoAprendizado:
    """Cria resultado estruturado de um mercado para aprendizado."""
    
    resultado = ResultadoMercadoAprendizado(
        mercado=mercado,
        tipo=tipo,
        linha=linha,
        p_raw=p_raw,
        p_calibrado=p_calibrado,
        eh_destaque=eh_destaque,
        acertou=acertou,
        cartoes_reais=cartoes_reais
    )
    
    resultado.calcular_faixa_prob()
    
    return resultado


# Instância global
_banco_aprendizado: BancoAprendizado = None
_motor_aprendizado: MotorAprendizado = None


def obter_banco_aprendizado(pasta: str) -> BancoAprendizado:
    """Obtém ou cria o banco de aprendizado."""
    global _banco_aprendizado
    if _banco_aprendizado is None:
        caminho = os.path.join(pasta, "aprendizado.pkl")
        _banco_aprendizado = BancoAprendizado(caminho)
    return _banco_aprendizado


def obter_motor_aprendizado(pasta: str) -> MotorAprendizado:
    """Obtém ou cria o motor de aprendizado."""
    global _motor_aprendizado, _banco_aprendizado
    
    if _banco_aprendizado is None:
        _banco_aprendizado = obter_banco_aprendizado(pasta)
    
    if _motor_aprendizado is None:
        _motor_aprendizado = MotorAprendizado(_banco_aprendizado)
    
    return _motor_aprendizado


def retreinar_regras(pasta: str) -> List[RegraDeOuro]:
    """Retreina as regras de ouro com os dados atuais."""
    banco = obter_banco_aprendizado(pasta)
    motor = MotorAprendizado(banco)
    
    regras = motor.descobrir_regras()
    banco.regras = regras
    banco.salvar()
    
    return regras


# =============================================================================
# GERAÇÃO DO GUIA INFORMATIVO
# =============================================================================

def gerar_guia_metodologia_html() -> str:
    """Gera o HTML do guia de metodologia."""
    
    return '''
        <div class="guia-metodologia">
            <div class="guia-header">
                <h2>📚 Guia de Metodologia - Como Funciona o Sistema</h2>
                <p>Entenda como as probabilidades são calculadas e como o sistema aprende com os dados.</p>
            </div>
            
            <div class="guia-section">
                <div class="guia-section-title">
                    <span class="guia-icon">📊</span>
                    <h3>1. Modelo Matemático: Negative Binomial</h3>
                </div>
                <div class="guia-content">
                    <p>O sistema usa a distribuição <strong>Negative Binomial</strong> em vez da Poisson tradicional porque:</p>
                    <ul>
                        <li><strong>Poisson assume</strong> que variância = média (eventos independentes)</li>
                        <li><strong>Na realidade</strong>, cartões têm variância > média (sobredispersão)</li>
                        <li><strong>Motivo:</strong> cartões vêm em "clusters" (um cartão leva a mais tensão, que leva a mais cartões)</li>
                    </ul>
                    
                    <div class="guia-formula">
                        <strong>Fórmula:</strong> P(Y = k) = C(k + r - 1, k) × p<sup>r</sup> × (1-p)<sup>k</sup>
                    </div>
                    
                    <p>Onde <strong>r</strong> é o parâmetro de dispersão (varia por liga) e <strong>p</strong> é calculado a partir do λ.</p>
                </div>
            </div>
            
            <div class="guia-section">
                <div class="guia-section-title">
                    <span class="guia-icon">🧮</span>
                    <h3>2. Cálculo do Lambda (λ) - Modelo Aditivo</h3>
                </div>
                <div class="guia-content">
                    <p>O λ (expectativa de cartões) é calculado somando contribuições:</p>
                    
                    <div class="guia-formula">
                        λ_raw = λ_base + Δ_árbitro + Δ_times + ajuste_recência
                    </div>
                    
                    <table class="guia-table">
                        <tr>
                            <th>Componente</th>
                            <th>O que representa</th>
                            <th>Como é calculado</th>
                        </tr>
                        <tr>
                            <td><strong>λ_base</strong></td>
                            <td>Média da liga</td>
                            <td>Média histórica de cartões da competição</td>
                        </tr>
                        <tr>
                            <td><strong>Δ_árbitro</strong></td>
                            <td>Influência do árbitro</td>
                            <td>0.8 × (média_ponderada_árbitro - λ_base)</td>
                        </tr>
                        <tr>
                            <td><strong>Δ_times</strong></td>
                            <td>Perfil dos times</td>
                            <td>0.6 × (soma_cartões_times - λ_base)</td>
                        </tr>
                        <tr>
                            <td><strong>Recência</strong></td>
                            <td>Tendência recente</td>
                            <td>Ajuste de ±5% baseado nas últimas 5 partidas</td>
                        </tr>
                    </table>
                </div>
            </div>
            
            <div class="guia-section">
                <div class="guia-section-title">
                    <span class="guia-icon">📐</span>
                    <h3>3. Shrinkage Bayesiano - Regularização</h3>
                </div>
                <div class="guia-content">
                    <p>Quando os dados são limitados, o sistema "puxa" a estimativa para a média da liga:</p>
                    
                    <div class="guia-formula">
                        λ_shrunk = w × λ_raw + (1-w) × λ_base
                    </div>
                    
                    <p>O peso <strong>w</strong> (0 a 1) depende de:</p>
                    <ul>
                        <li>Qualidade dos dados (completude)</li>
                        <li>Número de jogos do árbitro</li>
                        <li>Dados de recência disponíveis</li>
                    </ul>
                    
                    <div class="guia-example">
                        <strong>Exemplo:</strong> Se w = 0.6, λ_raw = 6.5 e λ_base = 5.0:<br>
                        λ_shrunk = 0.6 × 6.5 + 0.4 × 5.0 = 3.9 + 2.0 = <strong>5.9</strong>
                    </div>
                </div>
            </div>
            
            <div class="guia-section">
                <div class="guia-section-title">
                    <span class="guia-icon">🎯</span>
                    <h3>4. Calibração - Aprendendo com os Erros</h3>
                </div>
                <div class="guia-content">
                    <p>O sistema ajusta as probabilidades baseado no histórico de acertos:</p>
                    
                    <table class="guia-table">
                        <tr>
                            <th>O que o modelo diz</th>
                            <th>O que acontece na prática</th>
                            <th>Calibração</th>
                        </tr>
                        <tr>
                            <td>60% de chance</td>
                            <td>Acerta 55% das vezes</td>
                            <td>Ajusta para 55%</td>
                        </tr>
                        <tr>
                            <td>75% de chance</td>
                            <td>Acerta 78% das vezes</td>
                            <td>Ajusta para 78%</td>
                        </tr>
                    </table>
                    
                    <p><strong>Mínimo necessário:</strong> 10 amostras por mercado para ativar calibração.</p>
                </div>
            </div>
            
            <div class="guia-section">
                <div class="guia-section-title">
                    <span class="guia-icon">📈</span>
                    <h3>5. Intervalo de Confiança [P10 - P90]</h3>
                </div>
                <div class="guia-content">
                    <p>Mostra a faixa onde 80% dos resultados devem cair:</p>
                    
                    <div class="guia-example">
                        <strong>Exemplo:</strong> Intervalo [2 - 8]<br>
                        Significa que em jogos com perfil semelhante, 80% têm entre 2 e 8 cartões.
                    </div>
                    
                    <p><strong>Variância alta:</strong> Se (P90 - P10) > 6, o sistema bloqueia destaques em mercados extremos (Over 5.5) por falta de previsibilidade.</p>
                </div>
            </div>
            
            <div class="guia-section">
                <div class="guia-section-title">
                    <span class="guia-icon">🏆</span>
                    <h3>6. Sistema de Aprendizado - Regras de Ouro</h3>
                </div>
                <div class="guia-content">
                    <p>O sistema analisa o histórico e descobre <strong>combinações de fatores</strong> com alta taxa de acerto:</p>
                    
                    <table class="guia-table">
                        <tr>
                            <th>Nível</th>
                            <th>Taxa de Acerto</th>
                            <th>Mínimo de Amostras</th>
                        </tr>
                        <tr>
                            <td><span style="color: #ffd700;">🥇 Ouro</span></td>
                            <td>≥ 75%</td>
                            <td>8</td>
                        </tr>
                        <tr>
                            <td><span style="color: #e5e4e2;">🥈 Platina</span></td>
                            <td>≥ 85%</td>
                            <td>8</td>
                        </tr>
                        <tr>
                            <td><span style="color: #b9f2ff;">💎 Diamante</span></td>
                            <td>≥ 90%</td>
                            <td>8</td>
                        </tr>
                    </table>
                    
                    <div class="guia-example">
                        <strong>Exemplo de Regra Descoberta:</strong><br>
                        "Over 3.5 Cartões + λ Alto + Árbitro Rigoroso + Brasil"<br>
                        → Histórico: 14/16 acertos = <strong>87.5%</strong> 🥈 Platina
                    </div>
                    
                    <p>Quanto mais você validar partidas, mais regras o sistema descobre!</p>
                </div>
            </div>
            
            <div class="guia-section">
                <div class="guia-section-title">
                    <span class="guia-icon">📊</span>
                    <h3>7. Métricas de Avaliação</h3>
                </div>
                <div class="guia-content">
                    <table class="guia-table">
                        <tr>
                            <th>Métrica</th>
                            <th>O que mede</th>
                            <th>Bom valor</th>
                        </tr>
                        <tr>
                            <td><strong>Brier Score</strong></td>
                            <td>Calibração geral (erro quadrático)</td>
                            <td>< 0.20</td>
                        </tr>
                        <tr>
                            <td><strong>Log Loss</strong></td>
                            <td>Discriminação (penaliza muito erros confiantes)</td>
                            <td>< 0.50</td>
                        </tr>
                        <tr>
                            <td><strong>Curva de Confiabilidade</strong></td>
                            <td>Se 60% previsto = 60% real</td>
                            <td>Δ < 5%</td>
                        </tr>
                    </table>
                </div>
            </div>
            
            <div class="guia-section">
                <div class="guia-section-title">
                    <span class="guia-icon">⚠️</span>
                    <h3>8. Limitações e Avisos</h3>
                </div>
                <div class="guia-content">
                    <ul>
                        <li><strong>Probabilidade ≠ Certeza:</strong> 80% significa que 2 em cada 10 vão errar</li>
                        <li><strong>Dados limitados:</strong> Árbitros novos ou competições desconhecidas têm mais incerteza</li>
                        <li><strong>Variância natural:</strong> Mesmo com bons dados, futebol é imprevisível</li>
                        <li><strong>Uso educacional:</strong> Este sistema é para análise estatística, não para apostas</li>
                    </ul>
                </div>
            </div>
            
            <div class="guia-footer">
                <p>💡 <strong>Dica:</strong> Quanto mais validações você fizer, mais preciso o sistema fica!</p>
            </div>
        </div>
    '''


def gerar_css_guia() -> str:
    """Gera CSS para o guia de metodologia."""
    
    return '''
        /* Guia de Metodologia */
        .guia-metodologia {
            background: linear-gradient(135deg, #16213e 0%, #1a1a2e 100%);
            border-radius: 15px;
            padding: 30px;
            margin-top: 40px;
            border: 1px solid #0f3460;
        }
        
        .guia-header {
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid #e94560;
        }
        
        .guia-header h2 {
            color: #e94560;
            font-size: 1.8em;
            margin-bottom: 10px;
        }
        
        .guia-header p {
            color: #a0a0a0;
        }
        
        .guia-section {
            background: rgba(15, 52, 96, 0.3);
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            border-left: 4px solid #3498db;
        }
        
        .guia-section-title {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 15px;
        }
        
        .guia-section-title h3 {
            color: #3498db;
            font-size: 1.2em;
            margin: 0;
        }
        
        .guia-icon {
            font-size: 1.5em;
        }
        
        .guia-content {
            color: #e0e0e0;
            line-height: 1.7;
        }
        
        .guia-content ul {
            margin: 10px 0;
            padding-left: 25px;
        }
        
        .guia-content li {
            margin: 8px 0;
        }
        
        .guia-formula {
            background: #1a1a2e;
            border: 1px solid #3498db;
            border-radius: 8px;
            padding: 15px;
            margin: 15px 0;
            font-family: 'Courier New', monospace;
            text-align: center;
            color: #f1c40f;
        }
        
        .guia-example {
            background: rgba(46, 204, 113, 0.1);
            border: 1px solid #2ecc71;
            border-radius: 8px;
            padding: 15px;
            margin: 15px 0;
        }
        
        .guia-table {
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
        }
        
        .guia-table th {
            background: #0f3460;
            color: #e0e0e0;
            padding: 12px;
            text-align: left;
        }
        
        .guia-table td {
            padding: 10px 12px;
            border-bottom: 1px solid #0f3460;
        }
        
        .guia-table tr:hover {
            background: rgba(15, 52, 96, 0.3);
        }
        
        .guia-footer {
            text-align: center;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #0f3460;
            color: #a0a0a0;
        }
        
        @media (max-width: 768px) {
            .guia-metodologia {
                padding: 15px;
            }
            
            .guia-section {
                padding: 15px;
            }
            
            .guia-table {
                font-size: 0.85em;
            }
        }
    '''


# =============================================================================
# TESTE
# =============================================================================

if __name__ == "__main__":
    print("Sistema de Aprendizado Avançado - RefStats V2.0")
    print("=" * 50)
    
    # Teste de criação de dados
    partida = criar_dados_partida_aprendizado(
        data="01/12/2025",
        time_mandante="Flamengo",
        time_visitante="Palmeiras",
        competicao="Brasileirão Série A",
        lambda_shrunk=5.8,
        qualidade_score=75,
        media_arbitro_5j=6.2,
        media_arbitro_10j=5.5,
        intervalo_p10=2,
        intervalo_p90=9,
        perfil_arbitro="Rigoroso",
        modelo="Negative Binomial"
    )
    
    print(f"\nPartida: {partida.time_mandante} vs {partida.time_visitante}")
    print(f"  λ = {partida.lambda_shrunk} → Faixa: {partida.faixa_lambda}")
    print(f"  Competição: {partida.competicao} → {partida.tipo_competicao}, {partida.regiao_competicao}")
    print(f"  Qualidade: {partida.qualidade_score} → {partida.faixa_qualidade}")
    print(f"  Tendência: {partida.tendencia_recente}")
    print(f"  Variância: {partida.variancia}")
