from __future__ import annotations

from unittest import TestCase

from RAG.application.chunking import ChunkingConfig, TextChunker


class TextChunkerTestCase(TestCase):
    def test_split_is_stable_and_respects_max_size(self) -> None:
        text = "First sentence. Second sentence has memory facts. " * 8
        chunker = TextChunker(ChunkingConfig(max_chars=80, overlap_chars=10))

        chunks = chunker.split(
            tenant_id="tenant-1",
            document_id="doc-1",
            version_id="ver-1",
            text=text,
            visibility="tenant",
        )
        repeated = chunker.split(
            tenant_id="tenant-1",
            document_id="doc-1",
            version_id="ver-1",
            text=text,
            visibility="tenant",
        )

        self.assertGreater(len(chunks), 1)
        self.assertEqual(chunks, repeated)
        self.assertTrue(all(len(chunk.text) <= 80 for chunk in chunks))
        self.assertEqual([chunk.index for chunk in chunks], list(range(len(chunks))))

    def test_split_uses_utf8_byte_offsets(self) -> None:
        text = "Привет. Memory fact."
        chunks = TextChunker(ChunkingConfig(max_chars=100, overlap_chars=0)).split(
            tenant_id="tenant-1",
            document_id="doc-1",
            version_id="ver-1",
            text=text,
            visibility="tenant",
        )

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].start_byte, 0)
        self.assertEqual(chunks[0].end_byte, len(text.encode("utf-8")))

    def test_split_preserves_offsets_from_original_text(self) -> None:
        text = "  Привет.  "
        chunk = TextChunker(ChunkingConfig(max_chars=100, overlap_chars=0)).split(
            tenant_id="tenant-1",
            document_id="doc-1",
            version_id="ver-1",
            text=text,
            visibility="tenant",
        )[0]

        self.assertEqual(chunk.start_byte, len("  ".encode("utf-8")))
        self.assertEqual(chunk.end_byte, len("  Привет.".encode("utf-8")))

    def test_split_applies_overlap_between_semantic_chunks(self) -> None:
        chunks = TextChunker(ChunkingConfig(max_chars=20, overlap_chars=5)).split(
            tenant_id="tenant-1",
            document_id="doc-1",
            version_id="ver-1",
            text="First sentence. Second sentence. Third sentence.",
            visibility="tenant",
        )

        self.assertGreater(len(chunks), 1)
        for previous, current in zip(chunks, chunks[1:]):
            self.assertLess(current.start_byte, previous.end_byte)
            self.assertLessEqual(len(current.text), 20)

    def test_split_limits_large_semantic_span(self) -> None:
        chunks = TextChunker(ChunkingConfig(max_chars=10, overlap_chars=2)).split(
            tenant_id="tenant-1",
            document_id="doc-1",
            version_id="ver-1",
            text="abcdefghijklmnopqrstuvwxyz. Next.",
            visibility="tenant",
        )

        self.assertTrue(all(len(chunk.text) <= 10 for chunk in chunks))
