from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/yuka", tags=["yukachin"])