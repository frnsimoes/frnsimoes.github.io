+++
date = 2024-06-18
title = "Brincando com fork()"
tags = ["Operating Systems"]
+++

A maneira como sistemas Unix criam um processo não é nada intuitiva. A princípio, eu imaginaria que criar um processo no sistema operacional seria tão simples quanto chamar uma system call `create`, ou algo assim.

Mas, na realidade, a gênese da criação de um processo no Unix envolve a criação de uma árvore hierárquica de processos.

O programa em execução que você está usando para criar um novo processo é um processo em si, então a maneira de criar um novo processo é criando um filho do processo atual.

A API envolve três passos: `fork()`, execute() e depois wait() (opcional). Um exemplo simples:

```c
#include <stdio.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/wait.h>

int main() {
    pid_t pid = `fork()`;

    if (pid < 0) {
        perror("Fork failed");
        return 1;

    } else if (pid == 0) {
        printf("World\n");

    } else {
        wait(NULL);
        printf("Hello\n");
    }

    return 0;
}
```

Primeiro, chamamos `fork()` para criar um processo filho. Se o pid (o valor retornado) for < 0, ocorreu um erro. Se for == 0, estamos no domínio do filho, caso contrário, no domínio do pai. Pelo que sei, se não chamarmos wait() no domínio do pai, não há como saber o que será executado primeiro (Hello\n ou World\n), porque a ordem de execução depende das implementações do scheduler do sistema operacional. Mas, ao chamar wait(), o processo pai espera pelo retorno do PID do filho.

Você até consegue construir um shell simplificado, com esse processo: o próprio shell é um processo, então ao criar e executar novos processos dentro de um shell (digamos que você digite yes no seu terminal e pressione return), você está verdadeiramente criando e executando um processo que é filho do processo bash / zsh / etc. Aqui está uma [implementação simples de um shell][implementation of a shell].

Este modelo pode ser estranho, alguns o adoram, outros o odeiam. Há um famoso (pelo menos famoso entre nós nerds) artigo acusando o fork de ser algo ruim em um sistema operacional, se você estiver curioso: [a `fork()` in the road].

O sistema operacional também exibe as relações do processo atual no seu sistema operacional em uma árvore. Tente chamar pstree no seu terminal.

Embora esta API possa ser estranha, gosto do que os autores de [OSTEP] dizem:

> the separation of `fork()` and `exec()` is essential in building a UNIX shell, because it lets the shell run code after the call to fork() but before the call to exec(); this code can alter the environment of the about-to-be-run program, and thus enables a variety of interesting features to be readily built.

Um exemplo seria o seguinte:

```c
int main(int argc, char *argv[]) {
    int rc = fork();
    if (rc < 0) {
        // fork falhou; sair
        fprintf(stderr, "fork failed\n");
        exit(1);
    } else if (rc == 0) {
        // filho: redirecionar saída padrão para um arquivo
        close(STDOUT_FILENO); 
        open("./p4.output", O_CREAT|O_WRONLY|O_TRUNC, S_IRWXU);
        // exec é chamado

```

Neste exemplo simples, chamamos close[^1] no file descriptor de saída padrão e abrimos um arquivo. Fazendo isso, podemos manipular o processo filho para gerar algo no arquivo aberto.

[^1]: do man page: A chamada close() exclui um descritor da tabela de referência de objetos por processo

[implementation of a shell]: https://github.com/frnsimoes/computer-science-studies/blob/main/operating-systems/programs-and-processes/basic-shell/shell.c
[a `fork()` in the road]: https://www.microsoft.com/en-us/research/uploads/prod/2019/04/fork-hotos19.pdf
[OSTEP]: https://pages.cs.wisc.edu/~remzi/OSTEP/cpu-api.pdf
