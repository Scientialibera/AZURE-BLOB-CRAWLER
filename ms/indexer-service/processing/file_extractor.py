"""
File processing service for extracting content from various file types

This module handles file content extraction from different formats including
text files, PDFs, Word documents, and JSON files with intelligent structure preservation.
"""

import io
import json
import logging
import PyPDF2
from docx import Document
from typing import Tuple, List, Any

from azure_clients import DirectBlobClient

from config.settings import (
    MAX_FILE_SIZE_MB, SUPPORTED_TEXT_EXTENSIONS, SUPPORTED_STRUCTURED_EXTENSIONS,
    SUPPORTED_DOCUMENT_EXTENSIONS, TEXT_ENCODING, TEXT_ENCODING_ERRORS,
    PARAGRAPHS_PER_PAGE, PAGE_PREFIX, SECTION_PREFIX, PAGE_SUFFIX
)

logger = logging.getLogger(__name__)


class FileExtractor:
    """
    Handles content extraction from various file types
    
    This class provides methods for extracting text content from different file formats
    while preserving document structure and metadata.
    """
    
    def __init__(self, blob_client: DirectBlobClient):
        """
        Initialize the file extractor
        
        Args:
            blob_client: Azure Blob Storage client instance
        """
        self.blob_client = blob_client
    
    async def extract_content_and_pages(self, blob_name: str, container_name: str) -> Tuple[str, List[str]]:
        """
        Extract content and pages from blob based on file type
        
        Args:
            blob_name: Name of the blob to extract content from
            container_name: Container containing the blob
            
        Returns:
            Tuple[str, List[str]]: (full_content, pages_list)
            
        Raises:
            ValueError: If blob client not initialized or file too large
            Exception: If content extraction fails
        """
        try:
            if not self.blob_client:
                raise ValueError("Blob client not initialized")
                
            blob_client = self.blob_client.get_blob_client(
                container=container_name, 
                blob=blob_name
            )
            
            # Check file size
            blob_properties = await blob_client.get_blob_properties()
            file_size_mb = blob_properties.size / (1024 * 1024)
            
            if file_size_mb > MAX_FILE_SIZE_MB:
                logger.warning(f"File {blob_name} ({file_size_mb:.2f}MB) exceeds size limit ({MAX_FILE_SIZE_MB}MB)")
                return f"File too large: {blob_name} ({file_size_mb:.2f}MB)", []
            
            # Download blob content
            blob_data = await blob_client.download_blob()
            content = await blob_data.readall()
            
            file_extension = blob_name.lower().split('.')[-1] if '.' in blob_name else ''
            
            if file_extension in SUPPORTED_TEXT_EXTENSIONS:
                text_content = content.decode(TEXT_ENCODING, errors=TEXT_ENCODING_ERRORS)
                return text_content, [text_content]  # Single page for text files
            
            elif file_extension in SUPPORTED_STRUCTURED_EXTENSIONS:
                try:
                    json_data = json.loads(content.decode(TEXT_ENCODING))
                    text_content = self._extract_text_from_json(json_data)
                    return text_content, [text_content]
                except json.JSONDecodeError:
                    text_content = content.decode(TEXT_ENCODING, errors=TEXT_ENCODING_ERRORS)
                    return text_content, [text_content]
            
            elif file_extension in SUPPORTED_DOCUMENT_EXTENSIONS:
                if file_extension == 'pdf':
                    return await self._extract_pdf_content(content)
                elif file_extension in ['docx', 'doc']:
                    return await self._extract_docx_content(content)
            
            else:
                # For other file types, return metadata
                content_text = f"Binary file: {blob_name} (Size: {file_size_mb:.2f}MB, Type: {file_extension})"
                return content_text, [content_text]
                
        except Exception as e:
            logger.error(f"Failed to extract content from {blob_name}: {e}")
            raise
    
    async def _extract_pdf_content(self, content: bytes) -> Tuple[str, List[str]]:
        """
        Extract content from PDF, preserving page structure
        
        Args:
            content: PDF file content as bytes
            
        Returns:
            Tuple[str, List[str]]: (full_content, pages_list)
        """
        try:
            pdf_file = io.BytesIO(content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            pages = []
            full_content = ""
            
            for page_num, page in enumerate(pdf_reader.pages):
                try:
                    page_text = page.extract_text()
                    if page_text.strip():
                        page_content = f"{PAGE_PREFIX}{page_num + 1}{PAGE_SUFFIX}\n{page_text.strip()}"
                        pages.append(page_content)
                        full_content += page_content + "\n\n"
                except Exception as e:
                    logger.warning(f"Failed to extract text from PDF page {page_num + 1}: {e}")
                    continue
            
            if not pages:
                return "No readable text found in PDF", []
            
            return full_content.strip(), pages
            
        except Exception as e:
            logger.error(f"Failed to process PDF: {e}")
            return "PDF processing failed", []
    
    async def _extract_docx_content(self, content: bytes) -> Tuple[str, List[str]]:
        """
        Extract content from DOCX, preserving paragraph structure
        
        Args:
            content: DOCX file content as bytes
            
        Returns:
            Tuple[str, List[str]]: (full_content, pages_list)
        """
        try:
            docx_file = io.BytesIO(content)
            doc = Document(docx_file)
            
            pages = []
            current_page = ""
            paragraph_count = 0
            paragraphs_per_page = PARAGRAPHS_PER_PAGE  # Arbitrary page break
            
            full_content = ""
            
            for paragraph in doc.paragraphs:
                para_text = paragraph.text.strip()
                if para_text:
                    current_page += para_text + "\n"
                    paragraph_count += 1
                    
                    # Create artificial "pages" based on paragraph count
                    if paragraph_count >= paragraphs_per_page:
                        if current_page.strip():
                            page_content = f"{SECTION_PREFIX}{len(pages) + 1}{PAGE_SUFFIX}\n{current_page.strip()}"
                            pages.append(page_content)
                            full_content += page_content + "\n\n"
                        current_page = ""
                        paragraph_count = 0
            
            # Add remaining content as final page
            if current_page.strip():
                page_content = f"{SECTION_PREFIX}{len(pages) + 1}{PAGE_SUFFIX}\n{current_page.strip()}"
                pages.append(page_content)
                full_content += page_content + "\n\n"
            
            if not pages:
                return "No readable text found in document", []
            
            return full_content.strip(), pages
            
        except Exception as e:
            logger.error(f"Failed to process DOCX: {e}")
            return "DOCX processing failed", []
    
    def _extract_text_from_json(self, data: Any) -> str:
        """
        Recursively extract text values from JSON
        
        Args:
            data: JSON data to extract text from
            
        Returns:
            str: Extracted text content
        """
        if isinstance(data, dict):
            texts = []
            for key, value in data.items():
                # Include key names for context
                text_value = self._extract_text_from_json(value)
                if text_value:
                    texts.append(f"{key}: {text_value}")
            return '\n'.join(texts)
        elif isinstance(data, list):
            texts = []
            for i, item in enumerate(data):
                text_value = self._extract_text_from_json(item)
                if text_value:
                    texts.append(f"[{i}] {text_value}")
            return '\n'.join(texts)
        elif isinstance(data, str):
            return data
        else:
            return str(data)
