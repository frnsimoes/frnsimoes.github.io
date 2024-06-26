+++
date = 2022-06-10
title = "Invariantes"
+++

Uma regra no Domain-Driven Design (DDD) diz que "cada entidade deve se auto-validar." Essa regra é clara, simples e funcional quando pensamos em uma entidade como Pessoa, onde o atributo nome não pode ser uma string vazia. Seria estranho e absurdo considerar que a validação do nome deve ocorrer fora da entidade Pessoa, seja durante a criação da instância ou ao chamar o método. Existem várias maneiras de realizar a validação interna, e este artigo oferece uma perspectiva interessante sobre elas.

No entanto, fora do âmbito da programação orientada a objetos, é fácil perder a noção de "unidade" de um objeto.

"Pagar uma assinatura" é um conjunto de regras de negócio representadas por pequenas funções que se chamam mutuamente, e mesmo para o programador que as escreve, parece não haver unidade entre elas. Pelo menos não unidade no sentido de uma "entidade." A unidade está no domínio, e muitas vezes o domínio está espalhado por diversos lugares diferentes.

Programadores sempre enfrentam uma escolha. Considere o exemplo:

```
# Option 1

## Module A
def create_checkout_subscription(...) -> None:
    create_subscription(...)

## Module B
if payment.status == 'PAID':
    create_checkout_subscription

# Option 2

# Module A
def create_checkout_subscription(...) -> None:
    if payment.status == 'PAID':
        create_subscription(...)
 
# Module B
do_something(...)
create_checkout_subscription(...)
do_one_more_thing(...)
```
Diante dessas duas opções, é fácil concluir intuitivamente que a segunda é melhor. Com ela, não precisamos validar a função criar_assinatura_checkout em todos os lugares onde ela é chamada. Mas intuição não é suficiente.

E se o cenário fosse assim?:

```
# Module A
def create_checkout_subscription(payment: Payment) -> None:
    if payment.status == 'PAID':
        create_subscription(...)
        
# Module B
if payment.status == 'PAID':
    send_email.enqueue(...)
    # create_checkout_subscription()
```

Neste caso, a validação externa seria imposta por outra função: enviar_email, cujas restrições internas não exigem que um email seja enviado apenas se o status for 'PAGO' em todos os casos (a função é chamada em várias outras partes do sistema sem essa restrição contextual).

Se o programador se depara primeiro com esse cenário onde a restrição de negócios foi estabelecida externamente (neste caso, no Módulo B), ele pode acabar se convencendo de que, ao criar a função criar_assinatura_checkout, não precisa criar nenhuma restrição interna.

Pesquisando esse problema que estava me incomodando—afinal, quão terrível é programar baseado no sentimento 100% do tempo sem conseguir nomear as coisas?—incomodei amigos e procurei sobre o assunto.

Encontrei algumas respostas:

[Esta do Uncle Bob](https://groups.google.com/g/clean-code-discussion/c/latn4x6Zo7w/m/bFwtDI1XSA8J?pli=1). O tópico é arquitetura limpa, e o contexto são entidades, mas a ideia já está ficando mais clara:
A restrição de idade deve ser imposta pela entidade funcionário, ou por um sub-interator chamado pelo interator de adicionar-funcionário e pelo interator de alterar-funcionário? Isso depende inteiramente da volatilidade da política.
(A noção de "volatilidade": se as coisas podem mudar, e sabemos que podem, uma restrição externa à entidade é uma opção melhor. Caso contrário, a restrição estabelecida internamente é melhor.)

[Esta resposta no stackoverflow](https://stackoverflow.com/questions/30190302/what-is-the-difference-between-invariants-and-validation-rules). O contexto é uma pergunta sobre regras invariantes e validações:
Com certeza, validação é o processo de aprovar um estado de objeto dado, enquanto a aplicação de invariantes acontece antes mesmo que esse estado seja alcançado.
(Perfeito! Fica fácil entender que, dentro de um contexto específico, uma invariante é uma limitação externa da entidade.)
