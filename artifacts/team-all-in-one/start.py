import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5100))
    print(f"🚀 ChatGPT 注册管理面板启动: http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
