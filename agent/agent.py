# agent.py

import requests
import time
import socket
import subprocess
import os
import sys
import logging
from logging.handlers import RotatingFileHandler

# --- 配置 ---
# SERVER_URL = "http://127.0.0.1:5000" # 用于本地测试
SERVER_URL = "http://192.168.15.208:5050" # ###################################
                                          # ## 部署时必须修改为服务器的真实IP ##
                                          # ###################################
POLL_INTERVAL_SECONDS = 20 # 轮询间隔 (秒)

# --- 路径设置 (确保在打包后也能正确工作) ---
# getattr(sys, 'frozen', False) 用于判断程序是否被打包
if getattr(sys, 'frozen', False):
    # 如果是打包后的 .exe 文件，AGENT_DIR 是 .exe 所在的目录
    AGENT_DIR = os.path.dirname(sys.executable)
else:
    # 如果是直接运行 .py 脚本，AGENT_DIR 是脚本所在的目录
    AGENT_DIR = os.path.dirname(os.path.abspath(__file__))

LOG_FILE = os.path.join(AGENT_DIR, 'agent.log')
SCRIPT_PATH = os.path.join(AGENT_DIR, 'temp_job_script.ps1')

# --- 日志配置 ---
def setup_logging():
    """配置日志记录，同时输出到文件和控制台"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            RotatingFileHandler(LOG_FILE, maxBytes=1024*1024, backupCount=5), # 1 MB per file
            logging.StreamHandler(sys.stdout)
        ]
    )

def get_hostname():
    """获取本机的主机名"""
    return socket.gethostname()

def report_job_result(job_id, status, output):
    """向服务器报告任务执行结果"""
    logging.info(f"Reporting result for job {job_id}...")
    payload = {'job_id': job_id, 'status': status, 'output': output}
    try:
        # 设置一个合理的超时时间
        requests.post(f"{SERVER_URL}/api/agent/report_job_result", json=payload, timeout=20)
        logging.info("Job result reported successfully.")
    except Exception as e:
        logging.error(f"Error reporting job result: {e}")

def execute_job(job_id, script_content):
    """执行从服务器获取的 PowerShell 脚本"""
    logging.info(f"Executing job {job_id}...")
    try:
        # 将脚本内容写入临时文件
        with open(SCRIPT_PATH, 'w', encoding='utf--sig') as f:
            f.write(script_content)
        
        # 定义并执行 PowerShell 命令
        command = ['powershell.exe', '-ExecutionPolicy', 'Bypass', '-File', SCRIPT_PATH]
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=300) # 5分钟超时

        # 根据返回码判断成功或失败
        status = 'completed' if result.returncode == 0 else 'failed'
        # 失败时同时记录标准输出和标准错误
        output = result.stdout if status == 'completed' else f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
        report_job_result(job_id, status, output)

    except subprocess.TimeoutExpired:
        logging.error(f"Job {job_id} timed out.")
        report_job_result(job_id, 'failed', 'Execution timed out after 5 minutes.')
    except Exception as e:
        logging.error(f"An error occurred while executing job {job_id}: {e}")
        report_job_result(job_id, 'failed', str(e))
    finally:
        # 确保临时脚本文件被删除
        if os.path.exists(SCRIPT_PATH):
            os.remove(SCRIPT_PATH)

def heartbeat_and_get_job():
    """发送心跳并检查是否有待处理任务"""
    logging.info("Sending heartbeat and checking for jobs...")
    try:
        payload = {'hostname': get_hostname()}
        response = requests.post(f"{SERVER_URL}/api/agent/heartbeat", json=payload, timeout=15)
        # 如果服务器返回错误状态码 (如 404, 500), 则会抛出异常
        response.raise_for_status()
        data = response.json()
        
        if data.get('job_id'):
            execute_job(data['job_id'], data['script_content'])
        else:
            logging.info("No pending jobs found.")
            
    # --- 优化：更具体的网络错误捕获 ---
    except requests.exceptions.ConnectionError:
        logging.error(f"Connection to server {SERVER_URL} failed. Check network or if the server is running.")
    except requests.exceptions.RequestException as e:
        logging.error(f"An error occurred while communicating with the server: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred during heartbeat: {e}")

if __name__ == "__main__":
    setup_logging()
    logging.info(f"Agent starting up... Working directory: {AGENT_DIR}")
    while True:
        heartbeat_and_get_job()
        logging.info(f"Sleeping for {POLL_INTERVAL_SECONDS} seconds...")
        time.sleep(POLL_INTERVAL_SECONDS)