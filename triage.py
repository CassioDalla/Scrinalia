import csv
import re
import time

import requests
from sqlalchemy import select

from memoria_curitibana.core.database import get_db
from memoria_curitibana.domains.staging.models import StagingDocument

# ================= CONFIGURATION =================
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "granite4.1:3b"  # Adjust to your model
OUTPUT_FILE = "Data/saida_para_revisao_db_granite_2.csv"
COLUMN_ID = "description_id"
COLUMN_TITLE = "title"
COLUMN_CONTENT = "admin_bio_history"

# How many documents to send to the API at the same time.
# Start with 5 or 10. If your machine can handle it, you can increase it.
PARALLEL_WORKERS = 10
# =================================================

# Regex filter to catch obvious errors instantly (Ignoring Upper/Lower case)
REGEX_REPEATED_ABBREVIATIONS = re.compile(
    r"\b("
    # Public ways (Streets)
    r"av\.?\s+avenida|avenida\s+av\.?|"
    r"r\.?\s+rua|rua\s+r\.?|"
    r"p[çc]a\.?\s+pra[çc]a|pra[çc]a\s+p[çc]a\.?|"
    r"trav\.?\s+travessa|tv\.?\s+travessa|travessa\s+trav\.?|travessa\s+tv\.?|"
    r"al\.?\s+alameda|alameda\s+al\.?|"
    r"rod\.?\s+rodovia|rodovia\s+rod\.?|"
    r"lg\.?\s+largo|largo\s+lg\.?|"
    r"est\.?\s+estrada|estrada\s+est\.?|"
    # Military ranks
    r"mal\.?\s+marechal|marechal\s+mal\.?|"
    r"brig\.?\s+brigadeiro|brigadeiro\s+brig\.?|"
    r"gen\.?\s+general|general\s+gen\.?|"
    r"cel\.?\s+coronel|coronel\s+cel\.?|"
    r"maj\.?\s+major|major\s+maj\.?|"
    r"cap\.?\s+capit[ãa]o|capit[ãa]o\s+cap\.?|"
    r"ten\.?\s+tenente|tenente\s+ten\.?|"
    r"sgt\.?\s+sargento|sargento\s+sgt\.?|"
    r"alm\.?\s+almirante|almirante\s+alm\.?|"
    # Civil and academic titles
    r"dr\.?\s+doutor|doutor\s+dr\.?|"
    r"dra\.?\s+doutora|doutora\s+dra\.?|"
    r"prof\.?\s+professor|professor\s+prof\.?|"
    r"profa\.?\s+professora|professora\s+profa\.?|"
    r"eng\.?\s+engenheiro|engenheiro\s+eng\.?|"
    r"arq\.?\s+arquiteto|arquiteto\s+arq\.?|"
    # Political and legal offices
    r"pres\.?\s+presidente|presidente\s+pres\.?|"
    r"gov\.?\s+governador|governador\s+gov\.?|"
    r"pref\.?\s+prefeito|prefeito\s+pref\.?|"
    r"sen\.?\s+senador|senador\s+sen\.?|"
    r"dep\.?\s+deputado|deputado\s+dep\.?|"
    r"ver\.?\s+vereador|vereador\s+ver\.?|"
    r"des\.?\s+desembargador|desembargador\s+des\.?|"
    r"min\.?\s+ministro|ministro\s+min\.?|"
    # Noble and religious titles
    r"com\.?\s+comendador|comendador\s+com\.?|"
    r"visc\.?\s+visconde|visconde\s+visc\.?|"
    r"mons\.?\s+monsenhor|monsenhor\s+mons\.?|"
    r"pe\.?\s+padre|padre\s+pe\.?|"
    r"ir\.?\s+irm[ãa]o?|irm[ãa]o?\s+ir\.?|"
    # Companies and others
    r"cia\.?\s+companhia|companhia\s+cia\.?|"
    r"ltda\.?\s+limitada|limitada\s+ltda\.?"
    r")\b",
    re.IGNORECASE,
)


def quick_regex_analysis(text: str) -> str | None:
    """Checks whether the text contains obvious errors using Regex before spending GPU."""
    if not text:
        return None

    if REGEX_REPEATED_ABBREVIATIONS.search(text):
        return "FALHA_REGEX: Abreviação duplicada (ex: Av. Avenida)"

    # You can add more super fast Regex rules here!
    # E.g.: if re.search(r"\d{5,}", text): return "FALHA_REGEX: Número longo solto"

    return None


def contains_ai_errors(row_id: str, title: str, content: str) -> tuple[str, str, str, str]:
    """Function that calls the Ollama API. Returns a tuple for Multithreading."""

    target_text = f"TÍTULO: {title}\nDESCRIÇÃO: {content or 'Vazio'}"

    prompt = f"""Você é um inspetor de qualidade do Arquivo Público de Curitiba.
            Sua única função é classificar se o texto contém anomalias estruturais ou erros.

            O que classificar como ERRO (SIM):
            - Erros de digitação, letras duplicadas ou ortografia claramente incorreta (ex: 'edifiício', 'terrenp', 'Curiitba').
            - Abreviações repetitivas que não fazem sentido (ex: 'Av. Avenida Marechal', 'Brig. Brigadeiro').

            Responda APENAS "SIM" ou "NAO".
            Texto para análise:
            {target_text}

            Resposta:"""

    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0},
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload)
        response.raise_for_status()
        ai_response = response.json().get("response", "").strip().upper()
        return (row_id, title, content, ai_response)
    except Exception as exc:
        return (row_id, title, content, f"ERRO_API: {exc}")


def main():
    start_time = time.time()
    print("🚀 Starting optimized triage of the collection...")

    # 1. Opens the session and fetches Title AND Content in a single pass
    with get_db() as db:
        stmt = select(StagingDocument.description_id, StagingDocument.title, StagingDocument.admin_bio_history).where(
            StagingDocument.title.is_not(None)
        )
        documents = db.execute(stmt).all()
        total_documents = len(documents)
        print(f"🔍 Found {total_documents} documents for analysis.")

    # Lists to split the flow
    docs_for_ai = []
    marked_for_review = 0
    counter = 0

    # 2. Prepares the output CSV file
    with open(OUTPUT_FILE, mode="w", encoding="utf-8", newline="") as outfile:
        fieldnames = [COLUMN_ID, COLUMN_TITLE, COLUMN_CONTENT, "motivo_revisao"]
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()

        # 3. PHASE 1: Regex Filter (Ultra fast)
        print("⚡ Running Fast-Track (Regex)...")
        for row in documents:
            row_id = row.description_id
            title = row.title or ""
            content = row.admin_bio_history or ""

            # Tests the Title and the Description against the Regex
            regex_error = quick_regex_analysis(title) or quick_regex_analysis(content)

            if regex_error:
                # Caught by Regex! Writes directly and does not even send it to the AI
                writer.writerow(
                    {
                        COLUMN_ID: row_id,
                        COLUMN_TITLE: title,
                        COLUMN_CONTENT: content,
                        "motivo_revisao": regex_error,
                    }
                )
                marked_for_review += 1
                counter += 1
            else:
                # If the Regex found nothing, it goes to the AI queue
                docs_for_ai.append((row_id, title, content))

        print(f"✅ Fast-Track finished! {marked_for_review} anomalies found instantly.")
        print(f"🧠 Sending the {len(docs_for_ai)} remaining documents to Ollama in parallel...")

        """
        # 4. PHASE 2: AI Processing in Parallel (Multithreading)
        if docs_for_ai:
            with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
                # Sends all tasks to the executor at once
                futures = {
                    executor.submit(contains_ai_errors, row_id, title, content): row_id
                    for row_id, title, content in docs_for_ai
                }

                # As the threads finish, we process the result
                for future in as_completed(futures):
                    row_id, title, content, analysis_result = future.result()
                    counter += 1

                    review_text = ""
                    if "SIM" in analysis_result:
                        review_text = "FALHA_IA: Anomalia detetada pelo modelo."
                        marked_for_review += 1
                    elif "NAO" not in analysis_result and "NÃO" not in analysis_result:
                        review_text = f"FALHA_NA_ANALISE: {analysis_result}"
                        marked_for_review += 1

                    # We only write to the CSV if there is a problem
                    if review_text:
                        writer.writerow(
                            {
                                COLUMN_ID: row_id,
                                COLUMN_TITLE: title,
                                COLUMN_CONTENT: content,
                                "motivo_revisao": review_text,
                            }
                        )

                    if counter % 10 == 0:
                        print(f"⏳ AI progress: {counter}/{total_documents} processed...")
        """

    end_time = time.time()
    total_seconds = end_time - start_time
    minutes = int(total_seconds // 60)
    seconds = total_seconds % 60

    print("\n" + "=" * 40)
    print("TRIAGE SUMMARY:")
    print(f"Total records analyzed: {counter}")
    print(f"Records sent for manual review: {marked_for_review}")
    print(f"File saved at: {OUTPUT_FILE}")
    print(f"Total processing time: {minutes} minutes and {seconds:.2f} seconds")
    print("=" * 40)


if __name__ == "__main__":
    main()
