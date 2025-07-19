from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/youc", tags=["starter"])