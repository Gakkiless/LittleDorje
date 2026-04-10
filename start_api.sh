#!/bin/bash
# 小多吉后端服务启动脚本

echo "🚀 启动小多吉推荐API服务..."

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到Python3，请先安装"
    exit 1
fi

# 检查依赖
echo "📦 检查依赖..."
python3 -c "import flask; import chromadb; import ollama" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠️  缺少依赖，正在安装..."
    pip3 install flask flask-cors chromadb ollama
fi

# 检查Ollama服务
echo "🔍 检查Ollama服务..."
curl -s http://localhost:11434/api/version > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "⚠️  Ollama服务未运行，请先启动: ollama serve"
    echo "   或拉取模型: ollama pull nomic-embed-text"
fi

# 启动服务
echo "✅ 启动API服务 (端口 5123)..."
echo ""
cd "$(dirname "$0")"
python3 recommend_api.py
