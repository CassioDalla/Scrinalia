import csv
import json
import time

import requests
from sqlalchemy import select

from core.database import get_db
from domains.staging.models import StagingDocument

# ================= CONFIGURATION =================
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "gemma4:e4b"  # Updated model
OUTPUT_FILE = "Data/saida_para_revisao_db_gemma.csv"
COLUMN_ID = "description_id"
COLUMN_TITLE = "title"
# =================================================


def has_errors(title: str) -> dict:
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

Descrição: "{title}"
"""

    payload = {
        "model": MODEL,
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

        response_text = response.json().get("response", "")
        return json.loads(response_text)

    except json.JSONDecodeError:
        return {"contem_erro": "ERRO", "motivo": "Falha ao decodificar JSON retornado."}
    except Exception as exc:
        return {"contem_erro": "ERRO", "motivo": f"ERRO_API: {exc}"}


def main():
    start_time = time.time()
    print("Starting triage of the collection straight from the Database...")

    with get_db() as db:
        stmt = select(StagingDocument.description_id, StagingDocument.title).where(StagingDocument.title.is_not(None))
        documents = db.execute(stmt).all()
        total_documents = len(documents)
        print(f"Found {total_documents} documents for analysis.")

    with open(OUTPUT_FILE, mode="w", encoding="utf-8", newline="") as outfile:
        # Added the new "motivo_ia" column to record the justification
        fieldnames = [COLUMN_ID, COLUMN_TITLE, "texto_para_revisar", "motivo_ia"]
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()

        counter = 0
        marked_for_review = 0

        for row in documents:
            row_id = row.description_id
            title = row.title

            if not title or not title.strip():
                continue

            analysis_result = has_errors(title)

            # Extracts the data from the returned JSON with default values to avoid errors
            error_status = str(analysis_result.get("contem_erro", "")).strip().upper()
            reason = str(analysis_result.get("motivo", "")).strip()

            if "SIM" in error_status:
                review_text = title
                marked_for_review += 1
            elif "NAO" in error_status or "NÃO" in error_status:
                review_text = ""
            else:
                review_text = f"FALHA NA ANALISE: {error_status}"

            writer.writerow(
                {
                    COLUMN_ID: row_id,
                    COLUMN_TITLE: title,
                    "texto_para_revisar": review_text,
                    # Saves the reason only if the AI marked it as an alert/error to spare reading
                    "motivo_ia": reason if review_text else "",
                }
            )

            counter += 1
            print(
                f"Processed ID {row_id} | Status: {'[ALERT]' if review_text else '[OK]'} | Progress: {counter}/{total_documents}"
            )

    end_time = time.time()
    total_seconds = end_time - start_time
    minutes = int(total_seconds // 60)
    seconds = total_seconds % 60

    print("\n" + "=" * 40)
    print("TRIAGE SUMMARY:")
    print(f"Total records processed: {counter} of {total_documents}")
    print(f"Records sent for manual review: {marked_for_review}")
    print(f"File saved at: {OUTPUT_FILE}")
    print(f"Total processing time: {minutes} minutes and {seconds:.2f} seconds")
    print("=" * 40)


if __name__ == "__main__":
    main()
