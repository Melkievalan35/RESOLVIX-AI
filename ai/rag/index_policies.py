from pathlib import Path
import fitz  # PyMuPDF

from .chunking import TextChunker
from .embedding import EmbeddingModel
from .vectordb import VectorDB

POLICY_DIR = Path("data/policies")

chunker = TextChunker(
    chunk_size=500,
    chunk_overlap=100,
)

embedder = EmbeddingModel(provider="local")

db = VectorDB()


def read_pdf(pdf_path: Path):
    doc = fitz.open(pdf_path)
    text = ""

    for page in doc:
        text += page.get_text()

    doc.close()

    return text


def main():

    total = 0

    for pdf in POLICY_DIR.glob("*.pdf"):

        print(f"Indexing {pdf.name}")

        text = read_pdf(pdf)

        chunks = chunker.chunk_text(
            text=text,
            source=pdf.name,
        )

        embeddings = embedder.embed_texts(
            [c.text for c in chunks]
        )

        db.delete_by_source(pdf.name)

        db.add_chunks(
            chunks,
            embeddings,
        )

        total += len(chunks)

    print("=" * 50)
    print("INDEX COMPLETE")
    print("Chunks:", total)
    print("Vector DB:", db.count())


if __name__ == "__main__":
    main()