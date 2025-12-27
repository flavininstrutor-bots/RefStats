#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RefStats - Tradutor de Jogos do Dia para Inglês
================================================
Este script traduz:
1. JOGOS_DO_DIA.html → ENG/Match_TODAY.html
2. Historico/JOGOS_DO_DIA_*.html → ENG/History/JOGOS_DO_DIA_*.html

Arquivos já traduzidos são ignorados (verifica se já existe no destino).
"""

import os
import re
import glob
from datetime import datetime

# ========================================
# CONFIGURAÇÃO
# ========================================

# Diretório raiz do site (onde está o index.html)
DIRETORIO_RAIZ = os.path.dirname(os.path.abspath(__file__))

# Caminhos
ARQUIVO_JOGOS_DO_DIA = os.path.join(DIRETORIO_RAIZ, "JOGOS_DO_DIA.html")
PASTA_HISTORICO = os.path.join(DIRETORIO_RAIZ, "Historico")
PASTA_ENG = os.path.join(DIRETORIO_RAIZ, "ENG")
PASTA_ENG_HISTORY = os.path.join(PASTA_ENG, "History")

# ========================================
# DICIONÁRIO DE TRADUÇÕES
# ========================================

TRADUCOES = {
    # === HTML Lang ===
    'lang="pt-BR"': 'lang="en"',
    
    # === Título da página ===
    '<title>RefStats - Jogos do Dia': '<title>RefStats - Today\'s Matches',
    
    # === Navbar ===
    '>INÍCIO</a>': '>HOME</a>',
    '>JOGOS DO DIA</a>': '>TODAY\'S MATCHES</a>',
    '>HISTÓRICO</a>': '>HISTORY</a>',
    '>CONTATO</a>': '>CONTACT</a>',
    
    # === Links de navegação (corrigir caminhos para versão EN) ===
    'href="index.html"': 'href="../index.html"',
    'href="JOGOS_DO_DIA.html"': 'href="Match_TODAY.html"',
    'href="refstats_historico.html"': 'href="../refstats_historico.html"',
    'href="refstats_contato.html"': 'href="../refstats_contato.html"',
    'href="refstats_termos.html"': 'href="../refstats_termos.html"',
    'href="refstats_privacidade.html"': 'href="../refstats_privacidade.html"',
    'href="refstats_aviso_legal.html"': 'href="../refstats_aviso_legal.html"',
    'href="refstats_faq.html"': 'href="../refstats_faq.html"',
    
    # === Header ===
    '<h1>⚽ Jogos do Dia</h1>': '<h1>⚽ Today\'s Matches</h1>',
    'partida(s) analisada(s)': 'match(es) analyzed',
    
    # === Barra de pesquisa ===
    'placeholder="Pesquisar na página..."': 'placeholder="Search on page..."',
    'title="Anterior (↑)"': 'title="Previous (↑)"',
    'title="Próximo (↓)"': 'title="Next (↓)"',
    'title="Fechar (Esc)"': 'title="Close (Esc)"',
    'title="Pesquisar (Ctrl+F)"': 'title="Search (Ctrl+F)"',
    '>Perfil:</span>': '>Profile:</span>',
    'title="Mostrar árbitros rigorosos"': 'title="Show strict referees"',
    'title="Mostrar árbitros médios"': 'title="Show average referees"',
    'title="Mostrar árbitros permissivos"': 'title="Show lenient referees"',
    'title="Limpar filtro"': 'title="Clear filter"',
    
    # === Filtros de perfil ===
    '>🔴 Rigoroso</button>': '>🔴 Strict</button>',
    '>🟡 Médio</button>': '>🟡 Average</button>',
    '>🟢 Permissivo</button>': '>🟢 Lenient</button>',
    
    # === Dica de atalho ===
    'Pressione <kbd>Ctrl</kbd> + <kbd>F</kbd> para pesquisar': 'Press <kbd>Ctrl</kbd> + <kbd>F</kbd> to search',
    
    # === Info bar do jogo ===
    '>🏆 Competição:</span>': '>🏆 Competition:</span>',
    '>🏟️ Estádio:</span>': '>🏟️ Stadium:</span>',
    '>📍 Local:</span>': '>📍 Location:</span>',
    '>📋 Fase:</span>': '>📋 Stage:</span>',
    'Rodada': 'Round',
    
    # === Seções ===
    '>⚖️ Árbitro</div>': '>⚖️ Referee</div>',
    
    # === Badges ===
    '>Liga</span>': '>League</span>',
    '>FIFA</span>': '>FIFA</span>',
    
    # === Métricas do árbitro ===
    '📊 Média Amarelos (10j)': '📊 Yellow Avg (10g)',
    '📊 Média Amarelos (5j)': '📊 Yellow Avg (5g)',
    '📊 Média Amarelos 1T': '📊 Yellow Avg 1H',
    '📊 Média Amarelos 2T': '📊 Yellow Avg 2H',
    '📊 Média Faltas (10j)': '📊 Fouls Avg (10g)',
    '📊 Média Faltas (5j)': '📊 Fouls Avg (5g)',
    '📊 Média Faltas 1T': '📊 Fouls Avg 1H',
    '📊 Média Faltas 2T': '📊 Fouls Avg 2H',
    '📊 Média Vermelhos': '📊 Red Avg',
    
    # === Tooltips do árbitro ===
    'Média de cartões amarelos por jogo nos últimos 10 jogos apitados pelo árbitro (soma dos dois times).': 
        'Average yellow cards per game in the last 10 games refereed (sum of both teams).',
    'Média de cartões amarelos por jogo nos últimos 5 jogos apitados. Amostra menor, mas mais recente.': 
        'Average yellow cards per game in the last 5 games. Smaller but more recent sample.',
    'Média de cartões amarelos aplicados apenas no 1º tempo (primeiros 45 minutos).': 
        'Average yellow cards given only in 1st half (first 45 minutes).',
    'Média de cartões amarelos aplicados apenas no 2º tempo (após os 45 minutos).': 
        'Average yellow cards given only in 2nd half (after 45 minutes).',
    'Média total de faltas por jogo nos últimos 10 jogos (soma dos dois times).': 
        'Total average fouls per game in the last 10 games (sum of both teams).',
    'Média de faltas nos últimos 5 jogos. Amostra mais recente.': 
        'Average fouls in the last 5 games. More recent sample.',
    'Média de faltas cometidas no 1º tempo.': 
        'Average fouls committed in 1st half.',
    'Média de faltas cometidas no 2º tempo.': 
        'Average fouls committed in 2nd half.',
    'Média de cartões vermelhos por jogo nos últimos 10 jogos.': 
        'Average red cards per game in the last 10 games.',
    
    # === Perfil do árbitro ===
    '>📋 Perfil do Árbitro</span>': '>📋 Referee Profile</span>',
    'O perfil é calculado comparando a média de amarelos do árbitro com a média da competição (baseline). Rigoroso: +15% acima da média. Permissivo: -15% abaixo da média.':
        'The profile is calculated by comparing the referee\'s yellow average with the competition average (baseline). Strict: +15% above average. Lenient: -15% below average.',
    
    # === Badges de perfil ===
    '>🔴 Rigoroso</span>': '>🔴 Strict</span>',
    '>🟡 Médio</span>': '>🟡 Average</span>',
    '>🟢 Permissivo</span>': '>🟢 Lenient</span>',
    
    # === Descrições de perfil ===
    'Este árbitro está na média da competição em termos de cartões amarelos. Comportamento equilibrado.':
        'This referee is at the competition average in terms of yellow cards. Balanced behavior.',
    'Este árbitro está ACIMA da média da competição em cartões amarelos. Tende a ser mais rigoroso.':
        'This referee is ABOVE the competition average in yellow cards. Tends to be more strict.',
    'Este árbitro está ABAIXO da média da competição em cartões amarelos. Tende a ser mais permissivo.':
        'This referee is BELOW the competition average in yellow cards. Tends to be more lenient.',
    
    # === Baseline ===
    '📈 Baseline da Competição': '📈 Competition Baseline',
    'Valores médios históricos da competição. Usados como referência para classificar o perfil do árbitro.':
        'Historical average values of the competition. Used as reference to classify referee profile.',
    '>Média Amarelos:</span>': '>Yellow Avg:</span>',
    '>Média Faltas:</span>': '>Fouls Avg:</span>',
    
    # === Qualidade dos dados ===
    '📉 Qualidade dos Dados': '📉 Data Quality',
    'Percentual de jogos dos últimos 10 que possuem dados de faltas por tempo (1T/2T). Quanto maior, mais confiáveis as médias por tempo.':
        'Percentage of games from the last 10 that have fouls data per half (1H/2H). The higher, the more reliable the half averages.',
    '>Disponibilidade Faltas 1T/2T:</span>': '>Fouls Availability 1H/2H:</span>',
    
    # === Tendências ===
    '% jogos com ≥5 amarelos (10j)': '% games with ≥5 yellows (10g)',
    'Percentual de jogos onde o total de amarelos foi 5 ou mais. Útil para mercado de Over 4.5 cartões.':
        'Percentage of games where total yellows were 5 or more. Useful for Over 4.5 cards market.',
    '% jogos com ≥3 amarelos no 1T (10j)': '% games with ≥3 yellows in 1H (10g)',
    'Percentual de jogos onde foram aplicados 3+ amarelos no 1º tempo. Útil para mercado de cartões no 1T.':
        'Percentage of games where 3+ yellows were given in 1st half. Useful for 1H cards market.',
    
    # === Notícias ===
    '📰 Notícias recentes envolvendo': '📰 Recent news involving',
    '>Ler mais →</a>': '>Read more →</a>',
    
    # === Histórico do árbitro ===
    '📜 Histórico do Árbitro (Últimos 10 Jogos)': '📜 Referee History (Last 10 Games)',
    'Histórico detalhado dos últimos 10 jogos apitados. Inclui cartões, faltas e dados por tempo quando disponíveis.':
        'Detailed history of last 10 games refereed. Includes cards, fouls and per-half data when available.',
    
    # === Tabela de histórico ===
    '>Data</th>': '>Date</th>',
    '>Jogo</th>': '>Match</th>',
    '>Amarelos</th>': '>Yellows</th>',
    '>Vermelhos</th>': '>Reds</th>',
    '>Faltas</th>': '>Fouls</th>',
    '>1T</th>': '>1H</th>',
    '>2T</th>': '>2H</th>',
    
    # === Times ===
    '>🏠 Time da Casa': '>🏠 Home Team',
    '>✈️ Time Visitante': '>✈️ Away Team',
    
    # === Classificação ===
    '>📊 Classificação</div>': '>📊 Standings</div>',
    'Posição atual do time na tabela de classificação da competição.':
        'Current team position in the competition standings.',
    
    # === Próximos jogos ===
    '>📅 Próximos Jogos</h5>': '>📅 Upcoming Matches</h5>',
    
    # === Médias do time ===
    '>Média Amarelos/Jogo</span>': '>Yellow Avg/Game</span>',
    '>Média Faltas/Jogo</span>': '>Fouls Avg/Game</span>',
    
    # === Últimos jogos do time ===
    '>📋 Últimos Jogos</div>': '>📋 Last Matches</div>',
    'Últimos 5 jogos do time com estatísticas de cartões e faltas.':
        'Team\'s last 5 matches with cards and fouls statistics.',
    '>Adversário</th>': '>Opponent</th>',
    '>Local</th>': '>Venue</th>',
    '>Resultado</th>': '>Result</th>',
    '>Casa</td>': '>Home</td>',
    '>Fora</td>': '>Away</td>',
    
    # === Gráfico comparativo ===
    '>📊 Gráfico Comparativo de Amarelos</div>': '>📊 Yellow Cards Comparison Chart</div>',
    'Comparação visual da média de amarelos: árbitro vs times da partida.':
        'Visual comparison of yellow averages: referee vs match teams.',
    '>Árbitro</span>': '>Referee</span>',
    
    # === Doação ===
    '<h2>💖 Apoie o RefStats</h2>': '<h2>💖 Support RefStats</h2>',
    'O RefStats é gratuito e mantido com dedicação. Se você gosta do projeto, considere fazer uma doação!':
        'RefStats is free and maintained with dedication. If you like the project, consider making a donation!',
    '<h4>🔲 PIX (Brasil)</h4>': '<h4>🔲 PIX (Brazil)</h4>',
    '>Rápido, fácil e sem taxas</p>': '>Fast, easy and fee-free</p>',
    '>Para doações internacionais</p>': '>For international donations</p>',
    '>Doar via PayPal': '>Donate via PayPal',
    '<h4>💡 Por que doar?</h4>': '<h4>💡 Why donate?</h4>',
    'Suas doações ajudam a manter o servidor online, melhorar as funcionalidades e adicionar novas features. Qualquer valor é bem-vindo e nos motiva a continuar!':
        'Your donations help keep the server online, improve features and add new ones. Any amount is welcome and motivates us to continue!',
    
    # === Footer ===
    '<strong>⚽ RefStats - Jogos do Dia</strong>': '<strong>⚽ RefStats - Today\'s Matches</strong>',
    '>Termos de Uso</a>': '>Terms of Use</a>',
    '>Política de Privacidade</a>': '>Privacy Policy</a>',
    '>Aviso Legal</a>': '>Legal Disclaimer</a>',
    'Dados coletados de fontes confiáveis': 'Data collected from reliable sources',
    '💡 Use Ctrl+F ou clique em 🔍 para pesquisar e filtrar por perfil do árbitro':
        '💡 Use Ctrl+F or click 🔍 to search and filter by referee profile',
    '⚠️ Este site é apenas para fins informativos. Aposte com responsabilidade.':
        '⚠️ This site is for informational purposes only. Bet responsibly.',
    
    # === JavaScript - Alerts ===
    "alert('✅ Chave PIX copiada: '": "alert('✅ PIX key copied: '",
    
    # === Caminhos de assets ===
    '"./assets/': '"../assets/',
    "'./assets/": "'../assets/",
}

# Traduções com regex (para padrões dinâmicos)
TRADUCOES_REGEX = [
    # Posição na tabela: "1º lugar" → "1st place"
    (r'(\d+)º lugar', r'\1° place'),
    (r'(\d+)ª Rodada', r'\1th Round'),
    # Comentário do navbar
    (r'NAVBAR \(igual ao Home\)', 'NAVBAR (same as Home)'),
]


def traduzir_conteudo(conteudo: str) -> str:
    """Aplica todas as traduções ao conteúdo HTML."""
    
    # Primeiro aplica traduções literais
    for pt, en in TRADUCOES.items():
        conteudo = conteudo.replace(pt, en)
    
    # Depois aplica traduções com regex
    for pattern, replacement in TRADUCOES_REGEX:
        conteudo = re.sub(pattern, replacement, conteudo)
    
    return conteudo


def corrigir_caminhos_history(conteudo: str) -> str:
    """Corrige caminhos específicos para arquivos na pasta History."""
    # Para arquivos em ENG/History/, os assets estão em ../../assets/
    conteudo = conteudo.replace('"../assets/', '"../../assets/')
    conteudo = conteudo.replace("'../assets/", "'../../assets/")
    
    # Corrigir links de navegação para subir dois níveis
    conteudo = conteudo.replace('href="../index.html"', 'href="../../index.html"')
    conteudo = conteudo.replace('href="Match_TODAY.html"', 'href="../Match_TODAY.html"')
    conteudo = conteudo.replace('href="../refstats_historico.html"', 'href="../../refstats_historico.html"')
    conteudo = conteudo.replace('href="../refstats_contato.html"', 'href="../../refstats_contato.html"')
    conteudo = conteudo.replace('href="../refstats_termos.html"', 'href="../../refstats_termos.html"')
    conteudo = conteudo.replace('href="../refstats_privacidade.html"', 'href="../../refstats_privacidade.html"')
    conteudo = conteudo.replace('href="../refstats_aviso_legal.html"', 'href="../../refstats_aviso_legal.html"')
    conteudo = conteudo.replace('href="../refstats_faq.html"', 'href="../../refstats_faq.html"')
    
    return conteudo


def traduzir_arquivo(caminho_origem: str, caminho_destino: str, is_history: bool = False) -> bool:
    """
    Traduz um arquivo HTML do português para inglês.
    
    Args:
        caminho_origem: Caminho do arquivo PT-BR
        caminho_destino: Caminho para salvar a versão EN
        is_history: Se True, ajusta caminhos para pasta History
        
    Returns:
        True se traduziu, False se já existia
    """
    # Verifica se já existe
    if os.path.exists(caminho_destino):
        # Verifica se o arquivo de origem é mais novo
        if os.path.getmtime(caminho_origem) <= os.path.getmtime(caminho_destino):
            return False  # Já traduzido e atualizado
    
    # Lê o arquivo original
    with open(caminho_origem, 'r', encoding='utf-8') as f:
        conteudo = f.read()
    
    # Traduz
    conteudo_traduzido = traduzir_conteudo(conteudo)
    
    # Corrige caminhos se for arquivo de histórico
    if is_history:
        conteudo_traduzido = corrigir_caminhos_history(conteudo_traduzido)
    
    # Cria diretório de destino se não existir
    os.makedirs(os.path.dirname(caminho_destino), exist_ok=True)
    
    # Salva o arquivo traduzido
    with open(caminho_destino, 'w', encoding='utf-8') as f:
        f.write(conteudo_traduzido)
    
    return True


def main():
    """Função principal."""
    print("=" * 60)
    print("🌐 RefStats - Tradutor de Jogos para Inglês")
    print("=" * 60)
    print(f"📂 Diretório: {DIRETORIO_RAIZ}")
    print()
    
    traduzidos = 0
    ignorados = 0
    erros = 0
    
    # 1. Traduzir JOGOS_DO_DIA.html → ENG/Match_TODAY.html
    print("📄 Processando JOGOS_DO_DIA.html...")
    if os.path.exists(ARQUIVO_JOGOS_DO_DIA):
        destino = os.path.join(PASTA_ENG, "Match_TODAY.html")
        try:
            if traduzir_arquivo(ARQUIVO_JOGOS_DO_DIA, destino):
                print(f"   ✅ Traduzido → ENG/Match_TODAY.html")
                traduzidos += 1
            else:
                print(f"   ⏭️  Já existe (atualizado)")
                ignorados += 1
        except Exception as e:
            print(f"   ❌ Erro: {e}")
            erros += 1
    else:
        print(f"   ⚠️  Arquivo não encontrado!")
    
    print()
    
    # 2. Traduzir arquivos do histórico
    print("📁 Processando pasta Historico...")
    if os.path.exists(PASTA_HISTORICO):
        arquivos_historico = glob.glob(os.path.join(PASTA_HISTORICO, "JOGOS_DO_DIA_*.html"))
        
        if arquivos_historico:
            print(f"   📊 Encontrados {len(arquivos_historico)} arquivos")
            
            for arquivo in sorted(arquivos_historico):
                nome_arquivo = os.path.basename(arquivo)
                destino = os.path.join(PASTA_ENG_HISTORY, nome_arquivo)
                
                try:
                    if traduzir_arquivo(arquivo, destino, is_history=True):
                        print(f"   ✅ {nome_arquivo}")
                        traduzidos += 1
                    else:
                        print(f"   ⏭️  {nome_arquivo} (já traduzido)")
                        ignorados += 1
                except Exception as e:
                    print(f"   ❌ {nome_arquivo}: {e}")
                    erros += 1
        else:
            print("   ℹ️  Nenhum arquivo JOGOS_DO_DIA_*.html encontrado")
    else:
        print(f"   ⚠️  Pasta Historico não encontrada!")
    
    print()
    print("=" * 60)
    print("📊 RESUMO:")
    print(f"   ✅ Traduzidos: {traduzidos}")
    print(f"   ⏭️  Ignorados (já existem): {ignorados}")
    print(f"   ❌ Erros: {erros}")
    print("=" * 60)
    
    if traduzidos > 0:
        print()
        print("📁 Arquivos gerados em:")
        print(f"   • ENG/Match_TODAY.html")
        print(f"   • ENG/History/JOGOS_DO_DIA_*.html")


if __name__ == "__main__":
    main()
