# agent/agent.py (带GUI和待处理列表注册功能)

import requests
import time
import socket
import subprocess
import os
import sys
import json

# 尝试导入tkinter，如果失败则提供提示
try:
    import tkinter as tk
    from tkinter import simpledialog, messagebox
    TKINTER_AVAILABLE = True
except ImportError:
    TKINTER_AVAILABLE = False
    print("警告: Tkinter 模块未找到。首次设置将使用命令行输入。")
    print("在大多数 Python 环境中，Tkinter 是内置的。如果缺失，请安装它 (例如: sudo apt-get install python3-tk)")


# --- 配置 ---
SERVER_URL = "http://192.168.15.208:5050"
POLL_INTERVAL_SECONDS = 20

# --- 路径设置 ---
if getattr(sys, 'frozen', False):
    # 如果是打包后的 .exe 文件
    AGENT_DIR = os.path.dirname(sys.executable)
else:
    # 如果是直接运行 .py 脚本
    AGENT_DIR = os.path.dirname(os.path.abspath(__file__))

SCRIPT_PATH = os.path.join(AGENT_DIR, 'temp_job_script.ps1')
CONFIG_FILE = os.path.join(AGENT_DIR, 'agent_config.json') # 配置文件，用于标记是否已设置

# --- 辅助函数 ---
def get_hostname():
    """获取本机的主机名"""
    return socket.gethostname()

def get_all_ips():
    """获取本机所有的IPv4地址"""
    hostname = get_hostname()
    try:
        _, _, ip_list = socket.gethostbyname_ex(hostname)
        return [ip for ip in ip_list if not ip.startswith("127.")]
    except Exception:
        try:
            # 备用方法
            ip = socket.gethostbyname(hostname)
            if not ip.startswith("127."):
                return [ip]
            return []
        except Exception:
            return []

# --- 首次运行设置 ---
def run_setup_gui():
    """使用 Tkinter 弹窗进行首次设置"""
    root = tk.Tk()
    root.withdraw() # 隐藏主窗口

    system_name = simpledialog.askstring("首次运行设置", "请输入此计算机在Web管理平台上的【系统全称】:", parent=root)
    
    if not system_name:
        messagebox.showerror("错误", "系统名称不能为空。设置已中止。")
        return False

    hostname = get_hostname()
    ip_string = ", ".join(get_all_ips())
    
    confirm_message = f"请确认信息：\n\n平台系统名称: {system_name}\n本机计算机名: {hostname}\n本机IP地址: {ip_string or '未找到'}\n\n点击“是”以上传信息。"
    if not messagebox.askyesno("确认信息", confirm_message):
        messagebox.showinfo("提示", "操作已取消。")
        return False

    payload = {'system_name': system_name, 'hostname': hostname, 'ip_addresses': ip_string}
    
    try:
        response = requests.post(f"{SERVER_URL}/api/agent/register_pending_system", json=payload, timeout=20)
        response.raise_for_status()
        result = response.json()
        if result.get('status') == 'success':
            messagebox.showinfo("成功", f"注册成功！\n{result.get('message')}")
            with open(CONFIG_FILE, 'w') as f:
                json.dump({'is_configured': True, 'hostname': hostname}, f)
            return True
        else:
            messagebox.showerror("失败", f"服务器返回错误: {result.get('message')}")
            return False
    except Exception as e:
        messagebox.showerror("连接失败", f"无法连接到服务器: {e}")
        return False
    finally:
        root.destroy()

def run_setup_cli():
    """如果Tkinter不可用，则使用命令行进行设置"""
    print("--- 首次部署设置向导 (命令行模式) ---")
    try:
        system_name = input("请输入此系统在管理平台上的【完整名称】: ")
        if not system_name:
            print("错误：系统名称不能为空。设置已中止。")
            return False
    except KeyboardInterrupt:
        print("\n设置已取消。")
        return False

    hostname = get_hostname()
    ip_string = ", ".join(get_all_ips())
    print(f"\n即将注册以下信息：\n  - 平台系统名称: {system_name}\n  - 本机计算机名: {hostname}\n  - 本机 IP 地址: {ip_string or '未找到'}")
    confirm = input("确认信息无误并上传？ (y/n): ")
    if confirm.lower() != 'y':
        print("操作已取消。")
        return False

    payload = {'system_name': system_name, 'hostname': hostname, 'ip_addresses': ip_string}
    print("\n正在上传信息到服务器...")
    try:
        response = requests.post(f"{SERVER_URL}/api/agent/register_pending_system", json=payload, timeout=20)
        response.raise_for_status()
        result = response.json()
        if result.get('status') == 'success':
            print(f"✓ 成功！{result.get('message')}")
            with open(CONFIG_FILE, 'w') as f:
                json.dump({'is_configured': True, 'hostname': hostname}, f)
            return True
        else:
            print(f"✗ 失败：服务器返回错误 - {result.get('message')}")
            return False
    except Exception as e:
        print(f"✗ 发生错误: {e}")
        return False

# --- 常规操作 ---
def report_job_result(job_id, status, output):
    """向服务器报告任务执行结果"""
    print(f"Reporting result for job {job_id}...")
    payload = {'job_id': job_id, 'status': status, 'output': output}
    try:
        requests.post(f"{SERVER_URL}/api/agent/report_job_result", json=payload, timeout=20)
        print("Job result reported successfully.")
    except Exception as e:
        print(f"Error reporting job result: {e}")

def execute_job(job_id, script_content):
    """执行从服务器获取的 PowerShell 脚本"""
    print(f"Executing job {job_id}...")
    try:
        with open(SCRIPT_PATH, 'w', encoding='utf-8-sig') as f:
            f.write(script_content)
        
        command = ['powershell.exe', '-ExecutionPolicy', 'Bypass', '-File', SCRIPT_PATH]
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=300)

        status = 'completed' if result.returncode == 0 else 'failed'
        output = result.stdout if status == 'completed' else f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
        report_job_result(job_id, status, output)

    except subprocess.TimeoutExpired:
        print(f"Job {job_id} timed out.")
        report_job_result(job_id, 'failed', 'Execution timed out after 5 minutes.')
    except Exception as e:
        print(f"An error occurred while executing job {job_id}: {e}")
        report_job_result(job_id, 'failed', str(e))
    finally:
        if os.path.exists(SCRIPT_PATH):
            os.remove(SCRIPT_PATH)

def heartbeat_and_get_job():
    """发送心跳并检查是否有待处理任务"""
    print("Sending heartbeat and checking for jobs...")
    try:
        payload = {'hostname': get_hostname()}
        response = requests.post(f"{SERVER_URL}/api/agent/heartbeat", json=payload, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if data.get('job_id'):
            execute_job(data['job_id'], data['script_content'])
        else:
            print("No pending jobs found.")
            
    except requests.exceptions.ConnectionError:
        print(f"Connection to server {SERVER_URL} failed.")
    except requests.exceptions.RequestException as e:
        print(f"An error occurred while communicating with the server: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during heartbeat: {e}")

def run_normal_operation():
    """常规的轮询和任务执行模式"""
    print(f"Agent starting up in normal mode...")
    while True:
        heartbeat_and_get_job()
        print(f"Sleeping for {POLL_INTERVAL_SECONDS} seconds...")
        time.sleep(POLL_INTERVAL_SECONDS)

# --- 主入口 ---
if __name__ == "__main__":
    # 检查配置文件是否存在，决定是进入设置模式还是常规模式
    if not os.path.exists(CONFIG_FILE):
        setup_success = False
        if TKINTER_AVAILABLE:
            setup_success = run_setup_gui()
        else:
            setup_success = run_setup_cli()
            
        if not setup_success:
            # 如果设置失败或被取消，程序直接退出
            if not TKINTER_AVAILABLE:
                # 在命令行模式下，暂停一下让用户看到错误信息
                input("按 Enter 键退出。")
            sys.exit(1)
    
    # 如果配置文件存在，或者设置刚刚成功，则进入常规操作
    run_normal_operation()