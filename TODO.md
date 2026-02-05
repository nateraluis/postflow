# PostFlow TODO

## 📸 Marketing & Landing Page

### Take Analytics Screenshots for Landing Page
**Priority**: High
**Location**: `postflow/static/postflow/screenshots/`

Take screenshots of the following analytics dashboards and save them with these exact filenames:
- `top-engagers.png` - Top Engagers/Super Fans dashboard
- `engagement-timeline.png` - Engagement timeline chart/graph
- `posting-calendar.png` - Posting calendar heatmap (once implemented)
- `platform-comparison.png` - Cross-platform analytics comparison view

**Tips**:
- Use actual data (blur sensitive usernames if needed)
- Resize to ~800-1000px wide
- Optimize/compress images for web
- PNG or JPG format
- Capture the most impressive/engaging parts of the dashboards

**Note**: The landing page works without these (images hide gracefully with `onerror`), but having them will significantly improve conversion rates by showing visitors what PostFlow looks like.

---

## Analytics Improvements - Priority Ranking

### 🚀 High Priority (Implement First)

#### 1. **GitHub-Style Posting Calendar** ⭐
- Create heatmap showing posts per day over time
- Color intensity based on frequency or total engagement
- Hover tooltips with post count and engagement metrics
- Date range selector (30/90/365 days)
- Streak counter for consecutive posting days
- **Data**: `PixelfedPost.posted_at`
- **Impact**: Visual, motivational, helps build consistency habit
- **Difficulty**: Medium

#### 2. ~~**Top Engagers / Super Fans Dashboard**~~ ✅ **COMPLETED**
- ✅ Leaderboard of users who engage most with your content
- ✅ Show total likes + comments per user
- ✅ Display username and interaction counts
- ✅ Filter by time period (all-time, 30/90 days)
- ✅ Implemented for **Pixelfed** and **Mastodon** (full engagement data available)
- ❌ **Not implemented for Instagram** - API doesn't provide commenter usernames
- **Data**: Aggregates from likes/favourites, comments/replies, shares/reblogs
- **Implementation**: Shared template `analytics/shared/top_engagers.html`
- **Features**: Top 3 widget on dashboard, dedicated leaderboard page, weighted scoring (comments 3x, shares 2x, likes 1x)

#### 3. **Best Time to Post Analysis** ⏰
- Heatmap showing average engagement by day of week + hour
- Identify optimal posting times for maximum reach
- Visual calendar grid with color-coded engagement levels
- **Data**: Extract hour/day from `PixelfedPost.posted_at`, aggregate engagement
- **Impact**: High - directly actionable insights for scheduling
- **Difficulty**: Medium

#### 4. **Engagement Velocity Chart** 📈
- Show how fast posts gain engagement in first 24/48/72 hours
- Compare "fast starters" vs "slow burners"
- Line chart with multiple post overlays
- Identify which content types gain traction quickly
- **Data**: Compare `PixelfedPost.posted_at` with `PixelfedLike.first_seen_at`
- **Impact**: Medium-High - unique insight into content performance
- **Difficulty**: Medium

#### 5. **Media Type Performance Comparison** 🎨
- Bar chart comparing engagement by media type (image/video/carousel)
- Average engagement per type
- Success rate and distribution metrics
- **Data**: `PixelfedPost.media_type`, aggregate engagement
- **Impact**: Medium - useful for content strategy
- **Difficulty**: Easy

### 📊 Medium Priority (Implement Second)

#### 6. **Engagement Timeline Enhancement**
- Improve existing timeline with stacked area/line chart
- Daily, weekly, or monthly aggregations toggle
- Cumulative vs. new engagement views
- Export data as CSV
- **Data**: `PixelfedLike.liked_at`, `PixelfedComment.commented_at`, `PixelfedShare.shared_at`
- **Impact**: Medium - deeper analysis of engagement patterns
- **Difficulty**: Medium

#### 7. **Top Performers Dashboard**
- Grid of top posts by engagement metric
- Visual cards with thumbnail, metrics, and engagement rate
- Filter by time period (7/30/90 days)
- Quick actions (view details, re-share, analyze)
- **Data**: `PixelfedEngagementSummary.total_engagement`
- **Impact**: Medium - showcases best content
- **Difficulty**: Easy

#### 8. **Consistency Score Meter** 🎯
- Calculate posting frequency regularity
- Visual gauge showing consistency (0-100 score)
- Posting streak counter
- Weekly/monthly posting patterns
- Recommendations to maintain consistency
- **Data**: Daily post counts from `PixelfedPost.posted_at`
- **Impact**: Medium - motivational, habit-building
- **Difficulty**: Medium

#### 9. **Engagement Quality Score**
- Weighted score: comments > shares > likes (comments show deeper engagement)
- Compare quality vs. quantity across posts
- Identify high-quality engagement content
- **Data**: Custom calculation from engagement counts
- **Impact**: Medium - quality over vanity metrics
- **Difficulty**: Easy

#### 10. ~~**Engagement Type Distribution**~~ ✅ **COMPLETED**
- ✅ Donut chart showing likes vs. comments vs. shares ratio
- ✅ Interactive visualization with click-to-filter
- ✅ Legend with percentage and count breakdowns
- ✅ Color-coded metrics (amber for likes, violet for comments, pink for shares)
- ✅ Summary stats cards showing totals and percentages
- ✅ Unified with Top Engagers view (single page with both visualizations)
- ✅ Implemented for **Pixelfed** and **Mastodon**
- **Data**: Aggregate counts from engagement summaries
- **Implementation**: Shared template `analytics/shared/engagement_distribution.html`
- **Features**: D3.js donut chart, sortable engagers table with HTMX, weighted engagement scoring

### 🔬 Low Priority (Advanced Features)

#### 11. **Engagement Decay Curve**
- Line chart showing engagement over time after posting
- Compare multiple posts to find patterns
- Identify content with "long tail" engagement
- **Data**: Days since `posted_at` vs. cumulative engagement
- **Impact**: Low-Medium - academic interest, limited actionability
- **Difficulty**: Medium

#### 12. **Caption Length vs. Engagement Analysis**
- Scatter plot showing caption length vs. total engagement
- Find optimal caption length sweet spot
- Correlation coefficient display
- **Data**: `len(PixelfedPost.caption_text)` vs. `total_engagement`
- **Impact**: Low-Medium - interesting but not always actionable
- **Difficulty**: Easy

#### 13. **Community Conversation Map** 💬
- Visual thread view showing comment chains
- Identify posts that spark most discussion
- Network graph of reply relationships
- **Data**: `PixelfedComment.in_reply_to_id` (threading)
- **Impact**: Low - interesting but niche use case
- **Difficulty**: Hard

#### 14. **Edited Posts Performance Tracker**
- Compare engagement before/after edit timestamp
- Track if edits improve performance
- Timeline showing edit impact
- **Data**: `PixelfedPost.edited_at`, compare engagement timing
- **Impact**: Low - limited use case (few posts get edited)
- **Difficulty**: Medium

#### 15. **Viral Coefficient Tracker** 🔥
- Shares-to-likes ratio (virality indicator)
- Posts with high share rates spread further
- Trend over time
- **Data**: `PixelfedEngagementSummary.total_shares / total_likes`
- **Impact**: Low-Medium - interesting metric but limited actionability
- **Difficulty**: Easy

#### 16. **Engagement Rate Trends**
- Line chart showing average engagement per post over time
- Identify growth or decline patterns
- Monthly/quarterly comparisons
- **Data**: Average `total_engagement` per week/month
- **Impact**: Medium - tracks overall account health
- **Difficulty**: Easy

#### 17. **Best Performing Content Themes** 🏷️
- Tag cloud or bar chart of hashtags/keywords in high-engagement posts
- Extract patterns from successful content
- Keyword frequency analysis
- **Data**: Parse `PixelfedPost.caption` for hashtags
- **Impact**: Low-Medium - requires NLP/text processing
- **Difficulty**: Hard

#### 18. **Growth Momentum Dashboard**
- Week-over-week growth in engagement
- Engagement growth rate percentage
- Velocity indicators (accelerating/decelerating)
- **Data**: Time-series comparison of engagement totals
- **Impact**: Medium - tracks progress over time
- **Difficulty**: Medium

## Technical Notes

- All analytics features are in the `analytics_pixelfed/` app
- Consider caching for expensive aggregation queries
- Test with accounts that have large numbers of posts (>1000)

### Pixelfed/Mastodon API Limitations

**Timestamp Availability:**
- ✅ **Post timestamps**: Available via `created_at` and `edited_at` fields in Status object
- ✅ **Comment timestamps**: Available via `created_at` field in Status object (comments are statuses)
- ❌ **Like timestamps**: NOT available - `/api/v1/statuses/:id/favourited_by` only returns Account objects
- ❌ **Share timestamps**: NOT available - `/api/v1/statuses/:id/reblogged_by` only returns Account objects

**Workaround Implemented:**
- Added `first_seen_at` field to PixelfedLike and PixelfedShare models
- Uses `timezone.now()` when first discovering a like/share
- Provides estimated timeline of engagement (better than nothing)
- More frequent fetching = more accurate timeline estimates

**Available Metrics:**
- ✅ Aggregate counts: `replies_count`, `reblogs_count`, `favourites_count` from Status object
- ✅ Post metadata: visibility, language, sensitive flags, spoiler text
- ✅ Threading information: reply chains and parent post references
- ✅ Edit history: `edited_at` timestamp when posts are modified
- ❌ Impressions/views: Not supported by Mastodon API
- ❌ Engagement rate: Cannot calculate without impression data
