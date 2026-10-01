import csv
import json
import time

import requests
from sqlalchemy import select

from core.database import get_db
from domains.staging.models import StagingDocument

# ================= CONFIGURAÇÕES =================
OLLAMA_URL = "http://localhost:11434/api/generate"
MODELO = "gemma4:e4b"  # Modelo atualizado
ARQUIVO_SAIDA = "Data/saida_para_revisao_db_gemma.csv"
COLUNA_ID = "description_id"
COLUNA_TITULO = "title"
# =================================================


def contem_erros(titulo: str) -> dict:
    prompt = f"""Você é um revisor ortográfico analisando descrições de um arquivo histórico.
Sua ÚNICA tarefa é identificar erros de digitação ou redundâncias evidentes.

=== O QUE É ERRO (SIM) ===
1. Palavras com letras trocadas, duplicadas ou erros ortográficos evidentes (ex: "edifiício", "terrenp", "Curiitba", "progeto").
2. Siglas, títulos ou palavras repetidas/redundantes em sequência (ex: "av. Avenida", "Rua r.", "projeto Projeto", "Av. Avenida Marechal", "Brig. Brigadeiro")

=== O QUE NÃO É ERRO (NAO) ===
- O texto está escrito corretamente e não possui repetições.
- Números, datas, nomes próprios e siglas usadas corretamente (sem redundância) NÃO SÃO erros.
- Na dúvida, considere que a grafia está correta (NAO).

Retorne APENAS um JSON válido.

Formato exigido:
{{
  "contem_erro": "SIM ou NAO",
  "motivo": "Se 'contem_erro' for SIM, escreva apenas a palavra errada ou o trecho repetido (ex: 'av. Avenida'). Se for NAO, deixe em branco (\"\")."
}}

Descrição: "{titulo}"
"""

    payload = {
        "model": MODELO,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.0,
            "top_k": 1,
            "top_p": 0.1,
        },
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload)
        response.raise_for_status()

        texto_resposta = response.json().get("response", "")
        return json.loads(texto_resposta)

    except json.JSONDecodeError:
        return {"contem_erro": "ERRO", "motivo": "Falha ao decodificar JSON retornado."}
    except Exception as e:
        return {"contem_erro": "ERRO", "motivo": f"ERRO_API: {e}"}


def main():
    tempo_inicio = time.time()
    print("Iniciando triagem do acervo direto do Banco de Dados...")

    with get_db() as db:
        stmt = select(StagingDocument.description_id, StagingDocument.title).where(StagingDocument.title.is_not(None))
        documentos = db.execute(stmt).all()
        total_documentos = len(documentos)
        print(f"Encontrados {total_documentos} documentos para análise.")

    with open(ARQUIVO_SAIDA, mode="w", encoding="utf-8", newline="") as outfile:
        # Adicionada a nova coluna "motivo_ia" para registrar a justificativa
        fieldnames = [COLUNA_ID, COLUNA_TITULO, "texto_para_revisar", "motivo_ia"]
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()

        contador = 0
        marcados_para_revisao = 0

        for row in documentos:
            id_linha = row.description_id
            titulo = row.title

            if not titulo or not titulo.strip():
                continue

            resultado_analise = contem_erros(titulo)

            # Extrai os dados do JSON retornado com valores padrão para evitar erros
            status_erro = str(resultado_analise.get("contem_erro", "")).strip().upper()
            motivo = str(resultado_analise.get("motivo", "")).strip()

            if "SIM" in status_erro:
                texto_revisao = titulo
                marcados_para_revisao += 1
            elif "NAO" in status_erro or "NÃO" in status_erro:
                texto_revisao = ""
            else:
                texto_revisao = f"FALHA NA ANALISE: {status_erro}"

            writer.writerow(
                {
                    COLUNA_ID: id_linha,
                    COLUNA_TITULO: titulo,
                    "texto_para_revisar": texto_revisao,
                    # Salva o motivo apenas se a IA marcou como alerta/erro para polpar leitura
                    "motivo_ia": motivo if texto_revisao else "",
                }
            )

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
