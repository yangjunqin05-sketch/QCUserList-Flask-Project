# main.py

from app import create_app

app = create_app()

if __name__ == '__main__':
    # 关键修改：
    # 添加 port=5050 参数，明确指定服务器运行在 5050 端口。
    app.run(host='0.0.0.0', port=5050, debug=True)