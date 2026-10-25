"""The vocabulary of a CSV a person exports from a spreadsheet.

The labels on the left are the file's **headers**, and they are the person's own Portuguese: they
are payload keys, never translated, exactly like a site's labels in the scraper. The map is built
from :mod:`scrinalia.domains.ingestion.csv_import`, the same catalogue the import route publishes
to the screen, so there is one list of accepted columns instead of a second one here.

There is no adapter and no site: the file is parsed in the browser and the rows arrive as JSON
(#191). This module exists because the staging transform reads an origin's vocabulary from a
``SourceSchema``, and the CSV origin must declare its own — the transform still learns no origin.
"""

from scrinalia.domains.ingestion.csv_import import CSV_DATE_LABEL, CSV_FIELD_MAP, CSV_TITLE_LABEL
from scrinalia.domains.ingestion.ports import SourceSchema

#: The title and the date are consumed through the schema's own keys, exactly like the manual
#: origin; putting them in ``field_map`` would append the title (or the date) to itself.
CSV_SOURCE_SCHEMA = SourceSchema(
    code="csv",
    field_map=CSV_FIELD_MAP,
    title_key=CSV_TITLE_LABEL,
    url_key="_csv_url",
    attachment_key="_csv_attachment",
    date_keys=(CSV_DATE_LABEL,),
)
