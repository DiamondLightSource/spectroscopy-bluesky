
## i0

BL20I-EA-IAMP-01

clibration mode,sensitvity mode
BL20I-EA-IAMP-01:IOUC

## i1

BL20I-EA-IAMP-04

and looks the same as the one above

## it

it's 02

## iref is 03

## table

BL20I-EA-TABLE-02:X.VAL with x, y, sample rotation, fine rotation

also MO-Table-03 with 6 degrees of movement

t1 opticts table EA-01
with x, y

## gas rig

it's opened in a separate window
has a complex diagram to the 4 ion chmbers

the root is BL20I-EA-GIT-01

and six valuves: V3

PCTRL1:SETPOINT:WR for setting argon

for puring
valve V5:CON to 2 to reset line valve
then to 0 then 0 to open

pressure = 01PCTRL1:P:RD

pump on = VACP1:CON set to 0, off to set to 1

v1 is Kr, v2 is N2, V3 is Ar

with .STA

then just some

## diagram

```mermaid
flowchart TD
    title([BL20I-EA-GIR-01 - Gas Injection Rig])

    subgraph Inputs
        %% Inputs
        Kr[Kr] --> KrV[Valve 1]
        N2[N2] --> N2V[Valve 2]
        Ar[Ar] --> ArV[Valve 3]

        %% He input goes directly to Pressure 2
        He[He] 
    end

    %% Pressure 1 Loop
    KrV --> P1[Pressure 1]
    N2V --> P1
    ArV --> P1

    He[He] --> HeV[Valve PCTRL2] --> P2
    P1 --> VToP2[Valve to Pressure 2] --> P2[Pressure 2]

    P1 --> ReadoutP1[readout 01:P1] --> Pump[Pump with on off reset]

    P1 --> V4[Top closed loop V4] --> P1
    P1 --> V5[Pump side closed loop V5] --> P1


    %% Outputs from Pressure 2
    P2 --> V6[Valve 6] --> ReadoutP2[Readout P2, between the valve and ionc 1715 mBar] --> IONC1
    P2 --> V7[Valve 7] --> ReadoutP3[Readout P3, between the valve and ionc 1713 mBar] --> IONC2
    P2 --> V8[Valve 8] --> ReadoutP4[Readout P4, between the valve and ionc 1692 mBar] --> IONC3
    P2 --> V9[Valve 9] --> ReadoutP5[Readout P5, between the valve and ionc 1611 mBar] --> IONC4

    title -.-> Kr
    title -.-> N2
    title -.-> Ar
    title -.-> He
```

and IONC1 is i0,

BL20I-EA-GIR-01:VACP1:CON is the pump - on, off, reset
