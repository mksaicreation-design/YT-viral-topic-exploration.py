import os
import hashlib
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests
import streamlit as st

API_BASE = "https://www.googleapis.com/youtube/v3"
SEARCH_URL = f"{API_BASE}/search"
VIDEOS_URL = f"{API_BASE}/videos"
CHANNELS_URL = f"{API_BASE}/channels"

CATEGORY_KEYWORDS = {
    "Space & Science": [
        "NASA latest discoveries", "Mars exploration", "James Webb Space Telescope discoveries",
        "black holes explained", "alien life scientific evidence", "space mysteries documentary",
        "new exoplanets discovered", "solar system facts", "neutron stars explained",
        "space news this week", "dark matter explained", "astronomy discoveries",
        "Mars rover discoveries", "habitable planets", "universe mysteries",
        "NASA Artemis mission", "space documentary", "scientific mysteries of the universe",
    ],
    "History & Mystery": [
        "unsolved historical mysteries", "ancient civilizations discoveries", "lost cities history",
        "archaeological discoveries", "historical mysteries documentary", "forgotten history",
        "mysterious events in history", "ancient technology explained",
    ],
    "AI & Technology": [
        "latest AI tools", "artificial intelligence news", "new technology discoveries",
        "AI explained", "future technology documentary", "robotics breakthroughs",
        "AI tools for creators", "technology trends",
    ],
    "Pets & Animals": [
        "dog facts", "cat behavior explained", "rare animal discoveries",
        "amazing wildlife documentary", "pet care tips", "animal mysteries",
        "funny pet videos", "animal intelligence",
    ],
    "YouTube Shorts Trends": [
        "viral science shorts", "space facts shorts", "amazing facts shorts",
        "history facts shorts", "animal shorts", "technology shorts",
    ],
    "Reddit Relationship Stories": [
        "Reddit relationship stories", "Reddit cheating story", "AITA relationship update",
        "surviving infidelity story", "relationship advice Reddit", "marriage story Reddit",
    ],
}

st.set_page_config(page_title="YouTube Viral Topics Tool", page_icon="📈", layout="wide")
st.title("📈 YouTube Viral Topics Research Tool")
st.caption("Discover recent YouTube videos, rank topic opportunities, create original-script prompts, and export research results.")

with st.sidebar:
    st.header("Search settings")
    api_key = st.text_input(
        "YouTube Data API v3 key",
        value=st.secrets.get("YOUTUBE_API_KEY", os.getenv("YOUTUBE_API_KEY", "")),
        type="password",
        help="Your key is used for API requests. Do not publish it in your repository.",
    )
    days = st.slider("Published within the last (days)", 1, 30, 7)
    max_per_keyword = st.slider("Results per keyword", 5, 50, 10, step=5)
    subscriber_limit_mode = st.radio(
        "Subscriber limit mode",
        ["Use a limit", "No limit"],
        horizontal=True,
        index=0,
        help="Choose a maximum subscriber count, or remove the subscriber limit entirely.",
    )
    if subscriber_limit_mode == "No limit":
        max_subscribers = 0
    else:
        subscriber_limit_choice = st.selectbox(
            "Maximum channel subscribers",
            ["3,000 (recommended)", "1,000", "5,000", "10,000", "Custom (enter below)"],
            index=0,
            help="Choose a preset limit or enter your own number below.",
        )
        custom_subscriber_limit = st.number_input(
            "Custom maximum subscribers",
            min_value=1,
            max_value=1000000000,
            value=3000,
            step=500,
            help="This field is always available when 'Use a limit' is selected. It is used only when 'Custom (enter below)' is selected.",
        )
        if subscriber_limit_choice == "Custom (enter below)":
            max_subscribers = int(custom_subscriber_limit)
        else:
            max_subscribers = int(subscriber_limit_choice.split()[0].replace(",", ""))

    hidden_subscriber_option = st.selectbox(
        "Channels with hidden subscriber counts",
        [
            "Exclude hidden subscriber channels (recommended)",
            "Include hidden subscriber channels",
        ],
        index=0,
        help="Hidden subscriber counts cannot be compared with a numeric limit. To include these channels, select No limit and then choose Include hidden subscriber channels.",
    )
    include_hidden_subscribers = hidden_subscriber_option.startswith("Include")
    if include_hidden_subscribers and max_subscribers > 0:
        st.info("Hidden-subscriber channels will be excluded while a numeric subscriber limit is active. Select No limit to include them.")

    min_views = st.number_input("Minimum views", min_value=0, value=1000, step=500)
    region = st.selectbox("Region", ["Worldwide", "United Kingdom", "United States", "Canada", "Australia", "India"])
    region_codes = {"Worldwide": None, "United Kingdom": "GB", "United States": "US", "Canada": "CA", "Australia": "AU", "India": "IN"}
    language = st.selectbox("Search language", ["Any", "English"])

st.subheader("1. Choose a topic category")
categories = list(CATEGORY_KEYWORDS.keys())
selected_category = st.selectbox("Topic Category", categories, index=categories.index("Space & Science"))

# When category changes, refresh the editable keyword text area with that category's defaults.
if "keyword_category" not in st.session_state:
    st.session_state.keyword_category = selected_category
if "keyword_text" not in st.session_state:
    st.session_state.keyword_text = "\n".join(CATEGORY_KEYWORDS[selected_category])
if selected_category != st.session_state.keyword_category:
    st.session_state.keyword_category = selected_category
    st.session_state.keyword_text = "\n".join(CATEGORY_KEYWORDS[selected_category])

st.caption("Selecting a category fills in suggested keywords automatically. You can edit, add, or delete any line before searching.")
st.text_area(
    "Search keywords (one phrase per line)",
    key="keyword_text",
    height=230,
    help="These are editable suggestions for your chosen category.",
)
keywords = list(dict.fromkeys([x.strip() for x in st.session_state.keyword_text.splitlines() if x.strip()]))

st.subheader("2. Search and analyse")
st.write(f"Selected category: **{selected_category}** · Keywords: **{len(keywords)}**")

def api_get(url, params):
    try:
        response = requests.get(url, params=params, timeout=25)
    except requests.RequestException as exc:
        raise RuntimeError(f"Network request failed: {exc}") from exc
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(f"YouTube API returned a non-JSON response (HTTP {response.status_code}).") from exc
    if response.status_code >= 400 or "error" in data:
        err = data.get("error", {}).get("message", f"HTTP {response.status_code}")
        raise RuntimeError(err)
    return data

def chunks(items, size=50):
    for i in range(0, len(items), size):
        yield items[i:i + size]

def fetch_research(api_key, keywords, days, max_per_keyword, max_subscribers, min_views, region_code, language, include_hidden_subscribers):
    published_after = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds").replace("+00:00", "Z")
    raw_videos = {}
    progress = st.progress(0, text="Preparing searches…")
    status = st.empty()
    total = max(len(keywords), 1)

    for idx, keyword in enumerate(keywords, start=1):
        status.write(f"Searching {idx}/{total}: **{keyword}**")
        params = {
            "part": "snippet", "q": keyword, "type": "video", "order": "viewCount",
            "publishedAfter": published_after, "maxResults": max_per_keyword, "key": api_key,
        }
        if region_code:
            params["regionCode"] = region_code
        if language == "English":
            params["relevanceLanguage"] = "en"
        data = api_get(SEARCH_URL, params)
        for item in data.get("items", []):
            vid = item.get("id", {}).get("videoId")
            snippet = item.get("snippet", {})
            if vid and vid not in raw_videos:
                raw_videos[vid] = {
                    "video_id": vid, "title": snippet.get("title", ""),
                    "description": snippet.get("description", "")[:300],
                    "channel_id": snippet.get("channelId", ""),
                    "channel_title": snippet.get("channelTitle", ""),
                    "published_at": snippet.get("publishedAt", ""),
                    "keyword": keyword,
                    "thumbnail": snippet.get("thumbnails", {}).get("medium", {}).get("url", ""),
                }
        progress.progress(idx / total, text=f"Completed {idx}/{total} keyword searches")

    progress.empty()
    status.empty()
    if not raw_videos:
        return pd.DataFrame()

    videos = list(raw_videos.values())
    video_stats = {}
    for group in chunks([v["video_id"] for v in videos], 50):
        data = api_get(VIDEOS_URL, {"part": "statistics,contentDetails,snippet", "id": ",".join(group), "key": api_key})
        for item in data.get("items", []):
            video_stats[item["id"]] = item

    channel_ids = list(dict.fromkeys(v["channel_id"] for v in videos if v["channel_id"]))
    channel_stats = {}
    for group in chunks(channel_ids, 50):
        data = api_get(CHANNELS_URL, {"part": "statistics,snippet", "id": ",".join(group), "key": api_key})
        for item in data.get("items", []):
            channel_stats[item["id"]] = item

    now = datetime.now(timezone.utc)
    rows = []
    for v in videos:
        vs = video_stats.get(v["video_id"], {})
        cs = channel_stats.get(v["channel_id"], {})
        stats = vs.get("statistics", {})
        cstats = cs.get("statistics", {})
        views = int(stats.get("viewCount", 0) or 0)
        hidden = cstats.get("hiddenSubscriberCount") is True
        subscribers = None if hidden or "subscriberCount" not in cstats else int(cstats.get("subscriberCount", 0) or 0)
        try:
            pub_dt = datetime.fromisoformat(v["published_at"].replace("Z", "+00:00"))
            age_days = max((now - pub_dt).total_seconds() / 86400, 1 / 24)
        except (ValueError, TypeError):
            pub_dt, age_days = None, float(days)
        views_per_day = views / age_days
        ratio = (views / subscribers) if subscribers and subscribers > 0 else None
        viral_score = round((views_per_day ** 0.55) * (max(ratio or 0, 0) + 1) ** 0.35, 2)
        rows.append({
            "Title": v["title"], "Channel": v["channel_title"],
            "Published": pub_dt.strftime("%Y-%m-%d %H:%M UTC") if pub_dt else v["published_at"],
            "Age (days)": round(age_days, 2), "Views": views,
            "Views/day": round(views_per_day, 1), "Subscribers": subscribers,
            "Views/subscribers": round(ratio, 2) if ratio is not None else None,
            "Viral score": viral_score, "Category": selected_category,
            "Keyword": v["keyword"], "URL": f"https://www.youtube.com/watch?v={v['video_id']}",
            "Description": v["description"], "Thumbnail": v["thumbnail"], "Video ID": v["video_id"],
        })
    df = pd.DataFrame(rows).drop_duplicates(subset=["Video ID"])
    if max_subscribers > 0:
        # Hidden subscriber counts cannot be verified against a numeric limit.
        df = df[df["Subscribers"].notna() & (df["Subscribers"] < max_subscribers)]
    elif not include_hidden_subscribers:
        # With no numeric limit, the user can still choose to exclude hidden counts.
        df = df[df["Subscribers"].notna()]
    df = df[df["Views"] >= min_views].copy()
    if df.empty:
        return df

    # Relative heuristics calculated only among the videos returned by this search.
    views_day_pct = df["Views/day"].rank(pct=True).fillna(0)
    ratio_pct = df["Views/subscribers"].rank(pct=True).fillna(0.5)
    freshness_pct = (1 - df["Age (days)"].rank(pct=True)).fillna(0)
    df["Viral Potential Score"] = (
        100 * (0.50 * views_day_pct + 0.35 * ratio_pct + 0.15 * freshness_pct)
    ).round().astype(int)

    # Competition proxy: number of candidate videos associated with each keyword.
    keyword_counts = df.groupby("Keyword")["Video ID"].transform("count")
    df["Observed topic results"] = keyword_counts.astype(int)
    count_rank = keyword_counts.rank(pct=True)
    df["Topic competition"] = count_rank.map(
        lambda p: "Low" if p <= 1/3 else ("Medium" if p <= 2/3 else "High")
    )
    df["Opportunity Score"] = (
        100 * (0.65 * (df["Viral Potential Score"] / 100) + 0.35 * (1 - count_rank))
    ).round().astype(int)
    df["Opportunity label"] = df["Opportunity Score"].map(
        lambda score: "Strong opportunity" if score >= 70
        else ("Worth testing" if score >= 45 else "Lower signal / review carefully")
    )
    return df

if st.button("🔎 Fetch viral topic candidates", type="primary", use_container_width=True):
    if not api_key.strip():
        st.error("Enter a YouTube Data API v3 key in the sidebar first.")
    elif not keywords:
        st.error("Add at least one keyword.")
    else:
        try:
            with st.spinner("Collecting YouTube video and channel data…"):
                result_df = fetch_research(
                    api_key.strip(), keywords, days, max_per_keyword, int(max_subscribers),
                    int(min_views), region_codes[region], language, include_hidden_subscribers
                )
            st.session_state["viral_results"] = result_df
            st.session_state["viral_category"] = selected_category
            if result_df.empty:
                st.warning("No videos matched these filters. Try a longer date range, lower minimum views, or broader keywords.")
            else:
                st.success(f"Found {len(result_df):,} matching videos for {selected_category}.")
        except RuntimeError as exc:
            st.error(f"YouTube API error: {exc}")
            st.caption("Check that YouTube Data API v3 is enabled, the key is valid, and your Google Cloud project has quota remaining.")
        except Exception as exc:
            st.error(f"Unexpected error: {exc}")

results = st.session_state.get("viral_results")
if isinstance(results, pd.DataFrame) and not results.empty:
    st.divider()
    st.subheader(f"Results: {st.session_state.get('viral_category', selected_category)}")
    sort_by = st.selectbox(
        "Sort results by",
        ["Opportunity Score", "Viral Potential Score", "Viral score", "Views", "Views/day", "Views/subscribers", "Newest"],
    )
    sort_map = {
        "Opportunity Score": ("Opportunity Score", False),
        "Viral Potential Score": ("Viral Potential Score", False),
        "Viral score": ("Viral score", False), "Views": ("Views", False),
        "Views/day": ("Views/day", False), "Views/subscribers": ("Views/subscribers", False),
        "Newest": ("Published", False),
    }
    col, asc = sort_map[sort_by]
    shown = results.sort_values(col, ascending=asc, na_position="last").reset_index(drop=True)
    a, b, c, d = st.columns(4)
    a.metric("Videos", f"{len(shown):,}")
    b.metric("Total views", f"{int(shown['Views'].sum()):,}")
    c.metric("Median views/day", f"{shown['Views/day'].median():,.0f}")
    ratios = shown["Views/subscribers"].dropna()
    d.metric("Median views/subscribers", f"{ratios.median():.2f}×" if not ratios.empty else "N/A")
    st.markdown("### Topic ideas ranked by opportunity")
    st.caption(
        "Scores are estimates relative to this search result set, not official YouTube metrics. "
        "Observed competition counts only the filtered candidate videos found for a keyword; "
        "it does not measure all competition on YouTube."
    )
    keyword_summary = (
        shown.groupby("Keyword", dropna=False)
        .agg(
            Candidate_videos=("Video ID", "count"),
            Median_views_per_day=("Views/day", "median"),
            Median_viral_potential=("Viral Potential Score", "median"),
            Median_opportunity=("Opportunity Score", "median"),
            Competition=("Topic competition", lambda values: values.mode().iloc[0] if not values.mode().empty else "Medium"),
        )
        .reset_index()
        .sort_values(["Median_opportunity", "Median_views_per_day"], ascending=False)
        .rename(columns={
            "Keyword": "Topic keyword",
            "Candidate_videos": "Candidate videos",
            "Median_views_per_day": "Median views/day",
            "Median_viral_potential": "Median viral potential",
            "Median_opportunity": "Opportunity score",
            "Competition": "Observed competition",
        })
    )
    st.dataframe(keyword_summary, use_container_width=True, hide_index=True)

    st.markdown("### Video candidates")
    st.dataframe(
        shown[["Title", "Channel", "Published", "Views", "Views/day", "Subscribers",
               "Views/subscribers", "Viral score", "Viral Potential Score",
               "Topic competition", "Opportunity Score", "Opportunity label", "Keyword", "URL"]],
        use_container_width=True, hide_index=True,
        column_config={
            "URL": st.column_config.LinkColumn("Watch", display_text="Open video"),
            "Views": st.column_config.NumberColumn(format="%d"),
            "Subscribers": st.column_config.NumberColumn(format="%d"),
            "Views/day": st.column_config.NumberColumn(format="%.1f"),
            "Views/subscribers": st.column_config.NumberColumn(format="%.2f×"),
            "Viral score": st.column_config.NumberColumn(format="%.2f"),
            "Viral Potential Score": st.column_config.NumberColumn(format="%d/100"),
            "Opportunity Score": st.column_config.NumberColumn(format="%d/100"),
        },
    )
    st.divider()
    st.subheader("3. Create an original-script prompt for ChatGPT")
    st.write(
        "Choose a promising topic and create a ready-to-paste prompt. The prompt uses public metadata "
        "as research context, not as material to copy or rewrite."
    )
    topic_options = keyword_summary["Topic keyword"].tolist()
    chosen_topic = st.selectbox("Choose a topic for your video", topic_options, key="prompt_topic")
    prompt_col1, prompt_col2, prompt_col3 = st.columns(3)
    with prompt_col1:
        target_language = st.selectbox("Script language", ["English", "Urdu", "English + Urdu"], index=0)
        target_duration = st.selectbox("Video duration", ["60-second Short", "3 minutes", "5 minutes", "8 minutes", "10 minutes"], index=2)
    with prompt_col2:
        target_style = st.selectbox("Video style", ["Documentary", "Explainer", "Mystery storytelling", "Top facts", "Educational storytelling"])
        target_audience = st.selectbox("Target audience", ["General audience", "Beginners", "Space and science fans", "History fans", "Families"])
    with prompt_col3:
        voice_style = st.selectbox("Narration tone", ["Clear and engaging", "Cinematic documentary", "Warm and conversational", "Suspenseful but factual"])
        include_shorts = st.checkbox("Also suggest a Shorts version", value=True)
    unique_angle = st.text_input(
        "Your preferred unique angle (optional)",
        placeholder="e.g. explain what most videos miss, with verified facts and a strong opening",
    )

    topic_rows = shown[shown["Keyword"] == chosen_topic].sort_values("Opportunity Score", ascending=False).head(5)
    refs = []
    for _, refrow in topic_rows.iterrows():
        refs.append(
            f"- Title: {refrow['Title']} | Channel: {refrow['Channel']} | "
            f"Views: {int(refrow['Views']):,} | Views/day: {refrow['Views/day']} | "
            f"Published: {refrow['Published']} | URL: {refrow['URL']}"
        )
    reference_block = "\\n".join(refs) if refs else "No candidate video metadata available."
    prompt_text = f"""You are an expert YouTube researcher, fact-checker, and original scriptwriter.

TASK
Create an ORIGINAL YouTube video concept and script about: {chosen_topic}
Selected category: {st.session_state.get('viral_category', selected_category)}
Language: {target_language}
Target duration: {target_duration}
Format: {target_style}
Audience: {target_audience}
Narration tone: {voice_style}
Optional unique angle: {unique_angle.strip() or "Choose a distinctive angle that adds value beyond common summaries."}

REFERENCE RESEARCH (metadata only; use as topic signals, not as text to copy)
{reference_block}

STRICT ORIGINALITY AND ACCURACY RULES
1. Do not copy, closely paraphrase, or imitate the wording, structure, jokes, distinctive framing, or narration of the reference videos.
2. Do not assume that video titles or view counts prove a factual claim. Verify important factual claims using reliable primary or authoritative sources, and provide source links.
3. If a fact cannot be verified, label it as uncertain or omit it. Never invent quotes, studies, dates, or statistics.
4. Develop a fresh thesis, structure, examples, and transitions. Do not reproduce any reference video's transcript.
5. Do not include copyrighted footage, music, images, or other assets unless the user has rights or a suitable licence. Suggest original visuals, public-domain materials, or properly licensed assets and identify any licensing checks needed.
6. Do not guarantee that the script is copyright-free or that it cannot receive a claim. Flag legal uncertainty for human review.

DELIVERABLES
A. Explain why this topic may interest viewers, distinguishing observed signals from speculation.
B. Give 3 original title options and 3 thumbnail concepts.
C. Write a compelling opening hook, then a complete timed script with narration, scene/visual suggestions, and on-screen text.
D. Add a fact-check table: claim, source URL, confidence, and whether further verification is needed.
E. Provide a list of original visual prompts and sound-design suggestions that avoid copying reference assets.
F. Add a pre-publication checklist for factual accuracy, originality, licences, music, and platform policies.
{"Also create a separate 30–60 second Shorts adaptation with a distinct hook and wording." if include_shorts else "Do not create a Shorts adaptation unless requested separately."}

Return practical, production-ready output. Clearly separate verified facts, creative suggestions, and items requiring human review."""
    prompt_widget_key = "generated_script_prompt_" + hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()[:12]
    st.text_area("Generated ChatGPT prompt", value=prompt_text, height=320, key=prompt_widget_key)
    st.download_button(
        "⬇️ Download ChatGPT script prompt (TXT)",
        data=prompt_text.encode("utf-8"),
        file_name="chatgpt_original_script_prompt.txt",
        mime="text/plain",
        use_container_width=True,
    )

    with st.expander("Quality & copyright review checklist"):
        st.caption(
            "This is a human review checklist, not a legal opinion or automated copyright detector. "
            "It cannot guarantee that a video will avoid claims."
        )
        review_items = [
            "The script has a distinct thesis, structure, and wording.",
            "Important facts have reliable source links and have been checked.",
            "No reference transcript, distinctive phrasing, or creator-specific style was copied.",
            "Every image, clip, music track, sound effect, and font has a documented licence or permission.",
            "AI-generated content has been reviewed for factual errors and misleading depictions.",
            "Titles and thumbnails accurately represent the video.",
            "The final script and assets have been reviewed by a human before publishing.",
        ]
        for item in review_items:
            st.checkbox(item, key="review_" + str(review_items.index(item)))

    with st.expander("Plugin Manager — future automation connectors"):
        st.info(
            "Manual workflow is active. This section is an extension point only; no external AI or video-generation plugin is connected yet."
        )
        st.markdown(
            "- **ChatGPT Prompt Export:** Available now; copy or download the generated prompt.\n"
            "- **OpenAI API Script Writer:** Planned plugin; requires an OpenAI API key and API usage billing.\n"
            "- **Research/Fact-check Connector:** Planned plugin; should return source URLs and confidence notes.\n"
            "- **Voice-over Connector:** Planned plugin for a provider such as ElevenLabs.\n"
            "- **Video Generation/Editing Connector:** Planned plugin for licensed assets and supported providers.\n\n"
            "Future connectors should be installed and configured individually, with API keys stored in Streamlit Secrets rather than source code."
        )

    st.divider()
    st.download_button(
        "⬇️ Download results as CSV",
        data=shown.to_csv(index=False).encode("utf-8-sig"),
        file_name="youtube_viral_topic_research.csv",
        mime="text/csv",
        use_container_width=True,
    )
    with st.expander("View video descriptions and thumbnails"):
        for _, row in shown.head(20).iterrows():
            st.markdown(f"**[{row['Title']}]({row['URL']})**")
            st.caption(f"{row['Channel']} · {row['Views']:,} views · Keyword: {row['Keyword']}")
            if row.get("Thumbnail"):
                st.image(row["Thumbnail"], width=220)
            st.write(row["Description"])
            st.divider()
else:
    st.markdown("### How the metrics work")
    st.markdown(
        "- **Views/day:** total views divided by the approximate age of the video.\n"
        "- **Views/subscribers:** compares video views with channel subscriber count.\n"
        "- **Viral score:** a heuristic for sorting candidates, not an official YouTube metric.\\n"
        "- **Viral Potential Score (0–100):** a relative score using views/day, views/subscribers, and recency within this result set.\\n"
        "- **Topic competition:** a low/medium/high proxy based on filtered candidate counts per keyword, not the whole YouTube market.\\n"
        "- **Opportunity Score (0–100):** combines the relative viral score with the inverse of the observed competition proxy."
    )
    st.caption("Search results depend on your keywords, region, selected date range, YouTube API quota, and public data availability.")
