"""
Text chunking utilities for intelligent document processing

This module provides token-aware text chunking with support for different document types
and intelligent boundary preservation (sentences, pages, sections).
"""

import re
import logging
import tiktoken
from typing import List

from config.settings import (
    ENCODING_MODEL, TIKTOKEN_FALLBACK_MODEL, CHUNK_MAX_TOKENS, OVERLAP_TOKENS,
    EMBEDDING_FALLBACK_TOKEN_RATIO
)

logger = logging.getLogger(__name__)


class TokenAwareChunker:
    """
    Handles intelligent text chunking with token limits
    
    This class provides methods for chunking text while respecting token limits
    and preserving document structure (sentences, pages, sections).
    """
    
    def __init__(self, encoding_model: str = ENCODING_MODEL):
        """
        Initialize tokenizer
        
        Args:
            encoding_model: The tokenizer model to use (e.g., 'cl100k_base')
        """
        try:
            self.tokenizer = tiktoken.get_encoding(encoding_model)
        except Exception as e:
            logger.warning(f"Failed to load tokenizer {encoding_model}, using fallback: {e}")
            self.tokenizer = tiktoken.get_encoding(TIKTOKEN_FALLBACK_MODEL)
    
    def count_tokens(self, text: str) -> int:
        """
        Count tokens in text
        
        Args:
            text: The text to count tokens for
            
        Returns:
            int: Number of tokens in the text
        """
        try:
            return len(self.tokenizer.encode(text))
        except Exception as e:
            logger.warning(f"Token counting failed, using character estimation: {e}")
            return len(text) // EMBEDDING_FALLBACK_TOKEN_RATIO  # Rough estimation: 1 token ≈ 4 characters
    
    def chunk_text(self, text: str, max_tokens: int = CHUNK_MAX_TOKENS, 
                  overlap_tokens: int = OVERLAP_TOKENS) -> List[str]:
        """
        Chunk text intelligently without breaking sentences
        
        Args:
            text: The text to chunk
            max_tokens: Maximum tokens per chunk
            overlap_tokens: Number of tokens to overlap between chunks
            
        Returns:
            List[str]: List of text chunks
        """
        if not text.strip():
            return []
        
        # If text is within limit, return as single chunk
        if self.count_tokens(text) <= max_tokens:
            return [text]
        
        chunks = []
        sentences = self._split_into_sentences(text)
        
        current_chunk = ""
        current_tokens = 0
        
        for sentence in sentences:
            sentence_tokens = self.count_tokens(sentence)
            
            # If single sentence exceeds max tokens, we need to split it
            if sentence_tokens > max_tokens:
                # Add current chunk if not empty
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                    current_tokens = 0
                
                # Split the long sentence by words or characters
                sentence_chunks = self._split_long_sentence(sentence, max_tokens)
                chunks.extend(sentence_chunks[:-1])  # Add all but last
                
                # Start new chunk with last piece
                current_chunk = sentence_chunks[-1] if sentence_chunks else ""
                current_tokens = self.count_tokens(current_chunk)
            
            # If adding this sentence would exceed limit, finalize current chunk
            elif current_tokens + sentence_tokens > max_tokens:
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                
                # Handle overlap
                overlap_text = self._get_overlap_text(current_chunk, overlap_tokens)
                current_chunk = overlap_text + " " + sentence
                current_tokens = self.count_tokens(current_chunk)
            else:
                # Add sentence to current chunk
                current_chunk += " " + sentence if current_chunk else sentence
                current_tokens += sentence_tokens
        
        # Add final chunk
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def chunk_pages(self, pages: List[str], max_tokens: int = CHUNK_MAX_TOKENS) -> List[str]:
        """
        Chunk pages keeping page boundaries intact when possible
        For PDF and DOCX files - don't separate pages unless necessary
        
        Args:
            pages: List of page contents
            max_tokens: Maximum tokens per chunk
            
        Returns:
            List[str]: List of chunked content
        """
        if not pages:
            return []
        
        chunks = []
        current_chunk = ""
        current_tokens = 0
        
        for page in pages:
            page_tokens = self.count_tokens(page)
            
            # If adding this page would exceed limit, finalize current chunk
            if current_chunk and current_tokens + page_tokens > max_tokens:
                chunks.append(current_chunk.strip())
                current_chunk = page
                current_tokens = page_tokens
            elif not current_chunk:
                # First page
                current_chunk = page
                current_tokens = page_tokens
            else:
                # Add page to current chunk
                current_chunk += "\n\n" + page
                current_tokens += page_tokens
            
            # If single page exceeds max tokens, chunk it
            if page_tokens > max_tokens:
                if current_chunk != page:  # Already added to current chunk
                    chunks.append(current_chunk.replace(page, "").strip())
                
                # Chunk the oversized page
                page_chunks = self.chunk_text(page, max_tokens)
                chunks.extend(page_chunks[:-1])  # Add all but last
                current_chunk = page_chunks[-1] if page_chunks else ""
                current_tokens = self.count_tokens(current_chunk)
        
        # Add final chunk
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences using regex
        
        Args:
            text: The text to split
            
        Returns:
            List[str]: List of sentences
        """
        # Improved sentence splitting that handles common abbreviations
        sentence_endings = r'[.!?]+(?:\s+|$)'
        sentences = re.split(sentence_endings, text)
        
        # Clean up and filter empty sentences
        sentences = [s.strip() for s in sentences if s.strip()]
        return sentences
    
    def _split_long_sentence(self, sentence: str, max_tokens: int) -> List[str]:
        """
        Split a sentence that's too long by words
        
        Args:
            sentence: The sentence to split
            max_tokens: Maximum tokens per chunk
            
        Returns:
            List[str]: List of sentence chunks
        """
        words = sentence.split()
        chunks = []
        current_chunk = ""
        
        for word in words:
            test_chunk = current_chunk + " " + word if current_chunk else word
            if self.count_tokens(test_chunk) > max_tokens:
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = word
                else:
                    # Single word exceeds limit - split by characters
                    chunks.extend(self._split_by_characters(word, max_tokens))
                    current_chunk = ""
            else:
                current_chunk = test_chunk
        
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks
    
    def _split_by_characters(self, text: str, max_tokens: int) -> List[str]:
        """
        Split text by characters when even words are too long
        
        Args:
            text: The text to split
            max_tokens: Maximum tokens per chunk
            
        Returns:
            List[str]: List of character-based chunks
        """
        chunks = []
        chars_per_token = EMBEDDING_FALLBACK_TOKEN_RATIO  # Rough estimation
        max_chars = max_tokens * chars_per_token
        
        for i in range(0, len(text), max_chars):
            chunks.append(text[i:i + max_chars])
        
        return chunks
    
    def _get_overlap_text(self, text: str, overlap_tokens: int) -> str:
        """
        Get the last part of text for overlap
        
        Args:
            text: The text to get overlap from
            overlap_tokens: Number of tokens for overlap
            
        Returns:
            str: Overlap text
        """
        if overlap_tokens <= 0:
            return ""
        
        words = text.split()
        overlap_text = ""
        
        # Work backwards from the end
        for i in range(len(words) - 1, -1, -1):
            test_text = " ".join(words[i:]) if overlap_text == "" else " ".join(words[i:])
            if self.count_tokens(test_text) > overlap_tokens:
                break
            overlap_text = test_text
        
        return overlap_text
