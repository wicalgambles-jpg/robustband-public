# Data and model attribution

The frozen examples in `demo/data/items.json`, `demo/data/Qwen0.5B_cot.jsonl`,
and `demo/data_real/{cot,plain}.jsonl` use the GSM8K test set.

GSM8K: Copyright (c) 2021 OpenAI. The dataset is distributed under the MIT
License; retain this copyright notice and the MIT permission notice in this
repository's `LICENSE` when redistributing these files.

- Original dataset: https://github.com/openai/grade-school-math
- Dataset license: https://github.com/openai/grade-school-math/blob/master/LICENSE
- Dataset card: https://huggingface.co/datasets/openai/gsm8k

The raw completions were generated using `Qwen/Qwen2.5-0.5B-Instruct`, whose
model card lists Apache-2.0. No model weights are included in this repository.
The exact model revision used for the frozen completions was not recorded.

- Model card: https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct

## EvalScope integration fixtures (0.4.0)

`examples/data/evalscope/` preserves four public visualization review files from
ModelScope EvalScope, revision `cbe6c8019c72a75749290b02a95be03aea094e49`.
The source repository is Apache-2.0, Copyright (c) 2022-2023 Alibaba ModelScope.
Its complete license is retained as `LICENSE-APACHE-2.0.txt`. Source URLs and
byte/normalized-text hashes are in `manifest.json`; these files were not edited.

- Source: https://github.com/modelscope/evalscope/tree/cbe6c8019c72a75749290b02a95be03aea094e49/examples/viz
- License: https://github.com/modelscope/evalscope/blob/cbe6c8019c72a75749290b02a95be03aea094e49/LICENSE
- GSM8K questions and answers retain OpenAI's MIT notice above.
- IFEval prompts originate from Google IFEval, distributed under Apache-2.0:
  https://huggingface.co/datasets/google/IFEval/blob/main/README.md
  and https://github.com/google-research/google-research/tree/master/instruction_following_eval

The files contain archived outputs attributed upstream to `qwen-plus` and
`qwen3-max`, plus upstream evaluation scores. No new inference was performed;
no model weights are redistributed. Those aliases do not identify immutable
weights or provide evidence of independent human grading. IFEval instruction
graders were not rerun. No GPQA examples are included in this addition.

The manuscript build script downloads the official JMLR style solely as a local
typesetting input. That style is excluded from the software source distribution;
its upstream URL and hash are recorded in the manuscript build report.
