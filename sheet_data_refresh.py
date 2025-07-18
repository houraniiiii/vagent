#!/usr/bin/env python3

import gspread
from google.oauth2.service_account import Credentials
import json
import uuid
from pinecone import Pinecone, ServerlessSpec
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", "google_credentials.json")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX = os.getenv("PINECONE_INDEX", "continental-property-data")
PINECONE_REGION = os.getenv("PINECONE_REGION", "us-east-1")
PINECONE_CLOUD = os.getenv("PINECONE_CLOUD", "aws")
PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "continental-property-data")
PINECONE_MAX_ROWS_IN_A_BATCH = int(os.getenv("PINECONE_MAX_ROWS_IN_A_BATCH", "100"))
PINECONE_VECTOR_DIMENSIONS = int(os.getenv("PINECONE_VECTOR_DIMENSIONS", "1536"))


def fetch_sheet_data():
    """
    Fetch data from the sheet SPREADSHEET_URL and save it to a JSON file called worksheet_data.json
    Returns the data as a list of dictionaries
    """
    SCOPES = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]

    # Authenticate and create a client
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE)
    creds_with_scope = creds.with_scopes(SCOPES)
    client = gspread.authorize(creds_with_scope)

    spreadsheet = client.open_by_url(SPREADSHEET_URL)

    worksheet = spreadsheet.get_worksheet(0)
    # Fetch all data
    data = worksheet.get_all_records()

    # Write data to a JSON file
    with open("worksheet_data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return data


def get_chunk_vectors(chunk):
    """
    Get the vectors for a chunk of data
    """
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    embedding = (
        openai_client.embeddings.create(
            input=str(chunk),
            model=OPENAI_EMBEDDING_MODEL,
            dimensions=PINECONE_VECTOR_DIMENSIONS,
        )
        .data[0]
        .embedding
    )
    return embedding


def initialize_pinecone():
    """
    Initialize pinecone index
    """
    pc = Pinecone(api_key=PINECONE_API_KEY)
    spec = ServerlessSpec(cloud=PINECONE_CLOUD, region=PINECONE_REGION)
    if PINECONE_INDEX not in pc.list_indexes().names():
        pc.create_index(PINECONE_INDEX, dimension=PINECONE_VECTOR_DIMENSIONS, spec=spec)

    pc_index = pc.Index(PINECONE_INDEX)
    return pc_index


def remove_old_vectors_from_pinecone(pc_index):
    """
    Remove old vectors from pinecone
    """
    try:
        pc_index.delete(delete_all=True, namespace=PINECONE_NAMESPACE)
    except Exception as e:
        print(f"Error removing old vectors from pinecone: {e}")


def refresh_sheet_data_in_pinecone():
    """
    Fetch data from the sheet SPREADSHEET_URL and add it to pinecone
    """
    data = fetch_sheet_data()

    data_chunks = [
        data[i : i + PINECONE_MAX_ROWS_IN_A_BATCH]
        for i in range(0, len(data), PINECONE_MAX_ROWS_IN_A_BATCH)
    ]
    chunk_vectors = []
    for chunk in data_chunks:
        chunk_vector_id = str(uuid.uuid4())
        chunk_embedding = get_chunk_vectors(chunk)
        chunk_metadata = chunk
        vector = {
            "id": chunk_vector_id,
            "values": chunk_embedding,
            "metadata": {"rows": str(chunk_metadata)},
        }
        chunk_vectors.append(vector)

    pc_index = initialize_pinecone()
    remove_old_vectors_from_pinecone(pc_index)
    pc_index.upsert(chunk_vectors, namespace=PINECONE_NAMESPACE)


if __name__ == "__main__":
    refresh_sheet_data_in_pinecone()
