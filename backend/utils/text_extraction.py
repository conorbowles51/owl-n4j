"""
Text extraction utility for extracting text from various file types.
"""

from pathlib import Path
from typing import Optional


def extract_text_from_file(file_path: Path) -> Optional[str]:
    """
    Extract text from a file based on its extension.
    
    Args:
        file_path: Path to the file
        
    Returns:
        Extracted text or None if extraction fails
    """
    if not file_path.exists():
        return None
    
    extension = file_path.suffix.lower()
    
    try:
        if extension == '.txt':
            # Plain text file
            try:
                return file_path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                return file_path.read_text(encoding='latin-1')
        
        elif extension == '.pdf':
            # PDF file
            try:
                from pypdf import PdfReader
                reader = PdfReader(str(file_path))
                chunks = []
                for i, page in enumerate(reader.pages):
                    page_text = page.extract_text() or ""
                    if page_text.strip():
                        chunks.append(page_text)
                return "\n\n".join(chunks)
            except ImportError:
                print("[Text Extraction] pypdf not available for PDF extraction")
                return None
            except Exception as e:
                print(f"[Text Extraction] Failed to extract PDF text: {e}")
                return None
        
        elif extension in ['.doc', '.docx']:
            # Word document
            try:
                from docx import Document
                doc = Document(str(file_path))
                return "\n".join([para.text for para in doc.paragraphs])
            except ImportError:
                print("[Text Extraction] python-docx not available for Word extraction")
                return None
            except Exception as e:
                print(f"[Text Extraction] Failed to extract Word text: {e}")
                return None
        
        else:
            # Try to read as text for other file types
            try:
                return file_path.read_text(encoding='utf-8')
            except (UnicodeDecodeError, Exception):
                return None
                
    except Exception as e:
        print(f"[Text Extraction] Error extracting text from {file_path}: {e}")
        return None
