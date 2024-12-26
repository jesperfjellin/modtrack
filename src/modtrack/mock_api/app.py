from fastapi import FastAPI, HTTPException
from datetime import datetime
import random

app = FastAPI()

# Mock data store
RESERVOIRS = {
    "reservoir_1": {"min": 100, "max": 150, "name": "Blue Lake"},
    "reservoir_2": {"min": 200, "max": 250, "name": "Green Valley"},
    "reservoir_3": {"min": 300, "max": 350, "name": "Mountain Peak"},
}

@app.get("/")
async def root():
    return {"status": "healthy", "service": "mock-water-api"}

@app.get("/water-level/{reservoir_id}")
async def get_water_level(reservoir_id: str):
    if reservoir_id not in RESERVOIRS:
        raise HTTPException(status_code=404, detail=f"Reservoir {reservoir_id} not found")
    
    reservoir = RESERVOIRS[reservoir_id]
    level = random.uniform(reservoir["min"], reservoir["max"])
    
    return {
        "reservoir_id": reservoir_id,
        "name": reservoir["name"],
        "timestamp": datetime.utcnow().isoformat(),
        "water_level": round(level, 2),
        "unit": "meters"
    }