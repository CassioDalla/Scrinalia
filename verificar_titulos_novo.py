import csv
import time

import requests
from sqlalchemy import select

from core.database import get_db
from domains.staging.models import StagingDocument

# ================= CONFIGURAÇÕES =================
OLLAMA_URL = "http://localhost:11434/api/generate"
MODELO = "granite4.1:3b"  # Ajuste para o seu modelo
ARQUIVO_SAIDA = "Data/saida_para_revisao_db_granite.csv"
COLUNA_ID = "description_id"
COLUNA_TITULO = "title"
# =================================================


def contem_erros(titulo: str) -> str:
    prompt = f"""Você é um inspetor de qualidade do Arquivo Público de Curitiba.
            Sua única função é classificar se a descrição arquivística contém anomalias estruturais ou erros.

            O que classificar como ERRO (SIM):
            - Números soltos ou IDs no meio do texto.
            - Uso de termos de sistema como 'Não consta'.
            - Omissão de nome onde deveria haver um.
            - Erros de digitação, letras duplicadas ou ortografia claramente incorreta (ex: 'edifiício', 'terrenp', 'Curiitba').

            Exemplos de classificação:
            Descrição: "Projeto de Varanda e portão para proprietário não Identificado do ano de 1924"
            Resposta: SIM

            Descrição: "Projeto de Santuario Senhor Bom Jesus para Não consta do ano de 1924"
            Resposta: SIM

            Descrição: "Projeto de um muro 1112 do ano de 1917"
            Resposta: SIM

            Descrição: "Planta de um terrenp em Curiitba"
            Resposta: SIM

            Descrição: "Ação de Rescisão de Concessão de Bombas de Gasolina"
            Resposta: NAO

            Descrição: "Projeto de casa de madeira com frente de alvenaria para Saturnino Pontes"
            Resposta: SIM

            Agora classifique a descrição abaixo. Retorne APENAS "SIM" ou "NAO".
            Descrição: "{titulo}"
            Resposta:"""

    payload = {
        "model": MODELO,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.0  # Temperatura ZERO para forçar respostas determinísticas e exatas
        },
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload)
        response.raise_for_status()
        return response.json().get("response", "").strip().upper()
    except Exception as e:
        return f"ERRO_API: {e}"


def main():
    tempo_inicio = time.time()
    print("Iniciando triagem do acervo direto do Banco de Dados...")

    # 1. Abre a sessão com o banco de dados
    with get_db() as db:
        # Traz apenas as colunas necessárias para poupar memória
        stmt = select(StagingDocument.description_id, StagingDocument.title).where(StagingDocument.title.is_not(None))
        # Busca os registros
        documentos = db.execute(stmt).all()
        total_documentos = len(documentos)
        print(f"Encontrados {total_documentos} documentos para análise.")

    # 2. Prepara o arquivo CSV de saída
    with open(ARQUIVO_SAIDA, mode="w", encoding="utf-8", newline="") as outfile:
        fieldnames = [COLUNA_ID, COLUNA_TITULO, "texto_para_revisar"]
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()

        contador = 0
        marcados_para_revisao = 0

        # 3. Itera sobre os resultados do banco
        for row in documentos:
            id_linha = row.description_id
            titulo = row.title

            if not titulo or not titulo.strip():
                continue

            resultado_analise = contem_erros(titulo)

            if "SIM" in resultado_analise:
                texto_revisao = titulo
                marcados_para_revisao += 1
            elif "NAO" in resultado_analise or "NÃO" in resultado_analise:
                texto_revisao = ""
            else:
                texto_revisao = f"FALHA NA ANALISE: {resultado_analise}"

            writer.writerow({COLUNA_ID: id_linha, COLUNA_TITULO: titulo, "texto_para_revisar": texto_revisao})

            contador += 1
            print(
                f"Processado ID {id_linha} | Status: {'[ALERTA]' if texto_revisao else '[OK]'} | Progresso: {contador}/{total_documentos}"
            )

    tempo_fim = time.time()
    tempo_total_segundos = tempo_fim - tempo_inicio
    minutos = int(tempo_total_segundos // 60)
    segundos = tempo_total_segundos % 60

    print("\n" + "=" * 40)
    print("RESUMO DA TRIAGEM:")
    print(f"Total de registros processados: {contador} de {total_documentos}")
    print(f"Registros enviados para revisão manual: {marcados_para_revisao}")
    print(f"Arquivo salvo em: {ARQUIVO_SAIDA}")
    print(f"Tempo total de processamento: {minutos} minutos e {segundos:.2f} segundos")
    print("=" * 40)


if __name__ == "__main__":
    main()
