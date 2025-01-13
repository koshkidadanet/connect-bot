import pytest
from unittest.mock import MagicMock, patch
import numpy as np
from data_science import VectorStore
from models import TelegramUser, RankedProfiles
import tempfile
import shutil

@pytest.fixture
def temp_dir():
    temp_path = tempfile.mkdtemp()
    yield temp_path
    shutil.rmtree(temp_path)

@pytest.fixture
def mock_chroma_client():
    client = MagicMock()
    about_collection = MagicMock()
    looking_collection = MagicMock()
    
    # Mock get method responses
    about_collection.get.return_value = {
        'embeddings': [[0.1] * 384],  # Match model dimension
        'metadatas': [{'telegram_id': 123}]
    }
    looking_collection.get.return_value = {
        'embeddings': [[0.1] * 384],
        'metadatas': [{'telegram_id': 123}]
    }
    
    client.get_or_create_collection.side_effect = [about_collection, looking_collection]
    return client

@pytest.fixture
def mock_embeddings():
    return np.array([0.1] * 384)

@pytest.fixture
def vector_store_with_mocks(temp_dir, mock_chroma_client, mock_embeddings):
    with patch('chromadb.PersistentClient', return_value=mock_chroma_client), \
         patch('sentence_transformers.SentenceTransformer.encode', return_value=mock_embeddings):
        store = VectorStore(persist_directory=temp_dir)
        yield store
        store.reset_collections()

@pytest.fixture
def vector_store(temp_dir, mock_chroma_client):
    with patch('chromadb.PersistentClient', return_value=mock_chroma_client):
        store = VectorStore(persist_directory=temp_dir)
        yield store
        store.reset_collections()

@pytest.fixture
def test_users():
    return [
        TelegramUser(
            id=1,
            telegram_id=123,
            name="User1",
            age=25,
            about_me="I love programming and AI",
            looking_for="Someone interested in technology"
        ),
        TelegramUser(
            id=2,
            telegram_id=456,
            name="User2",
            age=27,
            about_me="I'm passionate about technology",
            looking_for="A tech enthusiast"
        )
    ]

def test_vector_store_initialization(vector_store):
    assert vector_store.about_collection is not None
    assert vector_store.looking_collection is not None

def test_update_user_vectors(vector_store, test_users):
    user = test_users[0]
    vector_store.update_user_vectors(user)
    
    # Check if collections were called correctly
    vector_store.about_collection.upsert.assert_called_once()
    vector_store.looking_collection.upsert.assert_called_once()

def test_find_similar_profiles(vector_store, test_users):
    # Mock collection query responses
    vector_store.about_collection.get.return_value = {
        'embeddings': [[0.1] * 384],
        'metadatas': [{'telegram_id': 456}]  # Different ID than test user
    }
    vector_store.looking_collection.get.return_value = {
        'embeddings': [[0.1] * 384],
        'metadatas': [{'telegram_id': 456}]
    }
    
    similar_ids = vector_store.find_similar_profiles(test_users[0])
    assert len(similar_ids) > 0
    assert test_users[0].telegram_id not in similar_ids

def test_embedding_cache(vector_store):
    text = "Test text for embedding"
    
    # First call should compute embedding
    embedding1 = vector_store._get_embedding_cached(text)
    
    # Second call should use cache
    embedding2 = vector_store._get_embedding_cached(text)
    
    assert np.array_equal(embedding1, embedding2)

def test_content_changed_detection(vector_store_with_mocks, test_users, mock_embeddings):
    user = test_users[0]
    
    # Mock collection responses
    vector_store_with_mocks.about_collection.get.return_value = {
        'embeddings': [mock_embeddings.tolist()],
        'metadatas': [{'telegram_id': user.telegram_id}]
    }
    vector_store_with_mocks.looking_collection.get.return_value = {
        'embeddings': [mock_embeddings.tolist()],
        'metadatas': [{'telegram_id': user.telegram_id}]
    }
    
    # Test no change
    assert not vector_store_with_mocks._content_changed(user, str(user.id))
    
    # Mock different embeddings for changed content
    different_embedding = np.array([0.2] * 384)
    with patch('sentence_transformers.SentenceTransformer.encode', return_value=different_embedding):
        user.about_me = "Completely different text"
        assert vector_store_with_mocks._content_changed(user, str(user.id))

# Add more test cases for better coverage
def test_sync_with_database(vector_store_with_mocks, test_users):
    with patch('aiogram_bot.database.SessionLocal') as mock_session:
        mock_session.return_value.__enter__.return_value.query.return_value.all.return_value = test_users
        vector_store_with_mocks.sync_with_database()
        vector_store_with_mocks.about_collection.upsert.assert_called()
        vector_store_with_mocks.looking_collection.upsert.assert_called()

def test_find_similar_profiles_empty(vector_store_with_mocks, test_users):
    vector_store_with_mocks.about_collection.get.return_value = {'embeddings': [], 'metadatas': []}
    vector_store_with_mocks.looking_collection.get.return_value = {'embeddings': [], 'metadatas': []}
    
    result = vector_store_with_mocks.find_similar_profiles(test_users[0])
    assert result == []
