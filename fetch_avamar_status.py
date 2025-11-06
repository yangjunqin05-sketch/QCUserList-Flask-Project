import os
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

# --- 必须配置的部分 ---
AVAMAR_SERVER = 'CHDVLAVE01.hengrui.com'  # 替换为您的 Avamar 服务器地址
AVAMAR_USER = 'your_avamar_user'          # 替换为有权限的 Avamar 用户名
AVAMAR_PASSWORD = 'your_avamar_password'  # 替换为密码
# avmgr.exe 的完整路径。在 Windows 上通常在这里。请根据实际情况修改。
AVMGR_PATH = 'C:\\Program Files\\avs\\bin\\avmgr.exe' 

# --- Flask 应用加载 ---
# 这部分代码允许我们在独立脚本中使用 Flask 应用的上下文和数据库模型
from app import create_app, db
from app.models import System

app = create_app()

def fetch_avamar_logs():
    """使用 avmgr 命令获取过去24小时的备份日志 (XML格式)"""
    print("正在连接 Avamar 并获取日志...")
    
    # 构建命令。--xml 参数让输出格式化，便于解析。
    command = [
        AVMGR_PATH,
        'logshow',
        '--xml',
        '--err',  # 显示成功和失败的日志
        f'--server={AVAMAR_SERVER}',
        f'--id={AVAMAR_USER}',
        f'--ap={AVAMAR_PASSWORD}',
        "--since='24 hours ago'" # 获取过去24小时的日志
    ]

    try:
        # 执行命令
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='ignore', check=True)
        print("成功获取 Avamar 日志。")
        return result.stdout
    except FileNotFoundError:
        print(f"!!! 致命错误: 找不到 avmgr.exe，请检查 AVMGR_PATH 配置: {AVMGR_PATH}")
        return None
    except subprocess.CalledProcessError as e:
        print(f"!!! Avamar 命令执行失败: {e}")
        print(f"    错误输出: {e.stderr}")
        return None
    except Exception as e:
        print(f"!!! 未知错误: {e}")
        return None

def update_database_with_logs(xml_data):
    """解析XML日志并更新数据库"""
    if not xml_data:
        print("没有日志数据可供处理。")
        return

    print("开始解析日志并更新数据库...")
    
    # 使用 with app.app_context() 来访问数据库
    with app.app_context():
        # 1. 一次性获取所有需要匹配的系统，并存入字典以便快速查找
        systems_to_check = System.query.filter(System.computer_name != None, System.computer_name != '').all()
        systems_map = {s.computer_name.lower(): s for s in systems_to_check}
        
        # 2. 将所有系统的状态先重置为“24小时内无备份”
        for system in systems_to_check:
            system.avamar_status = '24h内无备份'
        
        # 3. 解析 XML
        try:
            root = ET.fromstring(xml_data)
            
            # 遍历日志中的每一行
            for row in root.findall('.//row'):
                client_name = row.get('client', '').strip().lower()
                status = row.get('status', 'Unknown')
                end_time_str = row.get('end', '')

                # 4. 匹配客户端名称
                if client_name in systems_map:
                    system_obj = systems_map[client_name]
                    
                    # 格式化状态信息
                    status_message = f"{status} @ {end_time_str}"
                    
                    # 更新对象的状态
                    system_obj.avamar_status = status_message
                    print(f"  匹配成功: {system_obj.computer_name} -> {status_message}")

            # 5. 提交所有更改到数据库
            db.session.commit()
            print("数据库更新完成！")

        except ET.ParseError as e:
            print(f"!!! XML 解析失败: {e}")
        except Exception as e:
            db.session.rollback()
            print(f"!!! 数据库更新时发生错误: {e}")

if __name__ == '__main__':
    print(f"--- Avamar 状态同步脚本 @ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
    logs = fetch_avamar_logs()
    if logs:
        update_database_with_logs(logs)
    print("--- 脚本执行完毕 ---")