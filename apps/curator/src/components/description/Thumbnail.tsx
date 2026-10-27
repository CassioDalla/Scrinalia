import { ImageOff } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/cn";

/**
 * The description's miniature, in the two places the archive shows it.
 *
 * The URL comes from ``DocumentSummary.thumbnail_url``, which the API derives from the stored
 * object; the component never assembles a path and never talks to the bucket. The three states are
 * all drawn: the image, **sem imagem** (the source had none — 4 of the reference collection's 101
 * descriptions) and **indisponível** (the object left the bucket, or the storage refused the read).
 * The two failures reserve the same box as the image, so the row does not jump when the bytes do not
 * arrive, and a broken-image glyph is never what the archivist sees.
 *
 * The dossier variant carries its own caption because it is the only one that can tell "no source
 * image" from "the stored file is gone": both look like an empty box until the words say which one
 * it is, and a caption owned by the screen would claim the file is there when it is not.
 */
export function DocumentThumbnail({
  url,
  title,
  variant,
}: {
  /** ``thumbnail_url`` of the read view; ``null`` when there is no stored image. */
  url: string | null;
  /** The description's title, used by the dossier's alternative text and the placeholder label. */
  title: string;
  variant: "dossier" | "list";
}) {
  const [failed, setFailed] = useState(false);
  const list = variant === "list";
  const label = failed ? "Imagem indisponível" : "Sem imagem";

  const box =
    !url || failed ? (
      <div
        role="img"
        aria-label={`${label}: ${title}`}
        title={label}
        className={cn(
          "flex shrink-0 items-center justify-center rounded-lg border border-dashed border-(--color-line) bg-black/[0.03] text-(--color-muted)",
          list ? "size-14" : "h-56 w-full max-w-sm flex-col gap-2",
        )}
      >
        <ImageOff className={list ? "size-5" : "size-7"} aria-hidden="true" />
        {list ? null : <span className="text-xs font-medium">{label}</span>}
      </div>
    ) : (
      <img
        src={url}
        // The list's title sits beside the image, so repeating it there would make a screen reader
        // say the same description twice. In the dossier the image is the content, and it is named.
        alt={list ? "" : `Imagem da descrição: ${title}`}
        loading={list ? "lazy" : "eager"}
        decoding="async"
        onError={() => setFailed(true)}
        className={cn(
          "shrink-0 rounded-lg bg-black/[0.03] ring-1 ring-(--color-line)",
          list ? "size-14 object-cover" : "h-56 w-full max-w-sm object-contain",
        )}
      />
    );

  if (list) {
    return box;
  }

  const heading = failed ? "Imagem Indisponível" : url ? "Miniatura Armazenada" : "Sem imagem de origem";
  const caption = failed
    ? "A imagem guardada não pôde ser lida"
    : url
      ? "Guardada no acervo; o dossiê mostra a miniatura, não o arquivo original."
      : "A origem deste registro não publica uma imagem; a descrição continua completa sem ela.";

  return (
    <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-center">
      {box}
      <div className="min-w-0 max-w-sm">
        <p className="text-sm font-medium">{heading}</p>
        <p className="mt-1 text-xs text-(--color-muted)">{caption}</p>
      </div>
    </div>
  );
}
