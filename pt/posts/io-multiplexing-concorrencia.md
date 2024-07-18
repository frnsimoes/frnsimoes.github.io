+++
date = 2024-07-09
title = "IO Multiplexing e Concorrência em Proxies"
tags = ["Programming"]
+++

IO multiplexing é um tópico complexo à primeira vista. Mas é a base da "concorrência" sem múltiplas threads ou processadores. Então, é bem útil. Um exemplo de um bom uso de IO multiplexing é o Redis; outro é o Nginx.

O segredo do IO multiplexing é ser capaz de lidar com várias coisas ao mesmo tempo. E por "coisas" quero dizer múltiplos comportamentos que têm entrada ou saída em file descriptors.

Multiplexing é um recurso bem conhecido para lidar com o cenário de "precisamos reunir algumas coisas e depois entregá-las aos seus próprios proprietários". É uma maneira de proxyar recibos diligentemente para os destinatários apropriados.

Multiplexing e demultiplexing são amplamente usados em protocolos de rede na camada de transporte. Quando você usa seu computador, você não se conecta a uma única rede por vez. Normalmente, você está ouvindo música, enviando e-mails, conversando e baixando arquivos. UDP e TCP sabem como lidar com isso e como entregar o datagrama/segmento apropriado ao socket correto.

Mas e se você tiver apenas um processo e quiser criar essa mesma funcionalidade? Suponha que você seja um servidor e queira responder a múltiplas requisições de diferentes origens. O que você poderia fazer? Bem, você poderia rodar em múltiplas threads ou talvez múltiplos processadores. Mas, em muitos casos, isso não é uma boa opção ou uma possibilidade.

Uma maneira de lidar com múltiplas requisições no escopo de um processo single-threaded é usar IO Multiplexing. Em sistemas Unix, temos os seguintes modelos de IO:

Blocking IO model
Nonblocking IO model
IO Multiplexing model
Blocking IO significa que o processo irá parar sua execução até que a operação de IO seja completada. Nonblocking IO, por outro lado, não espera que a execução de IO seja completada; em vez disso, o processo continua a rodar e, se a execução de IO não foi completada, retorna um erro.

O modelo de IO Multiplexing é hors-concours, por sua vez. Ele faz uso de chamadas de sistema como select, poll, epoll (dependendo do sistema operacional, no meu Mac uso select, mas se você é um nerd de Linux, pode preferir poll -- eu gostaria de poder) para rastrear file descriptors e lidar com sua prontidão para serem IOed.

Mas o que isso realmente significa? Como isso realmente acontece?

Imagine que você é um servidor. Alguém envia uma requisição com curl, e outra pessoa envia uma requisição com o navegador. A princípio, você não sabe o que fazer. Bem, você sabe, mas as coisas estão indo bem: seu socket vai processar a requisição curl, e a requisição do navegador ficará bloqueada potencialmente pelo tempo que a requisição curl levar para ser executada.

Você não quer isso. Você não é esse tipo de servidor. É? Você prefere ser capaz de ouvir a requisição curl e então, enquanto estiver bloqueado por ela (digamos que precise de alguma consulta ao banco de dados), você quer atender a requisição do navegador web.

Isso é o que o IO Multiplexing permite que você faça.

```python
import select
import socket

listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

listener.setblocking(False)

listener.bind(('0.0.0.0', 10000))
listener.listen(10)

inputs = [listener]
outputs = []

to_send = set()

while True:
    readable, writable, exceptional = select.select(inputs, outputs, inputs)
    print('readables')
    print(readable)

    print('writables')
    print(writable)

    for s in readable:
        if s is listener:
            client_sock, client_addr = s.accept()
            client_sock.setblocking(False)
            inputs.append(client_sock)
        else:
            data = s.recv(4096)
            if data:
                print(data)
                outputs.append(s)
                to_send.add(s)
            else:
                s.close()
            inputs.remove(s)

    for s in writable:
        if s in to_send:
            to_send.remove(s)
            outputs.remove(s)
            s.send(b'HTTP/1.0 200 ok \r\n\r\nbody text')
            s.close()
```

Aqui está o que está acontecendo nesse código feio:

Esta é uma conexão TCP (identificada por socket.SOCK_STREAM). Em vez de fazer o handshake imediatamente assim que a requisição do cliente chega, você chama select. O que select vai fazer é monitorar as entradas para você. Quando a requisição curl chega, você recebe sua mensagem; o mesmo acontece para a requisição do navegador. Elas se tornam "readable" porque o socket (o file descriptor) pode querer ler o que foi enviado por elas.

Note que tanto curl quanto a requisição do navegador são dois sockets diferentes, então são identificados por dois file descriptors diferentes.

Quando você processa a mensagem de um cliente, você quer respondê-la, é isso que o to_send() está fazendo. writable é uma maneira de dizer: "aqui está uma coisa que eu quero escrever para este file descriptor".

E aí está. Enquanto sendo apenas um socket, você acabou de criar uma maneira de lidar com múltiplas requisições simultaneamente.
