import os
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
st.caption("Discover recent YouTube videos, compare performance, and export research results.")

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
    return df[df["Views"] >= min_views]

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
    sort_by = st.selectbox("Sort results by", ["Viral score", "Views", "Views/day", "Views/subscribers", "Newest"])
    sort_map = {
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
    st.dataframe(
        shown[["Title", "Channel", "Published", "Views", "Views/day", "Subscribers", "Views/subscribers", "Viral score", "Keyword", "URL"]],
        use_container_width=True, hide_index=True,
        column_config={
            "URL": st.column_config.LinkColumn("Watch", display_text="Open video"),
            "Views": st.column_config.NumberColumn(format="%d"),
            "Subscribers": st.column_config.NumberColumn(format="%d"),
            "Views/day": st.column_config.NumberColumn(format="%.1f"),
            "Views/subscribers": st.column_config.NumberColumn(format="%.2f×"),
            "Viral score": st.column_config.NumberColumn(format="%.2f"),
        },
    )
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
        "- **Viral score:** a heuristic for sorting candidates, not an official YouTube metric."
    )
    st.caption("Search results depend on your keywords, region, selected date range, YouTube API quota, and public data availability.")
