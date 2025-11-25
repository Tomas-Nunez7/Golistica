# Simple TCP listener to receive alerts from backend and append to alerts.log
import socket, threading, os, sys

HOST = '0.0.0.0'
PORT = 9001
OUTFILE = 'alerts.log'

def handle_conn(conn, addr):
    with conn:
        data = b''
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk
        text = data.decode(errors='ignore').strip()
        if text:
            print('ALERT from', addr, text)
            with open(OUTFILE, 'a', encoding='utf-8') as f:
                f.write(text + '\n')

def serve():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen(5)
        print('TCP listener running on', HOST, PORT)
        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_conn, args=(conn, addr), daemon=True).start()

if __name__ == '__main__':
    try:
        serve()
    except KeyboardInterrupt:
        print('exiting')
