import sys
import os
from pathlib import Path

# Point Python to the backend/ folder so "from app import create_app" works
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from app import create_app

application = create_app()