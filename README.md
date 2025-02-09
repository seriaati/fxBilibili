# fxBilibili

## Quick Setup

1. Install requirements

`pip install -r requirements.txt`

2. Run the application

`hypercorn app:app --bind 0.0.0.0:5000 --worker-class asyncio`
