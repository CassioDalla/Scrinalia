import csv
import time

import requests
from sqlalchemy import select

from memoria_curitibana.core.database import get_db
from memoria_curitibana.domains.staging.models import StagingDocument

# ================= CONFIGURATION =================
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "granite4.1:3b"  # Adjust to your model
OUTPUT_FILE = "Data/saida_para_revisao_db_granite.csv"
COLUMN_ID = "description_id"
COLUMN_TITLE = "title"
# =================================================


def has_errors(title: str) -> str:
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
            Descrição: "{title}"
            Resposta:"""

    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.0  # ZERO temperature to force deterministic and exact answers
        },
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload)
        response.raise_for_status()
        return response.json().get("response", "").strip().upper()
    except Exception as exc:
        return f"ERRO_API: {exc}"


def main():
    start_time = time.time()
    print("Starting triage of the collection straight from the Database...")

    # 1. Opens the session with the database
    with get_db() as db:
        # Fetches only the necessary columns to save memory
        stmt = select(StagingDocument.description_id, StagingDocument.title).where(StagingDocument.title.is_not(None))
        # Fetches the records
        documents = db.execute(stmt).all()
        total_documents = len(documents)
        print(f"Found {total_documents} documents for analysis.")

    # 2. Prepares the output CSV file
    with open(OUTPUT_FILE, mode="w", encoding="utf-8", newline="") as outfile:
        fieldnames = [COLUMN_ID, COLUMN_TITLE, "texto_para_revisar"]
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()

        counter = 0
        marked_for_review = 0

        # 3. Iterates over the database results
        for row in documents:
            row_id = row.description_id
            title = row.title

            if not title or not title.strip():
                continue

            analysis_result = has_errors(title)

            if "SIM" in analysis_result:
                review_text = title
                marked_for_review += 1
            elif "NAO" in analysis_result or "NÃO" in analysis_result:
                review_text = ""
            else:
                review_text = f"FALHA NA ANALISE: {analysis_result}"

            writer.writerow({COLUMN_ID: row_id, COLUMN_TITLE: title, "texto_para_revisar": review_text})

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
