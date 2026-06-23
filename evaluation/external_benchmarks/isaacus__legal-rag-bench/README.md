---
pretty_name: Legal RAG Bench
task_categories:
- text-retrieval
- question-answering
tags:
- legal
- law
- australia
language:
- en
language_details: en-AU
annotations_creators:
- expert-generated
- found
language_creators:
- expert-generated
- found
license: cc-by-nc-sa-4.0
size_categories:
- 1K<n<10K
source_datasets:
- Criminal Charge Book
configs:
- config_name: corpus
  data_files:
  - split: test
    path: corpus.jsonl
  default: true
- config_name: qa
  data_files:
  - split: test
    path: qa.jsonl
---

# Legal RAG Bench ‍⚖️
[**Legal RAG Bench**](https://isaacus.com/blog/legal-rag-bench) by [Isaacus](https://isaacus.com/) is a reasoning-intensive benchmark for assessing the end-to-end, real-world performance of production-grade legal RAG systems.

Legal RAG Bench is composed of 4,876 passages sampled from the [Judicial College of Victoria’s Criminal Charge Book](https://resources.judicialcollege.vic.edu.au/article/1053858) alongside 100 complex, handwritten questions demanding expert-level knowledge of Victorian criminal law and procedure to be answered correctly.

Legal RAG Bench is the first open dataset for the evaluation of legal RAG systems to label both relevant passages as well as the correct answers to questions, enabling apples-to-apples assessments of the relative impact of information retrieval and generative models on end RAG performance.

[Kanon 2 Embedder](https://isaacus.com/blog/introducing-kanon-2-embedder) currently delivers the fewest errors on Legal RAG Bench out of Gemini 3 Pro, GPT-5.2, Text Embedding 3 Large, and Gemini Embedding 001. It also ranks first on the [Massive Legal Embedding Benchmark](https://isaacus.com/mleb), the most comprehensive benchmark for legal embeddings.


<a href="https://arxiv.org/abs/2603.01710"><img
  src="https://cdn-uploads.huggingface.co/production/uploads/6497ffbf2a997a45e987e139/GDWdLUsXfq-C-bTya291g.png"
  alt="Decomposed error rates for each combination of frontier embedding model and LLM on Legal RAG Bench." width="1024px" /></a>


## Usage 👩‍💻
Legal RAG Bench may be loaded like so using the Hugging Face 🤗 [`datasets`](https://huggingface.co/docs/datasets/en/index) Python library:
```python
import datasets

# Load passages in Legal RAG Bench.
corpus = datasets.load_dataset("isaacus/legal-rag-bench", name="corpus", split="test")

# Load question-answer-passage triplets from Legal RAG Bench.
qa = datasets.load_dataset("isaacus/legal-rag-bench", name="qa", split="test")
```

## Structure 🗂️
Passages in the Legal RAG Bench corpus are stored in the `corpus` subset, with each entry having the following fields:
- `id (string)`: a unique identifier for the passage.
- `text (string)`: the text of the passage, formatted in Markdown.

Questions, answers, and the IDs of relevant passages are stored in the `qa` subset, with each entry having the following fields:
- `id (string)`: a unique identifier for the question.
- `question (string)`: the text of the expert-written question.
- `answer (string)`: the text of the expert-written answer to the question.
- `relevant_passage_id (string)`: the unique identifier of the passage in the `corpus` subset that is most relevant to the question.

The `corpus` and `qa` subsets of Legal RAG Bench both currently have only a single split, `test`.

## Methodology 🧪
Legal RAG Bench was constructed by downloading each section of the Criminal Charge Book Book as Microsoft Word documents and converting them into Markdown. A complex set of heuristics was leveraged to break sections up into their full hierarchy, such as chapters and subchapters. Where necessary, sections were further chunked using the [`semchunk`](https://github.com/isaacus-dev/semchunk) semantic chunking algorithm such that no chunk was over 512 tokens in length as determined by the original [Kanon tokenizer](https://huggingface.co/isaacus/kanon-tokenizer).

After building a corpus of 4,876 passages, passages were randomly sampled to produce 100 handwritten, complex, and meaningfully challenging questions that, to the maximum extent possible, would require each of those passages alone to be answered correctly. Questions were deliberately designed to be lexically dissimilar from relevant passages in order to stress test the semantic understanding of evaluated models.

## License 📜
This dataset is licensed under [CC BY NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/deed.en) which allows for non-commercial use of this dataset as long as appropriate attribution is made to it.

## Citation 🔖
If you use this dataset, please cite the [Massive Legal Embeddings Benchmark (MLEB)](https://arxiv.org/abs/2510.19365) as well.

```
@misc{butler2026legalragbench,
      title={Legal RAG Bench: an end-to-end benchmark for legal RAG}, 
      author={Abdur-Rahman Butler and Umar Butler},
      year={2026},
      eprint={2603.01710},
      archivePrefix={arXiv},
      primaryClass={cs.CL},
      url={https://arxiv.org/abs/2603.01710}, 
}

@misc{butler2025massivelegalembeddingbenchmark,
      title={The Massive Legal Embedding Benchmark (MLEB)}, 
      author={Umar Butler and Abdur-Rahman Butler and Adrian Lucas Malec},
      year={2025},
      eprint={2510.19365},
      archivePrefix={arXiv},
      primaryClass={cs.CL},
      url={https://arxiv.org/abs/2510.19365}, 
}
```