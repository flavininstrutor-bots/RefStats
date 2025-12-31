#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                    TRADUTOR DE HTML - PORTUGUÊS → INGLÊS                       ║
║                              RefStats V2.0                                     ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║  Traduz os arquivos de Probabilidade e Relatório para inglês                  ║
║                                                                               ║
║  Entrada:                                                                     ║
║    - Probabilidade/*.html (PROBABILIDADE_*.html)                              ║
║    - Probabilidade/Relatorio/*.html (RELATORIO_*.html)                        ║
║                                                                               ║
║  Saída:                                                                       ║
║    - ENG/Probability/*.html (PROBABILITY_*.html)                              ║
║    - ENG/Probability/Report/*.html (REPORT_*.html)                            ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import re
import glob
from datetime import datetime

# =============================================================================
# DICIONÁRIO DE TRADUÇÃO
# =============================================================================

TRADUCOES = {
    # =========================================================================
    # TABELA DE CÁLCULO DO LAMBDA
    # =========================================================================
    'Construção do Lambda (λ) — MODELO ADITIVO + SHRINKAGE': 
        'Lambda (λ) Construction — ADDITIVE MODEL + SHRINKAGE',
    'Construção do Lambda': 'Lambda Construction',
    'MODELO ADITIVO': 'ADDITIVE MODEL',
    'Lambda Base da Liga': 'League Base Lambda',
    '1️⃣ Lambda Base da Liga': '1️⃣ League Base Lambda',
    '2️⃣ Ajuste do Árbitro': '2️⃣ Referee Adjustment',
    '3️⃣ Ajuste dos Times': '3️⃣ Teams Adjustment',
    '4️⃣ Ajuste de Recência': '4️⃣ Recency Adjustment',
    '5️⃣ Lambda Raw': '5️⃣ Raw Lambda',
    'Ajuste do Árbitro (Δ_arbitro)': 'Referee Adjustment (Δ_referee)',
    'Ajuste dos Times (Δ_times)': 'Teams Adjustment (Δ_teams)',
    'Ajuste de Recência (CAPADO ±5%)': 'Recency Adjustment (CAPPED ±5%)',
    'Lambda Raw (Soma Aditiva)': 'Raw Lambda (Additive Sum)',
    'Soma Aditiva': 'Additive Sum',
    'CAPADO': 'CAPPED',
    
    # Variáveis de cálculo
    'média_ponderada': 'weighted_avg',
    'soma_cartões': 'cards_sum',
    'ajuste_recencia': 'recency_adj',
    'F_capado': 'F_capped',
    'Δ_arbitro': 'Δ_referee',
    'Δ_times': 'Δ_teams',
    'variância': 'variance',
    'Variância': 'Variance',
    'frequência': 'frequency',
    'Frequência': 'Frequency',
    'recência': 'recency',
    'Fairização': 'Regularization',
    
    # =========================================================================
    # TABELA DE INTERPRETAÇÃO ESTATÍSTICA
    # =========================================================================
    'Interpretação Estatística': 'Statistical Interpretation',
    'Interpretation Estatística': 'Statistical Interpretation',
    'Com base no': 'Based on the',
    'modelo aditivo + shrinkage bayesiano': 'additive model + Bayesian shrinkage',
    'a expectativa final é de': 'the final expectation is',
    'A distribuição indica': 'The distribution indicates',
    'probabilidade moderada': 'moderate probability',
    'probabilidade alta': 'high probability',
    'probabilidade baixa': 'low probability',
    'de atingir ou superar': 'of reaching or exceeding',
    'Considerando a variância': 'Considering the variance',
    'os resultados podem variar entre': 'results may vary between',
    'com 80% de confiança': 'with 80% confidence',
    
    # =========================================================================
    # TÍTULOS E CABEÇALHOS
    # =========================================================================
    'Análise Probabilística V2.0': 'Probabilistic Analysis V2.0',
    'Análise Probabilística de Cartões': 'Card Probabilistic Analysis',
    'RefStats - Análise Probabilística': 'RefStats - Probabilistic Analysis',
    'RefStats - Relatório de Validação V2.0': 'RefStats - Validation Report V2.0',
    'Relatório de Validação V2.0': 'Validation Report V2.0',
    'JOGOS DO DIA': 'MATCHES OF THE DAY',
    'HISTÓRICO': 'HISTORY',
    'INÍCIO': 'HOME',
    'Guia de Metodologia': 'Methodology Guide',
    
    # =========================================================================
    # SEÇÕES DO CÁLCULO
    # =========================================================================
    'Cálculo do Lambda': 'Lambda Calculation',
    'Cálculo Detalhado do λ': 'Detailed λ Calculation',
    'Lambda Base da Liga': 'League Base Lambda',
    'Ajuste do Árbitro': 'Referee Adjustment',
    'Ajuste dos Times': 'Teams Adjustment',
    'Ajuste de Recência': 'Recency Adjustment',
    'Lambda Raw': 'Raw Lambda',
    'Lambda Final': 'Final Lambda',
    'Soma Aditiva': 'Additive Sum',
    
    # =========================================================================
    # SHRINKAGE BAYESIANO
    # =========================================================================
    'Shrinkage Bayesiano': 'Bayesian Shrinkage',
    'Regulariza estimativas com dados limitados': 'Regularizes estimates with limited data',
    'Peso (w)': 'Weight (w)',
    'λ Raw': 'λ Raw',
    'λ Shrunk (Final)': 'λ Shrunk (Final)',
    'Alta confiança nos dados': 'High confidence in data',
    'Confiança moderada nos dados': 'Moderate confidence in data',
    'Dados do árbitro incompletos': 'Incomplete referee data',
    'Dados dos times incompletos': 'Incomplete teams data',
    'Poucos jogos do árbitro': 'Few referee matches',
    'Qualidade baixa': 'Low quality',
    
    # =========================================================================
    # QUALIDADE DOS DADOS
    # =========================================================================
    'Qualidade dos Dados': 'Data Quality',
    'de 100 pontos': 'out of 100 points',
    'Completude Árbitro': 'Referee Completeness',
    'Completude Times': 'Teams Completeness',
    'Amostra Árbitro': 'Referee Sample',
    'Amostra Times': 'Teams Sample',
    'Recência': 'Recency',
    'Competição Mapeada': 'Mapped Competition',
    'Dados de recência disponíveis': 'Recency data available',
    'Dados de recência limitados': 'Limited recency data',
    'Amostra pequena do árbitro': 'Small referee sample',
    'Amostra muito pequena do árbitro': 'Very small referee sample',
    'Amostra pequena dos times': 'Small teams sample',
    'Competição não mapeada': 'Unmapped competition',
    
    # =========================================================================
    # MODELO ESTATÍSTICO
    # =========================================================================
    'Modelo: Negative Binomial': 'Model: Negative Binomial',
    'Modelo: Poisson': 'Model: Poisson',
    'Por que Negative Binomial?': 'Why Negative Binomial?',
    'Poisson assume variância = média, mas cartões frequentemente têm var > média': 
        'Poisson assumes variance = mean, but cards often have var > mean',
    'Negative Binomial captura melhor a sobredispersão de cartões':
        'Negative Binomial better captures card overdispersion',
    'Melhora previsões nas caudas': 'Improves predictions in the tails',
    'captura a sobredispersão': 'captures the overdispersion',
    'O parâmetro r=': 'Parameter r=',
    
    # =========================================================================
    # INTERVALO DE CONFIANÇA
    # =========================================================================
    'Faixa Provável de Cartões': 'Probable Card Range',
    'Intervalo de Confiança': 'Confidence Interval',
    'Mediana': 'Median',
    'dos jogos com perfil semelhante têm entre': 'of matches with similar profile have between',
    'cartões': 'cards',
    'Alta variância detectada': 'High variance detected',
    'Mercados extremos': 'Extreme markets',
    'não serão destacados': 'will not be highlighted',
    'Mostra a faixa onde 80% dos resultados devem cair': 
        'Shows the range where 80% of results should fall',
    
    # =========================================================================
    # PROBABILIDADES E MERCADOS
    # =========================================================================
    'Probabilidades': 'Probabilities',
    'Raw → Calibrado': 'Raw → Calibrated',
    'Over 2.5 Cartões': 'Over 2.5 Cards',
    'Over 3.5 Cartões': 'Over 3.5 Cards',
    'Over 4.5 Cartões': 'Over 4.5 Cards',
    'Over 5.5 Cartões': 'Over 5.5 Cards',
    'Under 2.5 Cartões': 'Under 2.5 Cards',
    'Under 3.5 Cartões': 'Under 3.5 Cards',
    'Under 4.5 Cartões': 'Under 4.5 Cards',
    'Under 5.5 Cartões': 'Under 5.5 Cards',
    'ou mais cartões': 'or more cards',
    'ou menos cartões': 'or fewer cards',
    '≥': '≥',
    '≤': '≤',
    
    # =========================================================================
    # DESTAQUE E BLOQUEIO
    # =========================================================================
    'Destaque': 'Highlight',
    'Destaques': 'Highlights',
    'Destaques:': 'Highlights:',
    'Bloqueado': 'Blocked',
    'Bloqueado: variância': 'Blocked: variance',
    'Bloqueado: qualidade': 'Blocked: quality',
    'BLOQUEADO': 'BLOCKED',
    'bloqueado': 'blocked',
    
    # =========================================================================
    # TENDÊNCIAS
    # =========================================================================
    'ELEVADA': 'HIGH',
    'MODERADA': 'MODERATE',
    'BAIXA': 'LOW',
    'Tendência': 'Trend',
    'Tendência recente': 'Recent trend',
    
    # =========================================================================
    # INTERPRETAÇÃO
    # =========================================================================
    'Interpretação': 'Interpretation',
    'O que isso significa?': 'What does this mean?',
    'cartões esperados': 'expected cards',
    'Previsão': 'Prediction',
    'Análise': 'Analysis',
    
    # =========================================================================
    # REGRAS DE OURO
    # =========================================================================
    'Regras de Ouro Descobertas': 'Golden Rules Discovered',
    'Regras de Ouro Ativadas': 'Golden Rules Activated',
    'Regra de Ouro': 'Golden Rule',
    'Esta partida ativa padrões com alta taxa histórica de acerto':
        'This match activates patterns with high historical accuracy',
    'Diamante': 'Diamond',
    'Platina': 'Platinum',
    'Ouro': 'Gold',
    'DIAMANTE': 'DIAMOND',
    'PLATINA': 'PLATINUM',
    'OURO': 'GOLD',
    'acertos': 'hits',
    'Condições': 'Conditions',
    'Taxa': 'Rate',
    'Amostras': 'Samples',
    'Nível': 'Level',
    'Mínimo de Amostras': 'Minimum Samples',
    
    # =========================================================================
    # GUIA DE METODOLOGIA
    # =========================================================================
    'Entenda como as probabilidades são calculadas e como o sistema aprende com os dados.':
        'Understand how probabilities are calculated and how the system learns from data.',
    'Modelo Probabilístico': 'Probabilistic Model',
    'O sistema usa a distribuição': 'The system uses the distribution',
    'para modelar a contagem de cartões': 'to model card count',
    'Cálculo do Lambda (λ)': 'Lambda (λ) Calculation',
    'O λ (expectativa de cartões) é calculado somando contribuições':
        'λ (card expectation) is calculated by adding contributions',
    'Componente': 'Component',
    'O que representa': 'What it represents',
    'Média da liga': 'League average',
    'Média histórica de cartões da competição': 'Historical card average of the competition',
    'Influência do árbitro': 'Referee influence',
    'Perfil dos times': 'Teams profile',
    'Tendência recente': 'Recent trend',
    'Regularização Bayesiana': 'Bayesian Regularization',
    'Quando os dados são limitados, o sistema "puxa" a estimativa para a média da liga':
        'When data is limited, the system "pulls" the estimate towards the league average',
    'Fórmula': 'Formula',
    'Onde': 'Where',
    'varia de 0 a 1 baseado na': 'ranges from 0 to 1 based on',
    'Qualidade dos dados (completude)': 'Data quality (completeness)',
    'Número de jogos do árbitro': 'Number of referee matches',
    'Calibração': 'Calibration',
    'O sistema ajusta as probabilidades baseado no histórico de acertos':
        'The system adjusts probabilities based on accuracy history',
    'O que o modelo diz': 'What the model says',
    'Na realidade': 'In reality',
    'O que acontece na prática': 'What happens in practice',
    'Acerta 55% das vezes': 'Hits 55% of the time',
    'Ajusta para 55%': 'Adjusts to 55%',
    'Acerta 78% das vezes': 'Hits 78% of the time',
    'Ajusta para 78%': 'Adjusts to 78%',
    'Intervalo de Confiança': 'Confidence Interval',
    'P10-P90': 'P10-P90',
    'Sistema de Aprendizado': 'Learning System',
    'O sistema analisa o histórico e descobre': 'The system analyzes history and discovers',
    'padrões': 'patterns',
    'Regra': 'Rule',
    'Exemplo de Regra Descoberta': 'Example of Discovered Rule',
    'Quanto mais você validar partidas, mais regras o sistema descobre':
        'The more matches you validate, the more rules the system discovers',
    'Métricas de Avaliação': 'Evaluation Metrics',
    'Métrica': 'Metric',
    'O que mede': 'What it measures',
    'Bom valor': 'Good value',
    'Brier Score': 'Brier Score',
    'Calibração geral (erro quadrático)': 'Overall calibration (squared error)',
    'Log Loss': 'Log Loss',
    'Discriminação (penaliza muito erros confiantes)': 'Discrimination (heavily penalizes confident errors)',
    'Curva de Confiabilidade': 'Reliability Curve',
    'Se 60% previsto = 60% real': 'If 60% predicted = 60% actual',
    'Limitações e Avisos': 'Limitations and Warnings',
    'Probabilidade ≠ Certeza': 'Probability ≠ Certainty',
    '80% significa que 2 em cada 10 vão errar': '80% means 2 out of 10 will be wrong',
    'Dados limitados': 'Limited data',
    'Árbitros novos ou competições desconhecidas têm mais incerteza':
        'New referees or unknown competitions have more uncertainty',
    'Variância natural': 'Natural variance',
    'Mesmo com bons dados, futebol é imprevisível': 'Even with good data, football is unpredictable',
    'Uso educacional': 'Educational use',
    'Este sistema é para análise estatística, não para apostas':
        'This system is for statistical analysis, not for betting',
    'Dica': 'Tip',
    'Quanto mais validações você fizer, mais preciso o sistema fica':
        'The more validations you do, the more accurate the system becomes',
    
    # =========================================================================
    # RELATÓRIO DE VALIDAÇÃO
    # =========================================================================
    'Resumo da Validação': 'Validation Summary',
    'Total de Partidas': 'Total Matches',
    'Partidas Validadas': 'Validated Matches',
    'Taxa de Acerto': 'Accuracy Rate',
    'Taxa de Acerto (Destaques)': 'Accuracy Rate (Highlights)',
    'Previsões em Destaque': 'Highlighted Predictions',
    'Acertos': 'Hits',
    'Erros': 'Errors',
    'Brier': 'Brier',
    'Esperado': 'Expected',
    'Real': 'Actual',
    'Partida': 'Match',
    'Mercado': 'Market',
    'Placar': 'Score',
    'Cart.': 'Cards',
    'Interv.': 'Range',
    'Comp.': 'Comp.',
    'Bloq.': 'Block.',
    'Faixa': 'Range',
    'Resultado': 'Result',
    'Status': 'Status',
    'encontrado': 'found',
    'não encontrado': 'not found',
    'Excelente': 'Excellent',
    'Bom': 'Good',
    'Regular': 'Fair',
    'Ruim': 'Poor',
    'St': 'St',
    'N': 'N',
    'Total': 'Total',
    'Gerado em': 'Generated on',
    
    # =========================================================================
    # RODAPÉ E LINKS
    # =========================================================================
    'Termos': 'Terms',
    'Privacidade': 'Privacy',
    'Aviso Legal': 'Legal Notice',
    'Modelo: Negative Binomial + Shrinkage Bayesiano + Calibração Isotônica':
        'Model: Negative Binomial + Bayesian Shrinkage + Isotonic Calibration',
    'Probabilidades representam frequência esperada no longo prazo':
        'Probabilities represent expected long-term frequency',
    'Erros individuais são parte natural de modelos probabilísticos':
        'Individual errors are a natural part of probabilistic models',
    'Conteúdo informativo e educacional. Não constitui conselho de apostas.':
        'Informative and educational content. Does not constitute betting advice.',
    
    # =========================================================================
    # FATORES DE ANÁLISE (para regras)
    # =========================================================================
    'Tipo=Liga': 'Type=League',
    'Tipo=Copa': 'Type=Cup',
    'Região=Brasil': 'Region=Brazil',
    'Região=Europa': 'Region=Europe',
    'Região=América': 'Region=America',
    'Região=Outro': 'Region=Other',
    'Qualidade=Baixa': 'Quality=Low',
    'Qualidade=Média': 'Quality=Medium',
    'Qualidade=Alta': 'Quality=High',
    'Árbitro=Rigoroso': 'Referee=Strict',
    'Árbitro=Médio': 'Referee=Medium',
    'Árbitro=Permissivo': 'Referee=Lenient',
    'Tendência=Subindo': 'Trend=Rising',
    'Tendência=Estável': 'Trend=Stable',
    'Tendência=Descendo': 'Trend=Falling',
    'faixa_delta_arbitro=': 'referee_delta_range=',
    'faixa_delta_times=': 'teams_delta_range=',
    'faixa_peso_shrinkage=': 'shrinkage_weight_range=',
    'faixa_media_arb_5j=': 'referee_5m_avg_range=',
    'faixa_amplitude=': 'amplitude_range=',
    'faixa_soma_times=': 'teams_sum_range=',
    'Negativo': 'Negative',
    'Neutro': 'Neutral',
    'Positivo': 'Positive',
    'Muito Positivo': 'Very Positive',
    'Baixo': 'Low',
    'Médio': 'Medium',
    'Alto': 'High',
    'Baixa': 'Low',
    'Média': 'Medium',
    'Alta': 'High',
    'Muito Alta': 'Very High',
    'Estreita': 'Narrow',
    'Larga': 'Wide',
    
    # =========================================================================
    # OUTROS TERMOS
    # =========================================================================
    'Nota': 'Note',
    'Motivo': 'Reason',
    'Exemplo': 'Example',
    'Como é calculado': 'How it is calculated',
    'Mínimo necessário': 'Minimum required',
    'vs': 'vs',
    'Liga': 'League',
    'Copa': 'Cup',
    'Quando uma partida ativar uma Regra de Ouro': 'When a match activates a Golden Rule',
    'ela terá um indicador especial no relatório de probabilidades':
        'it will have a special indicator in the probability report',
    'Rules de Gold': 'Golden Rules',
    'Sistema de Aprendizado - Regras de Ouro': 'Learning System - Golden Rules',
    
    # =========================================================================
    # MESES (para datas)
    # =========================================================================
    'janeiro': 'January',
    'fevereiro': 'February',
    'março': 'March',
    'abril': 'April',
    'maio': 'May',
    'junho': 'June',
    'julho': 'July',
    'agosto': 'August',
    'setembro': 'September',
    'outubro': 'October',
    'novembro': 'November',
    'dezembro': 'December',
}

# Traduções de atributos HTML (lang, title, etc.)
TRADUCOES_ATTR = {
    'lang="pt-BR"': 'lang="en"',
    'lang="pt"': 'lang="en"',
}


def traduzir_html(conteudo: str) -> str:
    """Traduz o conteúdo HTML de português para inglês."""
    
    resultado = conteudo
    
    # 1. Traduz atributos HTML
    for pt, en in TRADUCOES_ATTR.items():
        resultado = resultado.replace(pt, en)
    
    # 2. Traduz textos (ordem por tamanho decrescente para evitar substituições parciais)
    traducoes_ordenadas = sorted(TRADUCOES.items(), key=lambda x: len(x[0]), reverse=True)
    
    for pt, en in traducoes_ordenadas:
        resultado = resultado.replace(pt, en)
    
    # 3. Traduz padrões específicos com regex
    
    # "X cartões" → "X cards"
    resultado = re.sub(r'(\d+)\s*cartões', r'\1 cards', resultado)
    resultado = re.sub(r'(\d+)\s*cartão', r'\1 card', resultado)
    
    # "≥ X cartões" → "≥ X cards"
    resultado = re.sub(r'≥\s*(\d+)\s*cartões', r'≥ \1 cards', resultado)
    resultado = re.sub(r'≤\s*(\d+)\s*cartões', r'≤ \1 cards', resultado)
    
    # Renomeia arquivo no título
    resultado = resultado.replace('PROBABILIDADE_', 'PROBABILITY_')
    resultado = resultado.replace('RELATORIO_', 'REPORT_')
    resultado = resultado.replace('Probabilidade_', 'Probability_')
    resultado = resultado.replace('Relatorio_', 'Report_')
    
    return resultado


def traduzir_arquivo(caminho_entrada: str, caminho_saida: str) -> bool:
    """Traduz um arquivo HTML e salva no destino."""
    
    try:
        # Lê o arquivo
        with open(caminho_entrada, 'r', encoding='utf-8') as f:
            conteudo = f.read()
        
        # Traduz
        conteudo_traduzido = traduzir_html(conteudo)
        
        # Cria pasta de destino se não existir
        pasta_saida = os.path.dirname(caminho_saida)
        if pasta_saida:
            os.makedirs(pasta_saida, exist_ok=True)
        
        # Salva
        with open(caminho_saida, 'w', encoding='utf-8') as f:
            f.write(conteudo_traduzido)
        
        return True
        
    except Exception as e:
        print(f"   ❌ Erro ao traduzir {caminho_entrada}: {e}")
        return False


def processar_pasta(pasta_base: str = None):
    """Processa todos os arquivos HTML da pasta."""
    
    if pasta_base is None:
        pasta_base = os.path.dirname(os.path.abspath(__file__))
    
    # Define pastas
    pasta_probabilidade = os.path.join(pasta_base, "Probabilidade")
    pasta_relatorio = os.path.join(pasta_probabilidade, "Relatorio")
    
    pasta_saida_prob = os.path.join(pasta_base, "ENG", "Probability")
    pasta_saida_report = os.path.join(pasta_saida_prob, "Report")
    
    # Cria pastas de saída
    os.makedirs(pasta_saida_prob, exist_ok=True)
    os.makedirs(pasta_saida_report, exist_ok=True)
    
    print("""
╔═══════════════════════════════════════════════════════════════╗
║           TRADUTOR HTML - PORTUGUÊS → INGLÊS                  ║
║                      RefStats V2.0                            ║
╚═══════════════════════════════════════════════════════════════╝
    """)
    
    print(f"📁 Pasta base: {pasta_base}")
    print(f"📁 Saída Probabilidade: {pasta_saida_prob}")
    print(f"📁 Saída Relatórios: {pasta_saida_report}")
    
    # Processa arquivos de probabilidade
    print("\n" + "="*60)
    print("📊 Traduzindo arquivos de PROBABILIDADE...")
    print("="*60)
    
    arquivos_prob = glob.glob(os.path.join(pasta_probabilidade, "PROBABILIDADE_*.html"))
    
    if arquivos_prob:
        for arquivo in sorted(arquivos_prob):
            nome = os.path.basename(arquivo)
            nome_en = nome.replace("PROBABILIDADE_", "PROBABILITY_")
            saida = os.path.join(pasta_saida_prob, nome_en)
            
            print(f"\n   📄 {nome}")
            if traduzir_arquivo(arquivo, saida):
                print(f"   ✅ → {nome_en}")
    else:
        print("   ⚠️ Nenhum arquivo PROBABILIDADE_*.html encontrado")
    
    # Processa arquivos de relatório
    print("\n" + "="*60)
    print("📋 Traduzindo arquivos de RELATÓRIO...")
    print("="*60)
    
    arquivos_rel = glob.glob(os.path.join(pasta_relatorio, "RELATORIO_*.html"))
    
    # Também verifica na pasta Probabilidade diretamente
    arquivos_rel += glob.glob(os.path.join(pasta_probabilidade, "RELATORIO_*.html"))
    
    if arquivos_rel:
        for arquivo in sorted(set(arquivos_rel)):
            nome = os.path.basename(arquivo)
            nome_en = nome.replace("RELATORIO_", "REPORT_")
            saida = os.path.join(pasta_saida_report, nome_en)
            
            print(f"\n   📄 {nome}")
            if traduzir_arquivo(arquivo, saida):
                print(f"   ✅ → {nome_en}")
    else:
        print("   ⚠️ Nenhum arquivo RELATORIO_*.html encontrado")
    
    # Resumo
    print(f"""
╔═══════════════════════════════════════════════════════════════╗
║                    TRADUÇÃO CONCLUÍDA!                        ║
╠═══════════════════════════════════════════════════════════════╣
║  📊 Probabilidades: ENG/Probability/                          ║
║  📋 Relatórios: ENG/Probability/Report/                       ║
╚═══════════════════════════════════════════════════════════════╝
    """)


def traduzir_arquivo_unico(caminho: str, pasta_saida: str = None) -> str:
    """Traduz um único arquivo e retorna o caminho de saída."""
    
    nome = os.path.basename(caminho)
    
    # Determina tipo e pasta de saída
    if "PROBABILIDADE" in nome.upper() or "PROBABILITY" in nome.upper():
        nome_en = nome.replace("PROBABILIDADE_", "PROBABILITY_")
        if pasta_saida is None:
            pasta_saida = os.path.join(os.path.dirname(caminho), "..", "ENG", "Probability")
    elif "RELATORIO" in nome.upper() or "REPORT" in nome.upper():
        nome_en = nome.replace("RELATORIO_", "REPORT_")
        if pasta_saida is None:
            pasta_saida = os.path.join(os.path.dirname(caminho), "..", "ENG", "Probability", "Report")
    else:
        nome_en = nome
        if pasta_saida is None:
            pasta_saida = os.path.join(os.path.dirname(caminho), "ENG")
    
    # Cria pasta
    os.makedirs(pasta_saida, exist_ok=True)
    
    # Traduz
    caminho_saida = os.path.join(pasta_saida, nome_en)
    
    if traduzir_arquivo(caminho, caminho_saida):
        print(f"✅ Traduzido: {nome} → {nome_en}")
        return caminho_saida
    else:
        return None


def main():
    """Função principal."""
    import sys
    
    if len(sys.argv) > 1:
        # Modo: traduzir arquivo específico
        for arquivo in sys.argv[1:]:
            if os.path.isfile(arquivo):
                traduzir_arquivo_unico(arquivo)
            elif os.path.isdir(arquivo):
                processar_pasta(arquivo)
            else:
                print(f"⚠️ Arquivo não encontrado: {arquivo}")
    else:
        # Modo: processar pasta atual
        processar_pasta()


if __name__ == "__main__":
    main()
