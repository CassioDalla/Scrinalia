import time
from io import BytesIO

import requests
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from core.database import get_db
from core.logger import logger
from core.storage import S3Storage
from domains.archive.models import ArchiveDocument


def download_image_to_memory(url: str) -> BytesIO | None:
    """
    Efetua o download HTTP disfarçado de navegador de utilizador e processa
    os bytes da imagem, convertendo tudo para um padrão JPEG otimizado.

    Args:
        url (str): O link público direto para a imagem original.

    Returns:
        BytesIO | None: Buffer de memória contendo a imagem JPEG, ou None em caso de falha.
    """

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        resposta = requests.get(url, headers=headers, timeout=10)
        if resposta.status_code == 200:
            img = Image.open(BytesIO(resposta.content))

            # Converte imagens PNG/GIF com transparência para RGB seguro
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            output_buffer = BytesIO()
            img.save(output_buffer, format="JPEG", quality=100, subsampling=0)

            # Volta o ponteiro de leitura para o início do ficheiro
            output_buffer.seek(0)

            return output_buffer
        else:
            logger.warning(f"⚠️ Erro HTTP {resposta.status_code} ao acessar a: {url}")
            return None
    except Exception as e:
        logger.error(f"❌ Falha de rede ao descarregar {url}: {e}")
        return None


def execute(db: Session) -> None:
    """
    Orquestrador assíncrono responsável por migrar imagens de um link externo
    efémero para um Object Storage seguro (ex: MinIO/S3).

    Varre a tabela Fato em busca de documentos que possuem o link original, mas
    cuja URI de armazenamento local ainda está vazia.
    """
    logger.info("📸 Iniciando Worker de Thumbnails...")

    storage = S3Storage()

    # Busca imagens que ainda não foram enviadas E que não falharam permanentemente
    query = select(ArchiveDocument).where(
        ArchiveDocument.original_thumbnail_url.is_not(None)
        & ArchiveDocument.storage_thumbnail_uri.is_(None)
        & ~ArchiveDocument.execution_log.has_key("thumbnail_failed")
    )

    documentos_pendentes = db.scalars(query).yield_per(50)

    processados = 0
    sucessos = 0

    for doc in documentos_pendentes:
        try:
            with db.begin_nested():
                url_alvo = doc.original_thumbnail_url

                if not url_alvo:
                    continue

                nome_ficheiro = f"thumb_{doc.description_id}.jpg"
                caminho_no_bucket = f"thumbnails/{nome_ficheiro}"

                bytes_imagem = download_image_to_memory(url_alvo)

                if bytes_imagem:
                    uri_final = storage.upload_file(file_stream=bytes_imagem, file_path=caminho_no_bucket)
                    doc.storage_thumbnail_uri = uri_final
                    sucessos += 1
                else:
                    # Em caso de falha de download, carimba no JSONB para não tentar no próximo loop
                    novo_log = dict(doc.execution_log)
                    novo_log["thumbnail_failed"] = "True"
                    doc.execution_log = novo_log
                    flag_modified(doc, "execution_log")

                processados += 1

                if processados % 50 == 0:
                    logger.info(f"⏳ Progresso: {processados} imagens analisadas...")

                time.sleep(0.5)

        except Exception as e:
            logger.error(f"❌ Erro catastrófico no documento {doc.description_id}: {e}")
            continue

    db.commit()
    logger.success(
        f"✅ Worker de Thumbnails finalizado! {sucessos} imagens guardadas com sucesso de {processados} tentativas."
    )


if __name__ == "__main__":
    with get_db() as db:
        execute(db)
