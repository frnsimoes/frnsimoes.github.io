+++
date = 2021-12-05
title = "Brincando com recursão"
tags = ["programming languages"]
+++ 

Assistindo ao [CS61A](https://www.youtube.com/@JohnDeNero/videos) (miss you, John), bati muito a cabeça para entender como funções recursivas funcionam. Para entender melhor o problema, resolvi (tentar) desenhar o passo a passo para mim mesmo:

O exemplo clássico do fatorial:

```
def fact(n):
	if n == 0:
		return 1
	else:
		return n * fact(n-1)

fact(3) # 3*2*1=6
```

O que acontece aqui?

Cada `f` é um frame isolado. A função é chamada recursivamente e o valor de `n` muda dinamicamente a cada chamada, conforme o argumento do `fact()` recursivo:

```
|-------------------------------
| f1: fact. n=3
|-------------------------------
|-------------------------------
| f2: fact. n=2
|-------------------------------
|-------------------------------
| f3: fact. n=1
|-------------------------------
|-------------------------------
| f4: fact. n=0. return value: 1
|-------------------------------
```

### Como chegamos ao resultado de 6? 

Primeiro, temos o processo de encolhimento do argumento `n` conforme a chamada da função recursiva (`n-1`):

Depois, temos as _evaluations_ de cada um dos _frames_ (leia de baixo para cima):

```
|-------------------------------
| f1: fact. return value: 3
| n=3. return: 3*2=6
|-------------------------------
|-------------------------------
| f2: fact. return value: 2
| n=2. return: 2*1=2
|-------------------------------
|-------------------------------
| f3: fact. return value: 1
| n=1. return: 1*1=1
|-------------------------------
|-------------------------------
| f4: fact. n=0. return value: 1
| n=0. return: 1
|-------------------------------
```

 A cada iteração, há a subtração de _1_ no valor de `n`. Por isso, por exemplo, no frame 2 (f2), o valor de `n` é `3`, mas o valor pelo qual ele é multiplicado é `2`.

### O que aconteceu quando chamamos a função?

- A mesma função é chamada várias vezes. 
- Frames diferentes mantém o histórico dos diferentes argumentos em cada uma das chamadas. 
- A avaliação de `n`, portanto, depende de qual é o _environment_ atual.

### Um exemplo com lista:

```
def sum_list(xs:list):
	if not xs:
		return 0
	else:
		return xs[0] + sum_list(xs[1:])

xs = [1, 2, 3, 4, 5]

sum_list(xs)  # 1+2+3+4+5=15
```

Neste exemplo, cada chamada da função recursiva consome um elemento da lista. 

```
| f1: fact. xs=[1, 2, 3, 4, 5]
| return: [1, 2, 3, 4, 5]
|-------------------------------
|-------------------------------
| f2: fact. xs=[2, 3, 4, 5]
| return: 15
|-------------------------------
|-------------------------------
| f3: fact. xs=[3, 4, 5]
| return: 14
|-------------------------------
|-------------------------------
| f4: fact. xs=[4, 5]
| return: 12
|-------------------------------
|-------------------------------
| f5: fact. xs=[5]
| return: 9
|-------------------------------
|-------------------------------
| f6: fact. xs=[]
| return: 5
|-------------------------------
```
### No fim das contas

No fim das contas, a recursão é uma forma de iteração. Ou, como diz [John DeNero], a iteração é uma forma específica de recursão. 

Um exemplo besta, mas que clarifica bem essa qualidade da recursão:

```
def sum_a(a: int, b: int):
	if b == 0:
		return 0
	else:
		return a + sum_a(a, b-1)

sum_a(4, 4) # 4+4+4+4=16
```

Nesse caso específico, o argumento `b` serve apenas para fixar a quantidade de vezes que `a` será somado com o valor de `a`. Dessa forma, no exemplo acima o resultado é: 4+4+4+4. 

### Anatomia do negócio

- O def header é similar a outras funções
- A primeira condicional checa por casos de base (`a==0`)
- Casos de base são avaliados sem a chamada da recursão
- Casos recursivos são avaliados, em frames próprios, com chamadas recursivas.

