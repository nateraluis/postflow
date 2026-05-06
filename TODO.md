# PostFlow TODO

---

## Publishing Workflow Improvements (2026 Instagram Research)

Design principle: **minimize user effort** — automate everything possible, surface smart
defaults, and only ask the user when their input genuinely matters. Every feature must be
cross-platform compatible (Instagram, Pixelfed, Mastodon) or degrade gracefully.

### Phase 1: Critical & High-Impact

#### 1. ~~Platform-Aware Hashtag Limit Enforcement~~ COMPLETED
Instagram enforces a **hard limit of 5 hashtags per post** (Dec 2025). Posts with more
are blocked or stripped. Mastodon/Pixelfed have no such limit.

- [x] Add per-platform hashtag limit validation in the post composer
- [x] When Instagram is selected: warn if combined TagGroups exceed 5 hashtags
- [x] Show a live hashtag counter that reflects the limit per selected platform
- [x] **Smart auto-selection**: if a user has 15 hashtags across groups, auto-select the best 5
      for Instagram while sending all 15 to Mastodon/Pixelfed — user picks groups, PostFlow
      handles the math
- [x] Add hashtag rotation: cycle through different subsets of hashtags per Instagram post to
      maximize coverage and avoid repetition penalties
- [x] Allow users to pin "always include" hashtags within a group
- [x] Track which hashtags were used on recent posts to ensure even distribution
- [x] Update `cron.py` hashtag assembly to respect per-platform limits before publishing

#### 2. ~~Alt Text Support (All Platforms)~~ COMPLETED
Alt text improves accessibility and discoverability. Instagram API supports `alt_text` on
images (added March 2025). Mastodon/Pixelfed support `description` on media uploads.

- [x] Add `alt_text` field to the `PostImage` model
- [x] Add alt text input per image in the post composer (collapsible, non-intrusive)
- [x] Pass `alt_text` param in Instagram API container creation
- [x] Pass `description` param in Mastodon/Pixelfed `media_post()` calls
- [x] Show alt text in post preview and history views

#### 3. ~~Location Tagging~~ COMPLETED
Posts with location tags see up to 79% more engagement on Instagram. Mastodon/Pixelfed
have no equivalent, so skip silently on those platforms.

- [x] Create a `Location` model: `name`, `facebook_page_id`, `latitude`, `longitude`, `user` (FK)
- [x] Add optional `location` FK to `ScheduledPost`
- [x] Build a location search endpoint querying Facebook Places Search API
- [x] Add a location picker in the composer (search-as-you-type via HTMX)
- [x] **Save frequently used locations** per user for one-tap re-selection
- [x] Pass `location_id` in Instagram API container creation
- [x] No-op for Mastodon/Pixelfed (skip silently)

#### 4. ~~User/Account Tagging~~ COMPLETED
Tagging boosts reach by surfacing posts to tagged users' audiences.

- [x] Add a `UserTag` model: `username`, `platform`, `x`, `y`, linked to `PostImage`
      (positional) or `ScheduledPost` (mention-based)
- [x] Add "accounts to tag" field per image in the composer (search/autocomplete)
- [x] **Auto-tagging defaults**: let users save accounts they always tag (brand, photographer,
      etc.) — pre-fill on every new post automatically
- [x] For Instagram: pass `user_tags` array with `{username, x, y}` on image containers
- [x] For Mastodon/Pixelfed: auto-convert tags to `@username@instance` mentions appended to
      caption (same pattern as existing hashtag auto-insertion)

#### 5. ~~Collaborator Tagging (Instagram)~~ COMPLETED
The `collaborators` API param is a differentiator — most schedulers don't offer it.
Enables co-authorship, surfacing the post to collaborators' audiences.

- [x] Add `collaborators` field on `ScheduledPost` (username list, max 3)
- [x] Add collaborator input in composer (only visible when Instagram is selected)
- [x] Pass `collaborators` param in Instagram API container creation
- [x] Note in UI: collaborator must accept invite for it to take effect
- [x] No-op for Mastodon/Pixelfed

#### 6. ~~Banned Hashtag Checker~~ COMPLETED
Banned hashtags trigger Instagram shadowban. Users often don't know which are banned.

- [x] Maintain a banned hashtag list (JSON config, periodically updated)
- [x] **Pre-publish validation**: before posting to Instagram, check all hashtags — block and
      notify if any are banned
- [x] **Real-time validation**: flag banned hashtags inline as user types or selects TagGroups
- [x] Check existing TagGroups and surface warnings in the hashtag management view
- [x] Mastodon/Pixelfed: skip validation (no banned hashtag concept)

---

### Phase 2: Smart Automation & Optimization

#### 7. ~~Caption SEO Optimizer~~ COMPLETED
Instagram captions are indexed by both Instagram Search and Google (since mid-2025).
Keywords in captions now matter more than hashtags for discoverability.

- [x] **First-line preview**: show first 125 chars as users will see them (before "...more"
      truncation) — help users craft a strong hook
- [x] **Caption length indicator**: live character count with color zones per platform
      (Instagram: 2200 chars, Mastodon: 500 chars default)
- [x] **Per-platform caption preview**: show final caption with hashtags + mentions as it will
      appear on each selected platform
- [x] **Truncation warning**: alert if combined caption + hashtags exceeds any platform's limit

#### 8. ~~Optimal Posting Time Suggestions~~ COMPLETED
PostFlow already tracks analytics — use that data to suggest when to post.

- [x] Aggregate historical engagement by day-of-week and hour per user's accounts
- [x] When user picks a date, suggest the best hour based on their own data
- [x] Fallback to 2026 benchmarks if insufficient data: Wed/Thu, 9 AM / 12 PM / 6 PM
- [x] Show as a subtle hint in the time picker, not a blocker
- [x] Platform-agnostic — uses PostFlow's own analytics data

#### 9. ~~Hashtag Performance Analytics~~ COMPLETED
Help users understand which hashtags drive results.

- [x] Track which hashtag groups were used on each post (already stored via M2M)
- [x] Correlate hashtag groups with engagement metrics (reach, likes, comments, shares)
- [x] Dashboard: hashtag group performance over time
- [x] Highlight top-performing and underperforming groups
- [x] Suggest retiring low-performing hashtags

---

### Phase 3: Carousel & UX Enhancements

#### 10. Carousel Builder Enhancement
Carousels have the highest engagement (10.15%). PostFlow supports multi-image but the
UX could be better.

- [x] Drag-and-drop slide reordering
- [x] Per-slide alt text input
- [ ] Per-slide user tagging
- [ ] Swipeable preview
- [x] Auto-suggest carousel when user uploads 3+ images

---

### Phase 4: Quality of Life

#### 14. ~~Post Preview~~ COMPLETED
- [x] Instagram preview: image + first 125 chars + "...more" + hashtags + location + tags
- [x] Mastodon/Pixelfed preview: image + full caption + hashtags + mentions
- [x] Preview per platform in tabs
- [x] Character count warnings per platform

#### 15. ~~Draft & Template System~~ COMPLETED
- [x] Save posts as drafts (`status="draft"`) for later editing and scheduling
- [x] Caption templates: reusable caption structures with placeholders
- [x] Default settings per user: default hashtag groups, accounts, location

#### 16. ~~Post Editing & Deletion~~ COMPLETED
- [x] Edit caption, hashtags, date/time, accounts on pending posts
- [x] Delete scheduled posts before publishing
- [x] Warn if editing a post within 5 minutes of publishing

#### 17. ~~Comment Management Dashboard~~ COMPLETED
Fast comment replies boost algorithmic distribution (first-hour replies matter most).

- [x] Fetch comments via Mastodon/Pixelfed API
- [x] Unified inbox: comments across all platforms in one view
- [x] Quick-reply from PostFlow
- [x] Highlight comments on recent posts

---

### Technical Debt

#### T.1 ~~Per-Platform Publishing Pipeline Refactor~~ COMPLETED
New features (alt text, location, tags, collaborators) will multiply code duplication
across platform utils if not addressed.

- [x] Create a `PostPayload` dataclass assembling full post context once: caption,
      hashtags (platform-filtered), alt_text, location, user_tags, collaborators
- [x] Each platform util receives a `PostPayload` and maps to platform-specific API params
- [x] Centralize validation (hashtag limits, caption length, banned hashtags) in the payload builder
- [x] Prevents duplicating cross-platform logic as features grow

#### T.2 ~~Hashtag Format Normalization~~ COMPLETED
No validation on hashtag format — users can store tags with or without `#`.

- [x] Normalize all hashtags on save: strip `#`, store raw word, add `#` on display/publish
- [x] Migration to normalize existing tags in the database
- [x] Makes banned hashtag checking and analytics more reliable

#### T.3 ~~Platform Feature Matrix~~ COMPLETED
As features diverge across platforms, maintain a clear matrix.

- [x] Create `docs/platform_features.md` mapping each feature to platform support
- [x] Use this in the UI: show/hide fields based on selected platforms
- [x] Update as platforms add/remove API capabilities

---

### API Limitations (Cannot Be Worked Around)
Document these clearly for users in the UI:

| Limitation | Platform |
|---|---|
| Collaborators must accept invite manually | Instagram |
| No location tagging equivalent | Mastodon/Pixelfed |
| No collaborator concept (use mentions instead) | Mastodon/Pixelfed |

### Key 2026 Algorithm Reference
- Instagram #1 signal: **sends/shares per reach** (DM shares)
- Carousels: 10.15% avg engagement (highest), second distribution pass
- Captions indexed by Google since mid-2025 — caption SEO > hashtag stuffing
- Best days: Wednesday & Thursday
- Best times: 9 AM, 12 PM, 6 PM (user timezone)
- Reply to comments within first hour for max algorithmic benefit
- Hard limit: 5 hashtags per Instagram post (Dec 2025)

---

## Analytics Improvements

### High Priority

#### 1. ~~**GitHub-Style Posting Calendar**~~ COMPLETED
- Heatmap showing posts per day over time
- Color intensity based on frequency or total engagement
- Hover tooltips with post count and engagement metrics
- Date range selector (30/90/365 days)
- Streak counter for consecutive posting days
- **Data**: `PixelfedPost.posted_at`

#### 2. ~~**Top Engagers / Super Fans Dashboard**~~ COMPLETED
- Leaderboard of users who engage most with your content
- Implemented for **Pixelfed** and **Mastodon**
- **Not implemented for Instagram** — API doesn't provide commenter usernames

#### 3. ~~**Best Time to Post Analysis**~~ COMPLETED
- Heatmap showing average engagement by day of week + hour
- Identify optimal posting times for maximum reach
- **Data**: Extract hour/day from `PixelfedPost.posted_at`, aggregate engagement

#### 4. ~~**Engagement Velocity Chart**~~ COMPLETED
- Show how fast posts gain engagement in first 24/48/72 hours
- Compare "fast starters" vs "slow burners"
- **Data**: Compare `PixelfedPost.posted_at` with `PixelfedLike.first_seen_at`

#### 5. ~~**Media Type Performance Comparison**~~ COMPLETED
- Bar chart comparing engagement by media type (image/video/carousel)
- Average engagement per type
- **Data**: `PixelfedPost.media_type`, aggregate engagement

#### 6. **Repost/Share Tracking** (New — Instagram)
- Track repost counts (new Instagram API metric, media + account level)
- Track sends/shares per post (Instagram's #1 algorithm signal)
- Build a "post score" combining reach + engagement rate

### Medium Priority

#### 8. ~~**Engagement Timeline Enhancement**~~ COMPLETED
- Stacked bars with daily/weekly/monthly aggregation toggle
- CSV export
- Day range selector

#### 9. ~~**Top Performers Dashboard**~~ COMPLETED
- Grid of top posts by engagement metric
- Visual cards with thumbnail, metrics, engagement rate
- Filter by time period

#### 10. ~~**Consistency Score Meter**~~ COMPLETED
- Posting frequency regularity score (0-100)
- Posting streak counter
- Recommendations to maintain consistency

#### 11. ~~**Engagement Quality Score**~~ COMPLETED
- Weighted: comments > shares > likes
- Quality vs quantity comparison across posts

#### 12. ~~**Engagement Type Distribution**~~ COMPLETED
- Donut chart of likes vs comments vs shares
- Implemented for **Pixelfed** and **Mastodon**

### Low Priority

#### 13. ~~**Engagement Decay Curve**~~ COMPLETED
- Engagement at day 1/3/7/30 with long-tail detection

#### 14. ~~**Caption Length vs Engagement Analysis**~~ COMPLETED
- Length buckets with average engagement and sweet spot detection

#### 15. ~~**Community Conversation Map**~~ COMPLETED
- Expandable thread cards with comment chains and participant counts

#### 16. ~~**Viral Coefficient Tracker**~~ COMPLETED
- Shares-to-likes ratio with viral badges (ratio > 0.1)

#### 17. ~~**Best Performing Content Themes**~~ COMPLETED
- Hashtag cloud with engagement-colored sizing and stats table

#### 18. ~~**Growth Momentum Dashboard**~~ COMPLETED
- Week-over-week engagement growth
- Velocity indicators (accelerating/decelerating)

#### 19. ~~**Weekly Digest Email**~~ COMPLETED
- Top performing posts, consistency score, hashtag performance
- Actionable suggestions based on data
- Optimal time recommendations
- Scheduled every Monday at 09:00 UTC via APScheduler
- Browser preview at /digest/

---

## Marketing & Landing Page

### Take Analytics Screenshots for Landing Page
**Priority**: High
**Location**: `postflow/static/postflow/screenshots/`

Take screenshots of analytics dashboards:
- `top-engagers.png` - Top Engagers/Super Fans dashboard
- `engagement-timeline.png` - Engagement timeline chart/graph
- `posting-calendar.png` - Posting calendar heatmap (once implemented)
- `platform-comparison.png` - Cross-platform analytics comparison view

**Note**: Landing page works without these (images hide with `onerror`), but having them
improves conversion.

---

## Technical Notes

- All analytics features are in platform-specific apps (`analytics_pixelfed/`, etc.)
- Consider caching for expensive aggregation queries
- Test with accounts that have large numbers of posts (>1000)

### Pixelfed/Mastodon API Limitations

**Timestamp Availability:**
- Post timestamps: available via `created_at` and `edited_at`
- Comment timestamps: available via `created_at`
- Like timestamps: NOT available (only Account objects returned)
- Share timestamps: NOT available (only Account objects returned)

**Workaround Implemented:**
- `first_seen_at` field on PixelfedLike and PixelfedShare models
- Uses `timezone.now()` when first discovering engagement
- More frequent fetching = more accurate timeline

**Available Metrics:**
- Aggregate counts: `replies_count`, `reblogs_count`, `favourites_count`
- Post metadata: visibility, language, sensitive flags, spoiler text
- Threading: reply chains and parent post references
- Edit history: `edited_at` timestamp
- NOT available: impressions/views, engagement rate (no impression data)
