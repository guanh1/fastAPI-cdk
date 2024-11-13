# main.py
from fastapi import FastAPI

app = FastAPI(title="Backend API")


@app.get("/")
async def root():
    return {"This is the root of the API"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=80)
