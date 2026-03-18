"""
RAG pipeline: ingest PDFs, CSVs, and database tables into Azure AI Search,
then retrieve relevant chunks at query time.
"""
import hashlib
import io
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import pdfplumber
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
    SearchableField,
)
from azure.search.documents.models import VectorizedQuery
from azure.core.credentials import AzureKeyCredential
from langchain_openai import AzureOpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter

from backend.core.config import settings
from backend.core.logging_config import get_logger

logger = get_logger("rag.pipeline")


EMBEDDING_DIM = 1536  # text-embedding-ada-002


class RAGPipeline:
    """
    Manages document ingestion and retrieval for all agents.
    Each agent scope maps to a filter tag in the search index.
    """

    def __init__(self):
        cred = AzureKeyCredential(settings.AZURE_SEARCH_API_KEY)
        self.index_client = SearchIndexClient(
            endpoint=settings.AZURE_SEARCH_ENDPOINT,
            credential=cred,
        )
        self.search_client = SearchClient(
            endpoint=settings.AZURE_SEARCH_ENDPOINT,
            index_name=settings.AZURE_SEARCH_INDEX_NAME,
            credential=cred,
        )
        self.embeddings = AzureOpenAIEmbeddings(
            azure_deployment=settings.AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
        )
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=120,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        self._ensure_index()

    # ── Index management ─────────────────────────────────────────────────────
    def _ensure_index(self):
        existing = [i.name for i in self.index_client.list_indexes()]
        if settings.AZURE_SEARCH_INDEX_NAME not in existing:
            logger.info("Creating Azure AI Search index…")
            self.index_client.create_index(self._build_index_schema())
            logger.info("Index created.")

    def _build_index_schema(self) -> SearchIndex:
        fields = [
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SearchableField(name="content", type=SearchFieldDataType.String),
            SimpleField(name="source", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="agent_scope", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="chunk_index", type=SearchFieldDataType.Int32),
            SearchField(
                name="embedding",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=EMBEDDING_DIM,
                vector_search_profile_name="hnsw-profile",
            ),
        ]
        return SearchIndex(
            name=settings.AZURE_SEARCH_INDEX_NAME,
            fields=fields,
            vector_search=VectorSearch(
                profiles=[VectorSearchProfile(name="hnsw-profile", algorithm_configuration_name="hnsw")],
                algorithms=[HnswAlgorithmConfiguration(name="hnsw")],
            ),
            semantic_search=SemanticSearch(
                configurations=[
                    SemanticConfiguration(
                        name="default",
                        prioritized_fields=SemanticPrioritizedFields(
                            content_fields=[SemanticField(field_name="content")]
                        ),
                    )
                ]
            ),
        )

    # ── Ingestion ─────────────────────────────────────────────────────────────
    async def ingest_pdf(self, path: str, agent_scope: str) -> int:
        text = ""
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text += (page.extract_text() or "") + "\n"
        return await self._index_text(text, source=Path(path).name, agent_scope=agent_scope)

    async def ingest_csv(self, path: str, agent_scope: str) -> int:
        df = pd.read_csv(path)
        rows_text = df.to_string(index=False)
        return await self._index_text(rows_text, source=Path(path).name, agent_scope=agent_scope)

    async def ingest_database_query(
        self, query_result: List[Dict], source_name: str, agent_scope: str
    ) -> int:
        df = pd.DataFrame(query_result)
        text = df.to_string(index=False)
        return await self._index_text(text, source=source_name, agent_scope=agent_scope)

    async def _index_text(self, text: str, source: str, agent_scope: str) -> int:
        chunks = self.splitter.split_text(text)
        docs = []
        for i, chunk in enumerate(chunks):
            doc_id = hashlib.md5(f"{source}_{i}_{chunk[:32]}".encode()).hexdigest()
            embedding = self.embeddings.embed_query(chunk)
            docs.append({
                "id": doc_id,
                "content": chunk,
                "source": source,
                "agent_scope": agent_scope,
                "chunk_index": i,
                "embedding": embedding,
            })
        # Batch upload
        batch_size = 100
        for start in range(0, len(docs), batch_size):
            self.search_client.upload_documents(docs[start : start + batch_size])
        logger.info(f"Indexed {len(docs)} chunks from '{source}' for scope '{agent_scope}'")
        return len(docs)

    # ── Retrieval ─────────────────────────────────────────────────────────────
    async def retrieve(
        self,
        query: str,
        agent_scope: str,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        query_vec = self.embeddings.embed_query(query)
        vector_query = VectorizedQuery(
            vector=query_vec,
            k_nearest_neighbors=top_k,
            fields="embedding",
        )
        results = self.search_client.search(
            search_text=query,
            vector_queries=[vector_query],
            filter=f"agent_scope eq '{agent_scope}'",
            top=top_k,
            query_type="semantic",
            semantic_configuration_name="default",
        )
        return [
            {
                "content": r["content"],
                "source": r["source"],
                "score": r.get("@search.score", 0.0),
                "reranker_score": r.get("@search.reranker_score"),
            }
            for r in results
        ]


# Singleton
_rag_pipeline: Optional[RAGPipeline] = None


def get_rag_pipeline() -> RAGPipeline:
    global _rag_pipeline
    if _rag_pipeline is None:
        _rag_pipeline = RAGPipeline()
    return _rag_pipeline
