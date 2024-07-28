+++ 
date = 2024-07-28
title = "TCP reliable delivery: ACKs e Seqs"
tags = ["Computer Networking"]
+++

"Reliable delivery" é um dos temas centrais e mais interessantes do transport layer. O sentido de "reliable" foi definido na [RFC793]:

> The TCP must recover from data that is damaged, lost, duplicated, or delivered out of order by the internet communication system.  This is achieved by assigning a sequence number to each octet transmitted, and requiring a positive acknowledgment (ACK) from the receiving TCP.  If the ACK is not received within a timeout interval, the data is retransmitted.  At the receiver, the sequence numbers are used to correctly order segments that may be received out of order and to eliminate duplicates.  Damage is handled by adding a checksum to each segment transmitted, checking it at the receiver, and discarding damaged segments.

> As long as the TCPs continue to function properly and the internet system does not become completely partitioned, no transmission errors will affect the correct delivery of data.  TCP recovers from internet communication system errors.


ACKs e Seq são recursos utilizados para tornar a entrega de segmentos confiável. Esse tema é bastante amplo, e os problemas que podem surgir durante a comunicação e o envio de pacotes (ou segmentos) é bastante variado e complexo. a RFC cita alguns quando dize que o TCP precisa poder se recuperar nos casos de: 1. dados corrompidos; 2. dados perdidos; 3. dados duplicados; 4. dados entregues fora de ordem.

Vamos supor um cenário prático: temos um servidor e um cliente. O socket do cliente envia três segmentos para o socket do servidor: A, B e C. Esses segmentos chegaram a um roteador que estava com o buffer cheio. O socket do servidor recebeu o segmento A, perdeu o segmento B (devido ao buffer cheio), e depois "recebeu" o segmento C.

O problema é que o processo do socket no servidor não pode processar o segmento C imediatamente, porque B é parte essencial da mensagem completa. O resultado desejado é que o kernel do servidor faça o buffer do segmento C até que o segmento B chegue. (Pense que "o dado" é apenas um, e os segmentos são particionamentos desse dado).

Também precisamos de um mecanismo de retransmissão para o segmento B. Certo? Porque ele precisa ser reenviado. A comunicação não pode terminar apenas porque o buffer do roteador estava cheio e o segmento B não foi entregue com sucesso.

Portanto, precisamos:

- Que o cliente possa informar ao servidor que o segmento B não foi recebido.
- De um mecanismo que permita ao servidor inferir que, se não houve um ACK do cliente para um segmento, aquele segmento provavelmente se perdeu.
- Garantir a ordem do recebimento. Pode ser que os segmentos B e C não tenham tomado o mesmo caminho entre os links.
- Evitar o recebimento de segmentos duplicados.

Não quero escrever sobre todos esses pontos neste texto, mas refletir um pouco sobre o ACK e o Seq, dois campos do TCP Header.

TCP implementa a noção de número sequencial (seq #), ligado ao tamanho dos bytes recebidos anteriormente. Quando uma conexão TCP é estabelecida, cliente e servidor fazem um acordo com relação ao número sequencial para os pacotes iniciais, conhecido como ISN (Initial Sequence Number)[^1]. Portanto, se o último segmento continha seq: 10.000, o próximo número de sequência será baseado no tamanho dos dados do segmento anterior.

Um exemplo simples é quando um segmento é enviado com um tamanho de 1000 bytes. Nesse cenário, temos o seguinte, de maneira simplificada:

```
Envio: segmento 1: seq = 1001, data = 1000 (bytes)
Recebimento: ack = 2002
```

Isso significa que o servidor recebeu o segmento 1, verificou que os dados têm 1000 bytes, e agora aguarda pelo segmento com seq = 2001.

A [RFC793] fala de "data offsets", um campo no cabeçalho TCP que indica onde os dados começam. O kernel do receptor usa esse campo para verificar o próximo comprimento esperado com base no tamanho do segmento já recebido.

> The number of 32 bit words in the TCP Header.  This indicates where the data begins.  The TCP header (even one including options) is an integral number of 32 bits long.

Uma implementação simples de sequence numbers poderia ser algo deste tipo:

```python
class ReliableDelivery:
    def __init__(self, target_addr=None):
        self.target_addr = target_addr
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.seq = 0
        # self.ack = 0
        
    def bind(self, own_addr):
        self._sock.bind(own_addr)

    def send(self, data):
        i = 0
        while i < len(data):
            payload = data[i:i+MAX_PAYLOAD_SIZE]
            segment = pack_segment(self.seq, self.ack, payload)
            self._sock.sendto(segment, self.target_addr)
            self.seq += 1
            i += len(payload)

    def recv(self):
        pass
```

Agora, o que é o ACK? O ACK é o número que representa, por parte do receptor, tudo o que já foi recebido por ele. Suponha, portanto, que o servidor recebeu, de um cliente, até o byte 12.000. Neste caso, a última requisição conterá um ACK de 12.001. Da mesma RFC:

> If the ACK control bit is set this field contains the value of the next sequence number the sender of the segment is expecting to receive.  Once a connection is established this is always sent.

Voltando ao exemplo inicial em que o segmento B é perdido:
- Segmento A tem dados de 1500 bytes.
- O receptor assume que o segmento B irá de 1501 a 3000
- O receptor recebe C, com offset em 3001
- O ACK da resposta, no TCP header, será de 1501 (compreendendo apenas o reconhecimento dos primeiros 1500 bytes do segmento A e indicando que o próximo esperado é o 1501)


Outro assunto interessante é a seguinte questão: por quanto tempo o socket que enviou o segmento espera pelo ACK até que ele decida reenviá-lo, assumindo que foi perdido?

Um modo de medir esse tempo é usar o primeiro handshake como pedida do tempo esperado no "roundtrip". O roundtrip time inclui tanto o tempo de ida quanto o tempo de volta. O problema é que o RTT é influenciado por diversos fatores (distância entre links, por exemplo, ou quantidade de clients). Por isso, outra medida interessante é medir a variação dos diversos RTTs.

Portanto, voltando aos problemas mencionados lá no início: Seq e ACKs são o suficiente para: reordenar corretamente os segmentos recebidos fora de ordem, pois cada segmento tem um número único sequencial. O ACK ausente indica ao cliente que determinado segmento não foi recebido, o que faz com que ele retransmita os dadoss; e os dados duplicados são descartados com base nos números de sequência e o checksum.



[RFC793]: https://www.ietf.org/rfc/rfc793.txt
[1]: O sequence number do header é o primeiro octeto no segmento, exceto quando o SYN está presente no header.
