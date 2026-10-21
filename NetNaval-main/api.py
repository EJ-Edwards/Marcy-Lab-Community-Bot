from fastAPI import fastAPI

app = FastAPI()

@app.get("/")
async def read_root():
    return {"status": "online"}

@app.get("/health")
def health():
    return {"ok": True}