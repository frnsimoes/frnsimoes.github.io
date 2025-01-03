import socket
data = b'X' * 1024 * 1024  # 1MB of data
client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect(('localhost', 8080))
client.sendall(data)
