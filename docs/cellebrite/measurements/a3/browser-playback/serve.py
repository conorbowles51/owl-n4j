import sys, uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles
app = Starlette(routes=[Mount("/", StaticFiles(directory=sys.argv[1], html=True))])
uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[2]), log_level="warning")
