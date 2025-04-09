# TWCC Utilities

## Environment Setup

Clone `.env.example` to `.env` and fill in the values.

Install the requirements.

```bash
pip install -r requirements.txt
```

## Analyze GPU time of all containers.

```bash
# default to fetch 7 days
python fetch_gpu_util.py && python check_gpu_util.py
```

## Easily create TWCC container

TBD
