import logging
from typing import Any

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
    HnswAlgorithmConfiguration,
)
from azure.search.documents.models import VectorizedQuery

logger = logging.getLogger(__name__)


class AzureSearchService:
    """Service for managing and querying the Azure AI Search index."""

    def __init__(self, endpoint: str, api_key: str, index_name: str) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.index_name = index_name
        self._credential = AzureKeyCredential(api_key)

    def _get_index_client(self) -> SearchIndexClient:
        return SearchIndexClient(
            endpoint=self.endpoint, credential=self._credential
        )

    def _get_search_client(self) -> SearchClient:
        return SearchClient(
            endpoint=self.endpoint,
            index_name=self.index_name,
            credential=self._credential,
        )

    async def ensure_index(self) -> None:
        """Create the search index if it does not already exist."""
        index_client = self._get_index_client()

        fields = [
            SimpleField(
                name="chunk_id",
                type=SearchFieldDataType.String,
                key=True,
                filterable=True,
            ),
            SimpleField(
                name="project_id",
                type=SearchFieldDataType.String,
                filterable=True,
            ),
            SimpleField(
                name="file_id",
                type=SearchFieldDataType.String,
                filterable=True,
            ),
            SearchableField(
                name="file_name",
                type=SearchFieldDataType.String,
                filterable=True,
            ),
            SimpleField(
                name="file_type",
                type=SearchFieldDataType.String,
                filterable=True,
            ),
            SearchableField(
                name="hierarchy",
                type=SearchFieldDataType.String,
            ),
            SimpleField(
                name="source_url",
                type=SearchFieldDataType.String,
            ),
            SearchableField(
                name="content",
                type=SearchFieldDataType.String,
                analyzer_name="en.microsoft",
            ),
            SearchField(
                name="content_vector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=1536,
                vector_search_profile_name="default-vector-profile",
            ),
            SearchField(
                name="questions",
                type=SearchFieldDataType.Collection(SearchFieldDataType.String),
                searchable=True,
            ),
            SearchField(
                name="questions_vector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=1536,
                vector_search_profile_name="default-vector-profile",
            ),
            SearchField(
                name="keywords",
                type=SearchFieldDataType.Collection(SearchFieldDataType.String),
                searchable=True,
                filterable=True,
            ),
            SimpleField(
                name="page_number",
                type=SearchFieldDataType.Int32,
                filterable=True,
            ),
            SimpleField(
                name="sheet_name",
                type=SearchFieldDataType.String,
                filterable=True,
            ),
            SearchableField(
                name="section_heading",
                type=SearchFieldDataType.String,
            ),
            SimpleField(
                name="created_at",
                type=SearchFieldDataType.DateTimeOffset,
            ),
        ]

        vector_search = VectorSearch(
            algorithms=[
                HnswAlgorithmConfiguration(name="default-hnsw"),
            ],
            profiles=[
                VectorSearchProfile(
                    name="default-vector-profile",
                    algorithm_configuration_name="default-hnsw",
                ),
            ],
        )

        index = SearchIndex(
            name=self.index_name,
            fields=fields,
            vector_search=vector_search,
        )

        try:
            index_client.get_index(self.index_name)
            logger.info("Search index '%s' already exists.", self.index_name)
        except Exception:
            logger.info("Creating search index '%s'...", self.index_name)
            index_client.create_index(index)
            logger.info("Search index '%s' created.", self.index_name)

    async def upsert_chunks(self, chunks: list[dict]) -> None:
        """Batch upsert documents into the search index."""
        if not chunks:
            return

        search_client = self._get_search_client()
        # Process in batches of 1000 (Azure limit)
        batch_size = 1000
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            search_client.upload_documents(documents=batch)
            logger.info(
                "Upserted batch %d-%d of %d chunks.",
                i,
                min(i + batch_size, len(chunks)),
                len(chunks),
            )

    async def hybrid_search(
        self,
        query: str,
        query_vector: list[float],
        project_id: str,
        file_types: list[str] | None = None,
        top_k: int = 8,
    ) -> list[dict]:
        """
        Perform hybrid search combining text search and vector similarity.

        Filters on project_id and optionally on file_type.
        """
        search_client = self._get_search_client()

        # Build filter expression
        filter_expr = f"project_id eq '{project_id}'"
        if file_types:
            type_filters = " or ".join(
                f"file_type eq '{ft}'" for ft in file_types
            )
            filter_expr += f" and ({type_filters})"

        vector_query = VectorizedQuery(
            vector=query_vector,
            k_nearest_neighbors=top_k,
            fields="content_vector",
        )

        results = search_client.search(
            search_text=query,
            vector_queries=[vector_query],
            filter=filter_expr,
            top=top_k,
            select=[
                "chunk_id",
                "project_id",
                "file_id",
                "file_name",
                "file_type",
                "hierarchy",
                "source_url",
                "content",
                "keywords",
                "page_number",
                "sheet_name",
                "section_heading",
            ],
        )

        return [dict(result) for result in results]

    async def search_within_file(
        self,
        query: str,
        query_vector: list[float],
        file_id: str,
        project_id: str,
        top_k: int = 5,
    ) -> list[dict]:
        """Search within a specific file by filtering on file_id and project_id."""
        search_client = self._get_search_client()

        filter_expr = (
            f"project_id eq '{project_id}' and file_id eq '{file_id}'"
        )

        vector_query = VectorizedQuery(
            vector=query_vector,
            k_nearest_neighbors=top_k,
            fields="content_vector",
        )

        results = search_client.search(
            search_text=query,
            vector_queries=[vector_query],
            filter=filter_expr,
            top=top_k,
            select=[
                "chunk_id",
                "project_id",
                "file_id",
                "file_name",
                "file_type",
                "hierarchy",
                "source_url",
                "content",
                "keywords",
                "page_number",
                "sheet_name",
                "section_heading",
            ],
        )

        return [dict(result) for result in results]

    async def delete_by_project(self, project_id: str) -> None:
        """Delete all chunks belonging to a project."""
        search_client = self._get_search_client()

        # Search for all chunk IDs in the project
        results = search_client.search(
            search_text="*",
            filter=f"project_id eq '{project_id}'",
            select=["chunk_id"],
            top=10000,
        )

        docs_to_delete = [{"chunk_id": r["chunk_id"]} for r in results]

        if docs_to_delete:
            batch_size = 1000
            for i in range(0, len(docs_to_delete), batch_size):
                batch = docs_to_delete[i : i + batch_size]
                search_client.delete_documents(documents=batch)
            logger.info(
                "Deleted %d chunks for project %s.",
                len(docs_to_delete),
                project_id,
            )

    async def get_chunk_with_neighbors(
        self, chunk_id: str, project_id: str
    ) -> dict:
        """
        Get a specific chunk and its neighboring chunks for context expansion.

        Returns a dict with 'chunk', 'previous', and 'next' keys.
        """
        search_client = self._get_search_client()

        # Retrieve the target chunk
        try:
            chunk = search_client.get_document(key=chunk_id)
        except Exception:
            return {"chunk": None, "previous": None, "next": None}

        chunk_dict: dict[str, Any] = dict(chunk)
        file_id = chunk_dict.get("file_id", "")

        # Search for neighboring chunks in the same file
        filter_expr = (
            f"project_id eq '{project_id}' and file_id eq '{file_id}'"
        )

        results = search_client.search(
            search_text="*",
            filter=filter_expr,
            select=[
                "chunk_id",
                "file_id",
                "file_name",
                "content",
                "page_number",
                "section_heading",
            ],
            top=100,
            order_by=["chunk_id asc"],
        )

        all_chunks = [dict(r) for r in results]

        # Find the target chunk's position and get neighbors
        previous = None
        next_chunk = None
        for i, c in enumerate(all_chunks):
            if c["chunk_id"] == chunk_id:
                if i > 0:
                    previous = all_chunks[i - 1]
                if i < len(all_chunks) - 1:
                    next_chunk = all_chunks[i + 1]
                break

        return {
            "chunk": chunk_dict,
            "previous": previous,
            "next": next_chunk,
        }
