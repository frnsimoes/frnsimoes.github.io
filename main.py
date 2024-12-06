import socket

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(("0.0.0.0", 8778))
server.listen(5)

print("Listening on port 8778")

while True:
    # important part of the handshake. check accept() commentary.
    client_socket, addr = server.accept()
    print(f"Accepted connection from: {addr[0]}:{addr[1]}")
    request = client_socket.recv(1024)
    print(f"Received: {request.decode('utf-8')}")

    http_response = "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nHello, world!"
    client_socket.send(http_response.encode('utf-8'))
    client_socket.close()
