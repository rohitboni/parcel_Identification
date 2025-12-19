"""
Service 3: Identify API Service
Port: 8003 (internal, accessed via API Gateway on port 8000)
Purpose: Parcel identification and metadata endpoints
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from identify_api.identify_server import router as identify_router

app = FastAPI(title="Identify API Service", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all identify API endpoints
app.include_router(identify_router, prefix="/api")

@app.get("/health")
def health():
    return {"status": "ok", "service": "identify-api"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8003)

