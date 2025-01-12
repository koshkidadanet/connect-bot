import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from database import SessionLocal
from models import TelegramUser, RankedProfiles
import numpy as np
from typing import List, Dict, Any, Optional
import os
import torch
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from sklearn.metrics.pairwise import cosine_similarity

class VectorStore:
    def __init__(self, persist_directory: str = "chroma_db", batch_size: int = 32):
        self.persist_directory = persist_directory
        
        # Configure client settings
        settings = Settings(
            anonymized_telemetry=False,
            is_persistent=True,
            persist_directory=persist_directory
        )
        
        # Initialize persistent client with proper settings
        self.chroma_client = chromadb.PersistentClient(
            path=persist_directory,
            settings=settings
        )
        
        # Initialize the embedding model with GPU support if available
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Using device: {device} for embeddings generation")
        self.model = SentenceTransformer('intfloat/multilingual-e5-small', device=device)
        
        # Get existing collections or create new ones
        self.about_collection = self.chroma_client.get_or_create_collection(
            name="about_me_vectors",
            metadata={"description": "User about_me embeddings"}
        )
        self.looking_collection = self.chroma_client.get_or_create_collection(
            name="looking_for_vectors",
            metadata={"description": "User looking_for embeddings"}
        )
        print("Collections initialized successfully")
        
        self.batch_size = batch_size
        self._embedding_cache = {}  # Simple in-memory cache
        self.executor = ThreadPoolExecutor(max_workers=4)  # For parallel processing

    @lru_cache(maxsize=1024)
    def _get_embedding_cached(self, text: str) -> np.ndarray:
        """Cached version of embedding generation"""
        return np.array(self._get_embedding(text))

    def _get_embeddings_batch(self, texts: List[str]) -> List[np.ndarray]:
        """Generate embeddings in batches for better performance"""
        # First check cache
        embeddings = []
        texts_to_encode = []
        
        for text in texts:
            if text in self._embedding_cache:
                embeddings.append(self._embedding_cache[text])
            else:
                texts_to_encode.append(text)
        
        if texts_to_encode:
            # Generate embeddings in batches
            for i in range(0, len(texts_to_encode), self.batch_size):
                batch = texts_to_encode[i:i + self.batch_size]
                batch_embeddings = self.model.encode(batch)
                
                # Update cache and add to results
                for text, embedding in zip(batch, batch_embeddings):
                    self._embedding_cache[text] = embedding
                    embeddings.append(embedding)
        
        return embeddings

    def _get_embedding(self, text: str) -> List[float]:
        # Convert embedding to list and normalize
        return self.model.encode(text).tolist()

    def update_user_vectors(self, user: TelegramUser) -> None:
        """Update or create vector embeddings for a single user"""
        user_id = str(user.id)
        
        # Generate embeddings using cached version
        about_embedding = self._get_embedding_cached(user.about_me)
        looking_embedding = self._get_embedding_cached(user.looking_for)
        
        # Update collections with numpy arrays
        try:
            self.about_collection.upsert(
                ids=[user_id],
                embeddings=[about_embedding.tolist()],
                metadatas=[{"telegram_id": user.telegram_id}]
            )
            self.looking_collection.upsert(
                ids=[user_id],
                embeddings=[looking_embedding.tolist()],
                metadatas=[{"telegram_id": user.telegram_id}]
            )
        except Exception as e:
            print(f"Error updating vectors: {e}")

    def delete_user_vectors(self, user_id: str) -> None:
        """Delete vector embeddings for a user"""
        try:
            self.about_collection.delete(ids=[user_id])
            self.looking_collection.delete(ids=[user_id])
        except Exception as e:
            print(f"Error deleting user vectors: {e}")

    def reset_collections(self) -> None:
        """Reset ChromaDB collections by deleting and recreating them"""
        try:
            # Only delete if collections exist
            try:
                self.chroma_client.delete_collection("about_me_vectors")
                self.chroma_client.delete_collection("looking_for_vectors")
                print("Existing collections deleted")
            except Exception as e:
                print(f"No collections to delete: {e}")
            
            # Create new collections
            self.about_collection = self.chroma_client.create_collection(
                name="about_me_vectors",
                metadata={"description": "User about_me embeddings"}
            )
            self.looking_collection = self.chroma_client.create_collection(
                name="looking_for_vectors",
                metadata={"description": "User looking_for embeddings"}
            )
            print("New collections created")
        except Exception as e:
            print(f"Error resetting collections: {e}")

    def _content_changed(self, user: TelegramUser, user_id: str) -> bool:
        """Enhanced change detection with cached embeddings"""
        try:
            # Get current vectors
            about_results = self.about_collection.get(
                ids=[user_id],
                include=["embeddings"]
            )
            looking_results = self.looking_collection.get(
                ids=[user_id],
                include=["embeddings"]
            )
            
            if not about_results["embeddings"] or not looking_results["embeddings"]:
                return True
            
            # Use cached embeddings for comparison
            new_about_embedding = self._get_embedding_cached(user.about_me)
            new_looking_embedding = self._get_embedding_cached(user.looking_for)
            
            # Compare with cosine similarity
            about_similarity = cosine_similarity(
                new_about_embedding.reshape(1, -1),
                np.array(about_results["embeddings"][0]).reshape(1, -1)
            )[0][0]
            
            looking_similarity = cosine_similarity(
                new_looking_embedding.reshape(1, -1),
                np.array(looking_results["embeddings"][0]).reshape(1, -1)
            )[0][0]
            
            # Consider changed if similarity is below threshold
            return about_similarity < 0.999 or looking_similarity < 0.999
            
        except Exception:
            return True

    def sync_with_database(self) -> None:
        """Enhanced synchronization with parallel processing"""
        db = SessionLocal()
        try:
            # Get all users and existing IDs
            users = db.query(TelegramUser).all()
            existing_ids = set(self.about_collection.get()["ids"])
            
            # Prepare batches for vector operations
            to_update = []
            to_delete = []
            
            for user in users:
                user_id = str(user.id)
                if user_id not in existing_ids or self._content_changed(user, user_id):
                    to_update.append(user)
            
            # Find IDs to delete
            current_ids = {str(user.id) for user in users}
            to_delete = list(existing_ids - current_ids)
            
            # Parallel processing for updates
            if to_update:
                # Process updates in parallel
                with ThreadPoolExecutor() as executor:
                    list(executor.map(self.update_user_vectors, to_update))
            
            # Handle deletions
            if to_delete:
                self.about_collection.delete(ids=to_delete)
                self.looking_collection.delete(ids=to_delete)
                
        finally:
            db.close()

    def find_similar_profiles(self, 
                            user: TelegramUser, 
                            n_results: int = 5,
                            about_weight: float = 0.5) -> List[int]:
        """Enhanced profile matching with explicit cosine similarity"""
        # Generate query embeddings
        about_embedding = self._get_embedding_cached(user.about_me)
        looking_embedding = self._get_embedding_cached(user.looking_for)
        
        # Get results from both collections
        about_results = self.about_collection.get(include=["embeddings", "metadatas"])
        looking_results = self.looking_collection.get(include=["embeddings", "metadatas"])
        
        if not about_results["embeddings"] or not looking_results["embeddings"]:
            return []
        
        # Convert embeddings to numpy arrays
        about_embeddings = [np.array(emb) for emb in about_results["embeddings"]]
        looking_embeddings = [np.array(emb) for emb in looking_results["embeddings"]]
        
        # Compute similarities
        about_similarities = self._compute_similarity_scores(about_embedding, about_embeddings)
        looking_similarities = self._compute_similarity_scores(looking_embedding, looking_embeddings)
        
        # Combine scores with weights
        combined_scores = about_weight * about_similarities + (1 - about_weight) * looking_similarities
        
        # Create mapping of indices to telegram_ids
        telegram_ids = [meta["telegram_id"] for meta in about_results["metadatas"]]
        
        # Sort by combined scores and filter out the query user
        scored_pairs = [
            (score, tid) for score, tid in zip(combined_scores, telegram_ids)
            if tid != user.telegram_id
        ]
        scored_pairs.sort(reverse=True)  # Sort by similarity (highest first)
        
        # Return top n telegram_ids
        return [tid for _, tid in scored_pairs[:n_results]]

    def _compute_similarity_scores(self, query_embedding: np.ndarray, target_embeddings: List[np.ndarray]) -> np.ndarray:
        """Compute cosine similarity scores"""
        if not target_embeddings:
            return np.array([])
        
        # Reshape query embedding to 2D array
        query_2d = query_embedding.reshape(1, -1)
        target_2d = np.vstack(target_embeddings)
        
        # Compute cosine similarity
        similarities = cosine_similarity(query_2d, target_2d)[0]
        return similarities

    def inspect_collections(self) -> Dict[str, Any]:
        """Return a summary of the current state of ChromaDB collections"""
        summary = {
            "about_me_collection": {
                "count": self.about_collection.count(),
                "entries": []
            },
            "looking_for_collection": {
                "count": self.looking_collection.count(),
                "entries": []
            }
        }
        
        # Get all entries from about_me collection
        if summary["about_me_collection"]["count"] > 0:
            about_results = self.about_collection.get(
                include=["embeddings", "metadatas"]
            )
            summary["about_me_collection"]["entries"] = [
                {"telegram_id": meta["telegram_id"]}
                for meta in about_results["metadatas"]
            ]
        
        # Get all entries from looking_for collection
        if summary["looking_for_collection"]["count"] > 0:
            looking_results = self.looking_collection.get(
                include=["embeddings", "metadatas"]
            )
            summary["looking_for_collection"]["entries"] = [
                {"telegram_id": meta["telegram_id"]}
                for meta in looking_results["metadatas"]
            ]
        
        return summary

    def _get_db_id_by_telegram_id(self, telegram_id: int) -> str:
        """Convert telegram_id to database ID"""
        with SessionLocal() as db:
            user = db.query(TelegramUser).filter(TelegramUser.telegram_id == telegram_id).first()
            return str(user.id) if user else None

    def get_user_embeddings(self, telegram_id: int) -> Dict[str, Any]:
        """Get and display embeddings for a specific user by telegram_id"""
        try:
            # Convert telegram_id to database ID
            db_id = self._get_db_id_by_telegram_id(int(telegram_id))
            if not db_id:
                print(f"User with telegram_id {telegram_id} not found in database")
                return None

            about_results = self.about_collection.get(
                ids=[db_id],  # Use database ID here
                include=["embeddings", "metadatas"]
            )
            looking_results = self.looking_collection.get(
                ids=[db_id],  # Use database ID here
                include=["embeddings", "metadatas"]
            )
            
            return {
                "about_me": {
                    "embedding": about_results["embeddings"][0],
                    "metadata": about_results["metadatas"][0]
                },
                "looking_for": {
                    "embedding": looking_results["embeddings"][0],
                    "metadata": looking_results["metadatas"][0]
                }
            }
        except Exception as e:
            print(f"Error getting embeddings for telegram_id {telegram_id}: {e}")
            return None

    def compute_rankings(self, user: TelegramUser) -> List[Dict[str, Any]]:
        """Compute ranked profiles for a user based on looking_for vs about_me similarity"""
        looking_for_embedding = self._get_embedding(user.looking_for)
        
        # Query about_me collection for similar profiles
        results = self.about_collection.query(
            query_embeddings=[looking_for_embedding],
            n_results=100,
            include=["metadatas", "distances"]
        )
        
        # Format results
        ranked_profiles = []
        for idx, (telegram_id, distance) in enumerate(zip(
            results['metadatas'][0], results['distances'][0]
        )):
            if telegram_id['telegram_id'] != user.telegram_id:  # Exclude self
                ranked_profiles.append({
                    'target_telegram_id': telegram_id['telegram_id'],
                    'rank': idx,
                    'similarity_score': 1.0 - distance  # Convert distance to similarity
                })
        return ranked_profiles

    def update_user_rankings(self, user: TelegramUser) -> None:
        """Update rankings in database for a user"""
        with SessionLocal() as db:
            # Delete existing rankings
            db.query(RankedProfiles).filter(RankedProfiles.user_id == user.id).delete()
            
            # Compute new rankings
            rankings = self.compute_rankings(user)
            
            # Insert new rankings
            for ranking in rankings:
                target_user = db.query(TelegramUser).filter(
                    TelegramUser.telegram_id == ranking['target_telegram_id']
                ).first()
                if target_user:
                    ranked_profile = RankedProfiles(
                        user_id=user.id,
                        target_user_id=target_user.id,
                        rank=ranking['rank'],
                        similarity_score=ranking['similarity_score']
                    )
                    db.add(ranked_profile)
            
            db.commit()

    def handle_user_update(self, user: TelegramUser, delete: bool = False) -> None:
        """Handle user profile updates in vector store"""
        try:
            if delete:
                self.delete_user_vectors(str(user.id))
            else:
                self.update_user_vectors(user)
                # Update rankings when profile changes
                self.update_user_rankings(user)
        except Exception as e:
            print(f"Error handling vector store update: {e}")

# Initialize global vector store
vector_store = VectorStore()

def initialize_vector_store():
    """Initialize and sync vector store with database"""
    vector_store.sync_with_database()

if __name__ == "__main__":
    initialize_vector_store()  # This will now clean up and repopulate
    
    # Show summary
    summary = vector_store.inspect_collections()
    print("\nChromaDB Collections Summary:")
    print(f"About Me Collection: {summary['about_me_collection']['count']} entries")
    print("Telegram IDs:", [e['telegram_id'] for e in summary['about_me_collection']['entries']])
    print(f"\nLooking For Collection: {summary['looking_for_collection']['count']} entries")
    print("Telegram IDs:", [e['telegram_id'] for e in summary['looking_for_collection']['entries']])
    
    telegram_id = input("\nEnter Telegram ID to inspect embeddings (or press Enter to skip): ")
    if telegram_id:
        embeddings = vector_store.get_user_embeddings(int(telegram_id))
        if embeddings:
            print(f"\nEmbeddings for Telegram ID {telegram_id}:")
            print(f"Telegram ID: {embeddings['about_me']['metadata']['telegram_id']}")
            print("\nAbout Me embedding (first 10 dimensions):")
            print(embeddings['about_me']['embedding'][:10])
            print("\nLooking For embedding (first 10 dimensions):")
            print(embeddings['looking_for']['embedding'][:10])