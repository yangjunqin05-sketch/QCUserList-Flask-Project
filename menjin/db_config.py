# menjin/db_config.py

DB_SERVER = '192.168.15.208'
DB_DATABASE = 'AccessData'
DB_USERNAME = 'sa'
DB_PASSWORD = 'Aa123456'
DB_DRIVER = '{ODBC Driver 17 for SQL Server}' # 或者其他适合你系统的驱动

# 完整连接字符串
DB_CONNECTION_STRING = (
    f"DRIVER={DB_DRIVER};"
    f"SERVER={DB_SERVER};"
    f"DATABASE={DB_DATABASE};"
    f"UID={DB_USERNAME};"
    f"PWD={DB_PASSWORD};"
    "TrustServerCertificate=yes;" # 根据你的SQL Server配置可能需要
)