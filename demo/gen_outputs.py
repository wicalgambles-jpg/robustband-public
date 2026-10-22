# SPDX-License-Identifier: MIT
"""设备自适应的模型输出生成（C′ 真实演示的第一步）。
同一份脚本在 CPU / 4090D 上零改动运行：DEVICE = cuda if available else cpu。
逐序列贪心（do_sample=False）以保证可复现。
用法：
  HF_ENDPOINT=https://hf-mirror.com python gen_outputs.py \
      --model Qwen/Qwen2.5-0.5B-Instruct --items 200 --out data/out_Qwen0.5B.jsonl
"""

# 控制台健壮性：Windows 传统控制台默认 GBK，无法编码中文/−/✔ 等字形会直接崩溃。
# 强制 UTF-8 输出（现代终端正确渲染；无法编码的字符以替代符输出，绝不崩溃）。
import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import os
import re
import gc
import json
import argparse
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

HERE = os.path.dirname(os.path.abspath(__file__))

SYS = "You are a helpful math assistant. Solve the problem step by step, then give the final numeric answer."


def build_prompt(tok, q, style, model_id):
    user = q.strip()
    if style == "cot":
        user += "\n\nSolve step by step, then write the final answer on the last line as: 'The answer is <number>.'"
    msgs = [{"role": "system", "content": SYS}, {"role": "user", "content": user}]
    return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--items", type=int, default=200)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--max-new-tokens", type=int, default=256)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--style", default="cot", choices=["plain", "cot"])
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[dev] device={DEVICE} model={args.model} items={args.items} offset={args.offset}")

    items = json.load(open(os.path.join(HERE, "data", "items.json"), encoding="utf-8"))
    items = items[args.offset:args.offset + args.items]

    tok = AutoTokenizer.from_pretrained(args.model, padding_side="left")
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    # 设备自适应权重精度：GPU 用 fp16；CPU 用 bf16（= checkpoint 原生 dtype，无损且省内存，
    # 避免 fp32 上转把 1.5B 撑到 ~6.2GB 触发 OOM）。
    dtype = torch.float16 if DEVICE.type == "cuda" else torch.bfloat16
    # CPU 强制 eager 注意力：Qwen 的 sliding-window 未在 sdpa 实现，batched+padding 下会**原生硬崩**（本机实测）
    attn = "eager" if DEVICE.type == "cpu" else "sdpa"
    model = AutoModelForCausalLM.from_pretrained(args.model, torch_dtype=dtype, attn_implementation=attn)
    model.to(DEVICE).eval()

    outs = []
    t0 = time.time()
    path = os.path.join(HERE, args.out) if not os.path.isabs(args.out) else args.out
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # 增量落盘 + 逐批释放 + gc：CPU 上 1.5B 实测有 flaky 原生崩（无 traceback），
    # 增量写可保住已生成项；gc 缓解逐 batch 内存累积导致的 OOM。
    fout = open(path, "w", encoding="utf-8")
    try:
        for b in range(0, len(items), args.batch_size):
            chunk = items[b:b + args.batch_size]
            prompts = [build_prompt(tok, it["q"], args.style, args.model) for it in chunk]
            enc = tok(prompts, return_tensors="pt", padding=True).to(DEVICE)
            with torch.inference_mode():
                gen = model.generate(**enc, do_sample=False, max_new_tokens=args.max_new_tokens,
                                     pad_token_id=tok.pad_token_id)
            new = gen[:, enc["input_ids"].shape[1]:]
            for it, seq in zip(chunk, new):
                raw = tok.decode(seq, skip_special_tokens=True).strip()
                o = {"raw": raw, "gold": it["gold"], "meta": it["meta"]}
                outs.append(o)
                fout.write(json.dumps(o, ensure_ascii=False) + "\n")
                fout.flush()
            del enc, gen, new
            gc.collect()
            done = min(b + args.batch_size, len(items))
            el = time.time() - t0
            print(f"  {done}/{len(items)}  {el:.0f}s  ({done/max(el,1e-9):.2f} it/s)", flush=True)
    finally:
        fout.close()
    print(f"[done] wrote {len(outs)} -> {path}  ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
