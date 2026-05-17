# Deployment Or Recording Notes

## Preferred Public Demo

Run the Streamlit app:

```powershell
cd rag_demo
streamlit run src\ui\app.py
```

Then record or deploy a walkthrough of these six scenarios:

1. Cat Trail entity lookup: shows selected `fo_001` evidence and source domains.
2. Ralph phone query: abstains and highlights missing phone evidence.
3. Ohana SEC query: shows CRD `158515` and SEC citation.
4. Pathstone recent activity: shows date, outlet, activity, and source.
5. California SEC filtered listing: shows records as a table.
6. Cat Trail vs Ohana comparison: shows side-by-side fields and missing contact availability.

## Included Recording

`demo/task1_rag_walkthrough.mp4` was generated from the local Streamlit app on 2026-05-18. It covers all six scenarios above and can be uploaded as the final screen-recording link if a public Streamlit/Hugging Face deployment is not ready.

## Deployment Caveat

This repository is local-first and does not require paid API keys. Cold-start behavior on Streamlit Community Cloud or Hugging Face Spaces depends on local model cache and CPU budget. The eval runner intentionally uses BM25/exact-match retrieval for deterministic speed, while the interactive app exposes the hybrid dense + BM25 path.

Submission fallback: use the screen recording artifact generated from the local Streamlit walkthrough plus the public GitHub branch link. Public Hugging Face Spaces deployment remains a bonus because it requires account/project setup outside this repository.
