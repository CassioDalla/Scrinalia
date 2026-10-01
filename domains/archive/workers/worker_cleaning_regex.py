import re
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from core.database import get_db
from core.logger import logger
from domains.archive.repository.cleaning_repo import CleaningRepository

BATCH_SIZE = 500

def execute(db: Session) -> None:
    """
    Worker que aplica regras dinâmicas de Regex (Limpeza Textual) criadas pelos curadores.
    Processa documentos de forma incremental usando o 'execution_log' como rastreador.
    """
    logger.info("🧹 Iniciando Worker Limpador de Qualidade de Dados...")
    
    repo = CleaningRepository(db)
    active_rules = repo.get_active_rules()
    
    if not active_rules:
        logger.info("Nenhuma regra de limpeza ativa encontrada.")
        return

    logger.info(f"📋 Encontradas {len(active_rules)} regras ativas. Iniciando varredura...")

    for rule in active_rules:
        rule_key = f"cleaning_rule_{rule.rule_id}"
        
        try:
            # Compila o regex apenas uma vez por regra
            compiled_regex = re.compile(rule.regex_pattern, re.IGNORECASE)
        except Exception as e:
            logger.error(f"❌ Regra ID {rule.rule_id} ('{rule.rule_name}') tem sintaxe Regex inválida: {e}. Ignorando.")
            continue

        docs_processados = 0
        alteracoes_feitas = 0

        while True:
            # Pega o próximo lote de documentos que ainda não viram ESTA regra
            lote_docs = repo.get_unprocessed_documents_for_rule(
                rule_id=rule.rule_id, 
                target_column=rule.target_column, 
                limit=BATCH_SIZE
            )
            
            if not lote_docs:
                break # Fim da varredura para esta regra!

            try:
                for doc in lote_docs:
                    texto_original = getattr(doc, rule.target_column)
                    
                    if texto_original:
                        # Aplica a limpeza Pythonica
                        texto_limpo = compiled_regex.sub(rule.replacement_string, texto_original)
                        
                        if texto_limpo != texto_original:
                            # Sobrescreve a coluna na model
                            setattr(doc, rule.target_column, texto_limpo)
                            alteracoes_feitas += 1
                    
                    # Independentemente de ter alterado ou não, carimbamos para nunca mais olhar
                    log_atual = dict(doc.execution_log) if doc.execution_log else {}
                    log_atual[rule_key] = "DONE"
                    doc.execution_log = log_atual
                    flag_modified(doc, "execution_log")
                    
                    docs_processados += 1

                # Comita o lote inteiro
                db.commit()
                
            except Exception as e:
                logger.error(f"💥 Erro ao comitar lote na Regra {rule.rule_id}: {e}")
                db.rollback()
                break # Pula para a próxima regra para não estagnar

        if docs_processados > 0:
            logger.success(f"✅ Regra '{rule.rule_name}' concluída! Auditados: {docs_processados} | Alterados: {alteracoes_feitas}.")

    logger.info("🏁 Varredura do Worker Limpador finalizada.")

if __name__ == "__main__":
    with get_db() as db:
        execute(db)