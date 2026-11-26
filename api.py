from fastapi import FastAPI

app = FastAPI(title="DeviceHub Fleet & Security")

@app.get("/")
def read_root():
    return {"status": "online", "service": "DeviceHub Fleet & Security Platform"}

@app.get("/health")
def health_check():
    return {"status": "ok", "auth": "open", "environment": "production"}
