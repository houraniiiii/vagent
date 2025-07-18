import logging
import os
from openai import AsyncOpenAI
from pinecone import PineconeAsyncio, ServerlessSpec
from dotenv import load_dotenv


load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX = os.getenv("PINECONE_INDEX", "continental-property-data")
PINECONE_REGION = os.getenv("PINECONE_REGION", "us-east-1")
PINECONE_CLOUD = os.getenv("PINECONE_CLOUD", "aws")
PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "continental-property-data")
PINECONE_HOST = os.getenv("PINECONE_HOST")
PINECONE_VECTOR_DIMENSIONS = int(os.getenv("PINECONE_VECTOR_DIMENSIONS", "1536"))
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")


class PineconeHelper:
    """
    This class is used to help with the Pinecone DB.
    """

    def __init__(self):
        self._namespace = PINECONE_NAMESPACE

    async def initialize(self):
        """Async initialization method"""
        logging.info("Initializing PineconeHelper")
        async with PineconeAsyncio(api_key=PINECONE_API_KEY) as pc:
            self._pinecone_client = pc
            if not await self._pinecone_client.has_index(PINECONE_INDEX):
                await self._pinecone_client.create_index(
                    name=PINECONE_INDEX,
                    dimension=PINECONE_VECTOR_DIMENSIONS,
                    metric="cosine",
                    spec=ServerlessSpec(cloud=PINECONE_CLOUD, region=PINECONE_REGION),
                )
            self._index = self._pinecone_client.IndexAsyncio(host=PINECONE_HOST)

        self._async_openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

    async def _dense_query(self, query_vector, top_k):
        """
        Args:   query_vector (list): Query vector.
                top_k (int): Number of results to return.
        return: dict
        Asynchronously performs dense retrieval from Pinecone
        """
        try:
            result = await self._index.query(
                vector=query_vector,
                top_k=top_k,
                namespace=self._namespace,
                include_metadata=True,
            )
            documents = [
                match.get("metadata").get("rows") for match in result["matches"]
            ]
            logging.info("Documents from Pinecone: %s", documents)
            return documents

        except Exception as e:
            logging.exception("Error in dense query: %s", str(e))

    async def _get_openai_embedding(self, text):
        """
        Asynchronously get OpenAI embeddings
        """
        try:
            response = await self._async_openai_client.embeddings.create(
                input=text,
                model=OPENAI_EMBEDDING_MODEL,
                dimensions=PINECONE_VECTOR_DIMENSIONS,
            )
            return response.data[0].embedding
        except Exception as e:
            logging.error("Error getting embedding: %s", str(e))
            raise

    async def get_document_from_pinecone(self, query_vector, top_k=1):
        """
        Args:   query_vector (list): Query vector.
                top_k (int): Number of results to return.
        return: dict
        Asynchronously queries the index with the query_vector and returns top_k results.
        """
        # Ensure initialization
        if self._pinecone_client is None:
            await self.initialize()

        query_vector = await self._get_openai_embedding(query_vector)
        results = await self._dense_query(query_vector, top_k)
        return str(results)
