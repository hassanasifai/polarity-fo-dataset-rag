# Screen Recording Notes

## Official Task 1 Recording

The official screen-recording deliverable is committed in this repository:

- Local path: `demo/task1_rag_walkthrough.mp4`
- Raw main-branch link: `https://raw.githubusercontent.com/hassanasifai/polarity-fo-dataset-rag/main/demo/task1_rag_walkthrough.mp4`
- Repository main: `https://github.com/hassanasifai/polarity-fo-dataset-rag/tree/main`

The MP4 was generated from the local review UI on 2026-05-18 and covers the six scenarios below.

## Hosted URL Status

The Stage 1 task document asks for **a live URL or screen recording**. This submission uses the committed screen recording as the official demo evidence because no Hugging Face, Streamlit Community Cloud, or equivalent deployment token/login is available in this environment.

If a hosted URL is added later, deploy from:

- GitHub repository: `https://github.com/hassanasifai/polarity-fo-dataset-rag/tree/main`
- Streamlit entrypoint: `rag_demo/src/ui/app.py`
- Working directory: `rag_demo`
- Build command: `pip install -r requirements.txt && python scripts/build_all.py`
- Run command: `streamlit run src/ui/app.py`

After deployment, replace this section's status line and add the public app URL to `SUBMISSION_COVER.md`, `README.md`, and this file.

## Walkthrough Scenarios

1. Cat Trail entity lookup: shows selected `fo_001` evidence and source domains.
2. Ralph phone query: abstains and highlights missing phone evidence.
3. Ohana SEC query: shows CRD `158515` and SEC citation.
4. Pathstone recent activity: shows date, outlet, activity, and source.
5. California SEC filtered listing: shows records as a table.
6. Cat Trail vs Ohana comparison: shows side-by-side fields and missing contact availability.

The submitted deliverable is the committed MP4 above; no external deployment is required for Task 1 review.
