# PostFlow TODO

## Analytics Improvements

### Data Fetching
- [ ] **Fetch all available posts from Pixelfed**
  - Currently limited to 50 posts
  - Implement pagination to fetch all posts from connected accounts
  - Related file: `analytics_pixelfed/pixelfed_client.py`

- [x] **Review and expand Pixelfed API data collection** ✅ COMPLETED (2026-01-29)
  - ✅ Investigated Pixelfed/Mastodon API capabilities
  - ✅ **API Limitation Confirmed**: Individual like/share timestamps are NOT available
    - The `/api/v1/statuses/:id/favourited_by` endpoint only returns Account objects
    - The `/api/v1/statuses/:id/reblogged_by` endpoint only returns Account objects
    - No timestamp metadata is provided for individual likes/shares
    - Solution: Added `first_seen_at` field to track when we discovered each like/share
  - ✅ Added new fields captured from API:
    - **Post metadata**: visibility, language, sensitive, spoiler_text
    - **Threading**: in_reply_to_id, in_reply_to_account_id
    - **Edit tracking**: edited_at timestamp
    - **Aggregate metrics**: api_replies_count, api_reblogs_count, api_favourites_count
  - ✅ Comment timestamps ARE available and accurate (from Status created_at)
  - ❌ Impression/view counts: NOT supported by Mastodon/Pixelfed API
  - ✅ Updated models, fetcher, and created migration (0002_expand_analytics_fields)
  - Related files: `analytics_pixelfed/models.py`, `analytics_pixelfed/fetcher.py`, `analytics_pixelfed/migrations/0002_expand_analytics_fields.py`

### Data Sanitization
- [ ] **Clean HTML tags from post captions**
  - Captions currently include raw HTML tags
  - Implement HTML sanitization/stripping for display
  - Consider preserving plain text formatting where appropriate
  - Related files: `analytics_pixelfed/models.py`, `analytics_pixelfed/templates/`

### UI/UX Enhancements

#### Post Detail Page
- [ ] **Redesign post detail layout**
  - Show post image smaller (not full width)
  - Display caption below the image
  - Add second column showing analytics metrics
  - Improve mobile responsiveness
  - Related file: `analytics_pixelfed/templates/analytics_pixelfed/post_detail.html`

#### Analytics Dashboard
- [ ] **Add "Most Liked Post" section**
  - Highlight the post with highest engagement
  - Show thumbnail, like count, and quick stats

- [ ] **Implement engagement-based sorting**
  - Allow users to sort posts by:
    - Total likes
    - Total comments
    - Total shares
    - Combined engagement score
  - Add sort dropdown to dashboard

- [ ] **Add posting consistency metrics**
  - Create GitHub-style commit calendar visualization
  - Show posting frequency over time (daily/weekly/monthly)
  - Display average engagement per time period
  - Highlight most active posting days/times
  - Calculate consistency score (regularity of posting)
  - Related: Create new view/template for consistency dashboard

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
