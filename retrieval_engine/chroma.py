from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .core import BaseRetriever, DocumentChunk, RetrievalResult


class ChromaUnavailableError(ImportError):
    """Raised when chromadb is not importable in the current environment."""

    @classmethod
    def missing_dependency(cls) -> ChromaUnavailableError:
        return cls(
            "chromadb is required for ChromaRetriever. Install project dependencies or use an explicit "
            "KeywordRetriever/other retriever fallback."
        )


class ChromaDatabaseError(RuntimeError):
    """Raised when a Chroma path or collection cannot be opened or queried."""

    @classmethod
    def missing_path(cls, path: Path) -> ChromaDatabaseError:
        return cls(f"ChromaDB path does not exist: {path}")

    @classmethod
    def invalid_path(cls, path: Path) -> ChromaDatabaseError:
        return cls(f"ChromaDB path must be a directory: {path}")

    @classmethod
    def missing_sqlite(cls, path: Path) -> ChromaDatabaseError:
        return cls(f"ChromaDB path is missing chroma.sqlite3 and will not be opened as an existing database: {path}")

    @classmethod
    def open_failed(cls, path: Path, collection_name: str, cause: Exception) -> ChromaDatabaseError:
        return cls(f"Unable to open Chroma collection '{collection_name}' at '{path}': {cause}")

    @classmethod
    def query_failed(cls, path: Path, collection_name: str, cause: Exception) -> ChromaDatabaseError:
        return cls(f"Unable to query Chroma collection '{collection_name}' at '{path}': {cause}")


def _import_chromadb() -> tuple[Any, Any]:
    try:
        import chromadb
        from chromadb.config import Settings
    except ModuleNotFoundError as exc:
        raise ChromaUnavailableError.missing_dependency() from exc
    return chromadb, Settings


def _first_batch(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list) and value and isinstance(value[0], list):
        return value[0]
    if isinstance(value, list):
        return value
    return []


def _distance_to_score(distance: Any) -> float:
    if distance is None:
        return 0.0
    try:
        numeric = float(distance)
    except (TypeError, ValueError):
        return 0.0
    if numeric < 0:
        return 1.0
    return 1.0 / (1.0 + numeric)


def _embed_with(function: Any, query: str) -> Sequence[float]:
    vector = function.embed_query(query) if hasattr(function, "embed_query") else function([query])
    if isinstance(vector, list) and vector and isinstance(vector[0], list):
        return vector[0]
    return vector


def _client_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


class ChromaRetriever(BaseRetriever):
    """Retriever backed by an existing persistent ChromaDB collection."""

    name = "chroma"

    def __init__(
        self,
        *,
        persist_path: str | Path,
        collection_name: str,
        embedding_function: Any | None = None,
        query_embedding_fn: Callable[[str], Sequence[float]] | None = None,
        name: str | None = None,
    ) -> None:
        self.persist_path = Path(persist_path)
        self.collection_name = collection_name
        self.embedding_function = embedding_function
        self.query_embedding_fn = query_embedding_fn
        self.name = name or self.name

        if not self.persist_path.exists():
            raise ChromaDatabaseError.missing_path(self.persist_path)
        if not self.persist_path.is_dir():
            raise ChromaDatabaseError.invalid_path(self.persist_path)

        chromadb, Settings = _import_chromadb()
        sqlite_path = self.persist_path / "chroma.sqlite3"
        if not sqlite_path.exists():
            raise ChromaDatabaseError.missing_sqlite(self.persist_path)

        try:
            self.client = chromadb.PersistentClient(
                path=_client_path(self.persist_path),
                settings=Settings(anonymized_telemetry=False, is_persistent=True),
            )
            self.collection = self.client.get_collection(name=collection_name)
        except Exception as exc:
            raise ChromaDatabaseError.open_failed(self.persist_path, collection_name, exc) from exc

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        if top_k <= 0:
            return []
        if not query.strip():
            return []

        query_args: dict[str, Any] = {
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        if self.query_embedding_fn is not None:
            query_args["query_embeddings"] = [list(self.query_embedding_fn(query))]
        elif self.embedding_function is not None:
            query_args["query_embeddings"] = [list(_embed_with(self.embedding_function, query))]
        else:
            query_args["query_texts"] = [query]

        try:
            raw = self.collection.query(**query_args)
        except Exception as exc:
            raise ChromaDatabaseError.query_failed(self.persist_path, self.collection_name, exc) from exc

        ids = _first_batch(raw.get("ids"))
        documents = _first_batch(raw.get("documents"))
        metadatas = _first_batch(raw.get("metadatas"))
        distances = _first_batch(raw.get("distances"))

        results: list[RetrievalResult] = []
        for index, doc_id in enumerate(ids):
            document = documents[index] if index < len(documents) else ""
            metadata_value = metadatas[index] if index < len(metadatas) else {}
            metadata = dict(metadata_value) if isinstance(metadata_value, Mapping) else {}
            if doc_id is not None:
                metadata.setdefault("chroma_id", doc_id)
            distance = distances[index] if index < len(distances) else None
            chunk = DocumentChunk.from_text(str(document or ""), metadata=metadata, chunk_id=str(doc_id))
            results.append(
                RetrievalResult(
                    chunk=chunk,
                    score=_distance_to_score(distance),
                    retriever_name=self.name,
                )
            )
        return results
