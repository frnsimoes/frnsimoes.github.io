+++
date =  2024-05-03
title =  "O que é o body em uma mensagem HTTP?"
+++

Quando falamos sobre um HTTP body, estamos nos referindo a um "fluxo de dados", uma sequência de bytes transmitidos na mensagem HTTP.

Imagine o seguinte: uma mensagem HTTP é enviada pelo cliente ao servidor através de um socket. O servidor recebe essa mensagem de um buffer temporário, com capacidade limitada. Por exemplo: client_socket = server_socket.accept(); client_socket.recv(4096).

Suponha que o body da mensagem tenha 32768 bytes. O socket receptor não sabe quantos bytes serão recebidos, então ele processa os dados em chunks de 4096 bytes, já que esse é o tamanho máximo do buffer do socket.

Mas o que significa "sequência de bytes transmitidos na mensagem"? O que é "a mensagem"?

No contexto das especificações HTTP, uma requisição tem três elementos fundamentais:

- Request line
- Header line
- Body 

A request line contém o método, o alvo da requisição e a versão do HTTP. Exemplo: GET / HTTP/1.1.

Os campos do header, por sua vez, são pares de chave-valor separados por dois pontos e espaços opcionais.

O body da mensagem é descrito pela RFC 9110 como "um fluxo de octetos enviados após a seção de cabeçalho".

Como sabemos que a request line terminou? Ou que os headers terminaram? Eles são separados por algo tão simples quanto um CRLF (carriage return line feed: \r\n).

Sabemos que a request line acabou porque há um \r\n, e sabemos que os headers acabaram porque há um CRLF duplo: \r\n\r\n.

Por exemplo: GET / HTTP/1.1\r\nContent-length:5\r\nFoo: bar\r\n\r\n

Cada novo header line termina com um CRLF, mas o header em si também termina com um CRLF, então sabemos com certeza que quando vemos um \r\n\r\n na mensagem HTTP, o que houver de residual na mensagem é o body.

O body HTTP é especialmente interessante porque é consumido pelo socket receptor. Assim, se o servidor leu e consumiu o body uma vez, ele não pode ler e consumir novamente. Isso é a origem, por exemplo, do erro do Django "Você não pode acessar o body após ler o fluxo de dados da requisição."

Em Go, normalmente lemos o body com a chamada io.ReadAll. O método ReadAll lê o body (bytes) até o EOF (fim de arquivo) e retorna os dados lidos.

Então, vamos dar uma olhada mais de perto no que significa ler um body.


```python
while True:
    try:
        client_sock, client_addr = s.accept()
        # buffer of 4096 bytes as an example
        data = client_sock.recv(4096)
        upstream_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        upstream_sock.connect(UPSTREAM_ADDR)
        upstream_sock.send(data)

        while True:
            res = upstream_sock.recv(4096)

            if not res:
                break

            client_sock.send(res)
```

Neste exemplo, o socket upstream está recebendo um body do proxy socket, processando o body em loop até que ele termine, e então enviando de volta o body para o client socket. Veja [aqui](https://github.com/frnsimoes/computer-science-studies/tree/main/network-programming/http/proxy-basic) uma implementação mais completa.
