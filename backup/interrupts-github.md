Imagine this: someone keeps delivering you envelopes. They ring the bell and hand you the envelope. There's a truck full of them. You grab the first one, go inside the house, put it on the table. Go back outside, the driver handles you another one, but you know there are countless more to come. So you start grabbing them in batches. The driver is tired, and so are you. But you think: "this won't go on forever, right?, I can handle this". But they keep coming.

A few hours later, you change your strategy. You call your spouse: the drive handles the envelope to them, they tell you that more envelopes just arrive. You run to get them halfway. And keep pilling them on the table. 

Everyone gets tired a few hours later, and you change your strategy: you hire people to grab the envelopes and delegate the tasks

This is exactly how the Kernel handles interrupts. Whenever the hardware is ready, it issues a request to the kernel through the Interrupt Controller (which is also a hardware piece). The Interrupt Controller then calls the CPU: hey, the network card just receive data! 

Then the kernel switches its attention to that request. 

But here is the problem: the kernel has limited resources. It can only pay attention to a few interrupts at a time. The way kernel devs solved this was by dividing interrupts into two halves: top and bottom. Top halves talk to the Interrupt Controller, and registers internally a request so that the bottom half can, asynchronously, do the job. Something like this:

Top half (fast): 
- Acknowledge the hardware
- Schedule the real work for later
- Get out ASAP

Bottom half (deferred):
- Do the actual processing
- Can take its time (but has a budget)
- Runs when it's safe to do so

Muito bom esse RCA do Github (2019) mostrando um incidente causado por softirqs impedindo syscalls de retornar ao userspace.

Enxurrada de syscalls causada pelo cadvisor + quantidade absurda de dados chegando pelo network card.

O kernel simplesmente não conseguia retornar ao userspace porque sempre tinha softirqs pendentes para processar. O problema: enquanto o cadvisor consumia o budget de softirq com suas próprias tarefas, os packets de rede ficavam esperando na fila do NIC, acumulando latência.

Em acréscimo a essa maluquice, quando o budget acaba, o kernel joga a bola para o ksoftirqd, que é uma thread à parte.

Ambas as coisas aumentaram loucamente a latência das requests (> 100ms). Bem interessante. Deem uma lida.

https://github.blog/engineering/infrastructure/debugging-network-stalls-on-kubernetes/


How interrupts work

Imagine the following:

```
┌─────────────────┐
│      NIC        │
│  (Hardware)     │
└────────┬────────┘
         │ IRQ signal via PCIe
         ▼
┌─────────────────────┐
│ Interrupt Controller│
│   (APIC/IOAPIC)     │
└────────┬────────────┘
         │ Vector number
         ▼
┌─────────────────────┐
│       CPU           │
│                     │
│ Uses vector as      │
│ index into IDT      │
└────────┬────────────┘
         │
         ▼
┌─────────────────────────────┐
│   IDT (Kernel Memory)       │
│  [Interrupt Desc Table]     │
│                             │
│  Index │ Handler Address    │
│  ──────┼──────────────────  │
│    0   │ divide_error       │
│    1   │ debug              │
│   ...  │ ...                │
│   43   │ e1000_intr() ◄──── driver registered this
│   ...  │ ...                │
│   255  │ ...                │
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────┐
│  Handler Execution  │
│   (Kernel Code)     │
│                     │
│  - Read NIC regs    │
│  - Process packets  │
│  - Schedule softirq │
└─────────────────────┘
```


This is roughly a general representation of how interrupts work in the case of network traffic. The hardware part tells the interrupt controller (which is also hardware) that network segments are available. The interrupt controller yells at the CPU: hey, check this out! The kernel then reads its interrupt table, check which interrupt it must issue, and consume the network data. 

But this is a complex task. Imagine the interrupt controller is receiving dozens, thousands of requests per second. If the kernel issues an interrupt for each one of them (1 packet = 1MTU),


NIC - 

What they found out: 

1. 


