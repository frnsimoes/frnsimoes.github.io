import socket
import time

def demonstrate_buffer_issues():
    # Create server socket
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('localhost', 8080))
    server.listen(1)
    
    # Get the default receive buffer size
    default_buffer = server.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
    print(f"Default receive buffer size: {default_buffer} bytes")
    
    # Set a very small receive buffer to demonstrate overflow
    tiny_buffer = 256
    server.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, tiny_buffer)
    actual_buffer = server.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
    print(f"Set receive buffer size to: {actual_buffer} bytes")
    
    print("Waiting for connection...")
    conn, addr = server.accept()
    print(f"Connected by {addr}")
    
    # Slow reader scenario
    total_received = 0
    chunks_received = 0
    start_time = time.time()
    
    try:
        while True:
            # Intentionally slow down reading to cause buffer pressure
            time.sleep(0.1)  # Simulate slow processing
            
            # Try to receive data in small chunks
            chunk = conn.recv(64)
            if not chunk:
                break
                
            chunk_size = len(chunk)
            total_received += chunk_size
            chunks_received += 1
            
            print(f"Received chunk {chunks_received}: {chunk_size} bytes")
            print(f"Total received: {total_received} bytes")
            
    except socket.error as e:
        print(f"Socket error occurred: {e}")
    finally:
        elapsed = time.time() - start_time
        print(f"\nSummary:")
        print(f"Total data received: {total_received} bytes")
        print(f"Number of chunks: {chunks_received}")
        print(f"Time elapsed: {elapsed:.2f} seconds")
        print(f"Average receive rate: {total_received/elapsed:.2f} bytes/second")
        
        conn.close()
        server.close()

if __name__ == "__main__":
    demonstrate_buffer_issues()
