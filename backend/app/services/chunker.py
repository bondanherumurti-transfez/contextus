from nanoid import generate
from app.models import Chunk


def chunk_text(text: str, source: str) -> list[Chunk]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks = []
    chunk_size = 500
    overlap = 50

    for para in paragraphs:
        if len(para) <= chunk_size:
            word_count = len(para.split())
            if word_count >= 20:
                chunks.append(
                    Chunk(
                        id=generate(size=10),
                        source=source,
                        text=para,
                        word_count=word_count,
                    )
                )
        else:
            start = 0
            while start < len(para):
                end = start + chunk_size
                segment = para[start:end]
                word_count = len(segment.split())
                if word_count >= 20:
                    chunks.append(
                        Chunk(
                            id=generate(size=10),
                            source=source,
                            text=segment,
                            word_count=word_count,
                        )
                    )
                start = end - overlap

    return chunks


def chunk_pages(pages: list) -> list[Chunk]:
    all_chunks = []
    for page in pages:
        chunks = chunk_text(page.text, page.url)
        all_chunks.extend(chunks)
    return all_chunks
