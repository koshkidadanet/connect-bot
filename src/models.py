from sqlalchemy import Column, Integer, String, BigInteger, Text, ForeignKey, Enum, Float
from sqlalchemy.orm import relationship
import enum
from database import Base

class MediaType(enum.Enum):
    PHOTO = "photo"
    VIDEO = "video"

class TelegramUser(Base):
    __tablename__ = 'telegram_users'

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True)
    name = Column(String)
    age = Column(Integer)
    about_me = Column(Text)
    looking_for = Column(Text)
    
    media_files = relationship("UserMedia", back_populates="user", cascade="all, delete-orphan")

class UserMedia(Base):
    __tablename__ = 'user_media'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('telegram_users.id', ondelete='CASCADE'))
    file_id = Column(String, nullable=True)  # Set nullable=True to allow NULL values
    media_type = Column(Enum(MediaType), nullable=False)
    
    user = relationship("TelegramUser", back_populates="media_files")

class RankedProfiles(Base):
    __tablename__ = 'ranked_profiles'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('telegram_users.id', ondelete='CASCADE'))
    target_user_id = Column(Integer, ForeignKey('telegram_users.id', ondelete='CASCADE'))
    rank = Column(Integer, nullable=False)  # Position in ranked list
    similarity_score = Column(Float, nullable=False)  # Similarity score from ChromaDB
    
    user = relationship("TelegramUser", foreign_keys=[user_id])
    target_user = relationship("TelegramUser", foreign_keys=[target_user_id])