# DEAL — the language of contracts

**A contract-first programming language designed for AI-authored code.**
[Русский ниже](#deal--язык-договоров)

AI systems fail not at writing code, but at the free-text channel to it:
hallucinations live where an AI can write something "plausible" and it
ends up somewhere real. DEAL removes the channel. An AI never edits text —
it submits **verifiable transformations** over a canonical AST, and the
compiler is the only thing that ever touches the code, judging every
transaction mechanically.

```text
 AI (head / hands / small models)
      |  submits a TRANSFORMATION (atomic AST operation)
      v
 DEAL COMPILER (8 stages)
      |  completeness court -> feasibility court -> witness execution
      |  -> serial hash -> chronicle -> registry
      |  REFUSAL is always verbal (culprit + cause + what to fix)
      v
 .deal COMPONENT = canonical AST (single source of truth)
                      \--> PROJECTION (readable view, always printed from the AST)
```

## Example in 60 seconds

```text
contract деление(a: int, b: int) -> int
  requires  b != 0
  ensures   rounded(a / b, 2)
  refusal   деление_на_ноль

deal цена_за_единицу(месячный: int, человек: int) -> int
  body:
    price = деление(месячный, человек)
    return price
  witness:
    месячный=100000, человек=4  -> 25000.00
    месячный=100000, человек=0  -> refusal деление_на_ноль
```

- A `.deal` file stores the **machine-readable AST (JSON)** — the single
  source of truth. There is no "program text" to drift.
- The human-readable **projection is printed** from the AST — it cannot
  be written by hand, only rendered.
- **Witnesses** (input -> output / refusal) are executed by the compiler
  in a sandbox. Plausible-but-unverified code cannot pass.
- Every refusal is verbal: `{stage, culprit, cause, what_to_fix}` —
  the AI fixes itself without a human in the loop.

## Properties (each with a mechanism)

1. **Decompilation always, losslessly** — "decompile" means "print the AST".
2. **Canon** — one spelling, one encoding, one form of every construct.
3. **Address = hash of the contract** — components recognise each other
   by content, not paths; loose dependencies are impossible.
4. **Chronicle built into the runtime** — every transformation is
   recorded as before/after; history cannot be shortened.
5. **Machine verdicts** — a witness verdict is computed, never read.
6. **Refusals are always verbal** — no silent failures.
7. **Export modes** — transparent `.deal` or native binary without the
   AST, per component; the AST always stays in the vault.

## Status

A live pilot has closed stages 0–3 (Python VM -> self-compilation,
byte-for-byte) and is running stage 4: the x86-64 emitter is itself
written in DEAL. On vector workloads DEAL matches Rust (both sides
vectorized) and is 1350+ times faster than Python on the same task.
Full documentation, an interactive Python/Rust/DEAL benchmark, a
downloadable compiler and a browser interpreter: [deal-lang.lteam.ru](https://deal-lang.lteam.ru/).

## License

[MIT](LICENSE)

---

# DEAL — язык договоров

**Язык с договорами прежде всего — спроектирован для кода, который пишет ИИ.**

ИИ ненадёжен не в написании кода, а в свободном текстовом канале к нему:
галлюцинация живёт там, где ИИ может написать «похоже на правду» и это
куда-то попадёт. DEAL убирает канал. ИИ не редактирует текст — ИИ подаёт
**верифицируемые превращения** над каноничным AST, а компилятор
единственный касается кода и судит каждую сделку машинно.

- Файл `.deal` хранит **машиночитаемый AST в JSON** — единственный источник.
- Читаемая **проекция печатается** из AST — её нельзя написать руками.
- **Свидетели** (вход → выход / отказ) исполняются компилятором в песочнице.
- Каждый отказ — словами: `{стадия, виновник, причина, что_править}`.

## Статус

Живой пилот закрыл ступени 0–3 (питон-ВМ → самокомпиляция, байт-в-байт)
и живёт на ступени 4: эмиссор x86-64 написан НА DEAL. На векторных
задачах DEAL сопоставим с Rust (обе стороны векторные) и на ×1350+
быстрее питона на той же задаче. Полная документация, интерактивный
бенчмарк Python/Rust/DEAL, скачиваемый компилятор и веб-интерпретатор:
[deal-lang.lteam.ru](https://deal-lang.lteam.ru/).
