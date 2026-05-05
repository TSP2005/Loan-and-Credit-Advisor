"""
Document upload router — handles file uploads and extraction.
"""
import os
import uuid
import shutil
from datetime import datetime, timezone
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from auth.jwt_handler import get_current_user
from auth.service import user_service
from config import settings
from logger import get_logger, log_action

logger = get_logger("document_router")
router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Upload a document for parsing and profile enrichment."""
    user_id = current_user.get("sub")
    log_action(logger, "info", "document_router", "ENDPOINT_HIT",
               f"POST /documents/upload | user_id={user_id} | file={file.filename} | "
               f"content_type={file.content_type}")

    try:
        # Save uploaded file
        file_ext = os.path.splitext(file.filename)[1] if file.filename else ".txt"
        saved_name = f"{user_id}_{uuid.uuid4().hex[:8]}{file_ext}"
        save_path = os.path.join(settings.UPLOAD_DIR, saved_name)

        with open(save_path, "wb") as f:
            content = await file.read()
            f.write(content)

        file_size = len(content)
        log_action(logger, "info", "document_router", "FILE_SAVED",
                   f"user_id={user_id} | file={saved_name} | size={file_size} bytes")

        # Try to extract content and update profile
        extraction_result = _extract_and_update(save_path, user_id)

        log_action(logger, "info", "document_router", "UPLOAD_COMPLETE",
                   f"user_id={user_id} | file={file.filename} | extraction_success={extraction_result.get('success', False)}")

        return {
            "success": True,
            "message": "Document uploaded and processed",
            "file": file.filename,
            "size_bytes": file_size,
            "extraction": extraction_result
        }

    except Exception as e:
        log_action(logger, "error", "document_router", "UPLOAD_FAILED",
                   f"user_id={user_id} | file={file.filename} | error={str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


def _extract_and_update(file_path: str, user_id: str) -> dict:
    """Extract financial info from document and optionally update profile."""
    try:
        ext = os.path.splitext(file_path)[1].lower()

        if ext == '.txt':
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        elif ext == '.pdf':
            try:
                from PyPDF2 import PdfReader
                reader = PdfReader(file_path)
                content = " ".join(page.extract_text() or "" for page in reader.pages)
            except ImportError:
                content = "[PDF parsing requires PyPDF2]"
        else:
            content = ""

        if not content:
            return {"success": False, "message": "Could not extract content"}

        # Simple extraction
        # AI LLM Extraction
        try:
            from langchain_groq import ChatGroq
            from langchain_core.prompts import PromptTemplate
            from langchain_core.output_parsers import JsonOutputParser
            from pydantic import BaseModel, Field
            from typing import Optional

            class FinancialExtraction(BaseModel):
                annual_income: Optional[float] = Field(description="Annual or yearly income in INR. If monthly income is given, multiply by 12.")
                credit_score: Optional[int] = Field(description="Credit score or CIBIL score (usually 300 to 900).")
                existing_emi_amount: Optional[float] = Field(description="Existing or current monthly EMI amount in INR.")
                employment_months: Optional[int] = Field(description="Total months of employment. Convert years to months if needed.")
                existing_loans: Optional[int] = Field(description="Number of existing active loans.")
                age: Optional[int] = Field(description="Age of the applicant.")
                employer_name: Optional[str] = Field(description="Name of the employer or company.")

            llm = ChatGroq(model_name="llama-3.1-8b-instant", temperature=0)
            parser = JsonOutputParser(pydantic_object=FinancialExtraction)

            prompt = PromptTemplate(
                template=(
                    "Extract financial data from this document. "
                    "**Rules**: Return null for missing values. Do not infer or estimate. "
                    "Only extract explicitly stated numbers.\n\n"
                    "{format_instructions}\n\n"
                    "Document:\n{context}\n"
                ),
                input_variables=["context"],
                partial_variables={"format_instructions": parser.get_format_instructions()},
            )

            chain = prompt | llm | parser
            
            # Send up to the first 4000 characters to process
            llm_result = chain.invoke({"context": content[:4000]})
            
            extracted = {}
            for k, v in llm_result.items():
                if v is not None and v != "":
                    extracted[k] = v
                    
        except Exception as e:
            log_action(logger, "error", "document_router", "LLM_EXTRACTION_FAILED", str(e))
            extracted = {}

        # Update profile if we extracted anything
        if extracted:
            user_service.update_profile(user_id, extracted)
            log_action(logger, "info", "document_router", "PROFILE_AUTO_UPDATED",
                       f"user_id={user_id} | fields={list(extracted.keys())}")

        return {
            "success": True,
            "extracted_fields": extracted,
            "content_preview": content[:200]
        }

    except Exception as e:
        return {"success": False, "error": str(e)}
