# NVIDIA SASS Control Signals: SM70 (Volta) & SM80 (Ampere)

This document summarizes the technical understanding of the 128-bit SASS instruction control word mapping, reverse-engineered during the development of the FMA-to-MUL+ADD rewriter.

## Instruction Format Overview
Instructions on SM70/SM80 are 128-bit, represented as two 64-bit words: `h1` (Low) and `h2` (High).
*   **h1**: Contains the primary opcode, destination registers, and the first two source registers.
*   **h2**: Contains the third/fourth source registers (if applicable), immediate values, reuse flags, and the **Control Word**.

## Control Word Mapping
The Control Word occupies bits **41 through 63** of the `h2` word.

| Bits | Field | Description |
| :--- | :--- | :--- |
| **41-44** | **Stall** | 4-bit unsigned integer (0-15). Specifies the number of clock cycles the scheduler must wait before issuing the *next* instruction. |
| **45** | **Yield** | 1-bit flag. A hint to the scheduler that it is safe to switch to a different warp (latency hiding). `0` usually means Yield enabled. |
| **46-48** | **WriteSB** | 3-bit index (0-5). Marks a scoreboard to be set when the instruction finishes writing its result. `7` means no scoreboard allocation. |
| **49-51** | **ReadSB** | 3-bit index (0-5). Marks a scoreboard to be released once source operands are read (WAR hazard protection). `7` means no scoreboard allocation. |
| **52-57** | **WaitSB** | 6-bit mask. Each bit corresponds to a scoreboard (0-5). The instruction will block until all scoreboards marked in the mask are released. |
| **58-61** | **Reuse** | 4-bit mask. Hints to the register file to cache specific source operands for reuse by the next instruction. |

---

## Hazard Resolution Strategies

### 1. The RAW (Read-After-Write) Hazard
When splitting `FFMA RD, RA, RB, RC` into:
1. `FMUL temp, RA, RB`
2. `FADD RD, temp, RC`

The `FADD` has a RAW dependency on `temp`. On SM70, `FMUL` has a latency of ~4 cycles.

*   **Fixed Stall Strategy**: Setting the `Stall` bits of the `FMUL` to `4` (or `15` for maximum safety) ensures the hardware waits long enough for `temp` to be written before `FADD` issues.
*   **Scoreboard Strategy**: Setting `WriteSB=0` on `FMUL` and `WaitSB bit 0` on `FADD` allows the hardware to issue `FADD` as soon as the functional unit releases the result, maximizing throughput.

### 2. The WAR (Write-After-Read) Hazard
If an instruction is delayed (e.g., a Global Load `LDG`), a subsequent instruction might overwrite its source register before it has been read.
*   The `ReadSB` field is used to ensure the load is protected until the data is safely off the register file.

### 3. Surgical Dependency Inheritance
The rewriter uses a **Surgical Inheritance** strategy to ensure compatibility with compiler-generated code:
*   **FMUL** inherits the original `WaitSB` from the `FFMA`. This ensures `FMUL` doesn't start until the loads for `RA` and `RB` are complete.
*   **FADD** inherits the original `WriteSB` from the `FFMA`. This ensures that subsequent instructions in the program (which expect `RD` to be ready) still wait for the `FADD` to finish.

---

## Toolchain Observations

### NVDisasm Sensitivity
`nvdisasm` performs strict table lookups on the control bits.
*   Providing an invalid `Opclass` combined with non-zero bits in indices 0-7 of `h2` (where `RC` used to be) triggers `Unrecognized operation for functional unit 'uC'`.
*   Invalid scoreboard combinations or out-of-range stalls trigger `undefined value` errors in the internal `TABLES_opex` mappings.

### REGCOUNT Impact
The hardware traps (`Illegal Instruction`) if an instruction attempts to access a register index higher than the `REGCOUNT` value stored in the `.nv.info` and Section Header. Even if the SASS is valid, the hardware scheduler enforces this strictly to manage thread-block occupancy.
