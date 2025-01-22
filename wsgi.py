import sys
import os

# Add the application directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the Flask application
from app import app as application

if __name__ == "__main__":
    application.run()