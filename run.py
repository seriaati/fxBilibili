from __future__ import annotations

import uvicorn

from app.main import app

if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=9823)
