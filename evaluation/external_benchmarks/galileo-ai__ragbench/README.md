---
license: cc-by-4.0
dataset_info:
- config_name: covidqa
  features:
  - name: id
    dtype: string
  - name: question
    dtype: string
  - name: documents
    sequence: string
  - name: response
    dtype: string
  - name: generation_model_name
    dtype: string
  - name: annotating_model_name
    dtype: string
  - name: dataset_name
    dtype: string
  - name: documents_sentences
    sequence:
      sequence:
        sequence: string
  - name: response_sentences
    sequence:
      sequence: string
  - name: sentence_support_information
    list:
    - name: explanation
      dtype: string
    - name: fully_supported
      dtype: bool
    - name: response_sentence_key
      dtype: string
    - name: supporting_sentence_keys
      sequence: string
  - name: unsupported_response_sentence_keys
    sequence: string
  - name: adherence_score
    dtype: bool
  - name: overall_supported_explanation
    dtype: string
  - name: relevance_explanation
    dtype: string
  - name: all_relevant_sentence_keys
    sequence: string
  - name: all_utilized_sentence_keys
    sequence: string
  - name: trulens_groundedness
    dtype: float64
  - name: trulens_context_relevance
    dtype: float64
  - name: ragas_faithfulness
    dtype: float64
  - name: ragas_context_relevance
    dtype: float64
  - name: gpt3_adherence
    dtype: float64
  - name: gpt3_context_relevance
    dtype: float64
  - name: gpt35_utilization
    dtype: float64
  - name: relevance_score
    dtype: float64
  - name: utilization_score
    dtype: float64
  - name: completeness_score
    dtype: float64
  splits:
  - name: train
    num_bytes: 9055112
    num_examples: 1252
  - name: test
    num_bytes: 1727572
    num_examples: 246
  - name: validation
    num_bytes: 1912181
    num_examples: 267
  download_size: 5971008
  dataset_size: 12694865
- config_name: cuad
  features:
  - name: id
    dtype: string
  - name: question
    dtype: string
  - name: documents
    sequence: string
  - name: response
    dtype: string
  - name: generation_model_name
    dtype: string
  - name: annotating_model_name
    dtype: string
  - name: dataset_name
    dtype: string
  - name: documents_sentences
    sequence:
      sequence:
        sequence: string
  - name: response_sentences
    sequence:
      sequence: string
  - name: sentence_support_information
    list:
    - name: explanation
      dtype: string
    - name: fully_supported
      dtype: bool
    - name: response_sentence_key
      dtype: string
    - name: supporting_sentence_keys
      sequence: string
  - name: unsupported_response_sentence_keys
    sequence: string
  - name: adherence_score
    dtype: bool
  - name: overall_supported_explanation
    dtype: string
  - name: relevance_explanation
    dtype: string
  - name: all_relevant_sentence_keys
    sequence: string
  - name: all_utilized_sentence_keys
    sequence: string
  - name: trulens_groundedness
    dtype: float64
  - name: trulens_context_relevance
    dtype: float64
  - name: ragas_faithfulness
    dtype: float64
  - name: ragas_context_relevance
    dtype: float64
  - name: gpt3_adherence
    dtype: float64
  - name: gpt3_context_relevance
    dtype: float64
  - name: gpt35_utilization
    dtype: float64
  - name: relevance_score
    dtype: float64
  - name: utilization_score
    dtype: float64
  - name: completeness_score
    dtype: float64
  splits:
  - name: train
    num_bytes: 182478144
    num_examples: 1530
  - name: validation
    num_bytes: 57319053
    num_examples: 510
  - name: test
    num_bytes: 46748691
    num_examples: 510
  download_size: 84927484
  dataset_size: 286545888
- config_name: delucionqa
  features:
  - name: id
    dtype: string
  - name: question
    dtype: string
  - name: documents
    sequence: string
  - name: response
    dtype: string
  - name: generation_model_name
    dtype: string
  - name: annotating_model_name
    dtype: string
  - name: dataset_name
    dtype: string
  - name: documents_sentences
    sequence:
      sequence:
        sequence: string
  - name: response_sentences
    sequence:
      sequence: string
  - name: sentence_support_information
    list:
    - name: explanation
      dtype: string
    - name: fully_supported
      dtype: bool
    - name: response_sentence_key
      dtype: string
    - name: supporting_sentence_keys
      sequence: string
  - name: unsupported_response_sentence_keys
    sequence: string
  - name: adherence_score
    dtype: bool
  - name: overall_supported_explanation
    dtype: string
  - name: relevance_explanation
    dtype: string
  - name: all_relevant_sentence_keys
    sequence: string
  - name: all_utilized_sentence_keys
    sequence: string
  - name: trulens_groundedness
    dtype: float64
  - name: trulens_context_relevance
    dtype: float64
  - name: ragas_faithfulness
    dtype: float64
  - name: ragas_context_relevance
    dtype: float64
  - name: gpt3_adherence
    dtype: float64
  - name: gpt3_context_relevance
    dtype: float64
  - name: gpt35_utilization
    dtype: float64
  - name: relevance_score
    dtype: float64
  - name: utilization_score
    dtype: float64
  - name: completeness_score
    dtype: float64
  splits:
  - name: train
    num_bytes: 18650496
    num_examples: 1460
  - name: validation
    num_bytes: 2177923
    num_examples: 182
  - name: test
    num_bytes: 2375521
    num_examples: 184
  download_size: 5318525
  dataset_size: 23203940
- config_name: emanual
  features:
  - name: id
    dtype: string
  - name: question
    dtype: string
  - name: documents
    sequence: string
  - name: response
    dtype: string
  - name: generation_model_name
    dtype: string
  - name: annotating_model_name
    dtype: string
  - name: dataset_name
    dtype: string
  - name: documents_sentences
    sequence:
      sequence:
        sequence: string
  - name: response_sentences
    sequence:
      sequence: string
  - name: sentence_support_information
    list:
    - name: explanation
      dtype: string
    - name: fully_supported
      dtype: bool
    - name: response_sentence_key
      dtype: string
    - name: supporting_sentence_keys
      sequence: string
  - name: unsupported_response_sentence_keys
    sequence: string
  - name: adherence_score
    dtype: bool
  - name: overall_supported_explanation
    dtype: string
  - name: relevance_explanation
    dtype: string
  - name: all_relevant_sentence_keys
    sequence: string
  - name: all_utilized_sentence_keys
    sequence: string
  - name: trulens_groundedness
    dtype: float64
  - name: trulens_context_relevance
    dtype: float64
  - name: ragas_faithfulness
    dtype: float64
  - name: ragas_context_relevance
    dtype: float64
  - name: gpt3_adherence
    dtype: float64
  - name: gpt3_context_relevance
    dtype: float64
  - name: gpt35_utilization
    dtype: float64
  - name: relevance_score
    dtype: float64
  - name: utilization_score
    dtype: float64
  - name: completeness_score
    dtype: float64
  splits:
  - name: train
    num_bytes: 9748871
    num_examples: 1054
  - name: validation
    num_bytes: 1193359
    num_examples: 132
  - name: test
    num_bytes: 1280363
    num_examples: 132
  download_size: 2292660
  dataset_size: 12222593
- config_name: expertqa
  features:
  - name: id
    dtype: string
  - name: question
    dtype: string
  - name: documents
    sequence: string
  - name: response
    dtype: string
  - name: generation_model_name
    dtype: string
  - name: annotating_model_name
    dtype: string
  - name: dataset_name
    dtype: string
  - name: documents_sentences
    sequence:
      sequence:
        sequence: string
  - name: response_sentences
    sequence:
      sequence: string
  - name: sentence_support_information
    list:
    - name: explanation
      dtype: string
    - name: fully_supported
      dtype: bool
    - name: response_sentence_key
      dtype: string
    - name: supporting_sentence_keys
      sequence: string
  - name: unsupported_response_sentence_keys
    sequence: string
  - name: adherence_score
    dtype: bool
  - name: overall_supported_explanation
    dtype: string
  - name: relevance_explanation
    dtype: string
  - name: all_relevant_sentence_keys
    sequence: string
  - name: all_utilized_sentence_keys
    sequence: string
  - name: trulens_groundedness
    dtype: float64
  - name: trulens_context_relevance
    dtype: float64
  - name: ragas_faithfulness
    dtype: float64
  - name: ragas_context_relevance
    dtype: float64
  - name: gpt3_adherence
    dtype: float64
  - name: gpt3_context_relevance
    dtype: float64
  - name: gpt35_utilization
    dtype: float64
  - name: relevance_score
    dtype: float64
  - name: utilization_score
    dtype: float64
  - name: completeness_score
    dtype: float64
  splits:
  - name: train
    num_bytes: 41944570
    num_examples: 1621
  - name: validation
    num_bytes: 4179337
    num_examples: 203
  - name: test
    num_bytes: 5132792
    num_examples: 203
  download_size: 27804260
  dataset_size: 51256699
- config_name: finqa
  features:
  - name: id
    dtype: string
  - name: question
    dtype: string
  - name: documents
    sequence: string
  - name: response
    dtype: string
  - name: generation_model_name
    dtype: string
  - name: annotating_model_name
    dtype: string
  - name: dataset_name
    dtype: string
  - name: documents_sentences
    sequence:
      sequence:
        sequence: string
  - name: response_sentences
    sequence:
      sequence: string
  - name: sentence_support_information
    list:
    - name: explanation
      dtype: string
    - name: fully_supported
      dtype: bool
    - name: response_sentence_key
      dtype: string
    - name: supporting_sentence_keys
      sequence: string
  - name: unsupported_response_sentence_keys
    sequence: string
  - name: adherence_score
    dtype: bool
  - name: overall_supported_explanation
    dtype: string
  - name: relevance_explanation
    dtype: string
  - name: all_relevant_sentence_keys
    sequence: string
  - name: all_utilized_sentence_keys
    sequence: string
  - name: trulens_groundedness
    dtype: float64
  - name: trulens_context_relevance
    dtype: float64
  - name: ragas_faithfulness
    dtype: float64
  - name: ragas_context_relevance
    dtype: float64
  - name: gpt3_adherence
    dtype: float64
  - name: gpt3_context_relevance
    dtype: float64
  - name: gpt35_utilization
    dtype: float64
  - name: relevance_score
    dtype: float64
  - name: utilization_score
    dtype: float64
  - name: completeness_score
    dtype: float64
  splits:
  - name: train
    num_bytes: 141636050
    num_examples: 12502
  - name: validation
    num_bytes: 19723115
    num_examples: 1766
  - name: test
    num_bytes: 25607832
    num_examples: 2294
  download_size: 75943796
  dataset_size: 186966997
- config_name: hagrid
  features:
  - name: id
    dtype: string
  - name: question
    dtype: string
  - name: documents
    sequence: string
  - name: response
    dtype: string
  - name: generation_model_name
    dtype: string
  - name: annotating_model_name
    dtype: string
  - name: dataset_name
    dtype: string
  - name: documents_sentences
    sequence:
      sequence:
        sequence: string
  - name: response_sentences
    sequence:
      sequence: string
  - name: sentence_support_information
    list:
    - name: explanation
      dtype: string
    - name: fully_supported
      dtype: bool
    - name: response_sentence_key
      dtype: string
    - name: supporting_sentence_keys
      sequence: string
  - name: unsupported_response_sentence_keys
    sequence: string
  - name: adherence_score
    dtype: bool
  - name: overall_supported_explanation
    dtype: string
  - name: relevance_explanation
    dtype: string
  - name: all_relevant_sentence_keys
    sequence: string
  - name: all_utilized_sentence_keys
    sequence: string
  - name: trulens_groundedness
    dtype: float64
  - name: trulens_context_relevance
    dtype: float64
  - name: ragas_faithfulness
    dtype: float64
  - name: ragas_context_relevance
    dtype: float64
  - name: gpt3_adherence
    dtype: float64
  - name: gpt3_context_relevance
    dtype: float64
  - name: gpt35_utilization
    dtype: float64
  - name: relevance_score
    dtype: float64
  - name: utilization_score
    dtype: float64
  - name: completeness_score
    dtype: float64
  splits:
  - name: train
    num_bytes: 17710422
    num_examples: 2892
  - name: validation
    num_bytes: 1910449
    num_examples: 322
  - name: test
    num_bytes: 8238507
    num_examples: 1318
  download_size: 14435405
  dataset_size: 27859378
- config_name: hotpotqa
  features:
  - name: id
    dtype: string
  - name: question
    dtype: string
  - name: documents
    sequence: string
  - name: response
    dtype: string
  - name: generation_model_name
    dtype: string
  - name: annotating_model_name
    dtype: string
  - name: dataset_name
    dtype: string
  - name: documents_sentences
    sequence:
      sequence:
        sequence: string
  - name: response_sentences
    sequence:
      sequence: string
  - name: sentence_support_information
    list:
    - name: explanation
      dtype: string
    - name: fully_supported
      dtype: bool
    - name: response_sentence_key
      dtype: string
    - name: supporting_sentence_keys
      sequence: string
  - name: unsupported_response_sentence_keys
    sequence: string
  - name: adherence_score
    dtype: bool
  - name: overall_supported_explanation
    dtype: string
  - name: relevance_explanation
    dtype: string
  - name: all_relevant_sentence_keys
    sequence: string
  - name: all_utilized_sentence_keys
    sequence: string
  - name: trulens_groundedness
    dtype: float64
  - name: trulens_context_relevance
    dtype: float64
  - name: ragas_faithfulness
    dtype: float64
  - name: ragas_context_relevance
    dtype: float64
  - name: gpt3_adherence
    dtype: float64
  - name: gpt3_context_relevance
    dtype: float64
  - name: gpt35_utilization
    dtype: float64
  - name: relevance_score
    dtype: float64
  - name: utilization_score
    dtype: float64
  - name: completeness_score
    dtype: float64
  splits:
  - name: train
    num_bytes: 11178145
    num_examples: 1883
  - name: test
    num_bytes: 2264863
    num_examples: 390
  - name: validation
    num_bytes: 2493601
    num_examples: 424
  download_size: 9130974
  dataset_size: 15936609
- config_name: msmarco
  features:
  - name: id
    dtype: string
  - name: question
    dtype: string
  - name: documents
    sequence: string
  - name: response
    dtype: string
  - name: generation_model_name
    dtype: string
  - name: annotating_model_name
    dtype: string
  - name: dataset_name
    dtype: string
  - name: documents_sentences
    sequence:
      sequence:
        sequence: string
  - name: response_sentences
    sequence:
      sequence: string
  - name: sentence_support_information
    list:
    - name: explanation
      dtype: string
    - name: fully_supported
      dtype: bool
    - name: response_sentence_key
      dtype: string
    - name: supporting_sentence_keys
      sequence: string
  - name: unsupported_response_sentence_keys
    sequence: string
  - name: adherence_score
    dtype: bool
  - name: overall_supported_explanation
    dtype: string
  - name: relevance_explanation
    dtype: string
  - name: all_relevant_sentence_keys
    sequence: string
  - name: all_utilized_sentence_keys
    sequence: string
  - name: trulens_groundedness
    dtype: float64
  - name: trulens_context_relevance
    dtype: float64
  - name: ragas_faithfulness
    dtype: float64
  - name: ragas_context_relevance
    dtype: float64
  - name: gpt3_adherence
    dtype: float64
  - name: gpt3_context_relevance
    dtype: float64
  - name: gpt35_utilization
    dtype: float64
  - name: relevance_score
    dtype: float64
  - name: utilization_score
    dtype: float64
  - name: completeness_score
    dtype: float64
  splits:
  - name: train
    num_bytes: 18391043
    num_examples: 1870
  - name: test
    num_bytes: 4241489
    num_examples: 423
  - name: validation
    num_bytes: 3978837
    num_examples: 397
  download_size: 13254359
  dataset_size: 26611369
- config_name: pubmedqa
  features:
  - name: id
    dtype: string
  - name: question
    dtype: string
  - name: documents
    sequence: string
  - name: response
    dtype: string
  - name: generation_model_name
    dtype: string
  - name: annotating_model_name
    dtype: string
  - name: dataset_name
    dtype: string
  - name: documents_sentences
    sequence:
      sequence:
        sequence: string
  - name: response_sentences
    sequence:
      sequence: string
  - name: sentence_support_information
    list:
    - name: explanation
      dtype: string
    - name: fully_supported
      dtype: bool
    - name: response_sentence_key
      dtype: string
    - name: supporting_sentence_keys
      sequence: string
  - name: unsupported_response_sentence_keys
    sequence: string
  - name: adherence_score
    dtype: bool
  - name: overall_supported_explanation
    dtype: string
  - name: relevance_explanation
    dtype: string
  - name: all_relevant_sentence_keys
    sequence: string
  - name: all_utilized_sentence_keys
    sequence: string
  - name: trulens_groundedness
    dtype: float64
  - name: trulens_context_relevance
    dtype: float64
  - name: ragas_faithfulness
    dtype: float64
  - name: ragas_context_relevance
    dtype: float64
  - name: gpt3_adherence
    dtype: float64
  - name: gpt3_context_relevance
    dtype: float64
  - name: gpt35_utilization
    dtype: float64
  - name: relevance_score
    dtype: float64
  - name: utilization_score
    dtype: float64
  - name: completeness_score
    dtype: float64
  splits:
  - name: train
    num_bytes: 164267525
    num_examples: 19600
  - name: validation
    num_bytes: 20385411
    num_examples: 2450
  - name: test
    num_bytes: 20627293
    num_examples: 2450
  download_size: 100443939
  dataset_size: 205280229
- config_name: tatqa
  features:
  - name: id
    dtype: string
  - name: question
    dtype: string
  - name: documents
    sequence: string
  - name: response
    dtype: string
  - name: generation_model_name
    dtype: string
  - name: annotating_model_name
    dtype: string
  - name: dataset_name
    dtype: string
  - name: documents_sentences
    sequence:
      sequence:
        sequence: string
  - name: response_sentences
    sequence:
      sequence: string
  - name: sentence_support_information
    list:
    - name: explanation
      dtype: string
    - name: fully_supported
      dtype: bool
    - name: response_sentence_key
      dtype: string
    - name: supporting_sentence_keys
      sequence: string
  - name: unsupported_response_sentence_keys
    sequence: string
  - name: adherence_score
    dtype: bool
  - name: overall_supported_explanation
    dtype: string
  - name: relevance_explanation
    dtype: string
  - name: all_relevant_sentence_keys
    sequence: string
  - name: all_utilized_sentence_keys
    sequence: string
  - name: trulens_groundedness
    dtype: float64
  - name: trulens_context_relevance
    dtype: float64
  - name: ragas_faithfulness
    dtype: float64
  - name: ragas_context_relevance
    dtype: float64
  - name: gpt3_adherence
    dtype: float64
  - name: gpt3_context_relevance
    dtype: float64
  - name: gpt35_utilization
    dtype: float64
  - name: relevance_score
    dtype: float64
  - name: utilization_score
    dtype: float64
  - name: completeness_score
    dtype: float64
  splits:
  - name: train
    num_bytes: 164535889
    num_examples: 26430
  - name: validation
    num_bytes: 20771276
    num_examples: 3336
  - name: test
    num_bytes: 19828536
    num_examples: 3338
  download_size: 78488641
  dataset_size: 205135701
- config_name: techqa
  features:
  - name: id
    dtype: string
  - name: question
    dtype: string
  - name: documents
    sequence: string
  - name: response
    dtype: string
  - name: generation_model_name
    dtype: string
  - name: annotating_model_name
    dtype: string
  - name: dataset_name
    dtype: string
  - name: documents_sentences
    sequence:
      sequence:
        sequence: string
  - name: response_sentences
    sequence:
      sequence: string
  - name: sentence_support_information
    list:
    - name: explanation
      dtype: string
    - name: fully_supported
      dtype: bool
    - name: response_sentence_key
      dtype: string
    - name: supporting_sentence_keys
      sequence: string
  - name: unsupported_response_sentence_keys
    sequence: string
  - name: adherence_score
    dtype: bool
  - name: overall_supported_explanation
    dtype: string
  - name: relevance_explanation
    dtype: string
  - name: all_relevant_sentence_keys
    sequence: string
  - name: all_utilized_sentence_keys
    sequence: string
  - name: trulens_groundedness
    dtype: float64
  - name: trulens_context_relevance
    dtype: float64
  - name: ragas_faithfulness
    dtype: float64
  - name: ragas_context_relevance
    dtype: float64
  - name: gpt3_adherence
    dtype: float64
  - name: gpt3_context_relevance
    dtype: float64
  - name: gpt35_utilization
    dtype: float64
  - name: relevance_score
    dtype: float64
  - name: utilization_score
    dtype: float64
  - name: completeness_score
    dtype: float64
  splits:
  - name: train
    num_bytes: 54780607
    num_examples: 1192
  - name: validation
    num_bytes: 14226891
    num_examples: 304
  - name: test
    num_bytes: 14115978
    num_examples: 314
  download_size: 33240403
  dataset_size: 83123476
configs:
- config_name: covidqa
  data_files:
  - split: train
    path: covidqa/train-*
  - split: test
    path: covidqa/test-*
  - split: validation
    path: covidqa/validation-*
- config_name: cuad
  data_files:
  - split: train
    path: cuad/train-*
  - split: validation
    path: cuad/validation-*
  - split: test
    path: cuad/test-*
- config_name: delucionqa
  data_files:
  - split: train
    path: delucionqa/train-*
  - split: validation
    path: delucionqa/validation-*
  - split: test
    path: delucionqa/test-*
- config_name: emanual
  data_files:
  - split: train
    path: emanual/train-*
  - split: validation
    path: emanual/validation-*
  - split: test
    path: emanual/test-*
- config_name: expertqa
  data_files:
  - split: train
    path: expertqa/train-*
  - split: validation
    path: expertqa/validation-*
  - split: test
    path: expertqa/test-*
- config_name: finqa
  data_files:
  - split: train
    path: finqa/train-*
  - split: validation
    path: finqa/validation-*
  - split: test
    path: finqa/test-*
- config_name: hagrid
  data_files:
  - split: train
    path: hagrid/train-*
  - split: validation
    path: hagrid/validation-*
  - split: test
    path: hagrid/test-*
- config_name: hotpotqa
  data_files:
  - split: train
    path: hotpotqa/train-*
  - split: test
    path: hotpotqa/test-*
  - split: validation
    path: hotpotqa/validation-*
- config_name: msmarco
  data_files:
  - split: train
    path: msmarco/train-*
  - split: test
    path: msmarco/test-*
  - split: validation
    path: msmarco/validation-*
- config_name: pubmedqa
  data_files:
  - split: train
    path: pubmedqa/train-*
  - split: validation
    path: pubmedqa/validation-*
  - split: test
    path: pubmedqa/test-*
- config_name: tatqa
  data_files:
  - split: train
    path: tatqa/train-*
  - split: validation
    path: tatqa/validation-*
  - split: test
    path: tatqa/test-*
- config_name: techqa
  data_files:
  - split: train
    path: techqa/train-*
  - split: validation
    path: techqa/validation-*
  - split: test
    path: techqa/test-*
---
# RAGBench

## Dataset Overview
RAGBEnch is a large-scale RAG benchmark dataset of 100k RAG examples.
It covers five unique industry-specific domains and various RAG task types.
RAGBench examples are sourced from industry corpora such as user manuals, making it particularly relevant for industry applications.

RAGBench comrises 12 sub-component datasets, each one split into train/validation/test splits

## Usage
```
from datasets import load_dataset

# load train/validation/test splits of individual subset
ragbench_hotpotqa = load_dataset("rungalileo/ragbench", "hotpotqa")

# load a specific split of a subset dataset
ragbench_hotpotqa = load_dataset("rungalileo/ragbench", "hotpotqa", split="test")

# load the full ragbench dataset
ragbench = {}
for dataset in ['covidqa', 'cuad', 'delucionqa', 'emanual', 'expertqa', 'finqa', 'hagrid', 'hotpotqa', 'msmarco', 'pubmedqa', 'tatqa', 'techqa']:
  ragbench[dataset] = load_dataset("rungalileo/ragbench", dataset)
```