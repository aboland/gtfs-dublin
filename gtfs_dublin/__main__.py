# Entrypoint for FastAPI server

if __name__ == "__main__":
    import uvicorn

    from gtfs_dublin.transport_api_server import app

    uvicorn.run(app, host="0.0.0.0", port=8000)
