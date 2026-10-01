import csv
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from sqlalchemy import select

from core.database import get_db
from domains.staging.models import StagingDocument

# ================= CONFIGURAÇÕES =================
OLLAMA_URL = "http://localhost:11434/api/generate"
MODELO = "granite4.1:3b"  # Ajuste para o seu modelo
ARQUIVO_SAIDA = "Data/saida_para_revisao_db_granite_2.csv"
COLUNA_ID = "description_id"
COLUNA_TITULO = "title"
COLUNA_CONTEUDO = "admin_bio_history"

# Quantos documentos mandar para a API ao mesmo tempo.
# Comece com 5 ou 10. Se o seu PC aguentar, pode aumentar.
WORKERS_PARALELOS = 10
# =================================================

# Filtro de Regex para pegar erros óbvios instantaneamente (Ignorando Maiúsculas/Minúsculas)
REGEX_ABREVIACOES_REPETIDAS = re.compile(
    r"\b("
    # Logradouros (Vias)
    r"av\.?\s+avenida|avenida\s+av\.?|"
    r"r\.?\s+rua|rua\s+r\.?|"
    r"p[çc]a\.?\s+pra[çc]a|pra[çc]a\s+p[çc]a\.?|"
    r"trav\.?\s+travessa|tv\.?\s+travessa|travessa\s+trav\.?|travessa\s+tv\.?|"
    r"al\.?\s+alameda|alameda\s+al\.?|"
    r"rod\.?\s+rodovia|rodovia\s+rod\.?|"
    r"lg\.?\s+largo|largo\s+lg\.?|"
    r"est\.?\s+estrada|estrada\s+est\.?|"
    # Patentes Militares
    r"mal\.?\s+marechal|marechal\s+mal\.?|"
    r"brig\.?\s+brigadeiro|brigadeiro\s+brig\.?|"
    r"gen\.?\s+general|general\s+gen\.?|"
    r"cel\.?\s+coronel|coronel\s+cel\.?|"
    r"maj\.?\s+major|major\s+maj\.?|"
    r"cap\.?\s+capit[ãa]o|capit[ãa]o\s+cap\.?|"
    r"ten\.?\s+tenente|tenente\s+ten\.?|"
    r"sgt\.?\s+sargento|sargento\s+sgt\.?|"
    r"alm\.?\s+almirante|almirante\s+alm\.?|"
    # Títulos Civis e Acadêmicos
    r"dr\.?\s+doutor|doutor\s+dr\.?|"
    r"dra\.?\s+doutora|doutora\s+dra\.?|"
    r"prof\.?\s+professor|professor\s+prof\.?|"
    r"profa\.?\s+professora|professora\s+profa\.?|"
    r"eng\.?\s+engenheiro|engenheiro\s+eng\.?|"
    r"arq\.?\s+arquiteto|arquiteto\s+arq\.?|"
    # Cargos Políticos e Jurídicos
    r"pres\.?\s+presidente|presidente\s+pres\.?|"
    r"gov\.?\s+governador|governador\s+gov\.?|"
    r"pref\.?\s+prefeito|prefeito\s+pref\.?|"
    r"sen\.?\s+senador|senador\s+sen\.?|"
    r"dep\.?\s+deputado|deputado\s+dep\.?|"
    r"ver\.?\s+vereador|vereador\s+ver\.?|"
    r"des\.?\s+desembargador|desembargador\s+des\.?|"
    r"min\.?\s+ministro|ministro\s+min\.?|"
    # Títulos Nobiliárquicos e Religiosos
    r"com\.?\s+comendador|comendador\s+com\.?|"
    r"visc\.?\s+visconde|visconde\s+visc\.?|"
    r"mons\.?\s+monsenhor|monsenhor\s+mons\.?|"
    r"pe\.?\s+padre|padre\s+pe\.?|"
    r"ir\.?\s+irm[ãa]o?|irm[ãa]o?\s+ir\.?|"
    # Empresas e Outros
    r"cia\.?\s+companhia|companhia\s+cia\.?|"
    r"ltda\.?\s+limitada|limitada\s+ltda\.?"
    r")\b",
    re.IGNORECASE,
)


def analise_rapida_regex(texto: str) -> str | None:
    """Verifica se o texto contém erros óbvios usando Regex antes de gastar GPU."""
    if not texto:
        return None

    if REGEX_ABREVIACOES_REPETIDAS.search(texto):
        return "FALHA_REGEX: Abreviação duplicada (ex: Av. Avenida)"

    # Pode adicionar mais regras de Regex super rápidas aqui!
    # Ex: if re.search(r"\d{5,}", texto): return "FALHA_REGEX: Número longo solto"

    return None


def contem_erros_ia(id_linha: str, titulo: str, conteudo: str) -> tuple[str, str, str, str]:
    """Função que chama a API do Ollama. Retorna uma tupla para o Multithreading."""

    texto_alvo = f"TÍTULO: {titulo}\nDESCRIÇÃO: {conteudo or 'Vazio'}"

    prompt = f"""Você é um inspetor de qualidade do Arquivo Público de Curitiba.
            Sua única função é classificar se o texto contém anomalias estruturais ou erros.

            O que classificar como ERRO (SIM):
            - Erros de digitação, letras duplicadas ou ortografia claramente incorreta (ex: 'edifiício', 'terrenp', 'Curiitba').
            - Abreviações repetitivas que não fazem sentido (ex: 'Av. Avenida Marechal', 'Brig. Brigadeiro').

            Responda APENAS "SIM" ou "NAO".
            Texto para análise:
            {texto_alvo}
            
            Resposta:"""

    payload = {
        "model": MODELO,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0},
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload)
        response.raise_for_status()
        resposta_ia = response.json().get("response", "").strip().upper()
        return (id_linha, titulo, conteudo, resposta_ia)
    except Exception as e:
        return (id_linha, titulo, conteudo, f"ERRO_API: {e}")


def main():
    tempo_inicio = time.time()
    print("🚀 Iniciando triagem otimizada do acervo...")

    # 1. Abre a sessão e busca Titulo E Conteúdo numa única passada
    with get_db() as db:
        stmt = select(StagingDocument.description_id, StagingDocument.title, StagingDocument.admin_bio_history).where(
            StagingDocument.title.is_not(None)
        )
        documentos = db.execute(stmt).all()
        total_documentos = len(documentos)
        print(f"🔍 Encontrados {total_documentos} documentos para análise.")

    # Listas para separar o fluxo
    docs_para_ia = []
    marcados_para_revisao = 0
    contador = 0

    # 2. Prepara o arquivo CSV de saída
    with open(ARQUIVO_SAIDA, mode="w", encoding="utf-8", newline="") as outfile:
        fieldnames = [COLUNA_ID, COLUNA_TITULO, COLUNA_CONTEUDO, "motivo_revisao"]
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()

        # 3. FASE 1: Filtro Regex (Ultrarrápido)
        print("⚡ Rodando Fast-Track (Regex)...")
        for row in documentos:
            id_linha = row.description_id
            titulo = row.title or ""
            conteudo = row.admin_bio_history or ""

            # Testa o Título e a Descrição no Regex
            erro_regex = analise_rapida_regex(titulo) or analise_rapida_regex(conteudo)

            if erro_regex:
                # Pegou no Regex! Grava direto e nem manda pra IA
                writer.writerow(
                    {
                        COLUNA_ID: id_linha,
                        COLUNA_TITULO: titulo,
                        COLUNA_CONTEUDO: conteudo,
                        "motivo_revisao": erro_regex,
                    }
                )
                marcados_para_revisao += 1
                contador += 1
            else:
                # Se o Regex não achou nada, vai para a fila da IA
                docs_para_ia.append((id_linha, titulo, conteudo))

        print(f"✅ Fast-Track concluído! {marcados_para_revisao} anomalias encontradas instantaneamente.")
        print(f"🧠 Enviando os {len(docs_para_ia)} documentos restantes para o Ollama em paralelo...")

        """
        # 4. FASE 2: Processamento IA em Paralelo (Multithreading)
        if docs_para_ia:
            with ThreadPoolExecutor(max_workers=WORKERS_PARALELOS) as executor:
                # Envia todas as tarefas para o executor de uma vez
                futuros = {
                    executor.submit(contem_erros_ia, id_linha, tit, cont): id_linha
                    for id_linha, tit, cont in docs_para_ia
                }

                # Conforme as threads vão terminando, processamos o resultado
                for future in as_completed(futuros):
                    id_linha, titulo, conteudo, resultado_analise = future.result()
                    contador += 1

                    texto_revisao = ""
                    if "SIM" in resultado_analise:
                        texto_revisao = "FALHA_IA: Anomalia detetada pelo modelo."
                        marcados_para_revisao += 1
                    elif "NAO" not in resultado_analise and "NÃO" not in resultado_analise:
                        texto_revisao = f"FALHA_NA_ANALISE: {resultado_analise}"
                        marcados_para_revisao += 1

                    # Só gravamos no CSV se houver problema
                    if texto_revisao:
                        writer.writerow(
                            {
                                COLUNA_ID: id_linha,
                                COLUNA_TITULO: titulo,
                                COLUNA_CONTEUDO: conteudo,
                                "motivo_revisao": texto_revisao,
                            }
                        )

                    if contador % 10 == 0:
                        print(f"⏳ Progresso IA: {contador}/{total_documentos} processados...")
        """

    tempo_fim = time.time()
    tempo_total_segundos = tempo_fim - tempo_inicio
    minutos = int(tempo_total_segundos // 60)
    segundos = tempo_total_segundos % 60

    print("\n" + "=" * 40)
    print("RESUMO DA TRIAGEM:")
    print(f"Total de registros analisados: {contador}")
    print(f"Registros enviados para revisão manual: {marcados_para_revisao}")
    print(f"Arquivo salvo em: {ARQUIVO_SAIDA}")
    print(f"Tempo total de processamento: {minutos} minutos e {segundos:.2f} segundos")
    print("=" * 40)


if __name__ == "__main__":
    main()
