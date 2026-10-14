# YouTube Viral Topics Research Tool — Category Edition

## Run
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy from Android tablet
1. Extract this ZIP.
2. In GitHub, create a repository.
3. Upload `app.py`, `requirements.txt`, and `README.md` to the repository root.
4. Open https://share.streamlit.io/ and deploy the repository with main file `app.py`.
5. Enter your YouTube Data API v3 key in the app's password field.

## Category dropdown
The category selector automatically fills the editable keyword area. Changing category loads its suggested keyword set; edit any keywords before searching. Categories include Space & Science, History & Mystery, AI & Technology, Pets & Animals, YouTube Shorts Trends, and Reddit Relationship Stories.

## Safety and limitations
Do not commit your API key to GitHub. The app accepts it in the password field. Results are limited by YouTube Data API quota and search coverage. Viral score is a heuristic, not an official YouTube metric.
