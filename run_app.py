import subprocess
import time
import sys
import os
import socket
import webbrowser

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def main():
    port = 2903
    script_path = os.path.join(os.path.dirname(__file__), "main.py")
    restart_file = os.path.join(os.path.dirname(__file__), "restart.txt")
    shutdown_file = os.path.join(os.path.dirname(__file__), "shutdown.txt")
    
    # Nếu hệ thống đã chạy sẵn, chỉ cần mở trình duyệt và thoát
    if is_port_in_use(port):
        webbrowser.open(f'http://localhost:{port}')
        sys.exit(0)
        
    # Xoá các file điều hướng cũ
    for f in [restart_file, shutdown_file]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except:
                pass
                
    while True:
        # Chạy Streamlit ngầm
        creationflags = 0
        if os.name == 'nt':
            creationflags = subprocess.CREATE_NO_WINDOW
            
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        
        log_path = os.path.join(os.path.dirname(__file__), "streamlit_run.log")
        log_file = open(log_path, "a", encoding="utf-8")
        
        proc = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", script_path, "--server.headless", "true", "--server.port", str(port)],
            stdout=log_file,
            stderr=log_file,
            creationflags=creationflags,
            env=env
        )
        
        # Đợi 2 giây cho cổng được mở rồi gọi trình duyệt
        time.sleep(2)
        webbrowser.open(f'http://localhost:{port}')
        
        while True:
            # Kiểm tra yêu cầu Tắt hệ thống
            if os.path.exists(shutdown_file):
                try:
                    os.remove(shutdown_file)
                except:
                    pass
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                sys.exit(0)
                
            # Kiểm tra yêu cầu Cập nhật / Tải lại hệ thống
            if os.path.exists(restart_file):
                try:
                    os.remove(restart_file)
                except:
                    pass
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                time.sleep(1)
                break  # Thoát ra ngoài vòng lặp để khởi chạy lại Streamlit
                
            # Kiểm tra xem tiến trình có đột ngột chết
            ret = proc.poll()
            if ret is not None:
                sys.exit(ret)
                
            time.sleep(0.5)

if __name__ == '__main__':
    main()
