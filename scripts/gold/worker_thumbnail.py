import time
from io import BytesIO

import requests
from PIL import Image
from sqlalchemy import select

from core.database import get_db
from core.logger import logger
from core.models.gold_layer import GoldDescriptionModel
from core.storage import S3Storage


def download_image_to_memory(url: str) -> BytesIO | None:
    """Faz o request HTTP disfarçado de navegador e devolve os bytes."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        resposta = requests.get(url, headers=headers, timeout=10)
        if resposta.status_code == 200:
            img = Image.open(BytesIO(resposta.content))

            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            output_buffer = BytesIO()
            img.save(output_buffer, format="JPEG", quality=100, subsampling=0)

            # Volta o ponteiro de leitura para o início do ficheiro
            output_buffer.seek(0)

            return output_buffer
        else:
            logger.warning(f"⚠️ Erro HTTP {resposta.status_code} ao aceder a: {url}")
            return None
    except Exception as e:
        logger.error(f"❌ Falha de rede ao descarregar {url}: {e}")
        return None


def execute_worker_thumbnails() -> None:
    """
    Orquestrador que varre a base de dados em busca de documentos
    que tenham URL original da thumbnail mas ainda não foram enviados para o Storage.
    """
    logger.info("📸 Iniciando Worker de Thumbnails...")

    # Instancia o adaptador de armazenamento (Desacoplamento!)
    storage = S3Storage()

    with get_db() as db:
        query = select(GoldDescriptionModel).where(
            GoldDescriptionModel.original_thumbnail_url.is_not(None)
            & GoldDescriptionModel.storage_thumbnail_uri.is_(None)
        )

        documentos_pendentes = db.scalars(query).yield_per(50)

        processados = 0
        sucessos = 0

        for doc in documentos_pendentes:
            try:
                url_alvo = doc.original_thumbnail_url

                if not url_alvo:
                    continue

                nome_ficheiro = f"thumb_{doc.description_id}.jpg"
                caminho_no_bucket = f"thumbnails/{nome_ficheiro}"

                bytes_imagem = download_image_to_memory(url_alvo)

                if bytes_imagem:
                    # 2. Envia da Memória para o MinIO usando o nosso Adaptador
                    uri_final = storage.upload_file(file_stream=bytes_imagem, file_path=caminho_no_bucket)

                    # 3. Atualiza a Base de Dados
                    doc.storage_thumbnail_uri = uri_final
                    sucessos += 1
                else:
                    # Se falhar o download, carimbar no log de execução para não tentar infinitamente
                    doc.execution_log = dict(doc.execution_log or {})
                    doc.execution_log["thumbnail_download"] = "failed"

                processados += 1

                # Commit a cada 50 imagens
                if processados % 50 == 0:
                    db.commit()
                    logger.info(f"⏳ Progresso: {processados} imagens analisadas...")

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"❌ Erro catastrófico no documento {doc.description_id}: {e}")
                db.rollback()
                continue

        db.commit()
        logger.success(
            f"✅ Worker de Thumbnails finalizado! {sucessos} imagens guardadas com sucesso de {processados} tentativas."
        )


if __name__ == "__main__":
    execute_worker_thumbnails()
