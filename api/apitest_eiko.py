from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/eiko", tags=["eichan"])