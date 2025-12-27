"""
GERADOR DE DATAS DISPONÍVEIS - RefStats
========================================

Este script escaneia a pasta de histórico e gera um arquivo JavaScript
com todas as datas disponíveis para o calendário do site.

Execute este script sempre que adicionar novos arquivos de jogos.

Autor: RefStats
Data: 2025-12-24
"""

import os
import json
import re
from datetime import datetime

# Configuração - AJUSTE ESTE CAMINHO CONFORME NECESSÁRIO
PASTA_HISTORICO = r"C:\Users\PICHAU\Documents\GitHub\RefStats\Historico"

# Nome do arquivo JS de saída (será salvo na mesma pasta)
ARQUIVO_JS = "datas_disponiveis.js"


def extrair_data_do_arquivo(nome_arquivo):
    """
    Extrai a data do nome do arquivo JOGOS_DO_DIA_DDMMYYYY.html
    Retorna a data no formato DDMMYYYY ou None se não for válido
    """
    # Padrão: JOGOS_DO_DIA_DDMMYYYY.html
    padrao = r"JOGOS_DO_DIA_(\d{8})\.html"
    match = re.match(padrao, nome_arquivo, re.IGNORECASE)
    
    if match:
        data_str = match.group(1)
        # Valida se é uma data real
        try:
            dia = int(data_str[0:2])
            mes = int(data_str[2:4])
            ano = int(data_str[4:8])
            datetime(ano, mes, dia)  # Valida a data
            return data_str
        except ValueError:
            return None
    return None


def escanear_pasta_historico():
    """
    Escaneia a pasta de histórico e retorna lista de datas disponíveis
    """
    datas = []
    
    if not os.path.exists(PASTA_HISTORICO):
        print(f"❌ Pasta não encontrada: {PASTA_HISTORICO}")
        return datas
    
    print(f"📁 Escaneando pasta: {PASTA_HISTORICO}")
    print()
    
    for arquivo in os.listdir(PASTA_HISTORICO):
        if arquivo.lower().endswith('.html'):
            data = extrair_data_do_arquivo(arquivo)
            if data:
                datas.append(data)
                # Formata para exibição
                data_formatada = f"{data[0:2]}/{data[2:4]}/{data[4:8]}"
                print(f"   ✅ {arquivo} → {data_formatada}")
    
    return sorted(datas)


def gerar_js(datas):
    """
    Gera o arquivo JavaScript com as datas disponíveis
    """
    caminho_js = os.path.join(ARQUIVO_JS)
    
    # Gera o conteúdo do arquivo JS
    conteudo_js = f"""// Arquivo gerado automaticamente por gerar_datas_historico.py
// Atualizado em: {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}
// Total de datas: {len(datas)}

const DATAS_DISPONIVEIS = {json.dumps(datas)};
"""
    
    with open(caminho_js, 'w', encoding='utf-8') as f:
        f.write(conteudo_js)
    
    return caminho_js


def main():
    print("=" * 60)
    print("  📅 GERADOR DE DATAS DISPONÍVEIS - RefStats")
    print("=" * 60)
    print()
    
    # Escaneia a pasta
    datas = escanear_pasta_historico()
    
    print()
    print("-" * 60)
    
    if not datas:
        print("⚠️ Nenhum arquivo de jogos encontrado!")
        print()
        print("Certifique-se de que:")
        print(f"   1. A pasta existe: {PASTA_HISTORICO}")
        print("   2. Existem arquivos no formato: JOGOS_DO_DIA_DDMMYYYY.html")
        return
    
    # Gera o arquivo JS
    caminho_js = gerar_js(datas)
    
    print()
    print("✅ Arquivo JS gerado com sucesso!")
    print()
    print("📊 RESUMO:")
    print(f"   • Total de datas: {len(datas)}")
    print(f"   • Primeira data: {datas[0][0:2]}/{datas[0][2:4]}/{datas[0][4:8]}")
    print(f"   • Última data: {datas[-1][0:2]}/{datas[-1][2:4]}/{datas[-1][4:8]}")
    print()
    print(f"📄 Arquivo salvo em: {caminho_js}")
    print()
    print("💡 O calendário do histórico agora mostrará essas datas!")
    print()


if __name__ == '__main__':
    main()
