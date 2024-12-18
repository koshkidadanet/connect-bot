import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from database import SessionLocal
from models import TelegramUser, RankedProfiles
import numpy as np
from typing import List, Dict, Any
import os
import torch

class VectorStore:
    def __init__(self, persist_directory: str = "chroma_db"):
        self.persist_directory = persist_directory
        self.chroma_client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Initialize the embedding model with GPU support if available
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Using device: {device} for embeddings generation")
        self.model = SentenceTransformer('intfloat/multilingual-e5-small', device=device)
        
        # Create or get collections for about_me and looking_for
        self.about_collection = self.chroma_client.get_or_create_collection(
            name="about_me_vectors",
            metadata={"description": "User about_me embeddings"}
        )
        self.looking_collection = self.chroma_client.get_or_create_collection(
            name="looking_for_vectors",
            metadata={"description": "User looking_for embeddings"}
        )

    def _get_embedding(self, text: str) -> List[float]:
        # Convert embedding to list and normalize
        return self.model.encode(text).tolist()

    def update_user_vectors(self, user: TelegramUser) -> None:
        """Update or create vector embeddings for a single user"""
        user_id = str(user.id)
        
        # Generate embeddings
        about_embedding = self._get_embedding(user.about_me)
        looking_embedding = self._get_embedding(user.looking_for)
        
        # Update about_me collection
        try:
            self.about_collection.upsert(
                ids=[user_id],
                embeddings=[about_embedding],
                metadatas=[{"telegram_id": user.telegram_id}]
            )
        except Exception as e:
            print(f"Error updating about_me vectors: {e}")

        # Update looking_for collection
        try:
            self.looking_collection.upsert(
                ids=[user_id],
                embeddings=[looking_embedding],
                metadatas=[{"telegram_id": user.telegram_id}]
            )
        except Exception as e:
            print(f"Error updating looking_for vectors: {e}")

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
            # Delete existing collections if they exist
            self.chroma_client.delete_collection("about_me_vectors")
            self.chroma_client.delete_collection("looking_for_vectors")
            
            # Recreate collections
            self.about_collection = self.chroma_client.create_collection(
                name="about_me_vectors",
                metadata={"description": "User about_me embeddings"}
            )
            self.looking_collection = self.chroma_client.create_collection(
                name="looking_for_vectors",
                metadata={"description": "User looking_for embeddings"}
            )
        except Exception as e:
            print(f"Error resetting collections: {e}")

    def sync_with_database(self) -> None:
        """Synchronize vector store with the PostgreSQL database"""
        db = SessionLocal()
        try:
            # Reset collections before syncing
            self.reset_collections()
            
            users = db.query(TelegramUser).all()
            for user in users:
                self.update_user_vectors(user)
        finally:
            db.close()

    def find_similar_profiles(self, 
                            user: TelegramUser, 
                            n_results: int = 5,
                            about_weight: float = 0.5) -> List[int]:
        """
        Find similar profiles based on weighted combination of about_me and looking_for
        Returns list of telegram_ids sorted by similarity
        """
        about_embedding = self._get_embedding(user.about_me)
        looking_embedding = self._get_embedding(user.looking_for)
        
        # Get results from both collections
        about_results = self.about_collection.query(
            query_embeddings=[about_embedding],
            n_results=n_results * 2,  # Get more results for better filtering
            include=["metadatas"]
        )
        
        looking_results = self.looking_collection.query(
            query_embeddings=[looking_embedding],
            n_results=n_results * 2,
            include=["metadatas"]
        )
        
        # Combine and weight results
        results_dict = {}
        
        # Process about_me results
        for idx, score in enumerate(about_results['distances'][0]):
            telegram_id = about_results['metadatas'][0][idx]['telegram_id']
            if telegram_id != user.telegram_id:  # Exclude the query user
                results_dict[telegram_id] = score * about_weight
                
        # Process looking_for results
        for idx, score in enumerate(looking_results['distances'][0]):
            telegram_id = looking_results['metadatas'][0][idx]['telegram_id']
            if telegram_id != user.telegram_id:  # Exclude the query user
                results_dict[telegram_id] = results_dict.get(telegram_id, 0) + score * (1 - about_weight)
        
        # Sort by combined scores and return top n_results
        sorted_results = sorted(results_dict.items(), key=lambda x: x[1])
        return [tid for tid, _ in sorted_results[:n_results]]

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