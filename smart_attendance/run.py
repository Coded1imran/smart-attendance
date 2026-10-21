import sys
import os
import uvicorn

# Ensure project root is on Python sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

if __name__ == "__main__":
    print("=" * 60)
    print("  Smart Attendance (AttendAI) - Starting Server...")
    print("  Access Web App at: http://127.0.0.1:8000")
    print("  API Docs at:       http://127.0.0.1:8000/docs")
    print("=" * 60)
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
